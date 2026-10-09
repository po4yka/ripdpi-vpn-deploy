#!/usr/bin/env python3
"""Refuse target stop propagation into any unrecorded active systemd member."""

import json
import re
import subprocess
import sys


def query(unit, property_name):
    result = subprocess.run(
        ["systemctl", "show", unit, "--property=" + property_name, "--value"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode or len(result.stdout) > 16384:
        raise ValueError("unit state")
    return result.stdout.strip()


def verify(names):
    if (
        not isinstance(names, list)
        or len(names) > 32
        or any(
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}", name)
            for name in names
        )
    ):
        raise ValueError("ownership")
    expected = {"awg-quick@" + name + ".service" for name in names}
    members = query("awg-quick.target", "ConsistsOf").split()
    if len(members) > 64:
        raise ValueError("membership")
    for member in members:
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,160}", member):
            raise ValueError("membership")
        state = query(member, "ActiveState")
        if state not in {"active", "inactive", "failed"}:
            raise ValueError("unit transition")
        if member not in expected and state != "inactive":
            raise ValueError("foreign member")


def main():
    try:
        verify(json.loads(sys.stdin.read(4097)))
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print("shared AWG target ownership requires explicit recovery", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
