"""Render checks for firewall egress policy modes."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "firewall" / "templates" / "nftables.conf.j2"
CTR = REPO_ROOT / "scripts" / "check-templates-render.py"

_spec = importlib.util.spec_from_file_location("check_templates_render", CTR)
ctr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctr)


def _render(policy: str | None = None, *, vpn: dict | None = None) -> str:
    vars_ = ctr.merge_render_vars()
    if policy is not None:
        vars_["firewall_egress_policy"] = policy
    if vpn is not None:
        vars_["vpn"] = {**vars_["vpn"], **vpn}
    return ctr.render_template(TEMPLATE, vars_)


def _output_chain(rendered: str) -> str:
    marker = "  chain output {"
    start = rendered.index(marker)
    end = rendered.index("  }\n}", start)
    return rendered[start:end]


def test_permissive_is_default_and_preserves_accept_policy():
    assert _output_chain(_render()) == _output_chain(_render("permissive"))
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
        {"name": "hysteria", "protocol": "udp", "port": None, "port_range": "20000-40000"},
    ]
    rendered = ctr.render_template(TEMPLATE, vars_)
    assert "tcp dport 2053 accept" in rendered
    assert "udp dport 51820 accept" in rendered
    assert "udp dport 20000-40000 accept" in rendered
