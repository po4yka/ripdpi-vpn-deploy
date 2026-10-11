#!/usr/bin/env python3
"""Admit and lock an inherited descriptor retained by the calling shell."""

import fcntl
import os
from pathlib import Path
import stat
import sys


def acquire(path, descriptor):
    path = Path(path).absolute()
    parent = path.parent.resolve(strict=True)
    for directory in (parent, *parent.parents):
        info = directory.lstat()
        trusted_sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in (0, os.geteuid())
                or (info.st_mode & 0o022 and not trusted_sticky)):
            raise ValueError
    opened = os.fstat(descriptor)
    named = path.lstat()
    if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(named.st_mode)
            or opened.st_uid != os.geteuid() or opened.st_nlink != 1
            or opened.st_mode & 0o133
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)):
        raise ValueError
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    named = path.lstat()
    if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
        raise ValueError
    # Repair old same-owner 0644 locks only after authority and lock admission.
    os.fchmod(descriptor, 0o600)


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError
        acquire(sys.argv[1], int(sys.argv[2]))
    except (OSError, ValueError):
        print("operator lock unavailable or unsafe", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
