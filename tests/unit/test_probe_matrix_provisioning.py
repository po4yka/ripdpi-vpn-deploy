"""Static contract tests for probe target and split-hop provisioning."""

from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_research_roles_are_tiered_and_wired_behind_explicit_toggles() -> None:
    manifest = yaml.safe_load((ROOT / "ansible/role-tiers.yml").read_text())
    assert manifest["tiers"]["probe-matrix-target"] == "research"
    assert manifest["tiers"]["split-hop-ingress"] == "research"
    assert manifest["toggle_role_map"]["enable_probe_matrix_target"] == "probe-matrix-target"
    assert manifest["toggle_role_map"]["enable_split_hop_ingress"] == "split-hop-ingress"
    site = (ROOT / "ansible/playbooks/site.yml").read_text()
    assert "role: probe-matrix-target" in site
    assert "role: split-hop-ingress" in site


def test_listener_manifest_exposes_five_target_ports_and_ingress_wireguard() -> None:
    manifest = (ROOT / "ansible/templates/listener-manifest.json.j2").read_text()
    for name in ("mtproto", "xhttp_vless", "xhttp_trojan", "tcp_trojan", "tls_non_443"):
        assert f"probe_matrix_target.ports.{name}" in manifest
    assert "split_hop_ingress.listen_port" in manifest


def test_ingress_marks_only_new_original_direction_runtime_connections() -> None:
    policy = (ROOT / "ansible/roles/split-hop-ingress/templates/policy.nft.j2").read_text()
    assert "ct state new ct direction original" in policy
    assert "ct mark" in policy and "meta mark set ct mark" in policy
    config = (ROOT / "ansible/roles/split-hop-ingress/templates/split-hop-ingress.conf.j2").read_text()
    assert "Endpoint" not in config
    assert "PersistentKeepalive" not in config


def test_split_hop_egress_forwarding_is_allowed_by_firewall() -> None:
    firewall = (ROOT / "ansible/roles/firewall/templates/nftables.conf.j2").read_text()
    assert "split_hop_egress.wg_interface" in firewall
    assert "ct state new iifname" in firewall


def test_profile_emitter_writes_atomic_owner_only_driver_profile(tmp_path: Path) -> None:
    variables = tmp_path / "vars.yml"
    variables.write_text(yaml.safe_dump({"probe_matrix_target": {
        "server_name": "probe.example", "ports": {"mtproto": 10443, "xhttp_vless": 11443, "xhttp_trojan": 12443, "tcp_trojan": 13443, "tls_non_443": 14443},
        "paths": {"xhttp_vless": "/vless", "xhttp_trojan": "/trojan"},
    }}))
    secrets = tmp_path / "secrets.yml"
    secrets.write_text(yaml.safe_dump({
        "xray": {"version": "v26.3.27"},
        "probe_matrix_target_secrets": {"mtproto_secret": "a" * 32, "vless_uuid": "00000000-0000-4000-8000-000000000001", "xhttp_trojan_password": "b" * 24, "tcp_trojan_password": "c" * 24, "mtg_version": "v2.2.8"},
    }))
    output = tmp_path / "profile.json"
    result = subprocess.run([
        "python3", str(ROOT / "scripts/emit-probe-matrix-profile.py"), "--target-id", "generic-dual", "--endpoint", "203.0.113.9", "--vars-file", str(variables), "--secrets-file", str(secrets), "--output", str(output),
    ], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    document = json.loads(output.read_text())
    assert document["target_id"] == "generic-dual"
    assert document["expected_mtg_version"] == "v2.2.8"
    assert document["expected_mtproto_helper_version"] == "gotd-v0.160.0"
    assert document["protocols"]["mtproto"]["secret"] == "a" * 32
