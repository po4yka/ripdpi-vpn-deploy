#!/usr/bin/env python3
"""Prepare the exact owned access log before root-run Caddy validation."""

import argparse
import json
import os
from pathlib import Path
import pwd
import stat
import sys


def prepare(path, username, inspect=False):
    account = pwd.getpwnam(username)
    path = Path(path)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.name not in {"access.log", "site-error.log"}
    ):
        raise ValueError("path")
    for parent in reversed(path.parent.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("ancestor")
    try:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        if inspect:
            return False
        raise
    try:
        info = os.fstat(directory)
        if (
            info.st_uid != account.pw_uid
            or info.st_gid != account.pw_gid
            or stat.S_IMODE(info.st_mode) != 0o750
        ):
            raise ValueError("directory")
        flags = (
            (os.O_RDONLY if inspect else os.O_WRONLY | os.O_APPEND)
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
        )
        try:
            if inspect:
                fd = os.open(path.name, flags, dir_fd=directory)
                changed = False
            else:
                fd = os.open(
                    path.name, flags | os.O_CREAT | os.O_EXCL, 0o640, dir_fd=directory
                )
                changed = True
        except FileNotFoundError:
            if inspect:
                return False
            raise
        except FileExistsError:
            fd = os.open(path.name, flags, dir_fd=directory)
            changed = False
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid not in (0, account.pw_uid)
                or info.st_mode & 0o022
            ):
                raise ValueError("file")
            if inspect:
                return False
            expected = (account.pw_uid, account.pw_gid, 0o640)
            if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != expected:
                os.fchown(fd, account.pw_uid, account.pw_gid)
                os.fchmod(fd, 0o640)
                changed = True
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        return changed
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--user", default="naive")
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps({"changed": prepare(args.path, args.user, args.inspect)}))
    except (OSError, ValueError, KeyError):
        print("Naive log preparation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
