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
