#!/usr/bin/env python3
"""Issue, revoke or read one Naive device from an encrypted document."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile

NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
USERNAME = re.compile(r"[A-Za-z0-9_.@-]{1,64}\Z")


def validate_clients(clients):
    if not isinstance(clients, list) or len(clients) > 128:
        raise ValueError("invalid client collection")
    seen = {key: set() for key in ("name", "username", "password")}
    for item in clients:
        if not isinstance(item, dict) or set(item) != set(seen):
            raise ValueError("invalid client entry")
        if not isinstance(item["name"], str) or not NAME.fullmatch(item["name"]):
            raise ValueError("invalid device name")
        if not isinstance(item["username"], str) or not USERNAME.fullmatch(
            item["username"]
        ):
            raise ValueError("invalid username")
        password = item["password"]
        if (
            not isinstance(password, str)
            or not 20 <= len(password) <= 128
            or not all(33 <= ord(c) <= 126 for c in password)
        ):
            raise ValueError("invalid password")
        for key in seen:
            if item[key] in seen[key]:
                raise ValueError("duplicate device identity or credential")
            seen[key].add(item[key])


def update_clients(clients, action, name):
    validate_clients(clients)
    matching = [item for item in clients if item["name"] == name]
    if action == "issue":
        if (
            matching
            or any(item["username"] == name for item in clients)
            or len(clients) == 128
        ):
            raise ValueError("device already exists or capacity reached")
        return [
            *clients,
            {"name": name, "username": name, "password": secrets.token_urlsafe(32)},
        ]
    if not matching:
        raise ValueError("device not found")
    return [item for item in clients if item["name"] != name]


def run_sops(argv, *, data=None):
    result = subprocess.run(
        ["sops", *argv], input=data, capture_output=True, timeout=60
    )
    if result.returncode:
        # SOPS diagnostics may contain input/credentials; expose only the phase.
        raise RuntimeError("encrypted document operation failed")
    return result.stdout


def private_file(fd):
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise ValueError("unsafe private document authority")
    return info


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def operate(path, action, name):
    path = Path(os.path.abspath(path))
    path = path.parent.resolve(strict=True) / path.name
    parent = os.open(
        path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    lock = None
    temporary = None
    source = None
    try:
        directory = os.fstat(parent)
        if directory.st_uid != os.getuid() or directory.st_mode & 0o022:
            raise ValueError("unsafe encrypted document directory")
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
        lock = os.open(str(path) + ".new-client.lock", flags, 0o600)
        private_file(lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = private_file(source)
        if before.st_size > 4 * 1024 * 1024:
            raise ValueError("document exceeds capacity")
        encrypted = os.read(source, before.st_size + 1)
        if len(encrypted) != before.st_size or identity(os.fstat(source)) != identity(
            before
        ):
            raise ValueError("document changed during read")
        input_type = "json" if path.suffix == ".json" else "yaml"
        document = json.loads(
            run_sops(
                [
                    "--decrypt",
                    "--input-type",
                    input_type,
                    "--output-type",
                    "json",
                    "/dev/stdin",
                ],
                data=encrypted,
            )
        )
        block = document.get("naive_secrets")
        if not isinstance(block, dict) or "username" in block or "password" in block:
            raise ValueError("per-device Naive contract required")
        clients = block.get("clients", [])
        validate_clients(clients)
        if action == "readout":
            selected = next((item for item in clients if item["name"] == name), None)
            if selected is None:
                raise ValueError("device not found")
            server = block.get("server_name")
            if not isinstance(server, str) or not server:
                raise ValueError("server identity unavailable")
            if identity(os.stat(path, follow_symlinks=False)) != identity(before):
                raise ValueError("document changed during read")
            return {"server_name": server, **selected}
        updated = update_clients(clients, action, name)
        descriptor, temporary = tempfile.mkstemp(
            prefix="." + path.name + ".naive-client.",
            suffix=path.suffix,
            dir=path.parent,
        )
        try:
            output = os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            raise
        with output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        run_sops(
            ["set", "--value-stdin", temporary, '["naive_secrets"]'],
            data=json.dumps({**block, "clients": updated}).encode(),
        )
        check = json.loads(run_sops(["--decrypt", "--output-type", "json", temporary]))
        expected = {**document, "naive_secrets": {**block, "clients": updated}}
        if (
            check != expected
            or identity(os.stat(path, follow_symlinks=False)) != identity(before)
            or (os.stat(path.parent).st_dev, os.stat(path.parent).st_ino)
            != (directory.st_dev, directory.st_ino)
        ):
            raise ValueError("document changed during transaction")
        with open(temporary, "rb") as staged:
            private_file(staged.fileno())
            os.fsync(staged.fileno())
        os.replace(temporary, path)
        temporary = None
        os.fsync(parent)
        return {"device": name, "action": action, "clients": len(updated)}
    finally:
        try:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        finally:
            try:
                if source is not None:
                    os.close(source)
            finally:
                try:
                    if lock is not None:
                        os.close(lock)
                finally:
                    os.close(parent)


def export_readout(source, name, destination):
    """Publish only the selected device to a new owner-only artifact."""
    path = Path(os.path.abspath(destination))
    path = path.parent.resolve(strict=True) / path.name
    repository = Path(__file__).resolve().parent.parent
    if path.is_relative_to(repository) and not path.is_relative_to(
        repository / "secrets" / "local"
    ):
        raise ValueError("credential output must stay outside tracked source")
    for ancestor in reversed(path.parent.parents):
        metadata = ancestor.lstat()
        trusted_sticky = metadata.st_uid == 0 and metadata.st_mode & stat.S_ISVTX
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid not in (0, os.getuid())
            or (metadata.st_mode & 0o022 and not trusted_sticky)
        ):
            raise ValueError("unsafe credential output ancestry")
    parent = os.open(
        path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    descriptor = None
    created = None
    complete = False
    try:
        directory = os.fstat(parent)
        if directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) != 0o700:
            raise ValueError("unsafe credential output directory")
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass  # Only a new destination may receive selected credentials.
        else:
            raise ValueError("credential output already exists")
        material = operate(source, "readout", name)
        descriptor = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent,
        )
        created = os.fstat(descriptor)
        private_file(descriptor)
        payload = memoryview((json.dumps(material) + "\n").encode("utf-8"))
        while payload:
            written = os.write(descriptor, payload)
            if written <= 0:
                raise OSError("credential publication failed")
            payload = payload[written:]
        os.fsync(descriptor)
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        current_parent = os.stat(path.parent, follow_symlinks=False)
        pinned_parent = os.fstat(parent)
        if (
            (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino)
            or (current_parent.st_dev, current_parent.st_ino)
            != (directory.st_dev, directory.st_ino)
            or pinned_parent.st_uid != os.getuid()
            or stat.S_IMODE(pinned_parent.st_mode) != 0o700
        ):
            raise ValueError("credential output authority changed")
        private_file(descriptor)
        os.fsync(parent)
        complete = True
        return path
    finally:
        try:
            if not complete and created is not None:
                try:
                    current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass  # A removed owned artifact needs no cleanup.
                else:
                    if (current.st_dev, current.st_ino) == (
                        created.st_dev,
                        created.st_ino,
                    ):
                        os.unlink(path.name, dir_fd=parent)
                        os.fsync(parent)
        finally:
            try:
                if descriptor is not None:
                    os.close(descriptor)
            finally:
                os.close(parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("issue", "revoke", "readout"))
    parser.add_argument("name")
    parser.add_argument("--file", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    if not NAME.fullmatch(args.name):
        parser.error("invalid device name")
    if (args.action == "readout") != bool(args.output):
        parser.error("readout requires --output; mutation commands do not accept it")
    try:
        if args.action == "readout":
            destination = export_readout(args.file, args.name, args.output)
            result = {
                "device": args.name,
                "action": "readout",
                "output": str(destination),
            }
        else:
            operation = operate(args.file, args.action, args.name)
            result = {
                "device": args.name,
                "action": args.action,
                "clients": operation["clients"],
            }
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("Naive device operation refused or failed", file=sys.stderr)
        return 1
    if args.action != "readout":
        try:
            subprocess.run(
                [
                    str(Path(__file__).with_name("audit-log.sh")),
                    "append-best-effort",
                    "--action",
                    "naive-" + args.action,
                    "--client",
                    args.name,
                ],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            pass  # Audit availability cannot undo an already committed credential change.
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
