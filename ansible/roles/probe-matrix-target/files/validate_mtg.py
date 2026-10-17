#!/usr/bin/env python3
"""Validate the selected mtg binary and config without network probes or output."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


def validate(binary: str, version: str, config: str) -> None:
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", version):
        raise ValueError("invalid-version-pin")
    observed = subprocess.run([binary, "--version"], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=10, check=False)
    if observed.returncode or observed.stdout.split(maxsplit=1)[:1] != [version.removeprefix("v").encode()]:
        raise ValueError("native-version-mismatch")
    if not Path(config).is_file() or Path(config).stat().st_size > 65536:
        raise ValueError("invalid-config-file")
    # Explicit addresses bypass public-IP discovery. Access invokes ReadConfig
    # without starting the proxy or contacting Telegram. It prints credentials,
    # so neither native output stream may reach diagnostics.
    result = subprocess.run([binary, "access", "--ipv4=127.0.0.1", "--ipv6=::1", config],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=15, check=False)
    if result.returncode:
        raise ValueError("native-config-refused")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        validate(args.binary, args.version, args.config)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("mtg: native candidate validation refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
