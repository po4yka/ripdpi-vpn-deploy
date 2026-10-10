#!/usr/bin/env python3
"""Read and atomically persist the watchdog's bounded recovery budget."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
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


def stream(fd, mode):
    try:
        return os.fdopen(fd, mode)
    except BaseException:
        os.close(fd)
        raise


def operate(path: Path, operation: str) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise PermissionError("unsafe budget path")
    resources = ExitStack()
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    resources.callback(os.close, directory)
    temporary = ".watchdog-state-" + secrets.token_hex(16)
    candidate_identity = None
    try:
        for name in path.parent.parts[1:]:
            ancestor = os.fstat(directory)
            trusted_sticky = ancestor.st_uid == 0 and ancestor.st_mode & stat.S_ISVTX
            if ancestor.st_uid not in (0, os.geteuid()) or (
                ancestor.st_mode & 0o022 and not trusted_sticky
            ):
                raise PermissionError("unsafe budget ancestry")
            directory = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            resources.callback(os.close, directory)
        parent = os.fstat(directory)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise PermissionError("unsafe budget directory")
        fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            content = None
        else:
            with stream(fd, "r") as source:
                metadata = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) not in (0o600, 0o640)
                ):
                    raise PermissionError("unsafe budget file")
                content = validate(source.read(4097))
                if stat.S_IMODE(metadata.st_mode) == 0o640:
                    # Retire the exact previously canonical group grant only
                    # after complete typed-state validation; counters never reset.
                    os.fchmod(source.fileno(), 0o600)
                    os.fsync(source.fileno())
                    os.fsync(directory)
        if operation == "read":
            if content is not None:
                sys.stdout.write(content)
            return
        candidate = validate(sys.stdin.read(4097))
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            created = os.fstat(fd)
            candidate_identity = (created.st_dev, created.st_ino)
        except BaseException:
            os.close(fd)
            raise
        with stream(fd, "w") as destination:
            os.fchmod(destination.fileno(), 0o600)
            destination.write(candidate)
            destination.flush()
            os.fsync(destination.fileno())
        current = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != candidate_identity:
            raise PermissionError("foreign budget candidate")
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
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
        finally:
            resources.close()


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
