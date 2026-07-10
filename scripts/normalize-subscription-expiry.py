#!/usr/bin/env python3
"""Normalize subscription expiry input to an RFC 3339 UTC instant."""

from __future__ import annotations

import argparse
import datetime as dt
import re

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def normalize_expiry(raw: str) -> str:
    value = raw.strip()
    try:
        if DATE_PATTERN.fullmatch(value):
            parsed_date = dt.date.fromisoformat(value)
            parsed = dt.datetime.combine(parsed_date, dt.time.min, tzinfo=dt.timezone.utc)
        else:
            if not RFC3339_PATTERN.fullmatch(value):
                raise ValueError("timestamp is not RFC 3339")
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            parsed = parsed.astimezone(dt.timezone.utc)
    except ValueError as exc:
        raise ValueError(
            "invalid subscription expiry: expected YYYY-MM-DD or RFC 3339 timestamp with offset"
        ) from exc
    return parsed.isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("expiry")
    args = parser.parse_args()
    try:
        print(normalize_expiry(args.expiry))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
