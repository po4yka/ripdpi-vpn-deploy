"""Tests for the node capability manifest template."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CTR = REPO_ROOT / "scripts" / "check-templates-render.py"
LISTENER_TEMPLATE = REPO_ROOT / "ansible" / "templates" / "listener-manifest.json.j2"
NODE_TEMPLATE = REPO_ROOT / "ansible" / "roles" / "node_manifest" / "templates" / "manifest.json.j2"

_ctr_spec = importlib.util.spec_from_file_location("check_templates_render", CTR)
ctr = importlib.util.module_from_spec(_ctr_spec)
sys.modules[_ctr_spec.name] = ctr
_ctr_spec.loader.exec_module(ctr)


def _render_manifest(vars_: dict | None = None) -> dict:
    merged = ctr.merge_render_vars()
    merged.update({
        "inventory_hostname": "vpn-test",
        "ansible_hostname": "vpn-test",
        "ansible_date_time": {"iso8601": "2026-06-16T00:00:00Z"},
        "node_manifest_environment": "prod",
        "node_manifest_provider": "upcloud",
    })
    if vars_:
        merged.update(vars_)
    merged["public_listener_manifest"] = json.loads(ctr.render_template(LISTENER_TEMPLATE, merged))
    return json.loads(ctr.render_template(NODE_TEMPLATE, merged))


def test_default_manifest_contract():
    manifest = _render_manifest()
    assert manifest["schema_version"] == 1
    assert manifest["hostname"] == "vpn-test"
    assert manifest["environment"] == "prod"
    assert manifest["provider"] == "upcloud"
    assert set(manifest) == {
        "schema_version",
        "generated_at",
        "hostname",
        "environment",
        "provider",
        "enabled_transports",
        "public_listeners",
        "security_controls",
        "recovery",
    }
    assert "xray-reality" in manifest["enabled_transports"]
    assert "nginx-xhttp" in manifest["enabled_transports"]
    assert "hysteria2" in manifest["enabled_transports"]
    assert "amneziawg" in manifest["enabled_transports"]
    assert {"proto": "tcp", "port": 443, "role": "xray"} in manifest["public_listeners"]
    assert manifest["security_controls"]["ssh_strict"] is True
    assert manifest["security_controls"]["firewall_egress_policy"] == "permissive"
    assert manifest["recovery"]["backup"]["enabled"] is True
    assert "/etc/xray/config.json.prev" in manifest["recovery"]["rollback_artifacts"]


def test_subscription_only_manifest_skips_transport_roles():
    manifest = _render_manifest({
        "vpn_subscription_only": True,
        "vpn": {
            "enable_xray_reality": True,
            "enable_nginx_xhttp": True,
            "enable_hysteria": True,
            "enable_amneziawg": True,
            "enable_subscription_host": False,
        },
    })
    assert manifest["enabled_transports"] == ["subscription-host"]
    assert manifest["public_listeners"] == [{"proto": "tcp", "port": 8444, "role": "subscription-host"}]


def test_manifest_does_not_emit_obvious_secret_material():
    text = json.dumps(_render_manifest(), sort_keys=True).lower()
    forbidden = [
        "uuid",
        "shortid",
        "private_key",
        "privatekey",
        "password",
        "token",
        "subscription_url",
        "cert_pem",
        "client",
        "peer",
    ]
    assert not any(word in text for word in forbidden)
