#!/usr/bin/env python3
"""Read and atomically persist the watchdog's bounded recovery budget."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import os
import secrets
import stat
import sys
from pathlib import Path

KEYS = (
    "consecutive_fails",
    "last_alert_epoch",
    "alerts_this_hour",
    "alerts_hour_started",
    "kicks_this_hour",
    "kicks_hour_started",
)


def validate(content: str) -> str:
    values = {}
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if (
            not separator
            or key not in KEYS
            or key in values
            or not value.isascii()
            or not value.isdecimal()
            or len(value) > 12
        ):
            raise ValueError("invalid budget")
        values[key] = value
    if set(values) != set(KEYS):
        raise ValueError("incomplete budget")
    return "".join(f"{key}={int(values[key])}\n" for key in KEYS)


@contextmanager
def open_descriptor(path, flags, mode=0o600, *, dir_fd=None, optional=False):
    try:
        fd = os.open(path, flags, mode, dir_fd=dir_fd)
    except FileNotFoundError:
        if not optional:
            raise
        fd = None
    try:
        yield fd
    finally:
        if fd is not None:
            os.close(fd)


@contextmanager
def budget_directory(path):
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:]:
            ancestor = os.fstat(current)
            trusted_sticky = ancestor.st_uid == 0 and ancestor.st_mode & stat.S_ISVTX
            if ancestor.st_uid not in (0, os.geteuid()) or (
                ancestor.st_mode & 0o022 and not trusted_sticky
            ):
                raise PermissionError("unsafe budget ancestry")
            child = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
            )
            old = current
            current = child
            os.close(old)
        parent = os.fstat(current)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise PermissionError("unsafe budget directory")
        fcntl.flock(current, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield current
    finally:
        os.close(current)


def operate(path: Path, operation: str) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise PermissionError("unsafe budget path")
    temporary = ".watchdog-state-" + secrets.token_hex(16)
    candidate_identity = None
    with budget_directory(path.parent) as directory:
        try:
            # Only an acquisition-time ENOENT represents an absent budget.
            with open_descriptor(
                path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory, optional=True
            ) as fd:
                if fd is None:
                    content = None
                else:
                    with os.fdopen(fd, "r", closefd=False) as source:
                        metadata = os.fstat(fd)
                        if (
                            not stat.S_ISREG(metadata.st_mode)
                            or metadata.st_nlink != 1
                            or metadata.st_uid != os.geteuid()
                            or stat.S_IMODE(metadata.st_mode) not in (0o600, 0o640)
                        ):
                            raise PermissionError("unsafe budget file")
                        content = validate(source.read(4097))
                        if stat.S_IMODE(metadata.st_mode) == 0o640:
                            # Retire the prior grant only after typed validation.
                            os.fchmod(fd, 0o600)
                            os.fsync(fd)
                            os.fsync(directory)
            if operation == "read":
                if content is not None:
                    sys.stdout.write(content)
                return
            candidate = validate(sys.stdin.read(4097))
            with open_descriptor(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            ) as fd:
                created = os.fstat(fd)
                candidate_identity = (created.st_dev, created.st_ino)
                with os.fdopen(fd, "w", closefd=False) as destination:
                    os.fchmod(fd, 0o600)
                    destination.write(candidate)
                    destination.flush()
                    os.fsync(fd)
            current = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != candidate_identity:
                raise PermissionError("foreign budget candidate")
            os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            if candidate_identity is not None:
                try:
                    current = os.stat(
                        temporary, dir_fd=directory, follow_symlinks=False
                    )
                except FileNotFoundError:
                    # Successful writes rename the owned candidate away.
                    pass
                else:
                    if (current.st_dev, current.st_ino) != candidate_identity:
                        raise PermissionError("foreign budget candidate")
                    os.unlink(temporary, dir_fd=directory)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("read", "write"))
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()
    try:
        operate(arguments.path, arguments.operation)
    except (OSError, ValueError):
        print("watchdog: recovery budget unavailable or malformed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
