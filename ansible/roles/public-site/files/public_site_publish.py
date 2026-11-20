#!/usr/bin/env python3
"""Serve the scheduled generation of each public site bundle.

Usage: public_site_publish.py BUNDLES_DIR STATE_DIR

BUNDLES_DIR/<sha256>/ holds backlog.tar.gz (named by its own digest) and
schedule.json from `make public-site-build`. STATE_DIR/<sha256>/current becomes
a link to the latest generation whose scheduled time has passed. The result
depends only on the bundle and the clock, so a recreated node serves the same
bytes. The script needs no network and writes only below STATE_DIR.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import time
from pathlib import Path

MEMBER = re.compile(r"\Agenerations/(0|[1-9][0-9]*)/([^/]+(?:/[^/]+)*)\Z")


def members(archive: tarfile.TarFile) -> list[tuple[int, str, tarfile.TarInfo]]:
    """Every member as (generation, relative path, info). One unexpected member refuses the archive.

    The build writes regular files only, so a directory member is unexpected too."""
    found = []
    for member in archive.getmembers():
        match = MEMBER.match(member.name)
        if not member.isreg() or not match or any(part in ("", ".", "..") for part in match.group(2).split("/")):
            raise ValueError(f"unexpected archive member {member.name!r}")
        found.append((int(match.group(1)), match.group(2), member))
    return sorted(found, key=lambda item: item[0])


def publish(bundle: Path, state: Path, now: float) -> None:
    archive_path = bundle / "backlog.tar.gz"
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != bundle.name:
        raise ValueError("archive digest does not match its directory name")
    document = json.loads((bundle / "schedule.json").read_text(encoding="utf-8"))
    plan = document["generations"]
    if document.get("version") != 1 or [entry["n"] for entry in plan] != list(range(len(plan))) or not plan:
        raise ValueError("schedule is not version 1 with generations 0..n")
    if not all(type(entry["not_before"]) is int for entry in plan):
        raise ValueError("schedule times must be integers")
    # Generation 0 is the site that the vhost already serves, so it is the floor.
    number = max([0] + [entry["n"] for entry in plan if entry["not_before"] <= now])
    current = state / "current"
    target = f"generations/{number}"
    if not (os.path.islink(current) and os.readlink(current) == target and (state / target).is_dir()):
        build(archive_path, state, number, len(plan))
        link = state / "current.new"
        link.unlink(missing_ok=True)
        link.symlink_to(target)
        link.replace(current)
        print(f"{bundle.name[:12]}: serving generation {number}")
    # Also after an interrupted run: nothing but the served generation stays readable.
    for other in (state / "generations").iterdir():
        if other.name != str(number):
            shutil.rmtree(other, ignore_errors=True)


def build(archive_path: Path, state: Path, number: int, scheduled: int) -> None:
    staging = state / "generations" / f".{number}.building"
    shutil.rmtree(staging, ignore_errors=True)
    with tarfile.open(archive_path) as archive:
        found = members(archive)
        if {generation for generation, _, _ in found} != set(range(scheduled)):
            raise ValueError("archive generations do not match the schedule")
        # Later generations overlay earlier ones; members after `number` stay in the archive.
        for generation, relative, member in found:
            if generation > number:
                continue
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
            os.utime(path, (member.mtime, member.mtime))
    final = state / "generations" / str(number)
    shutil.rmtree(final, ignore_errors=True)
    staging.rename(final)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    bundles, state = Path(argv[1]), Path(argv[2])
    failed = False
    for bundle in sorted(bundles.iterdir()):
        if not re.fullmatch(r"[0-9a-f]{64}", bundle.name):
            continue
        try:
            publish(bundle, state / bundle.name, time.time())
        except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
            # One refused bundle keeps its previous generation and does not stop the others.
            print(f"{bundle.name[:12]}: {error}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
