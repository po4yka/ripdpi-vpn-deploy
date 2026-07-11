#!/usr/bin/env python3
"""Fail closed unless a cascade leg has a fresh authenticated completion."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "contract" / "cascade-leg-health.schema.json"
MAX_AGE = dt.timedelta(minutes=10)


class LegHealthBlocked(ValueError):
    """The cascade leg is not healthy enough for registration or converge."""


def _timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise LegHealthBlocked("checked_at must include a UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def validate_leg_health(path: Path, now: dt.datetime) -> dict[str, str]:
    if not path.is_file():
        raise LegHealthBlocked(f"per-leg health record missing: {path}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegHealthBlocked(f"per-leg health record unreadable or malformed: {exc}") from exc

    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - dependency loss is blocking
        raise LegHealthBlocked("per-leg health schema validator unavailable") from exc

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(record), key=lambda error: list(error.path))
    if errors:
        raise LegHealthBlocked("per-leg health schema invalid: " + "; ".join(error.message for error in errors))

    checked_at = _timestamp(str(record["checked_at"]))
    now = now.astimezone(dt.timezone.utc)
    if checked_at > now:
        raise LegHealthBlocked("per-leg health record is from the future")
    if now - checked_at > MAX_AGE:
        raise LegHealthBlocked("per-leg health record is stale")
    if record["status"] != "healthy":
        raise LegHealthBlocked(f"per-leg status is {record['status']}")
    if record["protocol_completed"] is not True:
        raise LegHealthBlocked("authenticated protocol completion did not succeed")
    if record["ingress_local_control"] != "healthy":
        raise LegHealthBlocked("ingress-local control is not healthy")
    if record["consecutive_failures"] != 0:
        raise LegHealthBlocked("healthy record must reset the failure streak")

    return {"host_id": str(record["host_id"]), "leg_id": str(record["leg_id"]), "status": "healthy"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-record", required=True, type=Path)
    parser.add_argument("--now", type=_timestamp, default=dt.datetime.now(dt.timezone.utc))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate_leg_health(args.health_record, args.now)
    except LegHealthBlocked as exc:
        print(f"cascade per-leg health blocked: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
