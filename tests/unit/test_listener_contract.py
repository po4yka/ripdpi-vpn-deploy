"""Tests for the provider-edge to runtime listener contract guard."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-listener-contract.py"
MANIFEST_TEMPLATE = REPO_ROOT / "ansible" / "templates" / "listener-manifest.json.j2"
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"

spec = importlib.util.spec_from_file_location("listener_contract", SCRIPT)
contract = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contract
spec.loader.exec_module(contract)

renderer_spec = importlib.util.spec_from_file_location("listener_renderer", RENDERER)
renderer = importlib.util.module_from_spec(renderer_spec)
sys.modules[renderer_spec.name] = renderer
renderer_spec.loader.exec_module(renderer)


def _expected(name: str, protocol: str, port: int) -> dict:
    return {"name": name, "protocol": protocol, "port": port, "port_range": None}


def _actual(role: str, protocol: str, port: int, *, enabled: bool = True) -> dict:
    return {"role": role, "protocol": protocol, "port": port, "enabled": enabled}


def test_matching_contract_passes() -> None:
    assert contract.check({
        "expected": [_expected("xray", "tcp", 443), _expected("amneziawg", "udp", 51820)],
        "actual": [_actual("xray", "tcp", 443), _actual("amneziawg", "udp", 51820)],
    }) == []


def test_missing_provider_edge_listener_fails_closed() -> None:
    findings = contract.check({
        "expected": [_expected("xray", "tcp", 443)],
        "actual": [_actual("xray", "tcp", 443), _actual("xray-fallback", "tcp", 2053)],
    })
    assert "runtime manifest lacks provider contract listener" in findings[0]
    assert "xray-fallback" in findings[0]


def test_disabled_runtime_listener_does_not_require_edge_rule() -> None:
    assert contract.check({
        "expected": [_expected("xray", "tcp", 443)],
        "actual": [_actual("xray", "tcp", 443), _actual("honeypot", "tcp", 4443, enabled=False)],
    }) == []


def test_port_range_is_compared_as_a_contract_value() -> None:
    assert contract.check({
        "expected": [{"name": "hysteria", "protocol": "udp", "port": None, "port_range": "20000-40000"}],
        "actual": [{"role": "hysteria", "protocol": "udp", "range": "20000-40000", "enabled": True}],
    }) == []


def test_default_runtime_manifest_matches_default_provider_contract() -> None:
    variables = renderer.merge_render_vars()
    actual = json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))
    expected = [
        _expected("xray", "tcp", 443),
        _expected("xray-fallback", "tcp", 2053),
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 8443),
        _expected("hysteria", "udp", 443),
        _expected("amneziawg", "udp", 51820),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_awg_evidence_server_listener_is_explicit_and_additive() -> None:
    variables = renderer.merge_render_vars()
    variables["real_vps_awg_nat_mode"] = "server"
    variables["real_vps_awg_nat_listen_port"] = 51920
    actual = json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))
    expected = [
        _expected("xray", "tcp", 443),
        _expected("xray-fallback", "tcp", 2053),
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 8443),
        _expected("hysteria", "udp", 443),
        _expected("amneziawg", "udp", 51820),
        _expected("awg-evidence", "udp", 51920),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_awg_evidence_echo_listeners_are_explicit_and_additive() -> None:
    variables = renderer.merge_render_vars()
    variables["real_vps_awg_nat_mode"] = "echo"
    variables["real_vps_awg_nat_tcp_echo_port"] = 10001
    variables["real_vps_awg_nat_udp_echo_port"] = 10002
    actual = json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))
    expected = [
        _expected("xray", "tcp", 443),
        _expected("xray-fallback", "tcp", 2053),
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 8443),
        _expected("hysteria", "udp", 443),
        _expected("amneziawg", "udp", 51820),
        _expected("awg-evidence-echo-tcp", "tcp", 10001),
        _expected("awg-evidence-echo-udp", "udp", 10002),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def _profile_manifest(name: str) -> list[dict]:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load((REPO_ROOT / "ansible" / "group_vars" / name).read_text())
    variables.update(profile)
    return json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))


def test_p0_minimal_listener_surface_is_reality_only() -> None:
    actual = _profile_manifest("vpn-p0-minimal.yml")
    expected = [_expected("xray", "tcp", 443), _expected("xray-fallback", "tcp", 2053)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p0_self_steal_keeps_the_same_public_listener_surface() -> None:
    actual = _profile_manifest("vpn-p0-self-steal.yml")
    expected = [_expected("xray", "tcp", 443), _expected("xray-fallback", "tcp", 2053)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p1_web_listener_surface_is_normal_http_and_https() -> None:
    actual = _profile_manifest("vpn-p1-web.yml")
    expected = [
        _expected("public-site-http", "tcp", 80),
        _expected("nginx-xhttp", "tcp", 443),
        # Subscription delivery co-located on the p1 web node (v1 default,
        # SUBSCRIPTION-HOST-SEPARATION.md) — the only non-web TCP listener.
        _expected("subscription-host", "tcp", 8444),
    ]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p2_udp_listener_surface_has_no_public_tcp_service() -> None:
    actual = _profile_manifest("vpn-p2-udp.yml")
    expected = [_expected("hysteria", "udp", 443), _expected("amneziawg", "udp", 51820)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_listener_contract_pre_tasks_run_during_tagged_deploys() -> None:
    play = yaml.safe_load((REPO_ROOT / "ansible" / "playbooks" / "site.yml").read_text())[0]
    required = {
        "Build effective public listener manifest",
        "Decode provider listener contract from rendered inventory",
        "Guard — provider edge and runtime listener contracts agree",
        "Guard — block public listener collisions before convergence",
    }
    tasks = {task["name"]: task for task in play["pre_tasks"] if task["name"] in required}
    assert set(tasks) == required
    assert all("always" in task.get("tags", []) for task in tasks.values())


def test_upcloud_dns_replies_select_primary_not_secondary_ipv4(tmp_path: Path) -> None:
    # Native Terraform mocks share computed IPs across repeated NIC blocks.
    # Evaluate the actual selector with distinct addresses, without a provider.
    source = (REPO_ROOT / "terraform/providers/upcloud/firewall.tf").read_text()
    selectors = re.findall(r"(?m)^\s*primary_public_ipv4\s*=\s*([^\n]+)$", source)
    assert len(selectors) == 1, "Expected exactly one primary IPv4 selector"
    selector = selectors[0]
    reference = "upcloud_server.vpn.network_interface"
    assert selector.count(reference) == 1
    destinations = re.findall(
        r"(?m)^\s*destination_address_(?:start|end)\s*=\s*(\S+)\s*$", source,
    )
    assert destinations == ["local.primary_public_ipv4", "local.primary_public_ipv4"]

    expressions = []
    expected = []
    for primary, secondary, utility_first in [
        ("203.0.113.10", "203.0.113.20", True),
        ("198.51.100.10", "198.51.100.20", False),
    ]:
        public = [
            {"type": "public", "ip_address_family": "IPv4", "ip_address": primary},
            {"type": "public", "ip_address_family": "IPv4", "ip_address": secondary},
        ]
        other = [
            {"type": "utility", "ip_address_family": "IPv4", "ip_address": "10.0.0.10"},
            {"type": "public", "ip_address_family": "IPv6", "ip_address": "2001:db8::10"},
        ]
        interfaces = other + public if utility_first else public + other
        expressions.append(selector.replace(reference, json.dumps(interfaces)))
        expected.append(primary)

    terraform = shutil.which("terraform")
    assert terraform is not None, "Terraform is required for the offline selector regression"
    result = subprocess.run(
        [terraform, "console", "-no-color"],
        input="jsonencode([" + ",".join(expressions) + "])\n",
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env={key: value for key, value in os.environ.items() if not key.startswith("TF_")},
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(json.loads(result.stdout)) == expected
