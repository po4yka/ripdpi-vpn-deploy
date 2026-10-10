#!/usr/bin/env python3
"""Adopt changed or unacknowledged owned Naive authority before recording it."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time


def safe_directory(path):
    current = Path("/")
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("path")
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise ValueError("unsafe-directory")


def digest(path):
    safe_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
            or info.st_size > 128 * 1024 * 1024
        ):
            raise ValueError("unsafe-file")
        result = hashlib.sha256()
        while block := os.read(fd, 1024 * 1024):
            result.update(block)
        after = os.fstat(fd)
        if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("file-changed")
        return result.hexdigest()
    finally:
        os.close(fd)


def command(argv):
    result = subprocess.run(
        argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError("activation-command")
    return result.stdout


def legacy_authority(args):
    """Identify only the former role-rendered credential file for retirement."""
    path = Path(args.config).with_name("Caddyfile")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        group = Path(args.config).stat().st_gid
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_gid != group
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o640
            or info.st_size > 1024 * 1024
        ):
            raise ValueError("foreign-legacy-config")
        raw = os.read(fd, 1024 * 1024 + 1)
        if (
            len(raw) != info.st_size
            or not raw.startswith(b"{\n  log default {")
            or b"    forward_proxy {" not in raw
            or b"      basic_auth " not in raw
            or b"# NOTE: NaiveProxy v147.0.7727.49-3" not in raw
        ):
            raise ValueError("foreign-legacy-config")
        return (
            path,
            (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            ),
            hashlib.sha256(raw).hexdigest(),
        )
    finally:
        os.close(fd)


def retire_legacy(args, authority):
    if authority is None:
        return False
    if legacy_authority(args) != authority:
        raise ValueError("changed-legacy-config")
    path = authority[0]
    path.unlink()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def runtime_identity(args):
    import re

    raw = command(["systemctl", "show", args.unit, "--property=MainPID,ActiveState"])
    values = dict(
        line.split("=", 1) for line in raw.decode("ascii").splitlines() if "=" in line
    )
    pid = values.get("MainPID", "")
    if values.get("ActiveState") != "active" or not re.fullmatch(
        r"[1-9][0-9]{0,9}", pid
    ):
        raise RuntimeError("runtime-not-ready")
    process = Path("/proc") / pid
    installed = Path(args.binary).stat()
    running = (process / "exe").stat()
    if (installed.st_dev, installed.st_ino) != (running.st_dev, running.st_ino):
        raise RuntimeError("runtime-identity")
    argv = (process / "cmdline").read_bytes()
    if len(argv) > 4096 or argv.split(b"\0")[:-1] != [
        os.fsencode(args.binary),
        b"run",
        b"--config",
        os.fsencode(args.config),
    ]:
        raise RuntimeError("runtime-identity")
    owned = set()
    with os.scandir(process / "fd") as entries:
        for index, entry in enumerate(entries):
            if index >= 4096:
                raise RuntimeError("runtime-capacity")
            try:
                target = os.readlink(entry.path)
            except FileNotFoundError:
                continue
            match = re.fullmatch(r"socket:\[([0-9]+)\]", target)
            if match:
                owned.add(match[1])
    listeners = set()
    for name in ("tcp", "tcp6"):
        with (process / "net" / name).open("rb") as source:
            table = source.read(1024 * 1024 + 1)
        if len(table) > 1024 * 1024:
            raise RuntimeError("runtime-capacity")
        for line in table.decode("ascii").splitlines()[1:]:
            row = line.split()
            if (
                len(row) >= 10
                and row[3] == "0A"
                and int(row[1].rsplit(":", 1)[1], 16) == args.port
            ):
                listeners.add(row[9])
    if not listeners or not listeners <= owned:
        raise RuntimeError("runtime-listener")
    return pid


def pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("unsafe-receipt")
        result[key] = value
    return result


def activate(args):
    import re

    if (
        not re.fullmatch(r"[a-z][a-z0-9_.-]{0,95}\.service", args.unit)
        or not 1 <= args.port <= 65535
    ):
        raise ValueError("unit")
    files = [args.binary, args.unit_file, args.config, args.certificate, args.key]
    state = Path(args.state)
    safe_directory(state.parent)
    state.mkdir(mode=0o700, exist_ok=True)
    safe_directory(state)
    if stat.S_IMODE(state.stat().st_mode) != 0o700:
        raise ValueError("unsafe-state")
    fd = os.open(state / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("unsafe-lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        expected = {
            "schema": 1,
            "fingerprint": hashlib.sha256(
                json.dumps([digest(Path(path)) for path in files]).encode()
            ).hexdigest(),
        }
        legacy = legacy_authority(args)
        receipt = state / "activated.json"
        previous = None
        try:
            receipt_fd = os.open(receipt, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            pass
        else:
            try:
                info = os.fstat(receipt_fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > 1024
                ):
                    raise ValueError("unsafe-receipt")
                previous = json.loads(
                    os.read(receipt_fd, 1025), object_pairs_hook=pairs
                )
                if (
                    not isinstance(previous, dict)
                    or set(previous) != set(expected)
                    or type(previous["schema"]) is not int
                    or previous["schema"] != 1
                    or not isinstance(previous["fingerprint"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", previous["fingerprint"])
                ):
                    raise ValueError("unsafe-receipt")
            finally:
                os.close(receipt_fd)
        if previous == expected:
            try:
                runtime_identity(args)
            except (OSError, RuntimeError):
                # Unchanged bytes do not prove a replaced executable or a
                # newly started process has adopted this authority yet.
                pass
            else:
                return retire_legacy(args, legacy)
        command([args.binary, "validate", "--config", args.config])
        command(["systemctl", "daemon-reload"])
        command(["systemctl", "restart", args.unit])
        context = ssl.create_default_context(cafile=args.certificate)
        deadline = time.monotonic() + 10
        while True:
            try:
                pid = runtime_identity(args)
                with context.wrap_socket(
                    socket.create_connection(("127.0.0.1", args.port), timeout=1),
                    server_hostname=args.server_name,
                ):
                    if runtime_identity(args) != pid:
                        raise RuntimeError("runtime-identity")
                    break
            except (OSError, RuntimeError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("runtime-not-ready") from None
                time.sleep(0.1)
        # Refuse an external authority change during restart before acknowledging.
        if (
            expected["fingerprint"]
            != hashlib.sha256(
                json.dumps([digest(Path(path)) for path in files]).encode()
            ).hexdigest()
        ):
            raise ValueError("file-changed")
        retire_legacy(args, legacy)
        out, temporary = tempfile.mkstemp(dir=state, prefix=".receipt-")
        try:
            with os.fdopen(out, "wb") as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(json.dumps(expected).encode())
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, receipt)
            directory_fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return True
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    for name in (
        "binary",
        "unit-file",
        "config",
        "certificate",
        "key",
        "unit",
        "state",
        "server-name",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps({"changed": activate(args)}))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("Naive activation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
