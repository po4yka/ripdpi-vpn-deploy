#!/usr/bin/env python3
"""Check that the Xray-core version pin is consistent.

Extracts the "current" pinned version asserted in docs/XRAY-RELEASE-LINE.md
(the heading marked "(current Latest") and compares it to the canonical
in-repo pin at secrets/prod.secrets.example.yaml → xray.version.

Source-of-truth table (from CLAUDE.md):
  Xray version pin | ansible/roles/xray/defaults/main.yml | docs/XRAY-RELEASE-LINE.md
  Actual pin:      | secrets/prod.secrets.example.yaml    | xray.version key

Exits 0 on match, 1 on mismatch or parse failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_LINE_DOC = REPO_ROOT / "docs" / "XRAY-RELEASE-LINE.md"
EXAMPLE_SECRETS = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"

# Matches a version heading that is marked as the current Latest, e.g.:
#   ## v26.3.27 — ~2026-03-27 (current Latest as of 2026-05-10)
# The version token is the first group.
_CURRENT_HEADING_RE = re.compile(
    r"^##\s+(v[\d.]+)[^\n]*\(current Latest",
    re.MULTILINE,
)


def extract_doc_version(text: str) -> str | None:
    """Return the version string from the '(current Latest' heading, or None."""
    m = _CURRENT_HEADING_RE.search(text)
    return m.group(1) if m else None


def extract_pin_version(data: dict) -> str | None:
    """Return xray.version from the parsed example secrets document, or None."""
    xray = data.get("xray")
    if not isinstance(xray, dict):
        return None
    v = xray.get("version")
    return str(v) if v is not None else None


def main() -> int:
    if not RELEASE_LINE_DOC.exists():
        print(f"missing: {RELEASE_LINE_DOC}", file=sys.stderr)
        return 1
    if not EXAMPLE_SECRETS.exists():
        print(f"missing: {EXAMPLE_SECRETS}", file=sys.stderr)
        return 1

    doc_text = RELEASE_LINE_DOC.read_text(encoding="utf-8")
    doc_version = extract_doc_version(doc_text)
    if doc_version is None:
        print(
            f"could not find a '(current Latest' heading in {RELEASE_LINE_DOC}\n"
            "Expected a heading of the form:\n"
            "  ## vX.Y.Z — <date> (current Latest as of <date>)",
            file=sys.stderr,
        )
        return 1

    example_data = yaml.safe_load(EXAMPLE_SECRETS.read_text(encoding="utf-8")) or {}
    pin_version = extract_pin_version(example_data)
    if pin_version is None:
        print(
            f"could not find xray.version in {EXAMPLE_SECRETS}",
            file=sys.stderr,
        )
        return 1

    if doc_version == pin_version:
        print(
            f"OK — Xray-core version pin is consistent: {pin_version}\n"
            f"  docs/XRAY-RELEASE-LINE.md current Latest : {doc_version}\n"
            f"  secrets/prod.secrets.example.yaml xray.version: {pin_version}"
        )
        return 0

    print(
        f"MISMATCH — Xray-core version pin is inconsistent:\n"
        f"  docs/XRAY-RELEASE-LINE.md current Latest : {doc_version}\n"
        f"  secrets/prod.secrets.example.yaml xray.version: {pin_version}\n"
        f"\n"
        f"Update one of the two files so they agree, then re-run this check.\n"
        f"See docs/XRAY-RELEASE-LINE.md 'Production rollout policy' before bumping.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
