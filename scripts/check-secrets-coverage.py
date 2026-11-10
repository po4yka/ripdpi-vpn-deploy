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

import sys
from pathlib import Path

from jinja2 import Environment, meta
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = REPO_ROOT / "ansible" / "roles"
GROUP_VARS = REPO_ROOT / "ansible" / "group_vars"
EXAMPLE_FILE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"

# Top-level variables provided by Ansible facts, group_vars/all.yml, or other
# roles' defaults. They legitimately appear in templates without being in the
# secrets file.
NON_SECRET_TOPLEVEL = {
    "item",  # Ansible loop item; heartbeat service/timer kind
    "ansible_user",
    "ansible_host",
    "vpn_service_address",
    "ansible_facts",
    "ansible_distribution",
    "ansible_python_interpreter",
    "vpn",
    "security_controls",
    "allowed_ssh_cidrs",
    "xray_port",
    "nginx_xhttp_port",
    "hysteria_port",
    "xray_install_root",
    "xray_config_dir",
    "xray_log_dir",
    "hysteria_install_root",
    "hysteria_config_dir",
    "hysteria_log_dir",
    "amneziawg_config_dir",
    "restic_repo_dir",
    "xray_runtime_user",
    "xray_runtime_group",
    "xray_runtime_binary",  # verified immutable release fact
    "xray_install_dir",
    "xray_etc_dir",
    "xray_log_path",
    "amneziawg",  # role defaults
    # `subscription` covers the subscription-host role, including the
    # opt-in continuous-mirror sub-keys (subscription.mirror.{enabled,
    # backend,interval,source,ssh_key,ssh_key_path,restic_repo,
    # restic_snapshot_path,restic_password,restic_password_file}). The
    # real secret fields there are mirror.ssh_key and
    # mirror.restic_password; sub-key schema lives in the example file
    # (subscription block) and is documentation-only, since the checker
    # validates only top-level identifiers.
    "monitoring",
    "monitoring_node_exporter_endpoint",  # normalized literal endpoint from private-address admission
    "subscription",
    "watchdog",
    "geodata",
    "destination_filter",  # pinned deny sources for the transport-egress normalizer
    "naive",
    # Private transport topology is built from admitted secrets and actual UIDs.
    "transport_egress_normalizer_config",
    "transport_egress_input_config",
    "transport_egress_policy_config_data",
    "transport_egress_runtime_binary",
    "transport_egress_frontend_units",
    "transport_egress_normalizer_uid",
    "_transport_egress_backend",
    "_transport_egress_backend_name",
    "_transport_egress_gateway_unit_list",
    "_transport_egress_forbidden",
    # Role-internal compute (set_fact)
    "watchdog_awg_interfaces",  # normalized interface names only, without peer credentials
    "_inst",  # admitted private per-loop AWG instance; never emitted into environment files
    # Validated provider address and interface from honeypot secondary-address tasks.
    "_honeypot_secondary_address",
    "_honeypot_secondary_interface",
    "_honeypot_secondary_unit",
    "xray_arch",
    "xray_sha256",
    "hysteria_arch",
    "hysteria_sha256",
    "node_manifest_environment",
    "node_manifest_provider",
    "node_manifest_host_class",
    "node_manifest_source_revision",
    "node_manifest_deployable_digest",
    # Task-local path to the shared P0 shape renderer.
    "p0_reality_shape_template",
    # real-vps-awg-nat template context assembled by role tasks/pre_tasks
    "_evidence_awg_toolchain_manifest",
    "_evidence_firewall_description",
    "_evidence_firewall_loader",
    "_evidence_firewall_policy",
    "_evidence_firewall_service",
    "_evidence_firewall_table",
    "_firewall_tailnet_initial_fragment",
    # observability-control-plane immutable generation facts
    "_observability_alert_rules_generation",
    "_observability_rules_generation",
    "_observability_telegram_generation",
    "_observability_kuma_tls_generation",
    "public_listener_contract",
    # role-local facts and inventory values read only inside statements or
    # parenthesized expressions
    "_awg_instances",
    "_baseline_mptcp_sysctl",
    "_filter",
    "_honeypot_secondary_required",
    "_observability_agent_self_steal_certificate",
    "_package_updates_effective_enabled",
    "hysteria_masquerade_hosts",
    "nginx_aliases",
    "nginx_fallback_hsts",
    "server_ipv6",
    "vpn_subscription_only",
    "_",
    "_all_clients",
    "_cohorts",
    "_firewall_effective_check_mode",
    "_firewall_tailnet_ssh_sets_was_absent",
    "_multi",
    "_network_exposure_plan",
    "firewall_awg_uplink_interface",
    "firewall_effective_ssh_ports",
    "public_ifaces",
    "public_listener_manifest",
    "structured_data",
    "watchdog_reality_probes",
    "xray_tcp_ports",
    # Ansible built-ins
    "ansible_check_mode",
    "inventory_hostname",
    "lookup",
}

# Top-level keys that are real secrets and must exist in the example file
# (sub-keys are not validated — checking schema is best-effort).
EXPECTED_SECRET_TOPLEVEL = {
    "xray",
    "nginx_xhttp",
    "hysteria",
    "amneziawg_secrets",
    "backup",
    "watchdog_secrets",
    "naive_secrets",
    "dns_morph_bridge_secrets",
    "hysteria_realm_secrets",
    "split_hop_egress_secrets",
    "split_hop_ingress_secrets",
    "probe_matrix_target_secrets",
    "snell_secrets",
    "real_vps_awg_nat_secrets",
    "observability_secrets",
    "observability_kuma_secrets",
    "observability_deadman_secrets",
    # Operator-side per-device configuration registry (issuance options,
    # lifecycle state, AWG private-key recovery copies). Not consumed by
    # Ansible templates but required in every secrets document so
    # new-client.sh / issue-sub-token.sh can persist issuance parameters.
    "client_registry",
}

# Non-greedy capture of {{ ... }} with optional whitespace
class _AnyName(dict):
    """Ansible filters and tests are unknown here; only variable names matter."""

    def __contains__(self, name: object) -> bool:
        return True

    def get(self, name, default=None):  # the compiler resolves names with get()
        return super().get(name, str)


# Parsing only; nothing is rendered. Every filter and test name is accepted so
# the analysis reaches expressions that use Ansible-only filters.
JINJA_ENVIRONMENT = Environment(autoescape=True, extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])
JINJA_ENVIRONMENT.filters = _AnyName(JINJA_ENVIRONMENT.filters)
JINJA_ENVIRONMENT.tests = _AnyName(JINJA_ENVIRONMENT.tests)


def extract_toplevel_vars(template_text: str) -> set[str]:
    """Return every context-supplied identifier the template reads.

    The Jinja AST covers output expressions and statements alike, and it
    resolves loop, set, macro and import scopes and raw blocks itself.
    """
    return set(meta.find_undeclared_variables(JINJA_ENVIRONMENT.parse(template_text)))


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
        var: paths for var, paths in referenced.items() if var not in legitimate
    }

    if unresolved:
        print(
            "Unresolved template variables (not in example secrets, group_vars, or role defaults):"
        )
        for var, paths in sorted(unresolved.items()):
            print(f"  {var}")
            for p in sorted(paths):
                print(f"    referenced in: {p}")
        return 1

    print(
        f"OK — {len(referenced)} top-level variables resolved across {sum(len(p) for p in referenced.values())} template references."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
