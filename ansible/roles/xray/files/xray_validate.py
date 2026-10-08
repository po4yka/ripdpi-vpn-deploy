#!/usr/bin/env python3
"""Validate a candidate with the same assets as the managed Xray service."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


def asset_directory(explicit: str | None) -> str:
    if explicit is None:
        result = subprocess.run(
            ["systemctl", "show", "xray.service", "--property=Environment", "--value"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        values = [
            entry.removeprefix("XRAY_LOCATION_ASSET=")
            for entry in shlex.split(result.stdout)
            if entry.startswith("XRAY_LOCATION_ASSET=")
        ]
        if len(values) != 1:
            raise ValueError("missing or ambiguous asset authority")
        explicit = values[0]
    if not os.path.isabs(explicit) or any(ord(char) < 32 for char in explicit):
        raise ValueError("invalid asset directory")
    return explicit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="/usr/local/bin/xray")
    parser.add_argument("--asset-dir")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dump-config", action="store_true")
    args = parser.parse_args()
    try:
        if not os.path.isabs(args.binary) or not os.path.isabs(args.config):
            raise ValueError("absolute paths required")
        environment = {**os.environ, "XRAY_LOCATION_ASSET": asset_directory(args.asset_dir)}
        command = [args.binary, "run", "-test"]
        if args.dump_config:
            command.append("-dump-config")
        command.extend(["-config", args.config])
        os.execve(args.binary, command, environment)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Xray validation could not resolve its managed runtime environment.", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
