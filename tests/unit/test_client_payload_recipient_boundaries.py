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
        "schema_version": 2, "selector_tag": "select",
        "probes": [
            {"url": f"https://control-{letter}.example.test/__throttle_probe?bytes=262144",
             "expected_bytes": 262144, "sha256": sha256(payload(262144)).hexdigest()}
            for letter in ("a", "b")
        ],
        "interval_seconds": 60, "timeout_seconds": 10,
        "failure_threshold": 2, "recovery_threshold": 2,
        "cooldown_seconds": 120, "max_backoff_seconds": 900,
        "quality": {"max_pass_bytes": 2097152, "max_window_bytes": 16777216,
                    "window_seconds": 3600, "minimum_gain_percent": 20,
                    "maximum_loaded_latency_increase_ms": 50},
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


def test_version_two_without_quality_keeps_health_only_policy(materialization, payload_policy):
    payload_policy.pop("quality")
    materialization[0]["client_payload_failover"] = payload_policy
    assert materialization[2]("ripdpi")["ripdpi"]["payload_failover"] == payload_policy


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
    ("schema_version", 1),
])
def test_policy_bounds_refuse(materialization, payload_policy, field, value):
    context, _, render = materialization
    context["client_payload_failover"] = dict(payload_policy, **{field: value})
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        render("ripdpi")


@pytest.mark.parametrize("url", [
    "http://control-b.example.test/", "HTTPS://control-b.example.test/", "https://user:private@control-b.example.test/",
    "https://control-b.example.test/#fragment", "https://control-b.example.test/#",
    "https://control-b.example.test:0/",
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
    detached["quality"]["max_pass_bytes"] = 0
    assert payload_policy["quality"]["max_pass_bytes"] == 2097152


@pytest.mark.parametrize("field,bad", [
    ("max_pass_bytes", 65537), ("max_pass_bytes", 16777217),
    ("max_window_bytes", 65537), ("max_window_bytes", 268435457),
    ("window_seconds", 59), ("window_seconds", 86401),
    ("minimum_gain_percent", 4), ("minimum_gain_percent", 101),
    ("maximum_loaded_latency_increase_ms", -1), ("maximum_loaded_latency_increase_ms", 2001),
    ("max_pass_bytes", True), ("max_window_bytes", "16777216"),
    ("window_seconds", 3600.0), ("minimum_gain_percent", False),
    ("maximum_loaded_latency_increase_ms", None),
])
def test_quality_numerical_bounds_reject_before_emission(materialization, payload_policy, field, bad):
    payload_policy["quality"][field] = bad
    materialization[0]["client_payload_failover"] = payload_policy
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        materialization[2]("ripdpi")


@pytest.mark.parametrize("quality", [None, [], {}, {"unknown": 1}])
def test_quality_requires_complete_exact_object(payload_policy, quality):
    from payload_failover_policy import validate_policy
    payload_policy["quality"] = quality
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        validate_policy(payload_policy)


@pytest.mark.parametrize("field", [
    "max_pass_bytes", "max_window_bytes", "window_seconds", "minimum_gain_percent",
    "maximum_loaded_latency_increase_ms",
])
def test_quality_missing_field_refuses(payload_policy, field):
    from payload_failover_policy import validate_policy
    payload_policy["quality"].pop(field)
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        validate_policy(payload_policy)


def test_quality_semantic_capacity_and_exact_bounds(payload_policy):
    from payload_failover_policy import validate_policy
    quality = payload_policy["quality"]
    required = 2 * sum(probe["expected_bytes"] + 1 for probe in payload_policy["probes"])
    quality.update(max_pass_bytes=required, max_window_bytes=required, window_seconds=60,
                   minimum_gain_percent=5, maximum_loaded_latency_increase_ms=0)
    assert validate_policy(payload_policy) == payload_policy
    for field, invalid in [("max_pass_bytes", required - 1), ("max_window_bytes", required - 1),
                           ("window_seconds", 59), ("unknown", 1)]:
        bad = deepcopy(payload_policy)
        bad["quality"][field] = invalid
        with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
            validate_policy(bad)
    payload_policy["interval_seconds"] = 120
    with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
        validate_policy(payload_policy)
    quality.update(max_pass_bytes=16777216, max_window_bytes=268435456, window_seconds=86400,
                   minimum_gain_percent=100, maximum_loaded_latency_increase_ms=2000)
    assert validate_policy(payload_policy) == payload_policy


@pytest.mark.parametrize("size,accepted", [(32767, False), (32768, True), (1048576, True), (1048577, False), (True, False)])
def test_version_two_payload_size_bounds(payload_policy, size, accepted):
    from payload_failover_policy import validate_policy
    payload_policy["probes"][0]["expected_bytes"] = size
    payload_policy["quality"]["max_pass_bytes"] = 16777216
    if accepted:
        assert validate_policy(payload_policy) == payload_policy
    else:
        with pytest.raises(ValueError, match="invalid-payload-failover-policy"):
            validate_policy(payload_policy)


@pytest.mark.parametrize("mutate", ["duplicate-origin", "empty-fragment", "backoff", "digest", "unknown", "null",
                                    "version-one", "quality-capacity", "quality-window", "quality-unknown"])
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
    elif mutate == "empty-fragment":
        policy["probes"][0]["url"] += "#"
    elif mutate == "backoff":
        policy["interval_seconds"] = 1000
    elif mutate == "digest":
        policy["probes"][0]["sha256"] = "a" * 63
    elif mutate == "unknown":
        policy["ignored"] = True
    elif mutate == "version-one":
        policy["schema_version"] = 1
    elif mutate == "quality-capacity":
        policy["quality"]["max_pass_bytes"] = 2 * sum(p["expected_bytes"] + 1 for p in policy["probes"]) - 1
    elif mutate == "quality-window":
        policy["quality"]["max_window_bytes"] = policy["quality"]["max_pass_bytes"] - 1
    elif mutate == "quality-unknown":
        policy["quality"]["ignored"] = True
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


def test_percent_encoded_hash_in_control_path_is_not_a_fragment(payload_policy):
    from payload_failover_policy import validate_policy
    payload_policy["probes"][1]["url"] = "https://control-b.example.test/payload%23suffix"
    assert validate_policy(payload_policy) == payload_policy
