#!/usr/bin/env python3
"""Locally validate a signed network-exposure review without host execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

import fleet_inspection as inspection

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "network-exposure-gate.py"
MAX_CONFIG = 64 * 1024
CONFIG_KEYS = {"mode", "artifact", "trusted_key", "trusted_key_sha256", "source_id", "promotion"}
PROMOTION_KEYS = {"approved", "digest", "authorized_hosts"}


class ReviewError(ValueError):
    """A redacted local-input failure."""


def _reject_ambient(environment):
    forbidden = [key for key in environment if (key.startswith("ANSIBLE_") and key != "ANSIBLE_LIMIT")
                 or key.startswith("GIT_") or "PLUGIN" in key.upper()]
    if forbidden:
        raise ReviewError("ambient-environment-forbidden")
    if environment.get("ANSIBLE_DEBUG", "").strip().lower() not in {"", "0", "false", "no", "off"}:
        raise ReviewError("ansible-debug-forbidden")


def _read_config(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise ReviewError("unsafe-config") from error
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ReviewError("unsafe-config")
        data = os.read(fd, MAX_CONFIG + 1)
        if len(data) > MAX_CONFIG:
            raise ReviewError("oversized-config")
        fingerprint = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_size,
                       hashlib.sha256(data).digest())
        return data, fingerprint
    finally:
        os.close(fd)


def _fence_config(path, expected):
    data, actual = _read_config(path)
    if actual != expected:
        raise ReviewError("config-replaced")
    return data


def _parse_config(raw):
    try:
        value = json.loads(raw, object_pairs_hook=lambda pairs: _unique_object(pairs))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ReviewError("invalid-config") from error
    if not isinstance(value, dict) or set(value) != CONFIG_KEYS:
        raise ReviewError("invalid-config")
    if (value["mode"] != "log_only" or any(not isinstance(value[key], str) or not value[key]
                                            for key in ("artifact", "trusted_key", "trusted_key_sha256", "source_id"))):
        raise ReviewError("invalid-config")
    promotion = value["promotion"]
    if (not isinstance(promotion, dict) or set(promotion) != PROMOTION_KEYS
            or not isinstance(promotion["approved"], bool) or not isinstance(promotion["digest"], str)
            or not isinstance(promotion["authorized_hosts"], list)
            or any(not isinstance(host, str) for host in promotion["authorized_hosts"])):
        raise ReviewError("invalid-config")
    return value


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate")
        value[key] = item
    return value


def _exact_aliases(value):
    if not value or any(part in {"", "all", "vpn"} for part in value.split(",")):
        raise ReviewError("explicit-aliases-required")
    aliases = value.split(",")
    if len(aliases) != len(set(aliases)):
        raise ReviewError("explicit-aliases-required")
    return aliases


def _snapshot(raw):
    directory = tempfile.TemporaryDirectory(prefix="network-exposure-review-")
    fd = None
    try:
        try:
            os.chmod(directory.name, 0o700)
            path = Path(directory.name) / "review.json"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    raise OSError("snapshot-write-failed")
                offset += written
            os.fsync(fd)
            return directory, path
        finally:
            if fd is not None:
                os.close(fd)
    except BaseException:
        directory.cleanup()
        raise


def review(environment, *, runner=subprocess.run):
    _reject_ambient(environment)
    config_path = environment.get("NETWORK_EXPOSURE_CONFIG", "")
    if not config_path:
        raise ReviewError("config-required")
    raw, fingerprint = _read_config(config_path)
    config = _parse_config(raw)
    aliases = _exact_aliases(environment.get("ANSIBLE_LIMIT", ""))
    # Resolve the exact canonical records once.  This validates the same strict
    # inventory transport contract without starting an SSH or Ansible process.
    inspection.select_hosts(ROOT / "ansible/inventory/generated.ini", aliases)
    snapshot_directory, snapshot = _snapshot(raw)
    try:
        _fence_config(config_path, fingerprint)
        if snapshot.read_bytes() != raw:
            raise ReviewError("snapshot-corrupt")
        config = _parse_config(snapshot.read_bytes())
        promotion = config["promotion"]
        argv = [sys.executable, str(GATE), "--mode", config["mode"], "--artifact", config["artifact"],
                "--trusted-key", config["trusted_key"], "--trusted-key-sha256", config["trusted_key_sha256"],
                "--source-id", config["source_id"], "--promotion-approved", str(promotion["approved"]).lower(),
                "--promotion-digest", promotion["digest"], "--authorized-hosts-json",
                json.dumps(promotion["authorized_hosts"], separators=(",", ":"))]
        child = {key: environment[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ") if key in environment}
        child.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
        result = runner(argv, cwd=ROOT, env=child, capture_output=True, text=True, timeout=20, check=False)
        if result.returncode:
            raise ReviewError("validation-failed")
        value = json.loads(result.stdout)
        summary = value.get("summary", value)
        if not isinstance(summary, dict) or set(summary) != {"validation", "source_id", "counts", "content_sha256", "artifact_sha256"}:
            raise ReviewError("invalid-validator-output")
        return {"source_id": summary["source_id"], "content_sha256": summary["content_sha256"],
                "artifact_sha256": summary["artifact_sha256"], "counts": summary["counts"]}
    finally:
        snapshot_directory.cleanup()


def main():
    try:
        print(json.dumps(review(dict(os.environ)), sort_keys=True))
        return 0
    except (ReviewError, inspection.InspectionError, OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"status": "error", "reason": "network-exposure-review-failed"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
