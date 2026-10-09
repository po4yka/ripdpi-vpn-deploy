#!/usr/bin/env python3
"""Build and verify a private, single-node SSH host-key seed for disposable CI."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

import staging_lifecycle as lifecycle

ROOT = Path(__file__).resolve().parents[1]
IMAGE_BYTES = 16 * 1024 * 1024
ENV_RE = re.compile(r"ci-staging-[A-Za-z0-9][A-Za-z0-9-]{0,47}\Z")
HOST_RE = re.compile(r"[a-z0-9][a-z0-9.-]{0,62}\Z")
HEX_RE = re.compile(r"[a-f0-9]{64}\Z")
TOOL_VERSIONS = {"linux": "1.47.0", "darwin": "1.47.4"}


class Refusal(ValueError):
    """A categorical failure that does not contain private input or tool output."""


def _command(argv: list[str], *, timeout: int = 30) -> bytes:
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Refusal("seed-tool-unavailable") from None
    if result.returncode:
        raise Refusal("seed-tool-failed")
    return result.stdout


def _digest(key: str) -> str:
    fields = key.split()
    if len(fields) != 2 or fields[0] != "ssh-ed25519":
        raise Refusal("seed-public-key-invalid")
    try:
        blob = base64.b64decode(fields[1], validate=True)
    except ValueError:
        raise Refusal("seed-public-key-invalid") from None
    if len(blob) != 51 or blob[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
        raise Refusal("seed-public-key-invalid")
    return hashlib.sha256(blob).hexdigest()


def _image_hash(path: Path) -> str:
    with lifecycle._parent(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                    or before.st_size != IMAGE_BYTES):
                raise Refusal("seed-image-boundary-invalid")
            with os.fdopen(os.dup(fd), "rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            after = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise Refusal("seed-image-changed")
            return digest
        finally:
            os.close(fd)


def _write(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _manifest(path: Path) -> dict:
    raw, _ = lifecycle.read(path)
    try:
        data = json.loads(raw)
        valid = (
            isinstance(data, dict) and set(data) == {"schema_version", "environment", "host_alias", "ssh_port",
                             "filesystem_uuid", "public_key", "host_public_key_sha256",
                             "image_sha256", "image_path", "known_hosts_path"}
            and data["schema_version"] == 1
            and ENV_RE.fullmatch(data["environment"])
            and HOST_RE.fullmatch(data["host_alias"])
            and type(data["ssh_port"]) is int and 1 <= data["ssh_port"] <= 65535
            and str(uuid.UUID(data["filesystem_uuid"])) == data["filesystem_uuid"]
            and HEX_RE.fullmatch(data["image_sha256"])
            and _digest(data["public_key"]) == data["host_public_key_sha256"]
            and data["image_path"] == str(path.parent / "seed.img")
            and data["known_hosts_path"] == str(path.parent / "known_hosts")
            and raw == (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        if not valid:
            raise ValueError("invalid manifest")
    except (ValueError, TypeError, KeyError, AttributeError):
        raise Refusal("seed-manifest-invalid") from None
    return data


def validate(path: Path) -> dict:
    data = _manifest(path)
    if _image_hash(Path(data["image_path"])) != data["image_sha256"]:
        raise Refusal("seed-image-digest-mismatch")
    known, _ = lifecycle.read(Path(data["known_hosts_path"]))
    alias = data["host_alias"] if data["ssh_port"] == 22 else f"[{data['host_alias']}]:{data['ssh_port']}"
    if known != f"{alias} {data['public_key']}\n".encode():
        raise Refusal("seed-known-hosts-mismatch")
    return data


def create(directory: Path, environment: str, host_alias: str, ssh_port: int, mke2fs: str) -> dict:
    if not ENV_RE.fullmatch(environment) or not HOST_RE.fullmatch(host_alias) or not 1 <= ssh_port <= 65535:
        raise Refusal("seed-scope-invalid")
    directory = directory.parent.resolve(strict=True) / directory.name
    if directory.name in {"", ".", ".."}:
        raise Refusal("seed-directory-invalid")
    expected_version = TOOL_VERSIONS.get(sys.platform)
    version = subprocess.run([mke2fs, "-V"], capture_output=True, timeout=10, check=False)
    if not expected_version or version.returncode or not re.search(
            rb"\Amke2fs " + re.escape(expected_version.encode()) + rb"(?:\s|$)", version.stderr):
        raise Refusal("seed-mke2fs-version-unpinned")
    directory.mkdir(mode=0o700)
    try:
        image = directory / "seed.img"
        filesystem_uuid = str(uuid.uuid4())
        with tempfile.TemporaryDirectory(prefix="keys-", dir=directory) as temporary:
            staging = Path(temporary)
            key = staging / "ssh_host_ed25519_key"
            _command(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(key)])
            public = _command(["ssh-keygen", "-y", "-f", str(key)]).decode().strip()
            digest = _digest(public)
            (staging / "ssh_host_ed25519_key.pub").write_text(public + "\n")
            (staging / "ssh_host_ed25519_key.pub").chmod(0o600)
            _write(image, b"")
            with image.open("r+b") as handle:
                handle.truncate(IMAGE_BYTES)
            _command([mke2fs, "-q", "-t", "ext4", "-F", "-U", filesystem_uuid,
                      "-O", "^orphan_file", "-E", "root_owner=0:0", "-d", str(staging), str(image)])
        alias = host_alias if ssh_port == 22 else f"[{host_alias}]:{ssh_port}"
        _write(directory / "known_hosts", f"{alias} {public}\n".encode())
        data = {"schema_version": 1, "environment": environment, "host_alias": host_alias,
                "ssh_port": ssh_port, "filesystem_uuid": filesystem_uuid, "public_key": public,
                "host_public_key_sha256": digest, "image_sha256": _image_hash(image),
                "image_path": str(image), "known_hosts_path": str(directory / "known_hosts")}
        _write(directory / "manifest.json", (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode())
        return validate(directory / "manifest.json")
    except BaseException:
        # This directory was created exclusively above; no preexisting work is removed.
        shutil.rmtree(directory)
        raise


def cleanup_local(path: Path) -> None:
    _manifest(path)
    if {entry.name for entry in path.parent.iterdir()} != {"seed.img", "known_hosts", "manifest.json"}:
        raise Refusal("seed-directory-has-foreign-files")
    with lifecycle._parent(path) as (parent, _):
        for name in ("seed.img", "known_hosts", "manifest.json"):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise Refusal("seed-cleanup-file-invalid")
        for name in ("seed.img", "known_hosts", "manifest.json"):
            os.unlink(name, dir_fd=parent)
    path.parent.rmdir()



def cleanup_seed(path: Path, state: Path, environment: str, request=None) -> dict:
    """Remove only a detached, state-recorded seed from an interrupted apply."""
    data = _manifest(path)
    if data["environment"] != environment:
        raise Refusal("seed-cleanup-environment-mismatch")
    spec = importlib.util.spec_from_file_location("seed_cleanup_guard", ROOT / "scripts/staging-cleanup-guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    raw = guard._private_read(state, "state", max_bytes=guard.MAX_STATE_BYTES, exact_parent_mode=False)
    value = guard._json_object(raw, "state")
    if value.get("version") != 4 or not isinstance(value.get("resources"), list):
        raise Refusal("seed-cleanup-state-invalid")
    seed = None
    seen = set()
    for resource in value["resources"]:
        if not isinstance(resource, dict) or resource.get("mode") != "managed" or "module" in resource:
            raise Refusal("seed-cleanup-state-invalid")
        address = (resource.get("type"), resource.get("name"))
        if address in seen or address not in {("terraform_data", "ssh_port"), ("upcloud_storage", "ci_ssh_seed")}:
            raise Refusal("seed-cleanup-needs-full-manifest")
        seen.add(address)
        instances = resource.get("instances")
        if not isinstance(instances, list) or len(instances) != 1 or not isinstance(instances[0], dict):
            raise Refusal("seed-cleanup-instance-invalid")
        if address[0] == "upcloud_storage":
            if instances[0].get("index_key") != 0:
                raise Refusal("seed-cleanup-instance-invalid")
            seed = instances[0].get("attributes")
    if not isinstance(seed, dict):
        raise Refusal("seed-cleanup-no-recorded-resource")
    identifier = guard._uuid(seed.get("id"), "seed storage UUID")
    expected_labels = {"managed_by": "terraform", "env": environment, "seed_id": data["filesystem_uuid"]}
    imports = seed.get("import")
    if (seed.get("encrypt") is not True or seed.get("title") != data["host_alias"] + "-ssh-seed"
            or not isinstance(seed.get("labels"), dict)
            or any(seed["labels"].get(k) != v for k, v in expected_labels.items())
            or not isinstance(imports, list) or len(imports) != 1 or not isinstance(imports[0], dict)
            or imports[0].get("source") != "direct_upload"
            or imports[0].get("source_hash") != data["image_sha256"]
            or imports[0].get("source_location") != data["image_path"]):
        raise Refusal("seed-cleanup-state-binding-invalid")
    request = request or guard._upcloud_request(guard._provider_authorization())
    guard._authenticated_account_username(request)
    api_path = f"/1.3/storage/{identifier}"
    status, body = request(api_path)
    if status != 404 or guard._error_code(body) != "STORAGE_NOT_FOUND":
        storage = body.get("storage")
        labels = storage.get("labels", []) if isinstance(storage, dict) else []
        if not isinstance(labels, list):
            raise Refusal("seed-cleanup-provider-labels-invalid")
        labels = {item.get("key"): item.get("value") for item in labels if isinstance(item, dict)}
        if (status != 200 or not isinstance(storage, dict) or storage.get("uuid") != identifier
                or storage.get("title") != seed["title"] or storage.get("encrypted") != "yes"
                or storage.get("servers") != {"server": []}
                or any(labels.get(k) != v for k, v in expected_labels.items())):
            raise Refusal("seed-cleanup-provider-binding-invalid")
        deleted, _ = request(api_path, method="DELETE")
        if deleted not in (200, 204):
            raise Refusal("seed-cleanup-delete-failed")
        status, body = request(api_path)
        if status != 404 or guard._error_code(body) != "STORAGE_NOT_FOUND":
            raise Refusal("seed-cleanup-absence-unverified")
    return {"status": "seed-storage-absent", "seed_storage_uuid": identifier}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("create")
    build.add_argument("--directory", type=Path, required=True)
    build.add_argument("--environment", required=True)
    build.add_argument("--host-alias", required=True)
    build.add_argument("--ssh-port", type=int, default=22)
    build.add_argument("--mke2fs", default="mke2fs")
    for name in ("validate", "cleanup-local"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
    cleanup = commands.add_parser("cleanup-seed")
    cleanup.add_argument("--manifest", type=Path, required=True)
    cleanup.add_argument("--state", type=Path, required=True)
    cleanup.add_argument("--environment", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "create":
            data = create(args.directory, args.environment, args.host_alias, args.ssh_port, args.mke2fs)
            data["manifest_path"] = str(Path(data["image_path"]).parent / "manifest.json")
        elif args.command == "validate":
            data = validate(args.manifest)
        elif args.command == "cleanup-seed":
            data = cleanup_seed(args.manifest, args.state, args.environment)
        else:
            cleanup_local(args.manifest)
            data = {"status": "local-seed-removed"}
        print(json.dumps(data, sort_keys=True))
        return 0
    except (Refusal, lifecycle.GuardError, OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"status": "refused", "reason": "ci-ssh-seed-refused"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
