#!/usr/bin/env python3
"""Verify both pinned geodata inputs before paired ordinary-failure publication."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

MAX_BYTES = 128 * 1024 * 1024


def activate():
    result = subprocess.run(
        ["/usr/local/sbin/vpn-xray-geodata-activate.sh"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("activation")


def verify_file(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
    ):
        raise ValueError("unsafe-file")
    return info


def replace(source, destination, *, mode, uid, gid):
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".geodata-")
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as data:
            os.fchmod(output.fileno(), mode)
            os.fchown(output.fileno(), uid, gid)
            shutil.copyfileobj(data, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(
            destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _publish_locked(request):
    directory = Path(request["install_dir"])
    info = directory.lstat()
    if (
        not directory.is_absolute()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
    ):
        raise ValueError("unsafe-directory")
    sources = request["sources"]
    if set(sources) != {"geosite.dat", "geoip.dat"}:
        raise ValueError("sources")
    pending = directory / ".geodata-pending"
    if os.path.lexists(pending):
        raise ValueError("manual-recovery-required")
    previous = {}
    for name in sources:
        path = directory / name
        if os.path.lexists(path):
            metadata = verify_file(path)
            previous[name] = {
                "mode": stat.S_IMODE(metadata.st_mode),
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
            }
        else:
            previous[name] = None
    pending.mkdir(mode=0o700)
    changed = False
    published = []
    try:
        for name, source in sources.items():
            if not isinstance(source["url"], str) or not re.fullmatch(
                r"[0-9a-fA-F]{64}", source["sha256"]
            ):
                raise ValueError("pin")
            candidate = pending / name
            result = subprocess.run(
                [
                    "curl",
                    "-fsSL",
                    "--max-time",
                    "120",
                    "-o",
                    str(candidate),
                    source["url"],
                ],
                capture_output=True,
                timeout=125,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("download")
            size = candidate.stat().st_size
            if (
                size > MAX_BYTES
                or hashlib.sha256(candidate.read_bytes()).hexdigest()
                != source["sha256"].lower()
            ):
                raise ValueError("checksum")
            current = directory / name
            if previous[name] is not None:
                shutil.copyfile(current, pending / ("old-" + name))
                changed = changed or current.read_bytes() != candidate.read_bytes()
            else:
                changed = True
        if not changed:
            return {"changed": False}
        (pending / "snapshot.json").write_text(json.dumps(previous))
        (pending / "snapshot.json").chmod(0o600)
        try:
            for name in sources:
                current = directory / name
                if previous[name] is not None:
                    verify_file(current)
                elif os.path.lexists(current):
                    raise ValueError("file-changed")
                published.append(name)
                replace(
                    pending / name,
                    current,
                    mode=0o644,
                    uid=os.geteuid(),
                    gid=os.getegid(),
                )
            activate()
        except Exception:
            try:
                for name in published:
                    current = directory / name
                    verify_file(current)
                    if previous[name] is None:
                        current.unlink()
                    else:
                        replace(pending / ("old-" + name), current, **previous[name])
                if all(previous[name] is not None for name in sources):
                    activate()
            except Exception:
                raise RuntimeError("manual-recovery-required") from None
            published.clear()
            raise RuntimeError("publication-compensated") from None
        published.clear()
        return {"changed": True}
    finally:
        # Failed rollback retains the private complete pair and snapshot.
        if not published:
            shutil.rmtree(pending)


def publish(request):
    directory = Path(request["install_dir"])
    if not directory.is_absolute() or ".." in directory.parts:
        raise ValueError("unsafe-directory")
    current = Path("/")
    for part in directory.parts[1:]:
        current /= part
        info = current.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in {0, os.geteuid()}
            or info.st_mode & 0o022
        ):
            raise ValueError("unsafe-directory")
    descriptor = os.open(
        directory / ".geodata-lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("unsafe-lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _publish_locked(request)
    finally:
        os.close(descriptor)


def main():
    try:
        request = json.load(sys.stdin)
        print(json.dumps(publish(request)))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ):
        print("geodata publication failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
