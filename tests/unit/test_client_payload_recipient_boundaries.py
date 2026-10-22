"""Recipient admission and multi-host metadata use the real materializer."""
from copy import deepcopy

import client_payload
import pytest


@pytest.fixture
def materialization(monkeypatch):
    context = {
        "vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": False,
                "enable_hysteria": True, "enable_amneziawg": False, "enable_snell": False},
        "hysteria_port": 443,
    }
    document = {"hysteria": {
        "version": "v2.13.0", "server_name": "owned.example.test",
        "masquerade_url": "https://owned.example.test", "salamander_enabled": True,
        "salamander_password": "synthetic-obfs-first",
        "clients": [{"name": "fixture-device", "password": "synthetic-password"}],
    }}
    monkeypatch.setattr(client_payload, "context", lambda _: deepcopy(context))

    def metadata(argv, **_):
        assert argv[-1] == "server_ipv4"
        return b"203.0.113.10"

    monkeypatch.setattr(client_payload, "command", metadata)

    def render(format_name, documents=None):
        documents = documents or [document]
        hosts = ["upcloud:fixture", "hetzner:fixture"][:len(documents)]
        sources = ["/synthetic-authority-" + str(index) for index in range(len(documents))]
        options = client_payload.options(format_name, hosts=hosts, cohorts=["fixture"] * len(hosts),
                                         awg_host="", utls="")
        return client_payload.materialize(
            "fixture-device", options, documents=dict(zip(sources, documents)),
            source_paths=sources, extended=format_name == "ripdpi",
        )[0]

    return context, document, render


def test_ripdpi_hysteria_hopping_refuses_instead_of_emitting_a_partial_profile(materialization):
    context, _, render = materialization
    context.update(hysteria_port_range="20000-21000", hysteria_hop_interval="45s")
    with pytest.raises(ValueError, match="RIPDPI.*port hopping"):
        render("ripdpi")


def test_ripdpi_hopping_cli_emits_no_artifact_or_private_diagnostic(materialization, monkeypatch, capsys):
    context, document, _ = materialization
    context["hysteria_port_range"] = "20000-21000"
    monkeypatch.setattr(client_payload, "paths", lambda _: ["/synthetic-authority"])
    monkeypatch.setattr(client_payload, "read_document", lambda *_, **__: document)
    monkeypatch.setattr("sys.argv", ["client_payload.py", "fixture-device", "--bundle"])
    monkeypatch.setenv("HOSTS", "upcloud:fixture")
    monkeypatch.setenv("COHORTS", "fixture")
    monkeypatch.setenv("AWG_HOST", "")
    result = client_payload.main()
    assert result == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "client-payload: RIPDPI Hysteria port hopping requires a qualified client\n"
    assert document["hysteria"]["clients"][0]["password"] not in output.err


def test_official_singbox_retains_exact_hysteria_hopping(materialization):
    context, _, render = materialization
    context.update(hysteria_port_range="20000-21000", hysteria_hop_interval="45s")
    outbound = next(value for value in render("singbox")["outbounds"] if value["type"] == "hysteria2")
    assert outbound["server_ports"] == ["20000:21000"]
    assert outbound["hop_interval"] == "45s"


def test_nonhopping_ripdpi_retains_the_hysteria_node(materialization):
    _, _, render = materialization
    payload = render("ripdpi")
    outbound = next(value for value in payload["outbounds"] if value["type"] == "hysteria2")
    assert "server_ports" not in outbound and "hop_interval" not in outbound
    assert payload["ripdpi"]["hysteria_extras"][outbound["tag"]]["insecure"] is False


def test_multihost_hysteria_extras_retain_each_tag_and_distinct_source_metadata(materialization):
    _, first, render = materialization
    second = deepcopy(first)
    second["hysteria"].update(version="v2.12.1", salamander_password="synthetic-obfs-second")
    payload = render("ripdpi", [first, second])
    outbounds = [value for value in payload["outbounds"] if value["type"] == "hysteria2"]
    extras = payload["ripdpi"]["hysteria_extras"]
    assert len(outbounds) == len(extras) == 2
    assert set(extras) == {value["tag"] for value in outbounds}
    for outbound, document in zip(outbounds, [first, second]):
        assert extras[outbound["tag"]] == {
            "insecure": False, "obfs": outbound["obfs"],
            "salamander_upstream_tag": document["hysteria"]["version"],
        }
        assert outbound["obfs"]["password"] == document["hysteria"]["salamander_password"]


@pytest.fixture
def payload_policy():
    from hashlib import sha256
    from payload_probe_content import payload

    return {
        "schema_version": 1, "selector_tag": "select",
        "probes": [
            {"url": f"https://control-{letter}.example.test/__throttle_probe?bytes=32768",
             "expected_bytes": 32768, "sha256": sha256(payload(32768)).hexdigest()}
            for letter in ("a", "b")
        ],
        "interval_seconds": 60, "timeout_seconds": 10,
        "failure_threshold": 2, "recovery_threshold": 2,
        "cooldown_seconds": 120, "max_backoff_seconds": 900,
    }


def test_payload_failover_emitted_fixture(materialization, payload_policy):
    import json
    from pathlib import Path
    import jsonschema

    context, first, render = materialization
    context["client_payload_failover"] = payload_policy
    second = deepcopy(first)
    second["hysteria"]["server_name"] = "second.example.test"
    emitted = render("ripdpi", [first, second])
    root = Path(__file__).resolve().parents[2]
    expected = json.loads((root / "contract/ripdpi-bundle.payload-failover.json").read_text())
    assert emitted == expected
    jsonschema.validate(emitted["ripdpi"], json.loads((root / "contract/ripdpi-bundle.schema.json").read_text()))
    assert emitted["route"]["final"] == "select"
    assert emitted["ripdpi"]["payload_failover"] == payload_policy
    assert len(next(item for item in emitted["outbounds"] if item["tag"] == "auto")["outbounds"]) == 2
    plain = render("singbox", [first, second])
    assert "ripdpi" not in plain
    assert next(item for item in plain["outbounds"] if item["tag"] == "auto")["url"].endswith("generate_204")


def test_policy_omitted_until_explicitly_configured(materialization):
    assert "payload_failover" not in materialization[2]("ripdpi")["ripdpi"]


def test_multihost_policy_disagreement_refuses(materialization, payload_policy, monkeypatch):
    context, first, render = materialization
    contexts = iter([dict(context, client_payload_failover=payload_policy), context])
    monkeypatch.setattr(client_payload, "context", lambda _: next(contexts))
    with pytest.raises(ValueError, match="conflicting-payload-failover-policy"):
        render("ripdpi", [first, deepcopy(first)])


def test_policy_requires_proxy_candidates(materialization, payload_policy):
    context, _, render = materialization
    context["client_payload_failover"] = payload_policy
    context["vpn"]["enable_hysteria"] = False
    with pytest.raises(ValueError, match="no enabled outbounds resolved"):
        render("ripdpi")


@pytest.mark.parametrize("field,value", [
    ("interval_seconds", 29), ("interval_seconds", True), ("timeout_seconds", 31),
    ("failure_threshold", 1), ("recovery_threshold", 1), ("cooldown_seconds", 0),
    ("max_backoff_seconds", 59), ("selector_tag", "direct"), ("schema_version", True),
])
def test_policy_bounds_refuse(materialization, payload_policy, field, value):
    context, _, render = materialization
    context["client_payload_failover"] = dict(payload_policy, **{field: value})
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        render("ripdpi")


@pytest.mark.parametrize("url", [
    "http://control-b.example.test/", "HTTPS://control-b.example.test/", "https://user:private@control-b.example.test/",
    "https://control-b.example.test/#fragment", "https://control-b.example.test:0/",
    "https://control-b.example.test\\@other.test/", "https://127.1/",
    "https://0177.0.0.1/", "https://0x7f000001/", "https://bad..example.test/",
    "https://control-a.example.test:443/different", "https://CONTROL-A.example.test./",
])
def test_invalid_or_duplicate_origins_refuse(payload_policy, url):
    from payload_failover_policy import validate_policy
    payload_policy["probes"][1]["url"] = url
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        validate_policy(payload_policy)


def test_policy_cross_field_and_exact_shape(payload_policy):
    from payload_failover_policy import validate_policy
    for policy in [dict(payload_policy, interval_seconds=1000), dict(payload_policy, extra=True),
                   dict(payload_policy, probes=payload_policy["probes"][:1])]:
        with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
            validate_policy(policy)
    detached = validate_policy(payload_policy)
    detached["probes"][0]["sha256"] = "changed"
    assert payload_policy["probes"][0]["sha256"] != "changed"


@pytest.mark.parametrize("mutate", ["duplicate-origin", "backoff", "digest", "unknown", "null"])
def test_bundle_validator_rejects_invalid_payload_policy(tmp_path, mutate):
    import json
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    document = json.loads((root / "contract/ripdpi-bundle.payload-failover.json").read_text())
    policy = document["ripdpi"]["payload_failover"]
    if mutate == "duplicate-origin":
        policy["probes"][1]["url"] = policy["probes"][0]["url"] + "&second=true"
    elif mutate == "backoff":
        policy["interval_seconds"] = 1000
    elif mutate == "digest":
        policy["probes"][0]["sha256"] = "a" * 63
    elif mutate == "unknown":
        policy["ignored"] = True
    else:
        document["ripdpi"]["payload_failover"] = None
    target = tmp_path / "bundle.json"
    target.write_text(json.dumps(document))
    result = subprocess.run([sys.executable, str(root / "scripts/validate-bundle.py"), str(target)],
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert "violation(s)" in result.stderr
    assert "synthetic-password" not in result.stderr


def test_mapped_ipv6_control_origin_alias_refuses(payload_policy):
    from payload_failover_policy import validate_policy
    payload_policy["probes"][0]["url"] = "https://192.0.2.10/control-a"
    payload_policy["probes"][1]["url"] = "https://[::ffff:c000:20a]/control-b"
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        validate_policy(payload_policy)
