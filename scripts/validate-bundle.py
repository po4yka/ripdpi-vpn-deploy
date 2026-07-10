#!/usr/bin/env python3
"""Validate a RIPDPI bundle's `ripdpi` object against the formal schema.

The schema (contract/ripdpi-bundle.schema.json) is the cross-repo contract
between this server and the RIPDPI Android client: the server emits the
`ripdpi` object, the client parses it. Today a typo or a dropped field in
emit-bundle.sh surfaces only as a silent handshake/subscription failure on a
real device. This script catches that drift at PR time, and the client repo
runs an equivalent contract test against a vendored copy of the same schema.

Two checks:
  1. jsonschema validation against contract/ripdpi-bundle.schema.json.
  2. cohort_fingerprint correctness — every amneziawg[] entry that carries a
     cohort_fingerprint must match the fingerprint recomputed from its own
     resolved params (catches an emit-side hash bug the schema cannot see).

Input may be a full sing-box bundle (the `ripdpi` key is extracted) or a bare
`ripdpi` object. Default target: contract/ripdpi-bundle.example.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ripdpi_cohort_fingerprint import ORDER, cohort_fingerprint  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "contract" / "ripdpi-bundle.schema.json"
DEFAULT_TARGET = REPO_ROOT / "contract" / "ripdpi-bundle.example.json"


def _extract_ripdpi(doc: dict) -> dict:
    """Return the ripdpi object: doc['ripdpi'] if present, else doc itself."""
    if isinstance(doc, dict) and isinstance(doc.get("ripdpi"), dict):
        return doc["ripdpi"]
    return doc


def _fingerprint_errors(ripdpi: dict) -> list[str]:
    errors: list[str] = []
    for i, entry in enumerate(ripdpi.get("amneziawg") or []):
        if not isinstance(entry, dict) or "cohort_fingerprint" not in entry:
            continue
        params = {k: entry.get(k) for k in ORDER if entry.get(k) is not None}
        expected = cohort_fingerprint(params)
        actual = entry["cohort_fingerprint"]
        if actual != expected:
            errors.append(
                f"amneziawg[{i}].cohort_fingerprint: {actual} "
                f"but params hash to {expected}"
            )
    return errors


def _hysteria_errors(ripdpi: dict) -> list[str]:
    errors: list[str] = []
    for tag, entry in (ripdpi.get("hysteria_extras") or {}).items():
        obfs = entry.get("obfs") if isinstance(entry, dict) else None
        if not isinstance(obfs, dict) or obfs.get("type") != "gecko":
            continue
        minimum = obfs.get("min_packet_size")
        maximum = obfs.get("max_packet_size")
        if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
            errors.append(f"hysteria_extras.{tag}.obfs: min_packet_size exceeds max_packet_size")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "bundle_file",
        nargs="?",
        help="A RIPDPI bundle JSON (or bare ripdpi object). "
        "Defaults to contract/ripdpi-bundle.example.json.",
    )
    args = ap.parse_args()

    target = Path(args.bundle_file) if args.bundle_file else DEFAULT_TARGET
    if not target.is_file():
        print(f"validate-bundle: not a file: {target}", file=sys.stderr)
        return 2

    try:
        import jsonschema
    except ImportError:
        print(
            "validate-bundle: missing 'jsonschema' — `pip install jsonschema`",
            file=sys.stderr,
        )
        return 2

    schema = json.loads(SCHEMA.read_text())
    try:
        doc = json.loads(target.read_text())
    except json.JSONDecodeError as exc:
        print(f"validate-bundle: JSON parse error: {exc}", file=sys.stderr)
        return 1

    ripdpi = _extract_ripdpi(doc)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ripdpi), key=lambda e: list(e.absolute_path))

    fp_errors = _fingerprint_errors(ripdpi)
    hysteria_errors = _hysteria_errors(ripdpi)

    if errors or fp_errors or hysteria_errors:
        print(
            f"validate-bundle: {len(errors) + len(fp_errors) + len(hysteria_errors)} violation(s) in {target}:",
            file=sys.stderr,
        )
        for e in errors:
            loc = ".".join(str(p) for p in e.absolute_path) or "<root>"
            print(f"  {loc}: {e.message}", file=sys.stderr)
        for msg in fp_errors:
            print(f"  {msg}", file=sys.stderr)
        for msg in hysteria_errors:
            print(f"  {msg}", file=sys.stderr)
        return 1

    print(f"validate-bundle: OK — {target} conforms to ripdpi-bundle.schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
