#!/usr/bin/env python3
"""Provision log entries through descriptors; never follow runtime links."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import grp
import json
import os
import pwd
import stat


@contextmanager
def log_directory(directory, check):
    parts = [part for part in directory.split("/") if part]
    if not parts:
        raise ValueError("unsafe-log-directory")
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    changed = False
    try:
        for index, name in enumerate(parts):
            info = os.fstat(current)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ValueError("unsafe-log-parent")
            try:
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                )
            except FileNotFoundError:
                if check:
                    yield None, True
                    return
                os.mkdir(
                    name, 0o750 if index == len(parts) - 1 else 0o755, dir_fd=current
                )
                child = os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                )
                changed = True
            old = current
            current = child
            os.close(old)
        yield current, changed
    finally:
        os.close(current)


@contextmanager
def log_entry(parent, name, check):
    changed = False
    try:
        fd = os.open(name, os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError:
        changed = True
        fd = (
            None
            if check
            else os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
        )
    try:
        if fd is not None:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("unsafe-log-entry")
        yield fd, changed
    finally:
        if fd is not None:
            os.close(fd)


def provision(directory: str, uid: int, gid: int, *, check: bool = False) -> bool:
    if not os.path.isabs(directory) or ".." in directory.split("/"):
        raise ValueError("unsafe-log-directory")
    with log_directory(directory, check) as (parent, changed):
        if parent is None:
            return True
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
        with log_entry(parent, "access.log", check) as (access, access_changed):
            with log_entry(parent, "error.log", check) as (error, error_changed):
                changed = changed or access_changed or error_changed
                # Validate the fixed complete write set before any file grant.
                for fd in (access, error):
                    if fd is not None:
                        info = os.fstat(fd)
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                            raise ValueError("unsafe-log-entry")
                for fd in (access, error):
                    if fd is not None:
                        info = os.fstat(fd)
                        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (
                            uid,
                            gid,
                            0o640,
                        ):
                            changed = True
                            if not check:
                                os.fchown(fd, uid, gid)
                                os.fchmod(fd, 0o640)
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
