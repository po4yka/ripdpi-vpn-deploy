#!/usr/bin/env python3
"""Own a one-shot, no-mount Colima liveness executor.

Operator surface:

* ``prepare`` creates one non-default profile and a private executor manifest;
* ``verify-binding`` validates a private binding against one accepted report;
* ``deonboard`` removes only the exact bound assignment after guarded provider
  absence.  It never creates, modifies, or destroys provider resources.

The manifest and binding are private controller artifacts.  They contain no
client credentials and are deliberately outside the public report schema.
"""

from __future__ import annotations

import hashlib
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable
from uuid import UUID, uuid4

import yaml

LIMIT = 256 * 1024
REPO = Path(__file__).resolve().parents[1]
PROFILE = re.compile(r"vpn-liveness-[a-z0-9][a-z0-9-]{0,39}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
FORBIDDEN_PROFILES = {"default", "colima", "vpn-ssh-ci-20260828"}
Command = Callable[..., bytes]
BINDING_FIELDS = {
    "schema_version",
    "kind",
    "executor_id",
    "profile",
    "executor_manifest_sha256",
    "cleanup_manifest_sha256",
    "config_sha256",
    "sentinel",
    "client",
    "generation_id",
    "provenance",
    "target_identity",
}


class ExecutorError(ValueError):
    """Categorical refusal; private paths and contents stay out of diagnostics."""


@contextmanager
def _exclusive_locks(paths: tuple[Path, ...]):
    descriptors: list[int] = []
    try:
        for path in paths:
            path = path.expanduser().absolute()
            _private_parent(path.parent)
            descriptor = os.open(
                path,
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
            )
            try:
                info = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                ):
                    raise ExecutorError("deonboard-lock")
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ExecutorError("deonboard-busy") from None
            except (Exception, KeyboardInterrupt, SystemExit):
                os.close(descriptor)
                raise
            descriptors.append(descriptor)
        yield
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )


def _private_parent(path: Path) -> None:
    path = path.absolute()
    if not path.exists() or path.is_symlink():
        raise ExecutorError("private-parent")
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.geteuid())
            or (info.st_mode & 0o022 and not sticky_root)
        ):
            raise ExecutorError("private-parent")
    info = path.lstat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ExecutorError("private-parent")


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path = path.expanduser().absolute()
    _private_parent(path.parent)
    if path.exists() or path.is_symlink():
        raise ExecutorError("evidence-exists")
    payload = _canonical(value)
    if len(payload) > LIMIT:
        raise ExecutorError("evidence-size")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    identity = os.fstat(fd)
    complete = False
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise ExecutorError("evidence-write")
            offset += written
        os.fsync(fd)
        complete = True
    finally:
        os.close(fd)
        if not complete:
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (
                    identity.st_dev,
                    identity.st_ino,
                ):
                    path.unlink()
            except FileNotFoundError:
                # A failed writer may have been interrupted after an exact
                # cleanup already removed its owned partial file.
                pass
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def _read_raw_private(path: Path) -> bytes:
    path = path.expanduser().absolute()
    _private_parent(path.parent)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ExecutorError("private-input") from exc
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size > LIMIT
        ):
            raise ExecutorError("private-input")
        chunks = []
        remaining = LIMIT + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(fd)
        if (
            len(payload) != before.st_size
            or len(payload) > LIMIT
            or (before.st_dev, before.st_ino, before.st_size)
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
            )
        ):
            raise ExecutorError("private-input")
    finally:
        os.close(fd)
    return payload


def _read_private(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = _read_raw_private(path)
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise ExecutorError("private-input") from exc
    if not isinstance(value, dict) or _canonical(value) != payload:
        raise ExecutorError("private-input")
    return value, payload


def _profile(value: str) -> str:
    if (
        value in FORBIDDEN_PROFILES
        or not isinstance(value, str)
        or not PROFILE.fullmatch(value)
    ):
        raise ExecutorError("profile-name")
    return value


def _context(runner: Command) -> str:
    try:
        value = (
            runner(("docker", "context", "show"), timeout=10).decode("ascii").strip()
        )
    except (OSError, UnicodeError, AttributeError) as exc:
        raise ExecutorError("executor-context") from exc
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value) is None:
        raise ExecutorError("executor-context")
    return value


def _config(home: Path, profile: str) -> tuple[Path, bytes, dict[str, Any]]:
    path = home / ".colima" / profile / "colima.yaml"
    try:
        info = path.lstat()
        payload = path.read_bytes()
        value = yaml.safe_load(payload)
    except (OSError, yaml.YAMLError) as exc:
        raise ExecutorError("executor-config") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
        or not isinstance(value, dict)
        or value.get("autoActivate") is not False
        or value.get("mounts") not in (None, [])
        or value.get("sshConfig") is not False
        or not isinstance(value.get("network"), dict)
        or value["network"].get("address") is not False
        or value["network"].get("mode") != "shared"
        or value["network"].get("portForwarder") != "none"
    ):
        raise ExecutorError("executor-config")
    return path, payload, value


def _inspect(profile: str, *, home: Path, runner: Command) -> tuple[bytes, bytes]:
    try:
        raw = runner(("colima", "status", "--profile", profile, "--json"), timeout=30)
        status = json.loads(raw)
    except (OSError, ValueError, TypeError) as exc:
        raise ExecutorError("executor-status") from exc
    if (
        not isinstance(status, dict)
        or status.get("name") != profile
        or status.get("status") != "Running"
        or status.get("runtime") != "docker"
        or status.get("arch") not in ("aarch64", "x86_64")
    ):
        raise ExecutorError("executor-status")
    mounts = runner(("colima", "ssh", "--profile", profile, "--", "mount"), timeout=30)
    lowered = mounts.lower()
    if any(
        token in lowered
        for token in (
            b" on /users/",
            b" on /volumes/",
            b" type 9p ",
            b" type virtiofs ",
            b" type fuse.sshfs ",
        )
    ):
        raise ExecutorError("executor-mount")
    pid1 = runner(
        ("colima", "ssh", "--profile", profile, "--", "ps", "-p", "1", "-o", "comm="),
        timeout=30,
    )
    if pid1.strip() != b"systemd":
        raise ExecutorError("executor-systemd")
    runner(
        ("colima", "ssh", "--profile", profile, "--", "sudo", "-n", "true"), timeout=30
    )
    return _canonical(status), mounts


MARKER = "/var/lib/vpn-liveness-executor-id"
MARKER_WRITE = """import os,sys
p=sys.argv[1]; v=sys.argv[2].encode('ascii')+b'\\n'
fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
try:
 os.write(fd,v); os.fsync(fd)
finally: os.close(fd)
d=os.open('/var/lib',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try: os.fsync(d)
finally: os.close(d)
"""
MARKER_READ = """import os,stat,sys
fd=os.open(sys.argv[1],os.O_RDONLY|os.O_NOFOLLOW)
try:
 s=os.fstat(fd); d=os.read(fd,129)
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or len(d)>128: raise SystemExit(1)
 sys.stdout.buffer.write(d)
finally: os.close(fd)
"""


def _write_marker(profile: str, executor_id: str, runner: Command) -> None:
    runner(
        (
            "colima",
            "ssh",
            "--profile",
            profile,
            "--",
            "sudo",
            "-n",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-S",
            "-c",
            MARKER_WRITE,
            MARKER,
            executor_id,
        ),
        timeout=30,
    )


def _read_marker(profile: str, runner: Command) -> str:
    raw = runner(
        (
            "colima",
            "ssh",
            "--profile",
            profile,
            "--",
            "sudo",
            "-n",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-S",
            "-c",
            MARKER_READ,
            MARKER,
        ),
        timeout=30,
    )
    try:
        value = raw.decode("ascii").strip()
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, UnicodeError) as exc:
        raise ExecutorError("executor-marker") from exc
    return value


def prepare_executor(
    *,
    profile: str,
    manifest_path: Path,
    home: Path,
    now: int,
    expires_at: int,
    runner: Command,
) -> dict[str, Any]:
    if os.environ.get("BUILD_GATE_HELD") != "1":
        raise ExecutorError("build-gate-required")
    profile = _profile(profile)
    if (
        type(now) is not int
        or type(expires_at) is not int
        or not now < expires_at <= now + 6 * 3600
    ):
        raise ExecutorError("executor-expiry")
    home = home.expanduser().resolve(strict=True)
    manifest_path = manifest_path.expanduser().absolute()
    if manifest_path.exists() or manifest_path.is_symlink():
        raise ExecutorError("evidence-exists")
    _private_parent(manifest_path.parent)
    if (home / ".colima" / profile).exists():
        raise ExecutorError("profile-exists")
    initial_context = _context(runner)
    executor_id = str(uuid4())
    start = (
        "colima",
        "start",
        "--profile",
        profile,
        "--activate=false",
        "--mount",
        "none",
        "--network-address=false",
        "--network-mode",
        "shared",
        "--port-forwarder",
        "none",
        "--ssh-config=false",
        "--runtime",
        "docker",
        "--cpus",
        "2",
        "--memory",
        "2",
        "--disk",
        "10",
    )
    started = False
    try:
        runner(start, timeout=600)
        started = True
        _, config_payload, _ = _config(home, profile)
        status_payload, mounts = _inspect(profile, home=home, runner=runner)
        _write_marker(profile, executor_id, runner)
        if _read_marker(profile, runner) != executor_id:
            raise ExecutorError("executor-marker")
        if _context(runner) != initial_context:
            raise ExecutorError("executor-context")
        manifest = {
            "schema_version": 1,
            "kind": "colima-systemd",
            "executor_id": executor_id,
            "profile": profile,
            "created_at": now,
            "expires_at": expires_at,
            "initial_docker_context": initial_context,
            "profile_config_sha256": hashlib.sha256(config_payload).hexdigest(),
            "profile_status_sha256": hashlib.sha256(status_payload).hexdigest(),
            "mount_table_sha256": hashlib.sha256(mounts).hexdigest(),
            "executor_marker_sha256": hashlib.sha256(
                (executor_id + "\n").encode("ascii")
            ).hexdigest(),
        }
        _write_new(manifest_path, manifest)
        return manifest
    except (Exception, KeyboardInterrupt, SystemExit):
        # VM ownership must be released even when the operator interrupts the
        # preflight before a manifest can make that ownership durable.
        if started:
            try:
                runner(("colima", "stop", "--profile", profile), timeout=180)
                runner(
                    ("colima", "delete", "--profile", profile, "--force", "--data"),
                    timeout=180,
                )
            except (OSError, ExecutorError):
                raise ExecutorError("executor-cleanup") from None
        raise


def _validate_manifest(value: dict[str, Any], now: int) -> None:
    if set(value) != {
        "schema_version",
        "kind",
        "executor_id",
        "profile",
        "created_at",
        "expires_at",
        "initial_docker_context",
        "profile_config_sha256",
        "profile_status_sha256",
        "mount_table_sha256",
        "executor_marker_sha256",
    }:
        raise ExecutorError("executor-manifest")
    try:
        UUID(value["executor_id"])
    except (ValueError, TypeError, KeyError) as exc:
        raise ExecutorError("executor-manifest") from exc
    if (
        value["schema_version"] != 1
        or value["kind"] != "colima-systemd"
        or _profile(value["profile"]) != value["profile"]
        or type(value["created_at"]) is not int
        or type(value["expires_at"]) is not int
        or not value["created_at"] <= now < value["expires_at"]
        or value["expires_at"] > value["created_at"] + 6 * 3600
        or value["executor_marker_sha256"]
        != hashlib.sha256((value["executor_id"] + "\n").encode("ascii")).hexdigest()
        or any(
            not isinstance(value[key], str) or not HEX64.fullmatch(value[key])
            for key in (
                "profile_config_sha256",
                "profile_status_sha256",
                "mount_table_sha256",
                "executor_marker_sha256",
            )
        )
    ):
        raise ExecutorError("executor-manifest")


def load_live_executor(
    manifest_path: Path,
    *,
    home: Path,
    now: int,
    runner: Command,
    allow_expired: bool = False,
) -> dict[str, Any]:
    manifest, _ = _read_private(manifest_path)
    _validate_manifest(manifest, manifest["created_at"] if allow_expired else now)
    _, config_payload, _ = _config(home, manifest["profile"])
    if hashlib.sha256(config_payload).hexdigest() != manifest["profile_config_sha256"]:
        raise ExecutorError("executor-config")
    if _context(runner) != manifest["initial_docker_context"]:
        raise ExecutorError("executor-context")
    _inspect(manifest["profile"], home=home, runner=runner)
    if _read_marker(manifest["profile"], runner) != manifest["executor_id"]:
        raise ExecutorError("executor-marker")
    return manifest


def _load_deonboard_executor(
    manifest_path: Path,
    *,
    home: Path,
    runner: Command,
) -> tuple[dict[str, Any], str]:
    manifest, _ = _read_private(manifest_path)
    _validate_manifest(manifest, manifest["created_at"])
    _, config_payload, _ = _config(home, manifest["profile"])
    if hashlib.sha256(config_payload).hexdigest() != manifest["profile_config_sha256"]:
        raise ExecutorError("executor-config")
    if _context(runner) != manifest["initial_docker_context"]:
        raise ExecutorError("executor-context")
    try:
        raw = runner(("colima", "list", "--json"), timeout=30)
        entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (OSError, ValueError, TypeError) as exc:
        raise ExecutorError("executor-status") from exc
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("name") == manifest["profile"]
    ]
    if (
        len(matches) != 1
        or matches[0].get("status") not in ("Running", "Stopped")
        or matches[0].get("runtime") != "docker"
        or matches[0].get("arch") not in ("aarch64", "x86_64")
    ):
        raise ExecutorError("executor-status")
    state = matches[0]["status"]
    if state == "Running":
        _inspect(manifest["profile"], home=home, runner=runner)
        if _read_marker(manifest["profile"], runner) != manifest["executor_id"]:
            raise ExecutorError("executor-marker")
    return manifest, state


def bind_executor(
    manifest_path: Path,
    binding_path: Path,
    config_path: Path,
    cleanup_manifest_path: Path,
    *,
    sentinel: str,
    client: str,
    generation_id: str,
    provenance: dict[str, Any],
    target_identity: dict[str, Any],
    home: Path,
    now: int,
    runner: Command,
) -> dict[str, Any]:
    if not NAME.fullmatch(sentinel) or not NAME.fullmatch(client):
        raise ExecutorError("binding-identity")
    manifest = load_live_executor(manifest_path, home=home, now=now, runner=runner)
    _, manifest_payload = _read_private(manifest_path)
    _, cleanup_manifest_payload = _read_private(cleanup_manifest_path)
    try:
        if str(UUID(generation_id)) != generation_id:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ExecutorError("binding-generation") from exc
    if provenance.get("client_generation_id") != generation_id:
        raise ExecutorError("binding-generation")
    config_payload = _read_raw_private(config_path)
    try:
        config = yaml.safe_load(config_payload)
    except yaml.YAMLError as exc:
        raise ExecutorError("binding-config") from exc
    declared = config.get("sentinels") if isinstance(config, dict) else None
    if (
        not isinstance(declared, list)
        or len(declared) != 1
        or not isinstance(declared[0], dict)
        or declared[0].get("id") != sentinel
    ):
        raise ExecutorError("binding-config")
    binding = {
        "schema_version": 1,
        "kind": "colima-systemd",
        "executor_id": manifest["executor_id"],
        "profile": manifest["profile"],
        "executor_manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "cleanup_manifest_sha256": hashlib.sha256(cleanup_manifest_payload).hexdigest(),
        "config_sha256": hashlib.sha256(config_payload).hexdigest(),
        "sentinel": sentinel,
        "client": client,
        "generation_id": generation_id,
        "provenance": provenance,
        "target_identity": target_identity,
    }
    if binding_path.exists():
        existing, existing_payload = _read_private(binding_path)
        if existing != binding or existing_payload != _canonical(binding):
            raise ExecutorError("binding-conflict")
    else:
        _write_new(binding_path, binding)
    return binding


def load_bound_executor(
    binding_path: Path,
    manifest_path: Path,
    config_path: Path,
    *,
    home: Path,
    now: int,
    runner: Command,
) -> dict[str, Any]:
    manifest = load_live_executor(manifest_path, home=home, now=now, runner=runner)
    binding, _ = _read_private(binding_path)
    _, manifest_payload = _read_private(manifest_path)
    if (
        set(binding) != BINDING_FIELDS
        or binding.get("schema_version") != 1
        or binding.get("kind") != "colima-systemd"
        or binding.get("executor_id") != manifest.get("executor_id")
        or binding.get("profile") != manifest.get("profile")
        or binding.get("executor_manifest_sha256")
        != hashlib.sha256(manifest_payload).hexdigest()
        or binding.get("config_sha256")
        != hashlib.sha256(_read_raw_private(config_path)).hexdigest()
    ):
        raise ExecutorError("binding-executor")
    return binding


def binding_digest(binding_path: Path) -> str:
    """Return the digest of one canonical private executor binding."""
    return hashlib.sha256(_read_private(binding_path)[1]).hexdigest()


def executor_command(profile: str, command: str) -> tuple[str, ...]:
    _profile(profile)
    if not isinstance(command, str) or not command or "\x00" in command:
        raise ExecutorError("executor-command")
    return (
        "colima",
        "ssh",
        "--profile",
        profile,
        "--",
        "/bin/sh",
        "-c",
        command,
    )


def verify_report_binding(
    binding_path: Path,
    manifest_path: Path,
    config_path: Path,
    report: dict[str, Any],
) -> dict[str, str]:
    binding, _ = _read_private(binding_path)
    _, manifest_payload = _read_private(manifest_path)
    try:
        config_payload = _read_raw_private(config_path)
    except OSError as exc:
        raise ExecutorError("binding-config") from exc
    if (
        set(binding) != BINDING_FIELDS
        or binding.get("schema_version") != 1
        or binding.get("kind") != "colima-systemd"
        or binding.get("executor_manifest_sha256")
        != hashlib.sha256(manifest_payload).hexdigest()
        or binding.get("config_sha256") != hashlib.sha256(config_payload).hexdigest()
        or report.get("sentinel") != binding.get("sentinel")
        or report.get("provenance") != binding.get("provenance")
        or report.get("target_identity") != binding.get("target_identity")
        or report.get("provenance", {}).get("client_generation_id")
        != binding.get("generation_id")
    ):
        raise ExecutorError("binding-report")
    return {
        "kind": "colima-systemd",
        "executor_id_sha256": hashlib.sha256(
            binding["executor_id"].encode("ascii")
        ).hexdigest(),
        "manifest_sha256": binding["executor_manifest_sha256"],
    }


def _verified_absence(path: Path) -> dict[str, Any]:
    value, _ = _read_private(path)
    if (
        value.get("schema_version") != 2
        or value.get("status") not in ("verified", "verified_after_expiry")
        or value.get("server_status") != "absent"
        or value.get("root_storage_status") != "absent"
        or value.get("billing_status") != "no-active-owned-resources"
        or not isinstance(value.get("manifest_sha256"), str)
        or not HEX64.fullmatch(value["manifest_sha256"])
    ):
        raise ExecutorError("target-absence")
    return value


def deonboard(
    *,
    binding_path: Path,
    manifest_path: Path,
    absence_evidence_path: Path,
    registry_path: Path,
    config_path: Path,
    sops_file: Path,
    output_path: Path,
    home: Path,
    runner: Command,
) -> dict[str, Any]:
    with _exclusive_locks(
        (
            registry_path.with_name(registry_path.name + ".lock"),
            sops_file.with_name(sops_file.name + ".new-client.lock"),
        )
    ):
        return _deonboard_locked(
            binding_path=binding_path,
            manifest_path=manifest_path,
            absence_evidence_path=absence_evidence_path,
            registry_path=registry_path,
            config_path=config_path,
            sops_file=sops_file,
            output_path=output_path,
            home=home,
            runner=runner,
        )


def _deonboard_locked(
    *,
    binding_path: Path,
    manifest_path: Path,
    absence_evidence_path: Path,
    registry_path: Path,
    config_path: Path,
    sops_file: Path,
    output_path: Path,
    home: Path,
    runner: Command,
) -> dict[str, Any]:
    absence = _verified_absence(absence_evidence_path)
    binding, _ = _read_private(binding_path)
    manifest, manifest_payload = _read_private(manifest_path)
    if (
        set(binding) != BINDING_FIELDS
        or binding.get("schema_version") != 1
        or binding.get("kind") != "colima-systemd"
        or binding.get("executor_id") != manifest.get("executor_id")
        or binding.get("profile") != manifest.get("profile")
        or binding.get("executor_manifest_sha256")
        != hashlib.sha256(manifest_payload).hexdigest()
        or binding.get("cleanup_manifest_sha256") != absence["manifest_sha256"]
    ):
        raise ExecutorError("deonboard-binding")
    profile = _profile(binding["profile"])
    client = binding.get("client")
    sentinel = binding.get("sentinel")
    if (
        not isinstance(client, str)
        or not NAME.fullmatch(client)
        or not isinstance(sentinel, str)
        or not NAME.fullmatch(sentinel)
    ):
        raise ExecutorError("deonboard-binding")

    binding_digest = hashlib.sha256(_read_private(binding_path)[1]).hexdigest()
    registry = None
    if registry_path.exists():
        registry, _ = _read_private(registry_path)
        if (
            set(registry) != {"schema_version", "sentinels"}
            or registry.get("schema_version") != 2
            or not isinstance(registry.get("sentinels"), dict)
        ):
            raise ExecutorError("deonboard-registry")
        entry = registry["sentinels"].get(sentinel)
        if entry is not None and (
            not isinstance(entry, dict)
            or entry.get("client") != client
            or entry.get("generation_id") != binding.get("generation_id")
            or entry.get("executor_binding_sha256") != binding_digest
        ):
            raise ExecutorError("deonboard-registry")

    config_payload = None
    if config_path.exists():
        config_payload = _read_raw_private(config_path)
        if hashlib.sha256(config_payload).hexdigest() != binding.get("config_sha256"):
            raise ExecutorError("deonboard-config")
        try:
            config = yaml.safe_load(config_payload)
        except yaml.YAMLError as exc:
            raise ExecutorError("deonboard-config") from exc
        declared = config.get("sentinels") if isinstance(config, dict) else None
        if (
            not isinstance(declared, list)
            or len(declared) != 1
            or not isinstance(declared[0], dict)
            or declared[0].get("id") != sentinel
        ):
            raise ExecutorError("deonboard-config")

    profile_present = (home / ".colima" / profile).exists()
    profile_state = None
    if profile_present:
        _, profile_state = _load_deonboard_executor(
            manifest_path, home=home, runner=runner
        )

    encrypted = _read_raw_private(sops_file)
    secret_bytes = runner(
        ("sops", "--decrypt", "--output-type", "yaml", str(sops_file)), timeout=30
    )
    try:
        secrets = yaml.safe_load(secret_bytes)
    except yaml.YAMLError as exc:
        raise ExecutorError("deonboard-secrets") from exc
    paths = _client_secret_paths(secrets, client)
    if paths:
        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=f".{sops_file.name}.deonboard.",
            suffix=sops_file.suffix or ".yaml",
            dir=sops_file.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(temporary_fd, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            for path in paths:
                runner(
                    ("sops", "unset", "--idempotent", str(temporary), path), timeout=30
                )
            # The encrypted file must remain encrypted and nonempty after every edit.
            if temporary.stat().st_size <= 0:
                raise ExecutorError("deonboard-secrets")
            confirmed_bytes = runner(
                ("sops", "--decrypt", "--output-type", "yaml", str(temporary)),
                timeout=30,
            )
            try:
                confirmed = yaml.safe_load(confirmed_bytes)
            except yaml.YAMLError as exc:
                raise ExecutorError("deonboard-secrets") from exc
            if _client_secret_paths(confirmed, client):
                raise ExecutorError("deonboard-secrets")
            os.replace(temporary, sops_file)
            _fsync_dir(sops_file.parent)
        finally:
            temporary.unlink(missing_ok=True)

    if registry is not None and sentinel in registry["sentinels"]:
        updated = dict(registry)
        updated["sentinels"] = dict(registry["sentinels"])
        del updated["sentinels"][sentinel]
        _replace_private(registry_path, _canonical(updated))
    if config_payload is not None:
        _unlink_exact(config_path, config_payload, "deonboard-config")

    if profile_present:
        _, profile_state = _load_deonboard_executor(
            manifest_path, home=home, runner=runner
        )
        if profile_state == "Running":
            runner(("colima", "stop", "--profile", profile), timeout=180)
        runner(
            ("colima", "delete", "--profile", profile, "--force", "--data"),
            timeout=180,
        )
    if (home / ".colima" / profile).exists():
        raise ExecutorError("deonboard-profile")
    result = {
        "schema_version": 1,
        "status": "deonboarded",
        "executor_id": binding["executor_id"],
        "sentinel_sha256": hashlib.sha256(sentinel.encode()).hexdigest(),
        "client_sha256": hashlib.sha256(client.encode()).hexdigest(),
        "target_absence_sha256": hashlib.sha256(
            _read_private(absence_evidence_path)[1]
        ).hexdigest(),
    }
    if output_path.exists():
        existing, _ = _read_private(output_path)
        if existing != result:
            raise ExecutorError("deonboard-evidence")
    else:
        _write_new(output_path, result)
    try:
        runner(
            (
                str(REPO / "scripts/audit-log.sh"),
                "append-best-effort",
                "--action",
                "deonboard-disposable-liveness",
                "--note",
                "executor-retired",
            ),
            timeout=30,
        )
    except ExecutorError:
        print("disposable-liveness-executor: audit-unavailable", file=sys.stderr)
    return result


def _client_secret_paths(value: Any, client: str) -> list[str]:
    if not isinstance(value, dict):
        raise ExecutorError("deonboard-secrets")

    def indexes(root: str, field: str) -> list[int]:
        collection = (
            value.get(root, {}).get(field)
            if isinstance(value.get(root), dict)
            else None
        )
        if not isinstance(collection, list):
            raise ExecutorError("deonboard-secrets")
        return [
            index
            for index, item in enumerate(collection)
            if isinstance(item, dict) and item.get("name") == client
        ]

    primary = {
        ("xray", "clients"): indexes("xray", "clients"),
        ("hysteria", "clients"): indexes("hysteria", "clients"),
        ("amneziawg_secrets", "peers"): indexes("amneziawg_secrets", "peers"),
    }
    registry = value.get("client_registry")
    if not isinstance(registry, dict):
        raise ExecutorError("deonboard-secrets")
    snell_paths = []
    variants = (
        value.get("snell_secrets", {}).get("variants", [])
        if isinstance(value.get("snell_secrets"), dict)
        else []
    )
    if not isinstance(variants, list):
        raise ExecutorError("deonboard-secrets")
    for variant_index in reversed(range(len(variants))):
        users = (
            variants[variant_index].get("users", [])
            if isinstance(variants[variant_index], dict)
            else []
        )
        if not isinstance(users, list):
            raise ExecutorError("deonboard-secrets")
        for user_index in reversed(range(len(users))):
            if (
                isinstance(users[user_index], dict)
                and users[user_index].get("name") == client
            ):
                snell_paths.append(
                    f'["snell_secrets"]["variants"][{variant_index}]["users"][{user_index}]'
                )
    present = [bool(matches) for matches in primary.values()] + [client in registry]
    if not any(present):
        if snell_paths:
            raise ExecutorError("deonboard-secrets")
        return []
    if not all(present) or any(len(matches) != 1 for matches in primary.values()):
        raise ExecutorError("deonboard-secrets")
    paths = [
        f'["xray"]["clients"][{primary[("xray", "clients")][0]}]',
        f'["hysteria"]["clients"][{primary[("hysteria", "clients")][0]}]',
        f'["amneziawg_secrets"]["peers"][{primary[("amneziawg_secrets", "peers")][0]}]',
    ]
    paths.extend(snell_paths)
    paths.append(f'["client_registry"][{json.dumps(client)}]')
    return paths


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_private(path: Path, payload: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _unlink_exact(path: Path, expected: bytes, category: str) -> None:
    try:
        if path.read_bytes() != expected:
            raise ExecutorError(category)
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ExecutorError(category)
        path.unlink()
        _fsync_dir(path.parent)
    except OSError as exc:
        raise ExecutorError(category) from exc


def _run_command(
    argv: tuple[str, ...] | list[str],
    *,
    timeout: int = 30,
    input_bytes: bytes = b"",
    environment: dict[str, str] | None = None,
) -> bytes:
    safe_environment = {
        key: value
        for key, value in (os.environ if environment is None else environment).items()
        if key
        in {"PATH", "HOME", "SOPS_AGE_KEY_FILE", "SOPS_AGE_KEY_CMD", "SSH_AUTH_SOCK"}
    }
    safe_environment.update(LANG="C", LC_ALL="C")
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=safe_environment,
        )
    except OSError as exc:
        raise ExecutorError("command-failed") from exc
    try:
        stdout, _ = process.communicate(input_bytes, timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt, SystemExit) as primary:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            # The command may already be gone; a surviving owned process group
            # is reclaimed below before the primary interruption is propagated.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                # The owned process group can exit between TERM and the
                # bounded KILL fallback; there is nothing left to reclaim.
                pass
            process.wait()
        if isinstance(primary, subprocess.TimeoutExpired):
            raise ExecutorError("command-failed") from primary
        raise
    if process.returncode != 0 or len(stdout) > LIMIT:
        raise ExecutorError("command-failed")
    return stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--profile", required=True)
    prepare.add_argument("--manifest", required=True, type=Path)
    prepare.add_argument("--ttl-seconds", type=int, default=6 * 3600)
    verify = subparsers.add_parser("verify-binding")
    verify.add_argument("--binding", required=True, type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--config", required=True, type=Path)
    verify.add_argument("--report", required=True, type=Path)
    remove = subparsers.add_parser("deonboard")
    for name in (
        "binding",
        "manifest",
        "absence-evidence",
        "registry",
        "config",
        "sops-file",
        "output",
    ):
        remove.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    now = int(time.time())
    try:
        if args.command == "prepare":
            result = prepare_executor(
                profile=args.profile,
                manifest_path=args.manifest,
                home=Path.home(),
                now=now,
                expires_at=now + args.ttl_seconds,
                runner=_run_command,
            )
        elif args.command == "verify-binding":
            report, _ = _read_private(args.report)
            result = verify_report_binding(
                args.binding, args.manifest, args.config, report
            )
        else:
            if os.environ.get("BUILD_GATE_HELD") != "1":
                raise ExecutorError("build-gate-required")
            result = deonboard(
                binding_path=args.binding,
                manifest_path=args.manifest,
                absence_evidence_path=args.absence_evidence,
                registry_path=args.registry,
                config_path=args.config,
                sops_file=args.sops_file,
                output_path=args.output,
                home=Path.home(),
                runner=_run_command,
            )
        if args.command == "prepare":
            public = {
                "schema_version": 1,
                "status": "prepared",
                "profile": result["profile"],
                "executor_id_sha256": hashlib.sha256(
                    result["executor_id"].encode("ascii")
                ).hexdigest(),
                "manifest_sha256": hashlib.sha256(
                    _read_private(args.manifest)[1]
                ).hexdigest(),
            }
        elif args.command == "verify-binding":
            public = {"schema_version": 1, "status": "verified", **result}
        else:
            public = {
                key: result[key]
                for key in (
                    "schema_version",
                    "status",
                    "sentinel_sha256",
                    "client_sha256",
                    "target_absence_sha256",
                )
            }
        print(json.dumps(public, sort_keys=True))
        return 0
    except ExecutorError as exc:
        print(f"disposable-liveness-executor: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
