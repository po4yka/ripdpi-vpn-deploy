"""Rendered Xray termination contract for the disabled cascade adapter."""

from __future__ import annotations

import json
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from template_render import merge_render_vars, render_template  # noqa: E402


TEMPLATE = ROOT / "ansible/roles/xray/templates/config.json.j2"
PROXY_PASSWORD = "test_proxy_password_abcdefghijklmnopqrstuvwxyz0123456789"


def _render_cascade_xray() -> dict:
    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_cascade_ingress": True}
    variables["cascade_secrets"] = {**variables["cascade_secrets"], "classifier_proxy_password": PROXY_PASSWORD}
    return json.loads(render_template(TEMPLATE, variables))


def test_cascade_tcp_default_uses_loopback_classifier_outbound() -> None:
    config = _render_cascade_xray()
    outbound = next(item for item in config["outbounds"] if item["tag"] == "cascade-classifier")
    default = config["routing"]["rules"][-1]

    assert outbound == {
        "tag": "cascade-classifier",
        "protocol": "socks",
        "targetStrategy": "ForceIPv4",
        "settings": {
            "servers": [
                {
                    "address": "127.0.0.1",
                    "port": 10808,
                    "users": [{"user": "cascade-xray", "pass": PROXY_PASSWORD}],
                }
            ]
        },
        "streamSettings": {"sockopt": {"domainStrategy": "ForceIPv4"}},
    }
    assert default["network"] == "tcp"
    assert default["outboundTag"] == "cascade-classifier"


def test_cascade_udp_is_explicitly_blocked_until_adapter_supports_it() -> None:
    config = _render_cascade_xray()
    udp_rules = [rule for rule in config["routing"]["rules"] if rule.get("network") == "udp"]

    assert any(rule.get("outboundTag") == "block" and rule.get("port") is None for rule in udp_rules)
    assert not any(rule.get("outboundTag") == "direct" and "udp" in rule.get("network", "") for rule in config["routing"]["rules"])
    assert not any(rule.get("outboundTag") == "dns-out" for rule in config["routing"]["rules"])
    assert config["dns"]["servers"] == ["tcp://1.1.1.1:53", "tcp://8.8.8.8:53"]
    assert config["dns"]["queryStrategy"] == "UseIPv4"
    assert any(rule.get("inboundTag") == ["dns-inbound"] and rule.get("outboundTag") == "cascade-classifier" for rule in config["routing"]["rules"])


def test_cascade_suppresses_warp_bypass_even_if_notional_vars_are_present() -> None:
    variables = merge_render_vars()
    variables["vpn"] = {
        **variables["vpn"],
        "enable_cascade_ingress": True,
        "enable_warp_outbound": True,
        "warp_outbound_routes": [{"domain": ["example:invalid"]}],
    }
    variables["cascade_secrets"] = {**variables["cascade_secrets"], "classifier_proxy_password": PROXY_PASSWORD}
    config = json.loads(render_template(TEMPLATE, variables))

    assert not any(outbound["tag"] == "warp-out" for outbound in config["outbounds"])
    assert not any(rule.get("outboundTag") == "warp-out" for rule in config["routing"]["rules"])


def test_non_cascade_default_remains_direct() -> None:
    variables = merge_render_vars()
    config = json.loads(render_template(TEMPLATE, variables))

    assert not any(item["tag"] == "cascade-classifier" for item in config["outbounds"])
    assert config["routing"]["rules"][-1]["outboundTag"] == "direct"
