#!/usr/bin/env python3
"""Deploy-profile tier guard.

Fails if a role tagged `research` or `exception` in ansible/role-tiers.yml is enabled without its explicit matching allowlist, and forbids both tiers from every family deploy profile. EXCEPTION authorization is accepted only from host_vars. The deploy-time half is in site.yml pre_tasks.

Checks performed:
  1. Manifest integrity — every role under ansible/roles/ has a tier; every tier is one of {core,tactical,research,exception}; every toggle in toggle_role_map resolves to a known role; no manifest role is unknown.
  2. Family profiles — for each file in `family_profiles`, the EFFECTIVE vpn.enable_* values (all.yml merged with the profile, profile wins) must not enable any research or exception role, and the file must not carry an allowlist override for either tier.
  3. Other files — RESEARCH requires a matching same-file allowlist, while EXCEPTION additionally requires the enable and allowlist to live in host_vars. Unknown enable_* toggles fail closed.

Exit 0 clean, 1 on findings, 2 on usage/IO error.

Usage:
  scripts/check-deploy-profile.py            # uses repo layout
  scripts/check-deploy-profile.py --root DIR # alternate repo root (tests)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

VALID_TIERS = {"core", "tactical", "research", "exception"}


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _vpn_enables(data: dict) -> dict:
    """Return the enable_* booleans from a file's `vpn:` mapping."""
    vpn = data.get("vpn") or {}
    return {k: v for k, v in vpn.items() if k.startswith("enable_")}


def _allow_list(data: dict, key: str) -> list[str]:
    val = data.get(key)
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return [str(x) for x in val]
    return []


def check(root: Path) -> list[str]:
    findings: list[str] = []
    ansible = root / "ansible"
    manifest = _load_yaml(ansible / "role-tiers.yml")

    tiers: dict = manifest.get("tiers") or {}
    toggle_map: dict = manifest.get("toggle_role_map") or {}
    family_profiles: list[str] = manifest.get("family_profiles") or []

    if not tiers or not toggle_map or not family_profiles:
        return ["role-tiers.yml is missing one of: tiers, toggle_role_map, "
                "family_profiles"]

    # --- 1. Manifest integrity -------------------------------------------
    roles_dir = ansible / "roles"
    on_disk = {p.name for p in roles_dir.iterdir() if p.is_dir()} if roles_dir.is_dir() else set()
    for role in sorted(on_disk - set(tiers)):
        findings.append(f"manifest: role '{role}' exists on disk but has no tier")
    for role in sorted(set(tiers) - on_disk):
        findings.append(f"manifest: tier lists '{role}' but no such role dir exists")
    for role, tier in sorted(tiers.items()):
        if tier not in VALID_TIERS:
            findings.append(f"manifest: role '{role}' has invalid tier '{tier}'")
    for toggle, role in sorted(toggle_map.items()):
        if role not in tiers:
            findings.append(f"manifest: toggle '{toggle}' maps to unknown role '{role}'")

    research_roles = {r for r, t in tiers.items() if t == "research"}
    exception_roles = {r for r, t in tiers.items() if t == "exception"}
    role_by_toggle = dict(toggle_map)
    known_toggles = set(toggle_map)

    gv = ansible / "group_vars"
    all_yml = _load_yaml(gv / "all.yml")
    base_enables = _vpn_enables(all_yml)

    def enabled_research(effective: dict) -> list[str]:
        out = []
        for toggle, on in effective.items():
            if on is True and role_by_toggle.get(toggle) in research_roles:
                out.append(role_by_toggle[toggle])
        return sorted(set(out))

    def enabled_exception(effective: dict) -> list[str]:
        return sorted({role_by_toggle[toggle] for toggle, on in effective.items() if on is True and role_by_toggle.get(toggle) in exception_roles})

    def unknown_toggles(enables: dict) -> list[str]:
        return sorted(t for t in enables if t not in known_toggles)

    family_set = set(family_profiles)

    # --- 2. Family profiles (effective = all.yml merged with profile) -----
    for rel in family_profiles:
        path = ansible / rel
        if not path.is_file():
            findings.append(f"family profile '{rel}' listed in manifest is missing")
            continue
        data = _load_yaml(path)
        effective = {**base_enables, **_vpn_enables(data)}
        for role in enabled_research(effective):
            findings.append(
                f"{rel}: RESEARCH role '{role}' is enabled in a family profile "
                f"(effective enable true) — research roles must never ship in the "
                f"default P0/P1/P2 deploy")
        for role in enabled_exception(effective):
            findings.append(f"{rel}: EXCEPTION role '{role}' is enabled in a family profile — jurisdiction exceptions never ship in family profiles")
        if "allow_research_roles" in data:
            findings.append(
                f"{rel}: family profile must not set allow_research_roles — the "
                f"override is for lab/pilot hosts only")
        if "allow_exception_roles" in data:
            findings.append(f"{rel}: family profile must not set allow_exception_roles — the override is per-host only")
        for t in unknown_toggles(_vpn_enables(data)):
            findings.append(f"{rel}: unknown enable toggle '{t}' not in toggle_role_map")

    # --- 3. Every other group_vars/ and host_vars/ file -------------------
    scan_files: list[Path] = []
    if gv.is_dir():
        scan_files += sorted(gv.glob("*.yml"))
    host_vars = ansible / "host_vars"
    if host_vars.is_dir():
        scan_files += sorted(host_vars.rglob("*.yml"))

    for path in scan_files:
        rel = str(path.relative_to(ansible))
        if rel in family_set:
            continue  # handled above
        data = _load_yaml(path)
        enables = _vpn_enables(data)
        allowed = set(_allow_list(data, "allow_research_roles"))
        allowed_exception = set(_allow_list(data, "allow_exception_roles"))
        if "allow_exception_roles" in data and not rel.startswith("host_vars/"):
            findings.append(f"{rel}: allow_exception_roles is valid only in host_vars; group-scoped jurisdiction authorization is forbidden")
        for role in enabled_research(enables):
            if role not in allowed:
                findings.append(
                    f"{rel}: RESEARCH role '{role}' is enabled but not listed in "
                    f"allow_research_roles — add it explicitly to opt this host "
                    f"into the research role, or disable it")
        for role in enabled_exception(enables):
            if not rel.startswith("host_vars/"):
                findings.append(f"{rel}: EXCEPTION role '{role}' may be enabled only in host_vars with an exact per-host allowlist")
            elif role not in allowed_exception:
                findings.append(f"{rel}: EXCEPTION role '{role}' is enabled but not listed in allow_exception_roles")
        for t in unknown_toggles(enables):
            findings.append(f"{rel}: unknown enable toggle '{t}' not in toggle_role_map")

    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None,
                    help="repo root (defaults to the repo this script lives in)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    if not (root / "ansible" / "role-tiers.yml").is_file():
        print(f"no ansible/role-tiers.yml under {root}", file=sys.stderr)
        return 2

    findings = check(root)
    if not findings:
        print("OK — no gated role is enabled without its exact allowlist, and family profiles contain no RESEARCH or EXCEPTION roles.")
        return 0
    print(f"deploy-profile tier guard: {len(findings)} finding(s):")
    for f in findings:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
