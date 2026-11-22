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

Restore re-initializes the workspace against the same backend file, decrypts the selected version in a private local root, refuses a lineage
other than the current one unless ALLOW_LINEAGE_CHANGE=1, sets the serial to the
current serial plus one and pushes it through scripts/terraform-env.sh, so the
backend lock and OpenTofu's serial and lineage checks apply. With
ALLOW_LINEAGE_CHANGE=1 the push is forced and skips those checks: stop every
other writer first. Every earlier version stays in the bucket.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NoReturn

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
}
"""


def fail(message: str, code: int = 1) -> NoReturn:
    print(f"restore-state: {message}", file=sys.stderr)
    sys.exit(code)


def admit(restoring: bool) -> tuple[str, str, dict[str, str]]:
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
    # The pair is written into a quoted curl config value.
    if re.search(r'["\\\s]', os.environ["AWS_ACCESS_KEY_ID"] + os.environ["AWS_SECRET_ACCESS_KEY"]):
        fail("the state key pair contains quotes, backslashes or whitespace", 2)
    try:
        text = (Path(root) / f"{provider}.s3.tfbackend").read_text()
    except OSError:
        fail(f"missing backend file: {root}/{provider}.s3.tfbackend", 2)
    settings = dict(re.findall(r'^\s*(\w+)\s*=\s*"([^"]*)"', text, re.MULTILINE))
    endpoint = re.search(r'\bs3\s*=\s*"(https://[^"]+)"', text)
    if not endpoint or not {"bucket", "key", "region"} <= settings.keys():
        fail("backend file needs bucket, key, region and an https endpoints.s3", 2)
    settings["endpoint"] = endpoint.group(1).rstrip("/")
    prefix = settings.get("workspace_key_prefix", "env:")
    settings["object"] = settings["key"] if env == "prod" else f"{prefix}/{env}/{settings['key']}"
    return provider, env, settings


def s3_get(settings: dict[str, str], query: str) -> bytes:
    """Signed GET on the bucket; the key pair reaches curl on stdin, never argv."""
    path = urllib.parse.quote(settings["bucket"]) + ("/" + urllib.parse.quote(settings["object"]) if "versionId" in query else "")
    url = f"{settings['endpoint']}/{path}?{query}"
    config = f'user = "{os.environ["AWS_ACCESS_KEY_ID"]}:{os.environ["AWS_SECRET_ACCESS_KEY"]}"\n'
    # -q first: an operator ~/.curlrc must not weaken TLS or trace the signed request.
    result = subprocess.run(["curl", "-q", "-sS", "--fail-with-body", "-K", "-", "--aws-sigv4",
                             f"aws:amz:{settings['region']}:s3", url], input=config.encode(), capture_output=True, check=False)
    if result.returncode:
        code = re.search(rb"<Code>([^<]+)</Code>", result.stdout)
        fail(f"object storage request failed ({code.group(1).decode() if code else f'curl exit {result.returncode}'})")
    return result.stdout


def versions(settings: dict[str, str]) -> list[dict[str, str]]:
    found, markers = [], ""
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
                detail = next((line.decode(errors="replace").strip() for line in result.stderr.splitlines()
                               if line.startswith(b"Error")), "")
                fail(f"cannot decrypt the selected version (tofu {args[0]} exit {result.returncode}) {detail[:200]}")
        try:
            state = json.loads(result.stdout)
        except ValueError:
            fail("the selected version did not decrypt to a state document")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not valid_state(state):
        fail("the selected version has an invalid state structure")
    return state


def terraform_env(provider: str, env: str, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([str(REPO_ROOT / "scripts/terraform-env.sh"), *args], input=data, capture_output=True, check=False,
                          env={**os.environ, "PROVIDER": provider, "ENV": env})


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


def main() -> None:
    os.umask(0o077)
    if len(sys.argv) > 2:
        fail("usage: restore-tf-state.py [version-id]", 2)
    version = sys.argv[1] if len(sys.argv) == 2 else os.environ.get("STATE_VERSION", "")
    if version and not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", version):
        fail("usage: restore-tf-state.py [version-id]", 2)
    provider, env, settings = admit(bool(version))
    if not version:
        for entry in versions(settings):
            print(f"{entry['version']}  {entry['modified']}  size={entry['size']}  latest={entry['latest']}  {entry['kind']}")
        return
    restored = decrypt(s3_get(settings, "versionId=" + version))
    # Bind the workspace to the backend file the version came from before reading or writing it.
    initialized = terraform_env(provider, env, "init", "-input=false", "-no-color", "-reconfigure")
    if initialized.returncode:
        fail(f"cannot initialize {provider}/{env} against {provider}.s3.tfbackend (exit {initialized.returncode})")
    pulled = terraform_env(provider, env, "state", "pull")
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
    # The push takes the backend lock; without -force OpenTofu refuses a lower or
    # equal serial, so a writer that moved the state since the pull wins.
    pushed = terraform_env(provider, env, "state", "push", "-no-color", *force, "-",
                           data=json.dumps(restored).encode())
    if pushed.returncode:
        reason = " ".join(line.strip() for line in pushed.stderr.decode(errors="replace").splitlines() if line.strip())
        fail(f"state push refused (exit {pushed.returncode}): {reason[-500:]}")
    # OpenTofu may raise the serial again when it persists, so report what the backend holds.
    after = terraform_env(provider, env, "state", "pull")
    stored = read_state(after) if after.returncode == 0 else None
    if stored is None or stored["lineage"] != restored["lineage"] or stored["serial"] < restored["serial"]:
        fail("the pushed state does not read back as the restored version; inspect the bucket versions")
    print(f"restored version {version} of {provider}/{env} as serial {stored['serial']}; "
          "run a plan and expect no changes")


if __name__ == "__main__":
    main()
