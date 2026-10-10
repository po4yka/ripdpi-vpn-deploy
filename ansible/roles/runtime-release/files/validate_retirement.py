#!/usr/bin/env python3
"""Validate the entire declared retirement authority before lifecycle changes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys

PROTECTED = {"/", "/etc", "/usr", "/usr/local", "/var", "/var/lib", "/run"}


def validate(paths: list[str]) -> list[str]:
    if (
        not isinstance(paths, list)
        or len(paths) > 256
        or any(not isinstance(value, str) or len(value) > 1024 for value in paths)
        or len(set(paths)) != len(paths)
    ):
        raise ValueError("retirement request")
    count = 0
    effective = []
    for value in paths:
        path = Path(value)
        if (
            not path.is_absolute()
            or str(path) != value
            or ".." in path.parts
            or value in PROTECTED
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("retirement path")
        for parent in reversed(path.parents):
            try:
                metadata = parent.lstat()
            except FileNotFoundError:
                break
            trusted_shared = (
                metadata.st_uid == os.geteuid() and metadata.st_mode & stat.S_ISVTX
            )
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o022
                and not trusted_shared
            ):
                raise ValueError("retirement ancestor")
        # Administrative unit masks are owner intent, not runtime artifacts.
        try:
            masked = (
                path.parent
                in (Path("/etc/systemd/system"), Path("/run/systemd/system"))
                and path.suffix in (".service", ".timer", ".target")
                and path.is_symlink()
                and os.readlink(path) == "/dev/null"
            )
        except OSError:
            masked = False
        if masked:
            if path.lstat().st_uid != os.geteuid():
                raise ValueError("retirement owner")
            continue
        effective.append(value)
        pending = [path]
        while pending:
            current = pending.pop()
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                continue
            count += 1
            if count > 10000 or metadata.st_uid != os.geteuid():
                raise ValueError("retirement owner")
            if stat.S_ISDIR(metadata.st_mode):
                if metadata.st_mode & 0o022:
                    raise ValueError("retirement directory")
                pending.extend(current.iterdir())
            elif stat.S_ISREG(metadata.st_mode):
                if metadata.st_nlink != 1 or metadata.st_mode & 0o022:
                    raise ValueError("retirement file")
            elif not stat.S_ISLNK(metadata.st_mode):
                raise ValueError("retirement entry")

    return effective


def main() -> int:
    try:
        paths = validate(json.loads(sys.stdin.read(262145)))
    except (ValueError, OSError):
        print("runtime retirement authority rejected", file=sys.stderr)
        return 2
    print(json.dumps({"status": "accepted", "paths": paths}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
