#!/usr/bin/env python3
"""List or restore retained versions of one encrypted OpenTofu state object.

Usage:
  make restore-state PROVIDER=<p> ENV=<env> [STATE_VERSION=<id>]  (TF_BACKEND_ROOT comes from fleet.mk)
  PROVIDER=<p> ENV=<env> TF_BACKEND_ROOT=<abs dir> scripts/restore-tf-state.py            # list versions
  PROVIDER=<p> ENV=<env> TF_BACKEND_ROOT=<abs dir> scripts/restore-tf-state.py <version>  # restore one
  (STATE_VERSION in the environment selects the version when no argument is given)

The bucket, endpoint and object keys come from ${TF_BACKEND_ROOT}/${PROVIDER}.s3.tfbackend.
The operator state identity (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) and
TF_VAR_state_passphrase (restore only) come from the environment only; nothing
secret is printed.

Restore holds the workspace's S3 lock from the current-state read through the
verified write. ALLOW_LINEAGE_CHANGE=1 permits replacement of another lineage.
Every earlier version stays in the bucket.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import posixpath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from tofu_backend import s3_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("upcloud", "hetzner", "vultr", "scaleway")
ENCRYPTED_ROOT = """terraform {
  encryption {
    key_provider "pbkdf2" "state" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "state" {
      keys = key_provider.pbkdf2.state
    }
    state {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

variable "state_passphrase" {
  type      = string
  sensitive = true
  ephemeral = true
}
"""


def fail(message: str, code: int = 1) -> NoReturn:
    print(f"restore-state: {message}", file=sys.stderr)
    sys.exit(code)


def admit(restoring: bool) -> tuple[str, str, bytes, dict[str, str]]:
    provider, env = os.environ.get("PROVIDER", "upcloud"), os.environ.get("ENV", "prod")
    if provider not in PROVIDERS:
        fail(f"unsupported PROVIDER: {provider}", 2)
    if env == "default":
        fail("ENV=default is reserved for the legacy prod workspace; use ENV=prod", 2)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", env):
        fail("ENV must contain only letters, numbers, and hyphens", 2)
    root = os.environ.get("TF_BACKEND_ROOT", "")
    if not root.startswith("/"):
        fail(f"TF_BACKEND_ROOT must be the absolute directory of {provider}.s3.tfbackend", 2)
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "TF_VAR_state_passphrase")[:3 if restoring else 2]:
        if not os.environ.get(name):
            fail(f"missing {name} in the environment", 2)
    raw = read_backend(Path(root) / f"{provider}.s3.tfbackend")
    settings = backend_settings(raw, provider)
    prefix = settings["workspace_key_prefix"]
    settings["object"] = settings["key"] if env == "prod" else posixpath.join(prefix, env, settings["key"])
    return provider, env, raw, settings


def read_backend(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        fail(f"missing backend file: {path}", 2)


def backend_settings(raw: bytes, provider: str | None) -> dict:
    try:
        settings = s3_settings(raw, provider)
    except ValueError as error:
        fail(str(error), 2)
    try:
        endpoint = urllib.parse.urlsplit(settings["endpoints"]["s3"])
        if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username is not None
                or endpoint.query or endpoint.fragment
                or any(not isinstance(settings.get(name), str) or not settings[name] for name in ("bucket", "key", "region"))
                or not isinstance(settings.get("workspace_key_prefix", ""), str)
                or "/" in settings["bucket"]
                or any(part in ("", ".", "..") for path in (settings["key"], settings.get("workspace_key_prefix"))
                       if path for part in path.split("/"))):
            raise ValueError
    except (AttributeError, KeyError, TypeError, ValueError):
        fail("backend file needs literal bucket, key, region and an https endpoints.s3", 2)
    settings["endpoint"] = endpoint.geturl().rstrip("/")
    return settings


def s3_get(settings: dict[str, str], query: str) -> bytes:
    key = settings["object"] if query.startswith("versionId=") else ""
    return s3_request(settings, key, query)


def s3_request(settings: dict, key: str, query: str, *options: str) -> bytes:
    """Sign a request without putting the key pair on the command line."""
    # The pair is written into a quoted curl config value.
    if re.search(r'["\\\s]', os.environ["AWS_ACCESS_KEY_ID"] + os.environ["AWS_SECRET_ACCESS_KEY"]):
        fail("the state key pair contains quotes, backslashes or whitespace", 2)
    path = urllib.parse.quote(settings["bucket"]) + ("/" + urllib.parse.quote(key) if key else "")
    url = f"{settings['endpoint']}/{path}" + ("?" + query if query else "")
    config = f'user = "{os.environ["AWS_ACCESS_KEY_ID"]}:{os.environ["AWS_SECRET_ACCESS_KEY"]}"\n'
    # -q first: an operator ~/.curlrc must not weaken TLS or trace the signed request.
    # A stalled request must not hold the restore lock indefinitely.
    result = subprocess.run(["curl", "-q", "-sS", "--fail-with-body", "--connect-timeout", "30", "--max-time", "300",
                             "-K", "-", "--aws-sigv4",
                             f"aws:amz:{settings['region']}:s3", *options, url], input=config.encode(), capture_output=True, check=False)
    if result.returncode:
        reason = f"curl exit {result.returncode}"
        for code in ("PreconditionFailed", "ConditionalRequestConflict", "AccessDenied", "NoSuchKey", "NoSuchVersion", "NoSuchBucket", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
            if f"<Code>{code}</Code>".encode() in result.stdout:
                reason = code
                break
        fail(f"object storage request failed ({reason})")
    return result.stdout


def versions(settings: dict[str, str]) -> list[dict[str, str]]:
    found, markers, seen = [], "", set()
    while True:
        # The listing comes from the configured bucket over TLS; expat refuses entity expansion.
        query = "versions=&prefix=" + urllib.parse.quote(settings["object"], safe="") + markers
        try:
            root = ET.fromstring(s3_get(settings, query))
            page = {child.tag.rsplit("}", 1)[-1]: child for child in root}
            for element in root:
                tag = element.tag.rsplit("}", 1)[-1]
                fields = {child.tag.rsplit("}", 1)[-1]: child.text or "" for child in element}
                if tag in ("Version", "DeleteMarker") and fields.get("Key") == settings["object"]:
                    found.append({"version": fields["VersionId"], "modified": fields["LastModified"],
                                  "size": fields.get("Size", "-"), "latest": fields["IsLatest"],
                                  "kind": "delete-marker" if tag == "DeleteMarker" else "state"})
        except (ET.ParseError, KeyError):
            fail("object storage returned an unexpected version listing")
        if getattr(page.get("IsTruncated"), "text", "false") != "true":
            return found
        markers = "".join(f"&{name}={urllib.parse.quote(page[tag].text or '', safe='')}"
                          for name, tag in (("key-marker", "NextKeyMarker"), ("version-id-marker", "NextVersionIdMarker"))
                          if tag in page)
        if not markers or markers in seen:
            fail("object storage returned a truncated listing without a new marker")
        seen.add(markers)


def valid_state(state: object) -> bool:
    return (isinstance(state, dict) and state.get("version") == 4 and type(state.get("serial")) is int
            and state["serial"] >= 0 and isinstance(state.get("lineage"), str) and bool(state["lineage"])
            and isinstance(state.get("resources"), list))


def decrypt(ciphertext: bytes) -> dict:
    """Let OpenTofu decrypt one retained version inside a private local root."""
    try:
        stored = json.loads(ciphertext)
    except ValueError:
        fail("the selected version is not a state document")
    if not isinstance(stored, dict) or "encrypted_data" not in stored:
        fail("the selected version is not encrypted state; refusing to restore it")
    work = Path(tempfile.mkdtemp(prefix="state-restore."))
    try:
        (work / "main.tf").write_text(ENCRYPTED_ROOT)
        (work / "terraform.tfstate").write_bytes(ciphertext)
        env = {**os.environ, "TF_DATA_DIR": str(work / ".data"), "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"}
        env.pop("TF_WORKSPACE", None)
        for args in (["init", "-input=false", "-no-color"], ["state", "pull"]):
            result = subprocess.run(["tofu", f"-chdir={work}", *args], env=env, capture_output=True, check=False)
            if result.returncode:
                fail(f"cannot decrypt the selected version (tofu {args[0]} exit {result.returncode})")
        try:
            state = json.loads(result.stdout)
        except ValueError:
            fail("the selected version did not decrypt to a state document")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not valid_state(state):
        fail("the selected version has an invalid state structure")
    return state


def terraform_env(provider: str, env: str, backend_root: str, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([str(REPO_ROOT / "scripts/terraform-env.sh"), *args], input=data, capture_output=True, check=False,
                          env={**os.environ, "PROVIDER": provider, "ENV": env, "TF_BACKEND_ROOT": backend_root})


def read_state(result: subprocess.CompletedProcess[bytes]) -> dict | None:
    if not result.stdout.strip():
        return None
    try:
        state = json.loads(result.stdout)
    except ValueError:
        fail("the current state is not a state document")
    if not valid_state(state):
        fail("the current state has an invalid structure")
    return state


def inspect_probe(backend: Path, key: str, workspace: str) -> None:
    if not re.fullmatch(r"state/_probe/[A-Za-z0-9]+/terraform\.tfstate", key):
        fail("expected a disposable probe key", 2)
    settings = backend_settings(read_backend(backend), None)
    run_id = key.split("/")[2]
    if workspace not in ("default", f"probe-{run_id}"):
        fail("workspace is not owned by this disposable probe", 2)
    prefix = settings["workspace_key_prefix"]
    settings["object"] = key if workspace == "default" else posixpath.join(prefix, workspace, key)
    retained = {entry["version"] for entry in versions(settings)
                if entry["kind"] == "state" and entry["version"] not in ("", "null")}
    if len(retained) < 2:
        fail("the probe did not retain two distinct state versions")
    for version in retained:
        raw = s3_get(settings, "versionId=" + urllib.parse.quote(version, safe=""))
        try:
            envelope = json.loads(raw)
        except ValueError:
            fail("a retained probe version has no encryption envelope")
        if (not isinstance(envelope, dict) or not envelope.get("encrypted_data")
                or set(envelope) - {"encrypted_data", "encryption_version", "lineage", "meta", "serial"}):
            fail("a retained probe version contains unencrypted state or unknown fields")
        decrypt(raw)
    print(f"verified {len(retained)} encrypted probe versions")


def main() -> None:
    os.umask(0o077)
    # SIGTERM would otherwise end the process without the finally that releases the restore lock.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if len(sys.argv) == 5 and sys.argv[1] == "--inspect-probe":
        inspect_probe(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
        return
    if len(sys.argv) > 2:
        fail("usage: restore-tf-state.py [version-id]", 2)
    version = sys.argv[1] if len(sys.argv) == 2 else os.environ.get("STATE_VERSION", "")
    if version and not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", version):
        fail("usage: restore-tf-state.py [version-id]", 2)
    provider, env, raw, settings = admit(bool(version))
    if not version:
        for entry in versions(settings):
            print(f"{entry['version']}  {entry['modified']}  size={entry['size']}  latest={entry['latest']}  {entry['kind']}")
        return
    with tempfile.TemporaryDirectory(prefix="state-backend.") as directory:
        (Path(directory) / f"{provider}.s3.tfbackend").write_bytes(raw)
        restore(provider, env, settings, version, directory)


@contextmanager
def state_lock(settings, run):
    lock_id = str(uuid.uuid4())
    lock_path = settings["bucket"] + "/" + settings["object"]
    record = json.dumps({"ID": lock_id, "Operation": "restore-state", "Path": lock_path,
                         "Created": datetime.now(timezone.utc).isoformat()})
    # Object Lock buckets require a checksum for this conditional PUT.
    checksum = base64.b64encode(hashlib.sha256(record.encode()).digest()).decode()
    response = s3_request(
        settings, settings["object"] + ".tflock", "", "--request", "PUT", "--write-out", "%{http_code}",
        "--header", "If-None-Match: *", "--header", "Content-Type: application/json",
        "--header", f"x-amz-checksum-sha256: {checksum}", "--data-binary", record,
    )
    if response != b"200":
        fail("object storage did not confirm the restore lock; inspect the backend lock record")
    try:
        yield
    finally:
        # The backend validates the UUID before deleting the lock. A lost PUT
        # response or an interrupted restore can leave a recoverable lock.
        unlocked = run("force-unlock", "-force", lock_id)
        if unlocked.returncode:
            fail(f"cannot release restore lock {lock_id}; inspect the backend lock record")


def restore(provider, env, settings, version, directory):
    def run(*args, data=None):
        return terraform_env(provider, env, directory, *args, data=data)

    restored = decrypt(s3_get(settings, "versionId=" + version))
    # Bind the workspace to the backend file the version came from before reading or writing it.
    initialized = run("init", "-input=false", "-no-color", "-reconfigure")
    if initialized.returncode:
        fail(f"cannot initialize {provider}/{env} against {provider}.s3.tfbackend (exit {initialized.returncode})")
    with state_lock(settings, run):
        serial = push_and_verify(run, restored, provider, env)
    print(f"restored version {version} of {provider}/{env} as serial {serial}; "
          "run a plan and review it against the selected recovery point")


def push_and_verify(run, restored, provider, env):
    pulled = run("state", "pull")
    if pulled.returncode:
        fail(f"cannot read the current state of {provider}/{env} (exit {pulled.returncode})")
    current = read_state(pulled)
    force = []
    if current is not None:
        if current["lineage"] != restored["lineage"]:
            if os.environ.get("ALLOW_LINEAGE_CHANGE") != "1":
                fail("the selected version has another lineage; set ALLOW_LINEAGE_CHANGE=1 to replace it deliberately")
            force = ["-force"]
        restored["serial"] = current["serial"] + 1
    # The outer native S3 lock covers the pull, push and readback.
    pushed = run("state", "push", "-lock=false", "-no-color", *force, "-", data=json.dumps(restored).encode())
    if pushed.returncode:
        fail(f"state push refused (exit {pushed.returncode})")
    # OpenTofu may raise the serial again when it persists, so report what the backend holds.
    after = run("state", "pull")
    stored = read_state(after) if after.returncode == 0 else None
    writer_metadata = {"serial", "terraform_version"}
    if (stored is None or stored["serial"] < restored["serial"]
            or {key: value for key, value in stored.items() if key not in writer_metadata}
            != {key: value for key, value in restored.items() if key not in writer_metadata}):
        fail("the pushed state does not read back as the restored version; inspect the bucket versions")
    return stored["serial"]


if __name__ == "__main__":
    main()
