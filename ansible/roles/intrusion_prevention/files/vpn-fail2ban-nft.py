#!/usr/bin/env python3
"""Enforce typed sshd ban membership; accept only observed idempotent races."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys

NFT = "/usr/sbin/nft"
MAX_BYTES = 4 * 1024 * 1024


class EnforcementError(RuntimeError):
    pass


def run(arguments):
    return subprocess.run(
        [NFT, *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )


def present(address, name):
    result = run(["-j", "list", "set", "inet", "filter", name])
    if result.returncode != 0 or len(result.stdout.encode()) > MAX_BYTES:
        raise EnforcementError()
    document = json.loads(result.stdout)
    rows = [row["set"] for row in document["nftables"] if "set" in row]
    if len(rows) != 1:
        raise EnforcementError()
    current = rows[0]
    if (
        current.get("family"),
        current.get("table"),
        current.get("name"),
        current.get("type"),
    ) != (
        "inet",
        "filter",
        name,
        f"ipv{address.version}_addr",
    ) or "timeout" not in current.get(
        "flags", []
    ):
        raise EnforcementError()
    entries = current.get("elem", [])
    if not isinstance(entries, list) or len(entries) > 16384:
        raise EnforcementError()
    found = False
    for entry in entries:
        value = entry.get("elem", {}).get("val") if isinstance(entry, dict) else entry
        if not isinstance(value, str):
            raise EnforcementError()
        parsed = ipaddress.ip_address(value)
        if parsed.version != address.version:
            raise EnforcementError()
        found = found or parsed == address
    return found


def enforce(operation, value, seconds=None):
    address = ipaddress.ip_address(value)
    name = "f2b_sshd" + str(address.version)
    arguments = [
        "add" if operation == "ban" else "delete",
        "element",
        "inet",
        "filter",
        name,
        "{",
        str(address),
    ]
    if operation == "ban":
        if type(seconds) is not int or not 0 < seconds <= 2**31 - 1:
            raise EnforcementError()
        arguments.extend(["timeout", str(seconds) + "s"])
    arguments.append("}")
    result = run(arguments)
    if result.returncode != 0:
        # Do not reinterpret permissions, invalid syntax or any other error as
        # a membership race, even if prior enforcement happens to be present.
        expected = "File exists" if operation == "ban" else "No such file or directory"
        errors = re.findall(r"(?m)^Error: Could not process rule: (.+)$", result.stderr)
        if errors != [expected] or present(address, name) != (operation == "ban"):
            raise EnforcementError()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["ban", "unban"])
    parser.add_argument("address")
    parser.add_argument("seconds", type=int, nargs="?")
    args = parser.parse_args(argv)
    try:
        enforce(args.operation, args.address, args.seconds)
    except (
        EnforcementError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ):
        print("Fail2Ban nft enforcement failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
