#!/usr/bin/env python3
"""Provision missing replay authority without repairing or following foreign files."""

import json
import os
from pathlib import Path
import pwd
import stat
import sys


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate authority key")
        result[key] = value
    return result


def provision(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"directory", "check", "initializing"}
        or any(type(value[key]) is not bool for key in ("check", "initializing"))
    ):
        raise ValueError("invalid request")
    path = Path(value["directory"])
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("invalid directory")
    try:
        account = pwd.getpwnam("vpn-bootstrap")
        root = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (KeyError, FileNotFoundError):
        if value["check"] and value["initializing"]:
            return {"changed": True}
        raise
    changed = False
    try:
        metadata = os.fstat(root)
        if metadata.st_uid != account.pw_uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError("unsafe directory")
        for name in ("sub", "bootstrap", ".vpn-bootstrap-consumed"):
            child = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
            )
            try:
                info = os.fstat(child)
                if (
                    info.st_uid != account.pw_uid
                    or info.st_gid != account.pw_gid
                    or stat.S_IMODE(info.st_mode) != 0o700
                ):
                    raise ValueError("unsafe retained route authority")
            finally:
                os.close(child)
        rows = {
            ".vpn-bootstrap-state.lock": b"",
            ".vpn-bootstrap-retired-before": b'{"schema":1,"retired_before":0}\n',
        }
        missing = []
        for name in rows:
            try:
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
                )
            except FileNotFoundError:
                missing.append(name)
                continue
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != account.pw_uid
                    or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600
                ):
                    raise ValueError("unsafe authority")
                if name == ".vpn-bootstrap-retired-before":
                    if info.st_size > 1024:
                        raise ValueError("oversized retirement authority")
                    document = json.loads(
                        os.read(fd, 1025), object_pairs_hook=unique_object
                    )
                    if (
                        not isinstance(document, dict)
                        or set(document) != {"schema", "retired_before"}
                        or type(document["schema"]) is not int
                        or document["schema"] != 1
                        or type(document["retired_before"]) is not int
                        or not 0 <= document["retired_before"] <= 9999999999
                    ):
                        raise ValueError("invalid retirement authority")
                elif info.st_size != 0:
                    raise ValueError("invalid lock authority")
            finally:
                os.close(fd)
        if missing and not value["initializing"]:
            raise ValueError(
                "retained replay authority is missing; explicit recovery required"
            )
        if value["check"]:
            return {"changed": bool(missing)}
        for name in missing:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=root,
            )
            with os.fdopen(fd, "wb") as output:
                os.fchown(output.fileno(), account.pw_uid, account.pw_gid)
                output.write(rows[name])
                output.flush()
                os.fsync(output.fileno())
            changed = True
        os.fsync(root)
    finally:
        os.close(root)
    return {"changed": changed}


if __name__ == "__main__":
    try:
        print(
            json.dumps(
                provision(
                    json.loads(sys.stdin.read(4097), object_pairs_hook=unique_object)
                )
            )
        )
    except (OSError, ValueError, KeyError):
        print("retention authority provisioning refused", file=sys.stderr)
        raise SystemExit(2)
