"""Preserve credential bytes across role templates and actual Python consumers."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

import client_payload
from template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS = [
    'synthetic-quoted-"-credential',
    "synthetic-backslash-\\n-credential",
    "synthetic-control-\n\t\r-credential",
    "synthetic-unicode-\u2603-credential",
]
IDS = ["quote", "backslash", "control", "unicode"]


@pytest.mark.parametrize("credential", CREDENTIALS, ids=IDS)
def test_snell_server_smoke_and_recipient_preserve_exact_credentials(tmp_path, monkeypatch, credential):
    snell = yaml.safe_load((ROOT / "ansible/roles/snell/defaults/main.yml").read_text())["snell"]
    authority = {
        "linux_amd64_sha256": "0" * 64, "linux_arm64_sha256": "0" * 64,
        "variants": [{"id": variant["id"], "psk": credential + str(index),
                      "users": [{"name": "audit-device", "userkey": credential + "-user" + str(index)}]}
                     for index, variant in enumerate(snell["variants"])],
    }
    schema = json.loads((ROOT / "secrets/schema.json").read_text())
    jsonschema.validate(authority, {"$defs": schema["$defs"], **schema["properties"]["snell_secrets"]})
    values = {"snell": snell, "snell_secrets": authority}
    server = json.loads(render_template(ROOT / "ansible/roles/snell/templates/config.json.j2", values))
    smoke = json.loads(render_template(ROOT / "ansible/roles/snell/templates/smoke-client.json.j2", values))

    context = {"snell": snell, "vpn": {
        "enable_xray_reality": False, "enable_nginx_xhttp": False,
        "enable_hysteria": False, "enable_amneziawg": False, "enable_snell": True,
    }}
    monkeypatch.setattr(client_payload, "context", lambda _: deepcopy(context))
    def metadata(argv, **_):
        assert argv[-3:] == ["output", "-raw", "server_ipv4"]
        return b"192.0.2.90"
    monkeypatch.setattr(client_payload, "command", metadata)
    source = str(tmp_path / "in-memory-authority")
    recipient, _ = client_payload.materialize(
        "audit-device", client_payload.options("singbox", hosts=["upcloud:fixture"], cohorts=["lab"]),
        documents={source: {"snell_secrets": authority}}, source_paths=[source],
    )
    # Consume the JSON output too: successful parsing alone must not conceal a
    # credential change shared by both role-rendered smoke and server paths.
    outbounds = json.loads(json.dumps(recipient))["outbounds"]
    for index, variant in enumerate(snell["variants"]):
        expected = authority["variants"][index]
        assert server["inbounds"][index]["psk"] == expected["psk"]
        assert server["inbounds"][index]["users"][0]["userkey"] == expected["users"][0]["userkey"]
        assert smoke["outbounds"][index]["psk"] == expected["psk"]
        assert smoke["outbounds"][index]["userkey"] == expected["users"][0]["userkey"]
        emitted = [outbound for outbound in outbounds
                   if outbound.get("type") == "snell" and outbound["server_port"] == variant["listen_port"]]
        assert len(emitted) == 2
        assert {outbound["reuse"] for outbound in emitted} == {False, True}
        assert all(outbound["psk"] == expected["psk"]
                   and outbound["userkey"] == expected["users"][0]["userkey"] for outbound in emitted)


def test_snell_and_naive_refuse_canonical_private_destinations():
    # Neither transport egresses through the guarded normalizer, so each must
    # enforce the recipient boundary itself (loopback admin APIs, metadata, Tailnet).
    from scripts.transport_destination_policy import IPV4_DENY, IPV6_DENY
    deny = list(IPV4_DENY) + list(IPV6_DENY)
    snell = yaml.safe_load((ROOT / "ansible/roles/snell/defaults/main.yml").read_text())["snell"]
    secrets = {"variants": [{"id": variant["id"], "psk": "psk", "users": [{"name": "d", "userkey": "k"}]}
                            for variant in snell["variants"]]}
    server = json.loads(render_template(ROOT / "ansible/roles/snell/templates/config.json.j2",
                                        {"snell": snell, "snell_secrets": secrets}))
    assert server["route"]["rules"] == [{"action": "resolve"}, {"ip_cidr": deny, "action": "reject"}]

    naive = yaml.safe_load((ROOT / "ansible/roles/naive/defaults/main.yml").read_text())["naive"]
    caddy = json.loads(render_template(ROOT / "ansible/roles/naive/templates/caddy.json.j2", {
        "naive": naive, "naive_secrets": {"probe_resistance_secret": "p",
                                          "clients": [{"username": "u", "password": "p"}]}}))
    proxies = [handler for server in caddy["apps"]["http"]["servers"].values()
               for route in server["routes"] for outer in route["handle"] if outer["handler"] == "subroute"
               for inner in outer["routes"] for handler in inner["handle"] if handler["handler"] == "forward_proxy"]
    assert [proxy["acl"] for proxy in proxies] == [[{"subjects": deny, "allow": False}]]


@pytest.mark.parametrize("credential", CREDENTIALS, ids=IDS)
def test_trojan_target_and_actual_probe_driver_preserve_exact_passwords(credential):
    schema = json.loads((ROOT / "secrets/schema.json").read_text())
    fields = schema["properties"]["probe_matrix_target_secrets"]["properties"]
    for field in ("xhttp_trojan_password", "tcp_trojan_password"):
        jsonschema.validate(credential, fields[field])
    target = {"ports": {"xhttp_vless": 11443, "xhttp_trojan": 12443, "tcp_trojan": 13443},
              "paths": {"xhttp_vless": "/vless", "xhttp_trojan": "/trojan"}}
    authority = {"vless_uuid": "00000000-0000-4000-8000-000000000001",
                 "xhttp_trojan_password": credential, "tcp_trojan_password": credential + "-tcp"}
    server = json.loads(render_template(ROOT / "ansible/roles/probe-matrix-target/templates/xray.json.j2",
                                       {"probe_matrix_target": target, "probe_matrix_target_secrets": authority}))
    spec = importlib.util.spec_from_file_location("credential_probe_driver", ROOT / "scripts/probe-matrix-driver.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    for index, (protocol, field) in enumerate((
            ("xhttp-trojan", "xhttp_trojan_password"), ("tcp-trojan", "tcp_trojan_password")), 1):
        settings = {"port": server["inbounds"][index]["port"], "server_name": "probe.example.com",
                    "path": "/trojan", "password": authority[field]}
        client = json.loads(json.dumps(driver.xray_outbound(protocol, "192.0.2.90", settings)))
        assert server["inbounds"][index]["settings"]["clients"][0]["password"] == authority[field]
        assert client["settings"]["servers"][0]["password"] == authority[field]
    # Probe credentials must not reach the node's loopback, metadata or private networks.
    from scripts.transport_destination_policy import IPV4_DENY, IPV6_DENY
    assert server["outbounds"][0]["settings"]["finalRules"] == [
        {"action": "block", "ip": list(IPV4_DENY) + list(IPV6_DENY)}, {"action": "allow"}]
