"""Hysteria endpoint options survive materialization and liveness admission."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import client_payload
from test_liveness_profiles import inputs, load


def emit(monkeypatch, *, rates=("100 mbps", "200 mbps"), profile="bandwidth-capped", format="singbox"):
    document = {"hysteria": {
        "version": "v2.13.0", "resource_profile": profile,
        "bandwidth_up": rates[0], "bandwidth_down": rates[1],
        "masquerade_url": "https://origin.example", "server_name": "origin.example",
        "salamander_enabled": True, "salamander_password": "fixture-obfs-password",
        "clients": [{"name": "phone", "password": "fixture-client-password"}],
    }}
    context = {"vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": False,
                       "enable_hysteria": True},
               "hysteria_port_range": "46000-46015", "hysteria_hop_interval": "30s"}
    # Provider resolution is outside this pure export boundary; no private IO.
    monkeypatch.setattr(client_payload, "command", lambda *args, **kwargs: b"192.0.2.1")
    monkeypatch.setattr(client_payload, "context", lambda cohort: deepcopy(context))
    source = str(Path("/public-export-fixture").absolute())
    options = client_payload.options(format, hosts=["upcloud:prod", "hetzner:prod"], cohorts=["lab", "lab"])
    payload, _ = client_payload.materialize("phone", options, documents={source: document},
        source_paths=[source, source], extended=format == "ripdpi")
    return payload


def test_every_bundle_endpoint_retains_hopping_and_salamander_metadata(monkeypatch):
    payload = emit(monkeypatch, format="ripdpi")
    outbounds = [item for item in payload["outbounds"] if item["type"] == "hysteria2"]
    extras = payload["ripdpi"]["hysteria_extras"]
    assert set(extras) == {item["tag"] for item in outbounds}
    for outbound in outbounds:
        assert extras[outbound["tag"]] == {
            "insecure": False, "obfs": outbound["obfs"],
            "salamander_upstream_tag": "v2.13.0",
            "port_hopping": {"ports": "46000:46015", "interval": "30s"},
        }


@pytest.mark.parametrize("rates,expected", [
    (("100 mbps", "200 mbps"), (200, 100)),
    (("1 bps", "1500 kbps"), (2, 1)),
    (("1000001 bps", "1 gbps"), (1000, 2)),
])
@pytest.mark.parametrize("format", ["singbox", "ripdpi"])
def test_hints_use_client_directions_and_positive_integer_mbps(monkeypatch, rates, expected, format):
    payload = emit(monkeypatch, rates=rates, format=format)
    for outbound in payload["outbounds"]:
        if outbound["type"] == "hysteria2":
            assert (outbound.get("up_mbps"), outbound.get("down_mbps")) == expected
            assert type(outbound["up_mbps"]) is type(outbound["down_mbps"]) is int


@pytest.mark.parametrize("profile", ["bbr-conservative", "bbr-standard"])
def test_bbr_profiles_do_not_advertise_brutal_bandwidth(monkeypatch, profile):
    payload = emit(monkeypatch, profile=profile)
    for outbound in payload["outbounds"]:
        if outbound["type"] == "hysteria2":
            assert "up_mbps" not in outbound and "down_mbps" not in outbound
            assert outbound["bbr_profile"] == profile.removeprefix("bbr-")


@pytest.mark.parametrize("mutation", ["missing", "reversed", "zero", "boolean", "fraction", "extra-bbr"])
def test_liveness_refuses_missing_or_changed_bandwidth_hints(mutation):
    module = load()
    arguments = inputs()
    outbound = arguments["standard_doc"]["outbounds"][1]
    outbound.update(up_mbps=200, down_mbps=100)
    if mutation == "missing":
        outbound.pop("up_mbps")
    elif mutation == "reversed":
        outbound.update(up_mbps=100, down_mbps=200)
    elif mutation == "extra-bbr":
        arguments["secrets_doc"]["hysteria"].update(version="v2.13.0", resource_profile="bbr-standard")
        outbound["bbr_profile"] = "standard"
    else:
        if mutation == "boolean":
            arguments["secrets_doc"]["hysteria"]["bandwidth_down"] = "1 mbps"
        outbound["up_mbps"] = {"zero": 0, "boolean": True, "fraction": 1.5}[mutation]
    with pytest.raises(module.ProfileError, match="wrong-hysteria-bandwidth"):
        module.build_profiles(**arguments)


def test_liveness_retains_exact_hints_and_binds_rates_in_digest():
    module = load()
    arguments = inputs()
    outbound = arguments["standard_doc"]["outbounds"][1]
    outbound.update(up_mbps=200, down_mbps=100)
    first = module.build_profiles(**arguments)
    selected = first["files"]["sing-box.json"]["outbounds"][1]
    assert (selected["up_mbps"], selected["down_mbps"]) == (200, 100)
    arguments["secrets_doc"]["hysteria"]["bandwidth_down"] = "201 mbps"
    outbound["up_mbps"] = 201
    assert first["public_profile_digest"] != module.build_profiles(**arguments)["public_profile_digest"]
