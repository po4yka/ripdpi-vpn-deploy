#!/usr/bin/env python3
"""Install a digest-bound disposable SSH host identity from its private disk."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid


def public_key(path: Path) -> bytes:
    result = subprocess.run(["ssh-keygen", "-y", "-f", str(path)], capture_output=True, timeout=15, check=True)
    fields = result.stdout.strip().split()
    if len(fields) != 2 or fields[0] != b"ssh-ed25519":
        raise ValueError("invalid public key")
    return b" ".join(fields)


def matches(path: Path, expected: str) -> bool:
    key = public_key(path)
    return hashlib.sha256(base64.b64decode(key.split()[1], validate=True)).hexdigest() == expected


def install(source: Path, destination: Path, expected: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("invalid digest")
    key = source / "ssh_host_ed25519_key"
    info = key.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 4096:
        raise ValueError("invalid source boundary")
    if not matches(key, expected):
        raise ValueError("key identity mismatch")
    destination.mkdir(mode=0o755, parents=True, exist_ok=True)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("invalid destination boundary")
    target = destination / "ssh_host_ed25519_key"
    if target.is_symlink():
        raise ValueError("invalid target boundary")
    if target.exists():
        target_info = target.lstat()
        if not stat.S_ISREG(target_info.st_mode) or target_info.st_nlink != 1:
            raise ValueError("invalid target boundary")
        try:
            if stat.S_IMODE(target_info.st_mode) == 0o600 and matches(target, expected):
                return
        except (ValueError, subprocess.SubprocessError):
            pass
    private = key.read_bytes()
    if len(private) > 4096:
        raise ValueError("invalid key size")
    # Private bytes never enter arguments, command output or cloud-init user_data.
    for name, data, mode in ((target.name, private, 0o600), (target.name + ".pub", public_key(key) + b"\n", 0o644)):
        fd, temporary = tempfile.mkstemp(prefix=".ci-seed-", dir=destination)
        try:
            with os.fdopen(fd, "wb") as handle:
                os.fchmod(handle.fileno(), mode)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filesystem-uuid", required=True)
    parser.add_argument("--public-key-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if str(uuid.UUID(args.filesystem_uuid)) != args.filesystem_uuid or os.geteuid() != 0:
            raise ValueError("invalid scope")
        device = Path("/dev/disk/by-uuid") / args.filesystem_uuid
        deadline = time.monotonic() + 120
        while not device.exists() and time.monotonic() < deadline:
            time.sleep(1)
        if not stat.S_ISBLK(device.stat().st_mode):
            raise ValueError("seed device missing")
        with tempfile.TemporaryDirectory(prefix="vpn-ssh-seed-", dir="/run") as temporary:
            mounted = False
            try:
                subprocess.run(["mount", "-t", "ext4", "-o", "ro,noload,nodev,nosuid,noexec", str(device), temporary],
                               capture_output=True, timeout=15, check=True)
                mounted = True
                install(Path(temporary), Path("/etc/ssh"), args.public_key_sha256)
            finally:
                if mounted:
                    subprocess.run(["umount", temporary], capture_output=True, timeout=15, check=True)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print("SSH seed identity installation refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
