#!/usr/bin/env python3
"""Check that the Xray-core version pin is consistent.

Extracts the "current" pinned version asserted in docs/reference/xray-release-line.md
(the heading marked "(repository pin)") and compares it to the canonical
in-repo pin at secrets/prod.secrets.example.yaml → xray.version. The pin must
also be in the xray-runtime production allowlist that deploys enforce.

Source-of-truth table (from CLAUDE.md):
  Xray version pin | ansible/roles/xray/defaults/main.yml | docs/reference/xray-release-line.md
  Actual pin:      | secrets/prod.secrets.example.yaml    | xray.version key

Exits 0 on match, 1 on mismatch or parse failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_LINE_DOC = REPO_ROOT / "docs/reference/xray-release-line.md"
EXAMPLE_PIN_FILE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"
PRODUCTION_ALLOWLIST_FILE = REPO_ROOT / "ansible/roles/xray-runtime/defaults/main.yml"

# Matches a version heading that is marked as the repository pin, e.g.:
#   ## v26.3.27 — ~2026-03-27 (repository pin)
# The version token is the first group.
_CURRENT_HEADING_RE = re.compile(
    r"^##\s+(v[\d.]+)[^\n]*\(repository pin\)",
    re.MULTILINE,
)


def extract_doc_version(text: str) -> str | None:
    """Return the version string from the '(repository pin)' heading, or None."""
    matches = _CURRENT_HEADING_RE.findall(text)
    return matches[0] if len(matches) == 1 else None


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
    if not EXAMPLE_PIN_FILE.exists():
        print(f"missing: {EXAMPLE_PIN_FILE}", file=sys.stderr)
        return 1

    doc_text = RELEASE_LINE_DOC.read_text(encoding="utf-8")
    doc_version = extract_doc_version(doc_text)
    if doc_version is None:
        print(
            f"expected exactly one '(repository pin)' heading in {RELEASE_LINE_DOC}\n"
            "Expected a heading of the form:\n"
            "  ## vX.Y.Z — <date> (repository pin)",
            file=sys.stderr,
        )
        return 1

    example_data = yaml.safe_load(EXAMPLE_PIN_FILE.read_text(encoding="utf-8")) or {}
    pin_version = extract_pin_version(example_data)
    if pin_version is None:
        print(
            f"could not find xray.version in {EXAMPLE_PIN_FILE}",
            file=sys.stderr,
        )
        return 1

    allowlist = (yaml.safe_load(PRODUCTION_ALLOWLIST_FILE.read_text(encoding="utf-8")) or {}).get(
        "xray_runtime_production_versions")
    if not isinstance(allowlist, list) or doc_version not in allowlist:
        print(
            f"repository pin {doc_version} is missing from xray_runtime_production_versions "
            f"in {PRODUCTION_ALLOWLIST_FILE}",
            file=sys.stderr,
        )
        return 1

    if doc_version == pin_version:
        print(
            f"OK — Xray-core version pin is consistent: {pin_version}\n"
            f"  docs/reference/xray-release-line.md repository pin : {doc_version}\n"
            f"  secrets/prod.secrets.example.yaml xray.version: {pin_version}"
        )
        return 0

    print(
        f"MISMATCH — Xray-core version pin is inconsistent:\n"
        f"  docs/reference/xray-release-line.md repository pin : {doc_version}\n"
        f"  secrets/prod.secrets.example.yaml xray.version: {pin_version}\n"
        f"\n"
        f"Update one of the two files so they agree, then re-run this check.\n"
        f"See docs/reference/xray-release-line.md 'Production rollout policy' before bumping.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
