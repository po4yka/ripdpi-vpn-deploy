"""Tests for scripts/check-singbox-killswitch.py.

Covers the positive case (valid fixture passes K1-K5) and selected negative
cases (missing auto_route, DNS leak, bad domain_strategy).
"""
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


# ---------------------------------------------------------------------------
# K2 — sniff
# ---------------------------------------------------------------------------

def test_k2_sniff_false_fails(tmp_path):
    bundle = _load_valid()
    tun = next(i for i in bundle["inbounds"] if i["type"] == "tun")
    tun["sniff"] = False
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
