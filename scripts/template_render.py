"""Canonical inputs and Jinja environment for repository template checks."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = REPO_ROOT / "ansible" / "roles"
GROUP_VARS = REPO_ROOT / "ansible" / "group_vars"
EXAMPLE_FILE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"

SYNTHETIC_FACTS = {
    "ansible_user": "deploy",
    "ansible_host": "198.51.100.10",
    "ansible_architecture": "x86_64",
    "ansible_os_family": "Debian",
    "ansible_distribution": "Debian",
    "ansible_distribution_release": "trixie",
    "allowed_ssh_cidrs": ["198.51.100.42/32"],
}


def load_role_defaults() -> dict:
    """Merge role defaults using the precedence used by repository checks."""
    out: dict = {}
    for defaults in ROLES_DIR.rglob("defaults/main.yml"):
        data = yaml.safe_load(defaults.read_text()) or {}
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key].update(value)
            else:
                out[key] = value
    return out


def merge_render_vars() -> dict:
    """Build the canonical synthetic Ansible context used by fast checks."""
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
    merged.setdefault(
        "watchdog_reality_probes",
        [
            {"name": "primary", "port": 443, "flow_mode": "vision", "finalmask": False},
            {"name": "fallback", "port": 2053, "flow_mode": "vision", "finalmask": False},
        ],
    )
    merged.setdefault(
        "public_listener_contract",
        [
            {"name": "xray", "protocol": "tcp", "port": 443, "port_range": None},
            {
                "name": "xray-fallback",
                "protocol": "tcp",
                "port": 2053,
                "port_range": None,
            },
            {
                "name": "nginx-xhttp",
                "protocol": "tcp",
                "port": 8443,
                "port_range": None,
            },
            {
                "name": "hysteria",
                "protocol": "udp",
                "port": 443,
                "port_range": None,
            },
            {
                "name": "amneziawg",
                "protocol": "udp",
                "port": 51820,
                "port_range": None,
            },
        ],
    )
    return merged


def render_template(path: Path, vars_: dict) -> str:
    """Render one repository template with Ansible-compatible polyfills."""
    env = Environment(
        loader=FileSystemLoader(str(path.parent)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=select_autoescape(),
    )
    env.filters["to_json"] = lambda value: json.dumps(value)
    env.filters["quote"] = lambda value: "'" + str(value).replace("'", "'\\''") + "'"
    env.filters["dirname"] = lambda value: os.path.dirname(str(value))
    env.filters["basename"] = lambda value: os.path.basename(str(value))
    env.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(
        pattern, replacement, str(value)
    )
    env.filters["regex_search"] = lambda value, pattern: (
        re.search(pattern, str(value)).group(0)
        if re.search(pattern, str(value))
        else ""
    )
    env.filters["extract"] = lambda key, container: container[key]
    env.tests["match"] = lambda value, pattern: bool(re.search(pattern, str(value)))
    env.tests["search"] = lambda value, pattern: bool(re.search(pattern, str(value)))
    return env.get_template(path.name).render(**vars_)
