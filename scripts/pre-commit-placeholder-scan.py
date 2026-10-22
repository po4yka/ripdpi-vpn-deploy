#!/usr/bin/env python3
"""Reject any staged file that carries a REPLACE_WITH_* placeholder where
one shouldn't ship.

Allowed: the schema example (secrets/prod.secrets.example.yaml) and the
generator script that intentionally emits placeholders (scripts/
bootstrap-secrets.sh). Everything else is rejected — placeholders in
templates, role defaults, group_vars, or runbooks usually mean the
operator pasted a real value somewhere else and a stray placeholder
slipped through.

Receives filenames from pre-commit on argv. Exit 1 lists offenders.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWLIST = {
    "secrets/prod.secrets.example.yaml",
    "secrets/README.md",
    "scripts/bootstrap-secrets.sh",
    "scripts/spot-check-secrets.py",
    "scripts/check-certs.sh",
    "scripts/check-secrets-coverage.py",
    "scripts/check-templates-render.py",
    "scripts/pre-commit-placeholder-scan.py",
    "scripts/render-snapshots.py",
    "docs/tutorials/quickstart.md",
    "docs/reference/secrets.md",
}

# Path prefixes whose contents legitimately echo the schema placeholders.
ALLOW_PREFIXES = (
    "tests/snapshot/golden/",
)

NEEDLE = re.compile(r"REPLACE_WITH_[A-Z0-9_]+")


def main(args: list[str]) -> int:
    offenders: list[tuple[str, str]] = []
    for arg in args:
        if arg in ALLOWLIST:
            continue
        if any(arg.startswith(prefix) for prefix in ALLOW_PREFIXES):
            continue
        p = Path(arg)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        m = NEEDLE.search(text)
        if m:
            offenders.append((arg, m.group(0)))

    if not offenders:
        return 0

    print("placeholder-scan: REPLACE_WITH_* leaked into a staged file:", file=sys.stderr)
    for path, hit in offenders:
        print(f"  {path}: {hit}", file=sys.stderr)
    print(file=sys.stderr)
    print("If the placeholder is legitimate (e.g. schema/docs), add the path "
          "to ALLOWLIST in scripts/pre-commit-placeholder-scan.py.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
