#!/usr/bin/env python3
"""Validate an anonymous client field report against its contract.

Two checks:
  1. jsonschema validation against contract/client-field-report.schema.json.
  2. Every bucket's latency_ms_histogram sums to its attempts, and
     window.start_utc is a real calendar instant; the schema cannot express
     either rule.

Diagnostics name the failed constraint and the bucket index, never a value,
because a rejected report may carry the identifying data the contract forbids.
Default target: contract/client-field-report.golden.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "contract" / "client-field-report.schema.json"
DEFAULT_TARGET = REPO_ROOT / "contract" / "client-field-report.golden.json"


def semantic_errors(report: dict) -> list[str]:
    errors = [f"buckets[{index}].latency_ms_histogram: counts must sum to attempts"
              for index, bucket in enumerate(report["buckets"])
              if sum(bucket["latency_ms_histogram"]) != bucket["attempts"]]
    try:
        datetime.fromisoformat(report["window"]["start_utc"])
    except ValueError:
        errors.append("window.start_utc: requires a valid calendar instant")
    return errors


def violations(report: object, validator) -> list[str]:
    """Return every contract violation of one parsed report; empty means valid.

    The field-report ingest on the subscription host calls this function, so
    the CLI and the ingest enforce one contract.
    """
    errors = [f"schema: {error.validator} constraint failed at /{'/'.join(map(str, error.absolute_path))}"
              for error in sorted(validator.iter_errors(report), key=lambda e: list(map(str, e.absolute_path)))]
    return errors or semantic_errors(report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_file", nargs="?", help="Field report JSON. Defaults to the golden report.")
    args = parser.parse_args()
    target = Path(args.report_file) if args.report_file else DEFAULT_TARGET
    if not target.is_file():
        print(f"validate-field-report: not a file: {target}", file=sys.stderr)
        return 2
    try:
        import jsonschema
    except ImportError:
        print("validate-field-report: missing 'jsonschema'", file=sys.stderr)
        return 2
    try:
        report = json.loads(target.read_text())
    except (ValueError, RecursionError):
        print("validate-field-report: malformed JSON input", file=sys.stderr)
        return 1

    errors = violations(report, jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())))
    if errors:
        print(f"validate-field-report: {len(errors)} violation(s) in {target}:", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        return 1
    print(f"validate-field-report: OK — {target} conforms to client-field-report.schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
