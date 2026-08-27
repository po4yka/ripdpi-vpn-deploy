#!/usr/bin/env python3
"""Render every Jinja2 template and compare against committed goldens.

The rendered output of `ansible/roles/*/templates/*.j2` is a sensitive
artifact — REALITY shortIds, nginx rate-limit zones, nftables rulesets,
the xray inbound-routing list, etc. all sit inside these files. The
existing `check-templates-render.py` proves the templates parse and
emit valid JSON / nginx config, but it cannot catch a quiet semantic
drift (e.g. a refactor that swaps `xray.target` for `vpn.xray_target`
and still renders).

This script renders every template against the canonical fixture
inputs (the committed schema + group_vars + role defaults) and diffs
the bytes against `tests/snapshot/golden/<rel-path>`. A divergence
means either:

  * the operator intentionally changed a template / variable / default
    and needs to refresh the goldens — `python3 scripts/render-snapshots.py --update`
  * or the change was accidental and review surfaces it before merge

Two modes:
  python3 scripts/render-snapshots.py            # check (CI / pre-commit)
  python3 scripts/render-snapshots.py --update   # rewrite goldens
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from jinja2 import UndefinedError

from template_render import REPO_ROOT, ROLES_DIR, merge_render_vars, render_template

GOLDEN_DIR = REPO_ROOT / "tests" / "snapshot" / "golden"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--update",
        action="store_true",
        help="rewrite the golden snapshots instead of comparing",
    )
    args = ap.parse_args()

    vars_ = merge_render_vars()
    diffs: list[str] = []
    updated: list[Path] = []
    rendered = 0

    for tpl in sorted(ROLES_DIR.rglob("*.j2")):
        rel = tpl.relative_to(ROLES_DIR)
        try:
            output = render_template(tpl, vars_)
        except UndefinedError as exc:
            diffs.append(f"{rel}: undefined — {exc}")
            continue
        except Exception as exc:
            diffs.append(f"{rel}: render error — {exc}")
            continue
        rendered += 1
        golden = GOLDEN_DIR / rel
        if args.update:
            golden.parent.mkdir(parents=True, exist_ok=True)
            if not golden.exists() or golden.read_text() != output:
                golden.write_text(output)
                updated.append(rel)
            continue
        if not golden.exists():
            diffs.append(
                f"{rel}: no golden — run `make snapshot-update` to create it"
            )
            continue
        committed = golden.read_text()
        if committed != output:
            udiff = "".join(
                difflib.unified_diff(
                    committed.splitlines(keepends=True),
                    output.splitlines(keepends=True),
                    fromfile=f"golden/{rel}",
                    tofile=f"rendered/{rel}",
                )
            )
            diffs.append(f"{rel}: drift\n{udiff}")

    if args.update:
        if updated:
            print(f"updated {len(updated)} golden(s):")
            for rel in updated:
                print(f"  {rel}")
        else:
            print("no goldens needed updating.")
        # Detect goldens left over for templates that no longer exist.
        stale = []
        if GOLDEN_DIR.exists():
            for fp in GOLDEN_DIR.rglob("*"):
                if fp.is_file():
                    src = ROLES_DIR / fp.relative_to(GOLDEN_DIR)
                    if not src.exists():
                        fp.unlink()
                        stale.append(fp.relative_to(GOLDEN_DIR))
        if stale:
            print(f"removed {len(stale)} orphan golden(s):")
            for rel in stale:
                print(f"  {rel}")
        if diffs:
            print(
                f"{len(diffs)} template(s) failed to render; their goldens were NOT refreshed:",
                file=sys.stderr,
            )
            for error in diffs:
                print(f"  {error}", file=sys.stderr)
            return 1
        return 0

    if diffs:
        print("Snapshot drift detected:", file=sys.stderr)
        for d in diffs:
            print(f"  {d}", file=sys.stderr)
        print(
            "\nIf the change is intended, refresh with: make snapshot-update",
            file=sys.stderr,
        )
        return 1
    print(f"OK — {rendered} templates match golden snapshots.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
