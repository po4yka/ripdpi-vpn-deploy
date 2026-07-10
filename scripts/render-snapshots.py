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
import json
import os
import re as _re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, UndefinedError, select_autoescape

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = REPO_ROOT / "ansible" / "roles"
GROUP_VARS = REPO_ROOT / "ansible" / "group_vars"
EXAMPLE_FILE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"
GOLDEN_DIR = REPO_ROOT / "tests" / "snapshot" / "golden"

SYNTHETIC_FACTS = {
    "ansible_user": "deploy",
    "ansible_architecture": "x86_64",
    "ansible_os_family": "Debian",
    "ansible_distribution": "Debian",
    "ansible_distribution_release": "trixie",
    "allowed_ssh_cidrs": ["198.51.100.42/32"],
}


def load_role_defaults() -> dict:
    out: dict = {}
    for defaults in ROLES_DIR.rglob("defaults/main.yml"):
        data = yaml.safe_load(defaults.read_text()) or {}
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    return out


def merge_render_vars() -> dict:
    merged: dict = {}
    merged.update(load_role_defaults())
    all_yml = GROUP_VARS / "all.yml"
    if all_yml.exists():
        merged.update(yaml.safe_load(all_yml.read_text()) or {})
    if EXAMPLE_FILE.exists():
        merged.update(yaml.safe_load(EXAMPLE_FILE.read_text()) or {})
    merged.update(SYNTHETIC_FACTS)
    merged.setdefault("xray_arch", "64")
    merged.setdefault("xray_sha256", "0" * 64)
    merged.setdefault("hysteria_arch", "amd64")
    merged.setdefault("hysteria_sha256", "0" * 64)
    merged.setdefault("public_listener_contract", [
        {"name": "xray", "protocol": "tcp", "port": 443, "port_range": None},
        {"name": "xray-fallback", "protocol": "tcp", "port": 2053, "port_range": None},
        {"name": "nginx-xhttp", "protocol": "tcp", "port": 8443, "port_range": None},
        {"name": "hysteria", "protocol": "udp", "port": 443, "port_range": None},
        {"name": "amneziawg", "protocol": "udp", "port": 51820, "port_range": None},
    ])
    return merged


def render_template(path: Path, vars_: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(path.parent)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=select_autoescape(),
    )
    env.filters["to_json"] = lambda v: json.dumps(v)
    env.filters["quote"] = lambda v: "'" + str(v).replace("'", "'\\''") + "'"
    env.filters["dirname"] = lambda v: os.path.dirname(str(v))
    env.filters["basename"] = lambda v: os.path.basename(str(v))
    env.filters["regex_replace"] = lambda v, p, r: _re.sub(p, r, str(v))
    env.filters["regex_search"] = lambda v, p: (
        _re.search(p, str(v)).group(0) if _re.search(p, str(v)) else ""
    )
    env.filters["extract"] = lambda key, container: container[key]
    env.tests["match"] = lambda v, p: bool(_re.search(p, str(v)))
    env.tests["search"] = lambda v, p: bool(_re.search(p, str(v)))
    return env.get_template(path.name).render(**vars_)


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
