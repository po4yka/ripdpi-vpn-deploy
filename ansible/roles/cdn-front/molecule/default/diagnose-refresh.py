#!/usr/bin/env python3
"""Fixture-only bounded refresh diagnostics, with URL queries and tokens redacted."""

from __future__ import annotations

import json
import re
import subprocess
from urllib.parse import urlsplit

UNIT = "cdn-front-prefix-refresh.service"


def run(argv):
    result = subprocess.run(
        argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10
    )
    return result.returncode, result.stdout[:65536]


def redact(message):
    def url(match):
        try:
            value = urlsplit(match[0])
            if (
                value.query
                or value.fragment
                or value.username is not None
                or value.password is not None
            ):
                return "[redacted URL]"
        except ValueError:
            return "[redacted URL]"
        return match[0]

    message = re.sub(r'https?://[^\s"<>]+', url, message)
    message = re.sub(
        r"(?i)authorization[\"']?\s*[:=][^\r\n]*", "authorization=[redacted]", message
    )
    message = re.sub(
        r"(?i)(token|password|secret)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        message,
    )
    message = re.sub(
        r"-----BEGIN .*?-----.*?-----END .*?-----",
        "[redacted PEM]",
        message,
        flags=re.S,
    )
    return message[:1024]


def main():
    document = {"unit": UNIT, "metadata": {}, "journal": []}
    try:
        rc, raw = run(
            ["systemctl", "show", UNIT, "--property=Result,ExecMainStatus,ExecMainCode"]
        )
        document["metadata_rc"] = rc
        for line in raw.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"Result", "ExecMainStatus", "ExecMainCode"}:
                document["metadata"][key] = redact(value)
        rc, raw = run(
            [
                "journalctl",
                "--unit=" + UNIT,
                "--no-pager",
                "--output=json",
                "--lines=16",
            ]
        )
        document["journal_rc"] = rc
        for line in raw.splitlines()[-16:]:
            try:
                value = json.loads(line).get("MESSAGE")
                if isinstance(value, str):
                    document["journal"].append(redact(value))
            except (ValueError, AttributeError):
                document["journal"].append("unavailable journal record")
    except (OSError, subprocess.SubprocessError):
        document["status"] = "diagnostic-unavailable"
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
