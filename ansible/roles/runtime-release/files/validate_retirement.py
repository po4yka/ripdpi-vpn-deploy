#!/usr/bin/env python3
"""Validate the entire declared retirement authority before lifecycle changes."""

from __future__ import annotations

import json
import os
import pwd
import re
from pathlib import Path
import stat
import sys

PROTECTED = {"/", "/etc", "/usr", "/usr/local", "/var", "/var/lib", "/run"}


def validate(paths: list[str], owners: dict[str, str] | None = None) -> list[str]:
    if (
        not isinstance(paths, list)
        or len(paths) > 256
        or any(not isinstance(value, str) or len(value) > 1024 for value in paths)
        or len(set(paths)) != len(paths)
    ):
        raise ValueError("retirement request")
    owners = {} if owners is None else owners
    if (
        not isinstance(owners, dict)
        or not set(owners) <= set(paths)
        or any(
            not isinstance(account, str)
            or re.fullmatch(r"[a-z_][a-z0-9_-]{0,63}", account) is None
            for account in owners.values()
        )
    ):
        raise ValueError("retirement file owners")
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
            permitted_uids = {os.geteuid()}
            if value in owners:
                # A producer grant applies only to the declared regular file,
                # never to a directory, symlink or recursively found child.
                if current != path or not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("retirement producer file")
                if metadata.st_uid not in permitted_uids:
                    try:
                        permitted_uids.add(pwd.getpwnam(owners[value]).pw_uid)
                    except KeyError:
                        raise ValueError("retirement account") from None
            if count > 10000 or metadata.st_uid not in permitted_uids:
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
        request = json.loads(sys.stdin.read(262145))
        if not isinstance(request, dict) or set(request) != {"paths", "owners"}:
            raise ValueError("retirement request")
        paths = validate(request["paths"], request["owners"])
    except (ValueError, OSError):
        print("runtime retirement authority rejected", file=sys.stderr)
        return 2
    print(json.dumps({"status": "accepted", "paths": paths}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
