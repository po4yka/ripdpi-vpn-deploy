#!/usr/bin/env python3
"""Provision log entries through descriptors; never follow runtime links."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import grp
import json
import os
import pwd
import stat


def provision(directory: str, uid: int, gid: int, *, check: bool = False) -> bool:
    if not os.path.isabs(directory) or ".." in directory.split("/"):
        raise ValueError("unsafe-log-directory")
    with ExitStack() as resources:
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        resources.callback(os.close, parent)
        files = []
        changed = False
        parts = [part for part in directory.split("/") if part]
        if not parts:
            raise ValueError("unsafe-log-directory")
        for index, name in enumerate(parts):
            final = index == len(parts) - 1
            info = os.fstat(parent)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ValueError("unsafe-log-parent")
            try:
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
            except FileNotFoundError:
                if check:
                    return True
                os.mkdir(name, 0o750 if final else 0o755, dir_fd=parent)
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                )
                changed = True
            resources.callback(os.close, child)
            parent = child
        info = os.fstat(parent)
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (
            os.geteuid(),
            gid,
            0o750,
        ):
            changed = True
            if not check:
                # Revoke runtime directory-entry authority before inspecting children.
                os.fchown(parent, os.geteuid(), gid)
                os.fchmod(parent, 0o750)
        for name in ("access.log", "error.log"):
            try:
                descriptor = os.open(
                    name, os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent
                )
            except FileNotFoundError:
                changed = True
                if check:
                    continue
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent,
                )
            try:
                entry = os.fdopen(descriptor, "ab")
            except BaseException:
                os.close(descriptor)
                raise
            try:
                resources.enter_context(entry)
            except BaseException:
                entry.close()
                raise
            files.append(entry)
            info = os.fstat(entry.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("unsafe-log-entry")
        # Validate every entry before changing any file's ownership or mode.
        for entry in files:
            descriptor = entry.fileno()
            info = os.fstat(descriptor)
            if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (
                uid,
                gid,
                0o640,
            ):
                changed = True
                if not check:
                    os.fchown(descriptor, uid, gid)
                    os.fchmod(descriptor, 0o640)
        return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        try:
            uid = pwd.getpwnam(args.user).pw_uid
            gid = grp.getgrnam(args.group).gr_gid
        except KeyError:
            if not args.check:
                raise
            uid, gid = -1, -1
        changed = provision(args.directory, uid, gid, check=args.check)
    except (OSError, ValueError, KeyError):
        raise SystemExit(
            "Xray log provisioning refused unsafe or unavailable state"
        ) from None
    print(json.dumps({"changed": changed}))


if __name__ == "__main__":
    main()
