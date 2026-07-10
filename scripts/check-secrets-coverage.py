#!/usr/bin/env python3
"""Verify that secrets/prod.secrets.example.yaml covers every template variable.

Walks every Jinja2 template under ansible/roles/, extracts the variable
references, drops the ones that are role-internal or globally provided
(group_vars/all.yml, ansible facts), and checks the rest are present in the
example secrets file. Exits non-zero if any variable is missing.

This catches: a new secret added to a role template without updating the
schema. Operators discover the gap at deploy time today; this catches it at
PR time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = REPO_ROOT / "ansible" / "roles"
GROUP_VARS = REPO_ROOT / "ansible" / "group_vars"
EXAMPLE_FILE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"

# Top-level variables provided by Ansible facts, group_vars/all.yml, or other
# roles' defaults. They legitimately appear in templates without being in the
# secrets file.
NON_SECRET_TOPLEVEL = {
    "ansible_user", "ansible_host", "ansible_facts", "ansible_architecture",
    "ansible_os_family", "ansible_distribution", "ansible_distribution_release",
    "ansible_python_interpreter", "ansible_hostname",
    "vpn", "security_controls", "allowed_ssh_cidrs",
    "xray_port", "nginx_xhttp_port", "hysteria_port",
    "xray_install_root", "xray_config_dir", "xray_log_dir",
    "hysteria_install_root", "hysteria_config_dir", "hysteria_log_dir",
    "amneziawg_config_dir", "restic_repo_dir",
    "xray_runtime_user", "xray_runtime_group",
    "xray_install_dir", "xray_etc_dir", "xray_log_path",
    "amneziawg",  # role defaults
    # `subscription` covers the subscription-host role, including the
    # opt-in continuous-mirror sub-keys (subscription.mirror.{enabled,
    # backend,interval,source,ssh_key,ssh_key_path,restic_repo,
    # restic_snapshot_path,restic_password,restic_password_file}). The
    # real secret fields there are mirror.ssh_key and
    # mirror.restic_password; sub-key schema lives in the example file
    # (subscription block) and is documentation-only, since the checker
    # validates only top-level identifiers.
    "monitoring", "subscription", "watchdog", "geodata", "naive",
    # Role-internal compute (set_fact)
    "xray_arch", "xray_sha256", "hysteria_arch", "hysteria_sha256",
    "node_manifest_environment", "node_manifest_provider",
}

# Top-level keys that are real secrets and must exist in the example file
# (sub-keys are not validated — checking schema is best-effort).
EXPECTED_SECRET_TOPLEVEL = {
    "xray", "nginx_xhttp", "hysteria", "amneziawg_secrets",
    "backup", "watchdog_secrets", "naive_secrets",
    "dns_morph_bridge_secrets", "hysteria_realm_secrets", "split_hop_egress_secrets",
}

# Non-greedy capture of {{ ... }} with optional whitespace
JINJA_VAR = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
JINJA_FOR = re.compile(r"\{%-?\s*for\s+(\w+)(?:\s*,\s*(\w+))?\s+in\s+", re.MULTILINE)
JINJA_SET = re.compile(r"\{%-?\s*set\s+(\w+)\s*=", re.MULTILINE)


def extract_toplevel_vars(template_text: str) -> set[str]:
    """Return the set of top-level identifiers referenced in {{ }} expressions,
    minus any names introduced by `{% for X in ... %}` or `{% set X = ... %}`.
    Always-available Jinja2 builtins (loop, none, true/false) are also excluded.
    """
    locals_ = {"loop", "none", "true", "false", "True", "False", "None"}
    for m in JINJA_FOR.finditer(template_text):
        locals_.add(m.group(1))
        if m.group(2):
            locals_.add(m.group(2))
    for m in JINJA_SET.finditer(template_text):
        locals_.add(m.group(1))

    found = set()
    for match in JINJA_VAR.finditer(template_text):
        expr = match.group(1)
        token = re.split(r"[\s.\[|]", expr, maxsplit=1)[0].strip()
        if token and token.replace("_", "").isalnum():
            found.add(token)
    return found - locals_


def main() -> int:
    if not EXAMPLE_FILE.exists():
        print(f"missing: {EXAMPLE_FILE}", file=sys.stderr)
        return 1

    example = yaml.safe_load(EXAMPLE_FILE.read_text()) or {}
    example_keys = set(example.keys())

    # Pre-flight: every expected secret top-level must be in the example
    missing_expected = EXPECTED_SECRET_TOPLEVEL - example_keys
    if missing_expected:
        print(
            "expected secret top-levels missing from example file: "
            f"{', '.join(sorted(missing_expected))}",
            file=sys.stderr,
        )
        return 1

    referenced: dict[str, set[Path]] = {}
    for tpl in ROLES_DIR.rglob("*.j2"):
        for var in extract_toplevel_vars(tpl.read_text()):
            referenced.setdefault(var, set()).add(tpl.relative_to(REPO_ROOT))

    # group_vars/all.yml additionally provides keys
    all_yml = GROUP_VARS / "all.yml"
    group_keys: set[str] = set()
    if all_yml.exists():
        group_keys = set((yaml.safe_load(all_yml.read_text()) or {}).keys())

    # role defaults
    for defaults in ROLES_DIR.rglob("defaults/main.yml"):
        data = yaml.safe_load(defaults.read_text()) or {}
        group_keys.update(data.keys())

    legitimate = NON_SECRET_TOPLEVEL | group_keys | example_keys

    unresolved = {
        var: paths
        for var, paths in referenced.items()
        if var not in legitimate
    }

    if unresolved:
        print("Unresolved template variables (not in example secrets, group_vars, or role defaults):")
        for var, paths in sorted(unresolved.items()):
            print(f"  {var}")
            for p in sorted(paths):
                print(f"    referenced in: {p}")
        return 1

    print(f"OK — {len(referenced)} top-level variables resolved across {sum(len(p) for p in referenced.values())} template references.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
