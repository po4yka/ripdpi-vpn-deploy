"""Behavior tests for the strict full-device sing-box kill-switch gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SCRIPT = REPO_ROOT / "scripts" / "check-singbox-killswitch.py"
VALID_FIXTURE = FIXTURES / "singbox-killswitch-valid.json"


def _run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
    )


def _run_dict(bundle: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    p = tmp_path / "bundle.json"
    p.write_text(json.dumps(bundle))
    return _run(p)


def _load_valid() -> dict:
    return json.loads(VALID_FIXTURE.read_text())


# ---------------------------------------------------------------------------
# Positive case
# ---------------------------------------------------------------------------

def test_valid_fixture_passes_all_checks():
    """The positive-case fixture must exit 0 and print the OK line."""
    result = _run(VALID_FIXTURE)
    assert result.returncode == 0, (
        f"expected exit 0 for valid fixture:\n{result.stdout}\n{result.stderr}"
    )
    assert "OK" in result.stdout
    assert "strict full-device dual-stack kill-switch verified" in result.stdout


# ---------------------------------------------------------------------------
# K1 — TUN auto_route / strict_route
# ---------------------------------------------------------------------------

def test_k1_missing_auto_route_fails(tmp_path):
    bundle = _load_valid()
    tun = next(i for i in bundle["inbounds"] if i["type"] == "tun")
    tun["auto_route"] = False
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K1" in result.stdout


def test_k1_missing_strict_route_fails(tmp_path):
    bundle = _load_valid()
    tun = next(i for i in bundle["inbounds"] if i["type"] == "tun")
    tun["strict_route"] = False
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K1" in result.stdout


def test_k1_no_tun_inbound_fails(tmp_path):
    bundle = _load_valid()
    bundle["inbounds"] = []
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K1" in result.stdout


def test_k1_legacy_tun_address_fields_fail(tmp_path):
    """Removed inet4/inet6 fields cannot certify a supported client bundle."""
    bundle = _load_valid()
    tun = next(i for i in bundle["inbounds"] if i["type"] == "tun")
    del tun["address"]
    tun["inet4_address"] = "172.19.0.1/30"
    tun["inet6_address"] = "fdfe:dcba:9876::1/126"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K1" in result.stdout
    assert "address" in result.stdout


def test_k1_ipv4_only_tun_address_fails(tmp_path):
    bundle = _load_valid()
    tun = next(i for i in bundle["inbounds"] if i["type"] == "tun")
    tun["address"] = ["172.19.0.1/30"]
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "no IPv6 prefix" in result.stdout


def test_k1_ipv6_only_tun_address_fails(tmp_path):
    bundle = _load_valid()
    tun = next(i for i in bundle["inbounds"] if i["type"] == "tun")
    tun["address"] = ["fdfe:dcba:9876::1/126"]
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "no IPv4 prefix" in result.stdout


def test_k1_malformed_tun_address_fails(tmp_path):
    bundle = _load_valid()
    tun = next(i for i in bundle["inbounds"] if i["type"] == "tun")
    tun["address"] = ["172.19.0.1/30", "not-an-ipv6-prefix"]
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "invalid prefix" in result.stdout


# ---------------------------------------------------------------------------
# K2 — sniff
# ---------------------------------------------------------------------------

def test_k2_missing_sniff_action_fails(tmp_path):
    bundle = _load_valid()
    bundle["route"]["rules"] = [
        rule for rule in bundle["route"]["rules"]
        if rule.get("action") != "sniff"
    ]
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K2" in result.stdout


# ---------------------------------------------------------------------------
# K3 — route.final
# ---------------------------------------------------------------------------

def test_k3_route_final_direct_fails(tmp_path):
    bundle = _load_valid()
    bundle["route"]["final"] = "direct"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K3" in result.stdout


def test_k3_route_final_select_passes(tmp_path):
    bundle = _load_valid()
    bundle["route"]["final"] = "select"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 0


def test_k3_route_final_auto_passes(tmp_path):
    bundle = _load_valid()
    bundle["route"]["final"] = "auto"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 0


def test_k3_route_rule_to_direct_type_alias_fails(tmp_path):
    bundle = _load_valid()
    direct = next(ob for ob in bundle["outbounds"] if ob["type"] == "direct")
    direct["tag"] = "clear-egress"
    bundle["route"]["rules"].insert(
        0,
        {
            "package_name": ["example.app"],
            "action": "route",
            "outbound": "clear-egress",
        },
    )
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K3" in result.stdout
    assert "route.rules[0]" in result.stdout


def test_k3_private_network_direct_rule_fails(tmp_path):
    bundle = _load_valid()
    bundle["route"]["rules"].insert(
        0,
        {"ip_is_private": True, "action": "route", "outbound": "direct"},
    )
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "route.rules[0]" in result.stdout


def test_k3_selector_that_can_choose_direct_fails(tmp_path):
    bundle = _load_valid()
    selector = next(ob for ob in bundle["outbounds"] if ob["tag"] == "select")
    selector["outbounds"].append("direct")
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "route.final 'select' can resolve to direct egress" in result.stdout


def test_k3_bypass_action_fails_without_outbound(tmp_path):
    bundle = _load_valid()
    bundle["route"]["rules"].insert(
        0,
        {"package_name": ["example.app"], "action": "bypass"},
    )
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "uses bypass" in result.stdout


def test_k3_undefined_outbound_reference_fails_closed(tmp_path):
    bundle = _load_valid()
    bundle["route"]["rules"].insert(
        0,
        {"package_name": ["example.app"], "action": "route", "outbound": "missing"},
    )
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "undefined" in result.stdout


def test_k3_outbound_graph_cycle_fails_closed(tmp_path):
    bundle = _load_valid()
    bundle["outbounds"].extend(
        [
            {"type": "selector", "tag": "cycle-a", "outbounds": ["cycle-b"]},
            {"type": "selector", "tag": "cycle-b", "outbounds": ["cycle-a"]},
        ]
    )
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "outbound graph cycle" in result.stdout


# ---------------------------------------------------------------------------
# K4 — DNS remote detour
# ---------------------------------------------------------------------------

def test_k4_dns_remote_detour_direct_fails(tmp_path):
    bundle = _load_valid()
    for srv in bundle["dns"]["servers"]:
        if srv.get("tag") == "remote":
            srv["detour"] = "direct"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K4" in result.stdout


def test_k4_dns_remote_detour_select_passes(tmp_path):
    bundle = _load_valid()
    # Fixture already has detour=select; just confirm it passes.
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 0


def test_k4_missing_dns_servers_fails(tmp_path):
    bundle = _load_valid()
    bundle["dns"]["servers"] = []
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K4: dns.servers must contain" in result.stdout


def test_k4_non_remote_dns_server_direct_detour_fails(tmp_path):
    bundle = _load_valid()
    bundle["dns"]["servers"].append(
        {"tag": "local", "address": "local", "detour": "direct"}
    )
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K4" in result.stdout


# ---------------------------------------------------------------------------
# K5 — domain_strategy
# ---------------------------------------------------------------------------

def test_k5_ipv6_only_domain_strategy_fails(tmp_path):
    bundle = _load_valid()
    bundle["outbounds"][0]["domain_strategy"] = "ipv6_only"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K5" in result.stdout


def test_k5_prefer_ipv6_domain_strategy_fails(tmp_path):
    bundle = _load_valid()
    bundle["outbounds"][0]["domain_strategy"] = "prefer_ipv6"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 1
    assert "K5" in result.stdout


def test_k5_prefer_ipv4_domain_strategy_passes(tmp_path):
    bundle = _load_valid()
    bundle["outbounds"][0]["domain_strategy"] = "prefer_ipv4"
    result = _run_dict(bundle, tmp_path)
    assert result.returncode == 0
