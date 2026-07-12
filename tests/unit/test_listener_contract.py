"""Tests for the provider-edge to runtime listener contract guard."""
from __future__ import annotations

import importlib.util
import json
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


def _profile_manifest(name: str) -> list[dict]:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load((REPO_ROOT / "ansible" / "group_vars" / name).read_text())
    variables.update(profile)
    return json.loads(renderer.render_template(MANIFEST_TEMPLATE, variables))


def test_p0_minimal_listener_surface_is_reality_only() -> None:
    actual = _profile_manifest("vpn-p0-minimal.yml")
    expected = [_expected("xray", "tcp", 443), _expected("xray-fallback", "tcp", 2053)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p1_web_listener_surface_is_normal_http_and_https() -> None:
    actual = _profile_manifest("vpn-p1-web.yml")
    expected = [_expected("public-site-http", "tcp", 80), _expected("nginx-xhttp", "tcp", 443)]
    assert contract.check({"expected": expected, "actual": actual}) == []


def test_p2_udp_listener_surface_has_no_public_tcp_service() -> None:
    actual = _profile_manifest("vpn-p2-udp.yml")
    expected = [_expected("hysteria", "udp", 443), _expected("amneziawg", "udp", 51820)]
    assert contract.check({"expected": expected, "actual": actual}) == []
