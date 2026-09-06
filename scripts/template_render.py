"""Canonical inputs and Jinja environment for repository template checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = REPO_ROOT / "ansible" / "roles"
GROUP_VARS = REPO_ROOT / "ansible" / "group_vars"
EXAMPLE_FILE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"
SHARED_TEMPLATES_DIR = REPO_ROOT / "ansible" / "templates"
_EXACT_VARIABLE_REFERENCE = re.compile(r"^\s*{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}\s*$")

SYNTHETIC_FACTS = {
    "ansible_user": "deploy",
    "ansible_host": "198.51.100.10",
    "vpn_service_address": "198.51.100.10",
    "ansible_facts": {
        "architecture": "x86_64",
        "os_family": "Debian",
        "distribution": "Debian",
        "distribution_release": "trixie",
        "default_ipv4": {"interface": "eth0"},
        "hostname": "unknown",
    },
    "allowed_ssh_cidrs": ["198.51.100.42/32"],
    "firewall_effective_ssh_ports": [22],
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
    _resolve_exact_variable_references(merged)
    merged.update(SYNTHETIC_FACTS)
    merged.setdefault("xray_arch", "64")
    merged.setdefault("xray_sha256", "0" * 64)
    merged.setdefault("hysteria_arch", "amd64")
    merged.setdefault("hysteria_sha256", "0" * 64)
    merged.setdefault("node_manifest_source_revision", "1" * 40)
    merged.setdefault("node_manifest_deployable_digest", "2" * 64)
    merged.setdefault(
        "p0_reality_shape_template",
        str(SHARED_TEMPLATES_DIR / "p0-reality-shape.json.j2"),
    )
    merged["_observability_agent_service_generation"] = "3" * 64
    merged["_observability_telegram_generation"] = "4" * 64
    merged.setdefault(
        "watchdog_reality_probes",
        [
            {
                "name": "primary",
                "port": 443,
                "p0_reality_shape_input": {
                    "flow_mode": "vision",
                    "finalmask": False,
                },
            },
            {
                "name": "fallback",
                "port": 2053,
                "p0_reality_shape_input": {
                    "flow_mode": "vision",
                    "finalmask": False,
                },
            },
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
                "name": "public-site-http",
                "protocol": "tcp",
                "port": 80,
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
    merged.setdefault("_evidence_firewall_table", "ripdpi_awg_evidence")
    merged.setdefault(
        "_evidence_firewall_policy",
        "/etc/ripdpi/real-vps-awg-nat-firewall.nft",
    )
    merged.setdefault(
        "_evidence_firewall_description",
        "RIPDPI AWG evidence firewall",
    )
    merged.setdefault(
        "_evidence_firewall_loader",
        "/usr/local/libexec/ripdpi-real-vps-awg-nat-firewall",
    )
    merged.setdefault(
        "_evidence_firewall_service",
        "ripdpi-real-vps-awg-nat-firewall.service",
    )
    merged.setdefault(
        "_evidence_awg_toolchain_manifest",
        {
            "toolchainId": "1" * 64,
            "binaries": {
                "amneziawg-go": "2" * 64,
                "awg": "3" * 64,
                "awg-quick": "4" * 64,
            },
        },
    )
    merged.setdefault("item", "server-control")
    merged.update(
        {
            "real_vps_awg_nat_sentinel_public_ipv4": "192.0.2.20",
            "real_vps_awg_nat_sentinel_public_ipv6": "2001:db8::20",
            "real_vps_awg_nat_server_egress_ipv4": "192.0.2.30",
            "real_vps_awg_nat_server_egress_ipv6": "2001:db8::30",
            "real_vps_awg_nat_tcp_echo_address": "192.0.2.10",
            "real_vps_awg_nat_udp_echo_address": "192.0.2.10",
            "real_vps_awg_nat_server_ssh_host": "192.0.2.30",
            "real_vps_awg_nat_server_uplink_interface": "eth0",
            "real_vps_awg_nat_runner_id": "snapshot-runner",
            "real_vps_awg_nat_expected_source_sha": "a" * 40,
            "real_vps_awg_nat_expected_source_archive_sha256": "b" * 64,
            "real_vps_awg_nat_apply_prerequisites": True,
        }
    )
    return merged


def _resolve_exact_variable_references(value: object, context: dict | None = None) -> object:
    """Resolve only whole-value references used by role defaults.

    Repository template snapshots load role defaults as YAML rather than through
    Ansible.  Runtime listener defaults intentionally point at the canonical
    flat group variable, so preserve that relationship without evaluating
    arbitrary Jinja in the lightweight renderer.
    """
    if context is None:
        context = value if isinstance(value, dict) else {}
    if isinstance(value, dict):
        for key, item in list(value.items()):
            value[key] = _resolve_exact_variable_references(item, context)
        return value
    if isinstance(value, list):
        return [_resolve_exact_variable_references(item, context) for item in value]
    if isinstance(value, str):
        match = _EXACT_VARIABLE_REFERENCE.fullmatch(value)
        if match and match.group(1) in context:
            referenced = context[match.group(1)]
            if referenced is not value:
                return _resolve_exact_variable_references(referenced, context)
    return value


def _sha256(value: str, algorithm: str) -> str:
    """The single Ansible hash operation required by credential templates."""
    if algorithm != "sha256" or not isinstance(value, str):
        raise ValueError("template hash requires a string and sha256")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def render_template(path: Path, vars_: dict) -> str:
    """Render one repository template with Ansible-compatible polyfills."""
    env = Environment(
        loader=FileSystemLoader(str(path.parent)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=select_autoescape(),
    )
    env.filters["hash"] = _sha256
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
    env.filters["from_json"] = json.loads

    def lookup(plugin: str, term: str, *, template_vars: dict | None = None) -> str:
        """Render a shared Ansible template used by repository fixtures only."""
        if plugin not in {"template", "ansible.builtin.template"}:
            raise ValueError(f"unsupported template lookup plugin: {plugin}")
        candidate = Path(term)
        if not candidate.is_absolute():
            candidate = SHARED_TEMPLATES_DIR / candidate
        resolved = candidate.resolve(strict=True)
        shared_root = SHARED_TEMPLATES_DIR.resolve()
        if not resolved.is_relative_to(shared_root) or resolved.suffix != ".j2":
            raise ValueError("template lookup is limited to shared Ansible templates")
        context = deepcopy(vars_)
        context.update(template_vars or {})
        return render_template(resolved, context)

    env.globals["lookup"] = lookup
    env.tests["match"] = lambda value, pattern: bool(re.search(pattern, str(value)))
    env.tests["search"] = lambda value, pattern: bool(re.search(pattern, str(value)))
    return env.get_template(path.name).render(**vars_)
