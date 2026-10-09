#!/usr/bin/env python3
"""Read and atomically persist the watchdog's bounded recovery budget."""

from __future__ import annotations

import argparse
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


def operate(path: Path, operation: str) -> None:
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".watchdog-state-" + secrets.token_hex(16)
    try:
        parent = os.fstat(directory)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise PermissionError("unsafe budget directory")
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            content = None
        else:
            with os.fdopen(fd, "r") as source:
                metadata = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_uid != os.geteuid()
                    or metadata.st_mode & 0o027
                ):
                    raise PermissionError("unsafe budget file")
                content = validate(source.read(4097))
        if operation == "read":
            if content is not None:
                sys.stdout.write(content)
            return
        candidate = validate(sys.stdin.read(4097))
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o640,
            dir_fd=directory,
        )
        with os.fdopen(fd, "w") as destination:
            os.fchmod(destination.fileno(), 0o640)
            destination.write(candidate)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


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
