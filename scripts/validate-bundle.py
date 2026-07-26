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
import base64
import binascii
import copy
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ripdpi_cohort_fingerprint import ORDER, cohort_fingerprint  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "contract" / "ripdpi-bundle.schema.json"
DEFAULT_TARGET = REPO_ROOT / "contract" / "ripdpi-bundle.example.json"


def _read_runtime_materialized(path: Path) -> str:
    """Read a private bundle only through an owner-controlled path."""
    target = path.absolute()
    owner = os.geteuid()
    for parent in reversed(target.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("runtime bundle path contains a symlink")
        writable = info.st_mode & 0o022
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if info.st_uid not in {0, owner} or (writable and not sticky_root):
            raise ValueError("runtime bundle path ancestry is not owner-controlled")

    before = target.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("runtime bundle must be a regular non-symlink file")
    if before.st_uid != owner or stat.S_IMODE(before.st_mode) != 0o600:
        raise ValueError("runtime bundle must be owned by the current user with mode 0600")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("runtime bundle changed while it was being opened")
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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


def _normalize_runtime_materialized(ripdpi: dict) -> tuple[dict, list[str]]:
    """Return a redacted in-memory copy of a locally materialized bundle."""
    normalized = copy.deepcopy(ripdpi)
    errors: list[str] = []
    entries = normalized.get("amneziawg")
    if not isinstance(entries, list):
        return normalized, errors

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        has_key = "private_key" in entry
        has_placeholder = "private_key_placeholder" in entry
        if not has_key or has_placeholder:
            errors.append(
                f"amneziawg[{i}]: runtime materialization requires private_key "
                "and forbids private_key_placeholder"
            )
            entry.pop("private_key", None)
            continue

        private_key = entry.pop("private_key")
        if not isinstance(private_key, str):
            errors.append(f"amneziawg[{i}].private_key: must be canonical base64")
            continue
        try:
            decoded = base64.b64decode(private_key, validate=True)
        except (binascii.Error, ValueError):
            errors.append(f"amneziawg[{i}].private_key: must be canonical base64")
            continue
        if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != private_key:
            errors.append(
                f"amneziawg[{i}].private_key: must encode exactly 32 bytes "
                "using canonical base64"
            )
            continue
        entry["private_key_placeholder"] = True

    return normalized, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "bundle_file",
        nargs="?",
        help="A RIPDPI bundle JSON (or bare ripdpi object). "
        "Defaults to contract/ripdpi-bundle.example.json.",
    )
    ap.add_argument(
        "--runtime-materialized",
        action="store_true",
        help="Validate a local runtime bundle containing inline AmneziaWG "
        "private keys after redacting them in memory. The default remains the "
        "strict distribution contract.",
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

    try:
        source = (
            _read_runtime_materialized(target)
            if args.runtime_materialized
            else target.read_text()
        )
    except (OSError, ValueError) as exc:
        print(f"validate-bundle: unsafe runtime input: {exc}", file=sys.stderr)
        return 2

    schema = json.loads(SCHEMA.read_text())
    try:
        doc = json.loads(source)
    except json.JSONDecodeError as exc:
        print(f"validate-bundle: JSON parse error: {exc}", file=sys.stderr)
        return 1

    ripdpi = _extract_ripdpi(doc)
    runtime_errors: list[str] = []
    if args.runtime_materialized:
        ripdpi, runtime_errors = _normalize_runtime_materialized(ripdpi)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ripdpi), key=lambda e: list(e.absolute_path))

    fp_errors = _fingerprint_errors(ripdpi)

    if errors or fp_errors or runtime_errors:
        print(
            "validate-bundle: "
            f"{len(errors) + len(fp_errors) + len(runtime_errors)} violation(s) "
            f"in {target}:",
            file=sys.stderr,
        )
        for e in errors:
            loc = ".".join(str(p) for p in e.absolute_path) or "<root>"
            print(f"  {loc}: {e.message}", file=sys.stderr)
        for msg in fp_errors:
            print(f"  {msg}", file=sys.stderr)
        for msg in runtime_errors:
            print(f"  {msg}", file=sys.stderr)
        return 1

    print(f"validate-bundle: OK — {target} conforms to ripdpi-bundle.schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
