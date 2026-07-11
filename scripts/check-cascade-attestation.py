#!/usr/bin/env python3
"""Fail closed unless a cascade candidate ASN attestation is current and measured."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "contract" / "cascade-asn-attestation.schema.json"
CADENCE_DAYS = 7


class AttestationBlocked(ValueError):
    """The candidate is not authorized for provisioning or converge."""


def validate_attestation(path: Path, today: dt.date) -> dict[str, object]:
    if not path.is_file():
        raise AttestationBlocked(f"attestation missing: {path}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttestationBlocked(f"attestation unreadable or malformed: {exc}") from exc

    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - environment failure is blocking
        raise AttestationBlocked("attestation schema validator unavailable") from exc

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(record), key=lambda error: list(error.path))
    if errors:
        detail = "; ".join(error.message for error in errors)
        raise AttestationBlocked(f"attestation schema invalid: {detail}")

    if record["verified_not_brand_inferred"] is not True:
        raise AttestationBlocked("brand-only or inferred attestation is forbidden")

    attested = dt.date.fromisoformat(str(record["attestation_date"]))
    recheck = dt.date.fromisoformat(str(record["next_recheck_date"]))
    if attested > today:
        raise AttestationBlocked("attestation date is in the future")
    if recheck != attested + dt.timedelta(days=CADENCE_DAYS):
        raise AttestationBlocked("next recheck must be exactly seven days after attestation")
    if today >= recheck:
        raise AttestationBlocked(f"attestation stale as of {recheck.isoformat()}")

    return {
        "status": "verified",
        "host_id": record["host_id"],
        "asn_id": record["asn_id"],
        "next_recheck_date": record["next_recheck_date"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attestation", required=True, type=Path)
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate_attestation(args.attestation, args.today)
    except AttestationBlocked as exc:
        print(f"cascade attestation blocked: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
