"""Render checks for firewall egress policy modes."""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    REPO_ROOT / "ansible" / "roles" / "firewall" / "templates" / "nftables.conf.j2"
)
AWG_TEMPLATE = (
    REPO_ROOT / "ansible" / "roles" / "amneziawg" / "templates" / "awg0.conf.j2"
)
CTR = REPO_ROOT / "scripts" / "check-templates-render.py"
EVIDENCE_ROLE = REPO_ROOT / "ansible" / "roles" / "real-vps-awg-nat"
PUBLIC_ADDRESS_VALIDATOR = EVIDENCE_ROLE / "files" / "validate-public-addresses.py"

_spec = importlib.util.spec_from_file_location("check_templates_render", CTR)
ctr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctr)


def _render(
    policy: str | None = None,
    *,
    vpn: dict | None = None,
    ssh_port: int = 22,
) -> str:
    vars_ = ctr.merge_render_vars()
    vars_["firewall_effective_ssh_ports"] = [ssh_port]
    if policy is not None:
        vars_["firewall_egress_policy"] = policy
    if vpn is not None:
        vars_["vpn"] = {**vars_["vpn"], **vpn}
    return ctr.render_template(TEMPLATE, vars_)


def test_firewall_uses_effective_custom_ssh_port() -> None:
    rendered = _render(ssh_port=2222)

    assert "tcp dport 2222 ip saddr" in rendered
    assert "tcp dport 22 ip saddr" not in rendered


def test_firewall_discovers_ssh_port_before_rendering() -> None:
    tasks = (REPO_ROOT / "ansible" / "roles" / "firewall" / "tasks" / "main.yml").read_text()

    assert "cmd: sshd -T" in tasks
    assert "firewall_effective_ssh_ports" in tasks
    assert tasks.index("Read effective sshd configuration") < tasks.index(
        "Render nftables config"
    )


def _output_chain(rendered: str) -> str:
    marker = "  chain output {"
    start = rendered.index(marker)
    end = rendered.index("  }\n}", start)
    return rendered[start:end]


def test_permissive_is_default_and_preserves_accept_policy():
    assert _output_chain(_render()) == _output_chain(_render("permissive"))
    assert "Additive forwarding contract:" not in _render()
    chain = _output_chain(_render("permissive"))
    assert "policy accept;" in chain
    assert "egress-observe" not in chain
    assert "counter drop" not in chain


def test_logged_keeps_accept_policy_and_uses_counters_not_logs():
    chain = _output_chain(_render("logged"))
    assert "policy accept;" in chain
    assert "egress-observe-unexpected-tcp" in chain
    assert "egress-observe-unexpected-udp" in chain
    assert " log " not in chain


def test_strict_drops_by_default_and_allows_baseline_infra():
    chain = _output_chain(
        _render(
            "strict",
            vpn={
                "enable_xray_reality": False,
                "enable_hysteria": False,
                "enable_naive": False,
                "enable_warp_outbound": False,
            },
        )
    )
    assert "policy drop;" in chain
    assert 'oif "lo" accept' in chain
    assert "ct state established,related accept" in chain
    assert "udp dport 53 accept" in chain
    assert "tcp dport 53 accept" in chain
    assert "udp dport 123 accept" in chain
    assert "tcp dport { 80, 443 } accept" in chain
    assert "\n    tcp accept\n" not in chain
    assert "\n    udp accept\n" not in chain


def test_strict_keeps_transport_egress_when_proxy_profiles_are_enabled():
    chain = _output_chain(_render("strict", vpn={"enable_xray_reality": True}))
    assert "policy drop;" in chain
    assert "\n    tcp accept\n" in chain
    assert "\n    udp accept\n" in chain


def test_strict_allows_warp_control_ports_when_warp_is_enabled():
    chain = _output_chain(_render("strict", vpn={"enable_warp_outbound": True}))
    assert "udp dport { 2408, 500, 4500 } accept" in chain


def test_public_listener_contract_drives_nftables_rules():
    vars_ = ctr.merge_render_vars()
    vars_["public_listener_contract"] = [
        {"name": "xray-fallback", "protocol": "tcp", "port": 2053, "port_range": None},
        {"name": "amneziawg", "protocol": "udp", "port": 51820, "port_range": None},
        {
            "name": "hysteria",
            "protocol": "udp",
            "port": None,
            "port_range": "20000-40000",
        },
    ]
    rendered = ctr.render_template(TEMPLATE, vars_)
    assert "tcp dport 2053 accept" in rendered
    assert "udp dport 51820 accept" in rendered
    assert "udp dport 20000-40000 accept" in rendered


def test_firewall_replaces_only_its_owned_tables():
    rendered = _render()

    assert "flush ruleset" not in rendered
    assert "destroy table inet filter" in rendered
    assert "destroy table inet nat" in rendered
    assert "destroy table inet split_hop_egress" not in rendered


def test_awg_forwarding_is_default_drop_with_only_uplink_egress():
    vars_ = ctr.merge_render_vars()
    vars_["vpn"] = {**vars_["vpn"], "enable_amneziawg": True}
    vars_["firewall_awg_uplink_interface"] = "eth0"
    rendered = ctr.render_template(TEMPLATE, vars_)
    forward = rendered[
        rendered.index("  chain forward {") : rendered.index("  chain output {")
    ]
    assert "policy drop;" in forward
    assert "ct state established,related accept" in forward
    assert 'ct state new iifname "awg0" oifname "eth0" accept' in forward
    assert "policy accept;" not in forward
    assert 'iifname "awg0" accept' not in forward
    assert 'oifname "awg0" accept' not in forward


def test_additive_forward_contract_stays_inside_canonical_drop_chain():
    vars_ = ctr.merge_render_vars()
    vars_["firewall_forward_interface_contract"] = [
        {
            "name": "real-vps-awg-evidence",
            "input_interface": "awg-evidence0",
            "output_interface": "eth1",
        }
    ]
    rendered = ctr.render_template(TEMPLATE, vars_)
    forward = rendered[
        rendered.index("  chain forward {") : rendered.index("  chain output {")
    ]

    assert "policy drop;" in forward
    assert 'ct state new iifname "awg-evidence0" oifname "eth1" accept' in forward
    assert 'iifname "awg-evidence0" accept' not in forward


def test_firewall_exclusively_owns_awg_masquerade_rule():
    vars_ = ctr.merge_render_vars()
    vars_["vpn"] = {**vars_["vpn"], "enable_amneziawg": True}
    rendered = ctr.render_template(TEMPLATE, vars_)

    assert (
        'iifname "awg0" oifname != "awg0" counter masquerade comment "awg-nat-awg0"'
        in rendered
    )
    assert 'counter comment "awg-nat-awg0" masquerade' not in rendered
    awg_config = AWG_TEMPLATE.read_text()
    assert "PostUp" not in awg_config
    assert "PostDown" not in awg_config


def test_evidence_server_requires_preinstalled_canonical_firewall():
    tasks = (EVIDENCE_ROLE / "tasks/server.yml").read_text()
    nft = (EVIDENCE_ROLE / "templates/server.nft.j2").read_text()
    private_vars = (EVIDENCE_ROLE / "templates/server-private-vars.yml.j2").read_text()

    assert "public_listener_contract" in tasks
    assert "firewall_forward_interface_contract" in tasks
    assert "nft, list, chain, inet, filter, input" in tasks
    assert "nft, list, chain, inet, filter, forward" in tasks
    assert "standard\n      firewall deployment" in tasks
    assert "_real_vps_awg_nat_public_listener_matches | length == 1" in tasks
    assert "_real_vps_awg_nat_forward_contract_matches | length == 1" in tasks
    assert "_real_vps_awg_nat_live_input.rc == 0" in tasks
    assert "_real_vps_awg_nat_live_forward.rc == 0" in tasks
    assert "udp dport " in tasks and "ct state new iifname" in tasks
    assert tasks.index(
        "Require canonical input and forwarding source contracts"
    ) < tasks.index("Install exact-source server apply prerequisites")
    assert tasks.index(
        "Require live canonical input and forwarding rules"
    ) < tasks.index("Enable dedicated evidence interface")
    assert "include_role" not in tasks
    assert "name: firewall" not in tasks
    assert "enable_amneziawg" not in tasks
    assert "firewall_forward_interface_contract:" in private_vars
    assert "chain input" not in nft
    assert "chain forward" not in nft
    assert "chain postrouting" in nft
    assert 'oifname "{{ real_vps_awg_nat_server_uplink_interface }}"' in nft
    assert 'oifname != "{{ real_vps_awg_nat_interface }}"' not in nft


def test_evidence_firewall_loader_validates_atomic_replacement_batch():
    loader = (EVIDENCE_ROLE / "templates/firewall-loader.j2").read_text()

    assert "destroy table inet {{ _evidence_firewall_table }}" in loader
    assert "nft delete table" not in loader
    assert loader.index('nft -c -f "$batch"') < loader.index('nft -f "$batch"')


def test_echo_policy_rate_limits_both_sources_and_protocols():
    nft = (EVIDENCE_ROLE / "templates/echo.nft.j2").read_text()
    service = (EVIDENCE_ROLE / "templates/echo.service.j2").read_text()

    for source in (
        "real_vps_awg_nat_sentinel_public_ipv4",
        "real_vps_awg_nat_server_egress_ipv4",
    ):
        assert (
            f"ip saddr {{{{ {source} }}}} tcp dport "
            "{{ real_vps_awg_nat_tcp_echo_port }} limit rate 50/second"
        ) in nft
        assert (
            f"ip saddr {{{{ {source} }}}} udp dport "
            "{{ real_vps_awg_nat_udp_echo_port }} limit rate 50/second"
        ) in nft
        assert f"--allow-address {{{{ {source} }}}}" in service


def test_echo_requires_preinstalled_canonical_tcp_and_udp_listeners():
    tasks = (EVIDENCE_ROLE / "tasks/echo.yml").read_text()

    assert "public_listener_contract" in tasks
    assert "_real_vps_awg_nat_tcp_echo_listener_matches | length == 1" in tasks
    assert "_real_vps_awg_nat_udp_echo_listener_matches | length == 1" in tasks
    assert "nft, list, chain, inet, filter, input" in tasks
    assert "_real_vps_awg_nat_live_echo_input.rc == 0" in tasks
    assert "tcp dport " in tasks and "udp dport " in tasks
    assert tasks.index(
        "Require canonical TCP and UDP echo listener contracts"
    ) < tasks.index("Install dual-protocol echo producer")
    assert tasks.index(
        "Require live canonical TCP and UDP echo accept rules"
    ) < tasks.index("Enable persistent echo firewall")
    assert tasks.index(
        "Require live canonical TCP and UDP echo accept rules"
    ) < tasks.index("Enable dual-protocol echo")
    assert "include_role" not in tasks
    assert "name: firewall" not in tasks


def _validate_public_addresses(
    payload: dict[str, list[str]],
) -> subprocess.CompletedProcess:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return subprocess.run(
        [sys.executable, str(PUBLIC_ADDRESS_VALIDATOR), encoded],
        text=True,
        capture_output=True,
        check=False,
    )


def test_echo_public_address_validator_accepts_public_v4_and_v6():
    result = _validate_public_addresses(
        {
            "required_ipv4": ["8.8.8.8", "1.1.1.1"],
            "optional_ipv6": ["2606:4700:4700::1111", "2001:4860:4860::8888"],
        }
    )

    assert result.returncode == 0, result.stderr


def test_echo_public_address_validator_fails_closed():
    invalid_payloads = (
        {"required_ipv4": ["10.0.0.1", "1.1.1.1"], "optional_ipv6": []},
        {"required_ipv4": ["8.8.8.8", "1.1.1.1"], "optional_ipv6": ["fd00::1"]},
        {"required_ipv4": ["not-an-ip", "1.1.1.1"], "optional_ipv6": []},
        {"required_ipv4": ["", "1.1.1.1"], "optional_ipv6": []},
    )

    for payload in invalid_payloads:
        result = _validate_public_addresses(payload)
        assert result.returncode != 0
        assert "public address contract:" in result.stderr
