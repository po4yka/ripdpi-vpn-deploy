#!/usr/bin/env python3
"""Collect a unique machine report; return categorical acceptance evidence only."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time


def validate_report(data, started, ended):
    if not isinstance(data, str) or not data or len(data) > 4 * 1024 * 1024:
        raise ValueError("invalid report")
    fields = {}
    warnings = 0
    for line in data.splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*(?:\[\])?", key):
            raise ValueError("malformed report")
        if key.endswith("[]"):
            if key == "warning[]":
                if not value or len(value.split("|")) < 4:
                    raise ValueError("malformed warning")
                warnings += 1
        else:
            if key in fields and key in {
                "finish",
                "lynis_version",
                "lynis_tests_done",
                "report_datetime_start",
                "report_datetime_end",
            }:
                raise ValueError("duplicate report field")
            fields[key] = value
    if (
        fields.get("finish") != "true"
        or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", fields.get("lynis_version", ""))
        or not fields.get("lynis_tests_done", "").isdigit()
        or int(fields["lynis_tests_done"]) < 1
    ):
        raise ValueError("incomplete report")
    first = (
        dt.datetime.strptime(fields["report_datetime_start"], "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=dt.timezone.utc)
        .timestamp()
    )
    last = (
        dt.datetime.strptime(fields["report_datetime_end"], "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=dt.timezone.utc)
        .timestamp()
    )
    if not started - 2 <= first <= last <= ended + 2:
        raise ValueError("stale report")
    return warnings


def collect(directory):
    root = Path(directory)
    info = root.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("unsafe report directory")
    report = root / "report.dat"
    log = root / "lynis.log"
    if os.path.lexists(report) or os.path.lexists(log):
        raise ValueError("report path is not fresh")
    started = time.time()
    environment = {**os.environ, "TZ": "UTC", "LC_ALL": "C"}
    result = subprocess.run(
        [
            "lynis",
            "audit",
            "system",
            "--quick",
            "--no-colors",
            "--report-file",
            str(report),
            "--log-file",
            str(log),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=environment,
    )
    ended = time.time()
    with (root / "command-output.txt").open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(
            f"rc={result.returncode}\n# stdout\n{result.stdout}\n# stderr\n{result.stderr}"
        )
    if result.returncode != 0:
        return {
            "collection_success": False,
            "category": "scan-failed",
            "rc": result.returncode,
        }
    descriptor = os.open(report, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o027
            or metadata.st_size > 4 * 1024 * 1024
            or metadata.st_mtime < started - 2
        ):
            raise ValueError("unsafe or stale report")
        warnings = validate_report(stream.read(4 * 1024 * 1024 + 1), started, ended)
    return {
        "collection_success": True,
        "category": "warnings" if warnings else "clean",
        "warnings": warnings,
        "rc": 0,
    }


def main():
    try:
        value = json.loads(sys.stdin.read(4097))
        if (
            not isinstance(value, dict)
            or set(value) != {"directory"}
            or not isinstance(value["directory"], str)
        ):
            raise ValueError("invalid request")
        result = collect(value["directory"])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        result = {"collection_success": False, "category": "collection-unavailable"}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
