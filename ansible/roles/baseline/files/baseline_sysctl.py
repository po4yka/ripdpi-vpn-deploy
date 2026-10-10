#!/usr/bin/env python3
"""Apply ordered sysctl policy with per-setting optional failure boundaries."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

DIRECTORIES = (
    "/etc/sysctl.d",
    "/run/sysctl.d",
    "/usr/local/lib/sysctl.d",
    "/usr/lib/sysctl.d",
    "/lib/sysctl.d",
)


def sources():
    selected = {}
    for directory in DIRECTORIES:
        for path in Path(directory).glob("*.conf"):
            selected.setdefault(path.name, path)
    result = [selected[name] for name in sorted(selected)]
    if Path("/etc/sysctl.conf").exists():
        result.append(Path("/etc/sysctl.conf"))
    return result


def invoke(argv, *, pass_fds=()):
    result = subprocess.run(
        ["/usr/sbin/sysctl", *argv],
        pass_fds=pass_fds,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def mandatory(lines):
    if not lines:
        return
    descriptor = os.memfd_create("vpn-sysctl-policy", os.MFD_CLOEXEC)
    try:
        data = memoryview(("\n".join(lines) + "\n").encode())
        while data:
            written = os.write(descriptor, data)
            if written <= 0:
                raise OSError("short-write")
            data = data[written:]
        os.lseek(descriptor, 0, os.SEEK_SET)
        if not invoke(
            ["-p", "/proc/self/fd/" + str(descriptor)], pass_fds=(descriptor,)
        ):
            raise RuntimeError("mandatory-setting-failed")
    finally:
        os.close(descriptor)


def apply(paths):
    optional_unavailable = 0
    for path in paths:
        raw = Path(path).read_bytes()
        if len(raw) > 262144:
            raise ValueError("policy-size")
        segment = []
        for line in raw.decode().splitlines():
            optional = re.fullmatch(r"\s*-([A-Za-z0-9_./]+)\s*=\s*(.+?)\s*", line)
            if optional:
                mandatory(segment)
                segment = []
                # Only this marked setting may fail; later mandatory work keeps
                # its own normal nonzero failure result, even in the same file.
                value = optional[2].split("#", 1)[0].strip()
                optional_unavailable += not invoke(["-w", optional[1] + "=" + value])
            else:
                segment.append(line)
        mandatory(segment)
    return optional_unavailable


def main():
    try:
        count = apply([Path(value) for value in sys.argv[1:]] or sources())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("mandatory sysctl policy failed", file=sys.stderr)
        return 1
    if count:
        print("optional sysctl setting unavailable", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
