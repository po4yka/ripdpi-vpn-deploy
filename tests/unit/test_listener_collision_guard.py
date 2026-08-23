"""Tests for the public listener collision guard."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-listener-collisions.py"
MANIFEST_TEMPLATE = REPO_ROOT / "ansible" / "templates" / "listener-manifest.json.j2"
CTR = REPO_ROOT / "scripts" / "check-templates-render.py"

_guard_spec = importlib.util.spec_from_file_location("check_listener_collisions", SCRIPT)
guard = importlib.util.module_from_spec(_guard_spec)
sys.modules[_guard_spec.name] = guard
_guard_spec.loader.exec_module(guard)

_ctr_spec = importlib.util.spec_from_file_location("check_templates_render", CTR)
ctr = importlib.util.module_from_spec(_ctr_spec)
sys.modules[_ctr_spec.name] = ctr
_ctr_spec.loader.exec_module(ctr)


def _entry(role: str, protocol: str, port: int, *, enabled: bool = True) -> dict:
    return {
        "role": role,
        "protocol": protocol,
        "port": port,
        "enabled": enabled,
        "reason": f"{role} listener",
    }


def test_live_default_manifest_has_no_collision():
    vars_ = ctr.merge_render_vars()
    manifest = ctr.render_template(MANIFEST_TEMPLATE, vars_)
    assert guard.check({"listeners": __import__("json").loads(manifest), "allowlist": []}) == []


def test_duplicate_exact_protocol_port_reports_roles():
    findings = guard.check({
        "listeners": [
            _entry("xray", "tcp", 443),
            _entry("naive", "tcp", 443),
        ],
        "allowlist": [],
    })
    assert findings == [
        "tcp/443: duplicate enabled listeners: xray (xray listener), naive (naive listener)"
    ]


def test_duplicate_different_protocol_is_allowed():
    findings = guard.check({
        "listeners": [
            _entry("xray", "tcp", 443),
            _entry("hysteria", "udp", 443),
        ],
        "allowlist": [],
    })
    assert findings == []


def test_disabled_listener_does_not_collide():
    findings = guard.check({
        "listeners": [
            _entry("xray", "tcp", 443),
            _entry("naive", "tcp", 443, enabled=False),
        ],
        "allowlist": [],
    })
    assert findings == []


def test_range_containing_exact_port_reports_both_roles():
    findings = guard.check({
        "listeners": [
            _entry("hysteria", "udp", 443),
            {
                "role": "hysteria",
                "protocol": "udp",
                "range": "400-500",
                "enabled": True,
                "reason": "port hopping",
            },
        ],
        "allowlist": [],
    })
    assert findings == [
        "udp/443: hysteria (hysteria listener) is inside udp/400-500 owned by hysteria (port hopping)"
    ]


def test_allowlist_suppresses_explicit_collision():
    findings = guard.check({
        "listeners": [
            _entry("subscription-host", "tcp", 8444),
            _entry("hysteria-realm", "tcp", 8444),
        ],
        "allowlist": [{"protocol": "tcp", "port": 8444, "reason": "lab only"}],
    })
    assert findings == []


def test_xray_fallback_collision_is_caught_by_manifest_render():
    vars_ = ctr.merge_render_vars()
    vars_["xray_fallback_port"] = 8443
    manifest = ctr.render_template(MANIFEST_TEMPLATE, vars_)
    findings = guard.check({"listeners": __import__("json").loads(manifest), "allowlist": []})
    assert any("tcp/8443" in finding and "xray" in finding and "nginx-xhttp" in finding for finding in findings)


def _range_entry(role: str, protocol: str, start: int, end: int) -> dict:
    return {
        "role": role,
        "protocol": protocol,
        "range": f"{start}-{end}",
        "enabled": True,
        "reason": f"{role} listener",
    }


def test_overlapping_ranges_are_reported():
    findings = guard.check({
        "listeners": [
            _range_entry("hysteria", "udp", 20000, 20100),
            _range_entry("amneziawg-hops", "udp", 20050, 20200),
        ],
        "allowlist": [],
    })
    assert len(findings) == 1
    assert "udp/20000-20100" in findings[0]
    assert "overlaps udp/20050-20200" in findings[0]


def test_disjoint_and_cross_protocol_ranges_pass():
    findings = guard.check({
        "listeners": [
            _range_entry("hysteria", "udp", 20000, 20100),
            _range_entry("amneziawg-hops", "udp", 20101, 20200),
            _range_entry("xray-hops", "tcp", 20000, 20200),
        ],
        "allowlist": [],
    })
    assert findings == []


def test_overlapping_range_allowed_via_allowlist():
    findings = guard.check({
        "listeners": [
            _range_entry("hysteria", "udp", 20000, 20100),
            _range_entry("amneziawg-hops", "udp", 20050, 20200),
        ],
        "allowlist": ["udp/20000-20100"],
    })
    assert findings == []
