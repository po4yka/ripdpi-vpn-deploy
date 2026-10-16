"""Canonical endpoint delivery and bounded XHTTP tuning share admission."""
from copy import deepcopy
import json
from pathlib import Path

import jsonschema
import pytest

import client_payload
from scripts.template_render import merge_render_vars
from transport_semantics import xhttp_errors
from liveness_profiles import build_profiles

ROOT = Path(__file__).resolve().parents[2]


def materialize(monkeypatch, *, alternate=True, mode="auto", xmux=None, version="v26.3.27"):
    context = merge_render_vars()
    context["vpn"].update(enable_xray_reality=False, enable_nginx_xhttp=True,
        enable_hysteria=False, enable_amneziawg=False, enable_snell=False, enable_naive=False)
    context["nginx_xhttp"]["fallback_enabled"] = alternate
    context.update(nginx_xhttp_public_port=8443, nginx_xhttp_fallback_port=2083)
    document = {key: deepcopy(context[key]) for key in ("xray", "nginx_xhttp")}
    document["nginx_xhttp"].pop("fallback_enabled", None)
    document["client_registry"] = {"laptop": {"status": "active"}}
    document["nginx_xhttp"]["fallback_server_name"] = "alternate.example.test"
    document["xray"]["clients"] = [dict(name="laptop", uuid="11111111-1111-4111-8111-111111111111", short_id="0123456789abcdef")]
    document["xray"]["version"] = version
    document["xray"]["xhttp_mode"] = mode
    if xmux is not None:
        document["xray"]["xhttp_xmux"] = xmux
    monkeypatch.setattr(client_payload, "context", lambda _: context)
    monkeypatch.setattr(client_payload, "command", lambda *a, **kw: b"192.0.2.90")
    source = str(Path("synthetic.json").absolute())
    payload, _ = client_payload.materialize("laptop", client_payload.options("ripdpi", hosts=["upcloud:fixture"], cohorts=["test"]),
        documents={source: document}, source_paths=[source])
    return payload, document


@pytest.mark.parametrize("mode", ["auto", "packet-up", "stream-up"])
@pytest.mark.parametrize("alternate", [False, True])
def test_endpoints_retain_exact_tls_identity_and_typed_native_settings(monkeypatch, mode, alternate):
    xmux = {"maxConnections": 2, "hMaxRequestTimes": 64, "hMaxReusableSecs": 30}
    payload, document = materialize(monkeypatch, alternate=alternate, mode=mode, xmux=xmux)
    outbounds = [o for o in payload["outbounds"] if o.get("tag", "").startswith("p1-xhttp-")]
    assert len(outbounds) == (2 if alternate else 1)
    assert [o["server_port"] for o in outbounds] == ([8443, 2083] if alternate else [8443])
    if alternate:
        assert outbounds[1]["tls"]["server_name"] == "alternate.example.test"
        assert outbounds[1]["tag"].endswith("-alternate")
    profiles = build_profiles(None, payload, document, "laptop", ["p1-xhttp"], None, None, None,
        lambda _: pytest.fail("unused AWG key"), "/owned-generation", awg_defaults={}, awg_cohort={})
    assert all(profile["mode"] == mode and profile["xmux"] == xmux
               for profile in profiles["public_profiles"])
    native = profiles["files"]["xray.json"]["outbounds"]
    for emitted, engine in zip(outbounds, native):
        stream = engine["streamSettings"]
        assert stream["tlsSettings"]["serverName"] == emitted["tls"]["server_name"]
        assert stream["tlsSettings"]["allowInsecure"] is False
        assert stream["xhttpSettings"]["mode"] == mode
        assert stream["xhttpSettings"]["xmux"] == xmux


@pytest.mark.parametrize("xmux", [{"extra": {}}, {"maxConnections": 0}, {"maxConnections": 17},
    {"maxConnections": True}, {"hMaxRequestTimes": 1025}, {"hMaxReusableSecs": 601}, []])
def test_unknown_or_unbounded_tuning_is_rejected_by_schema_and_semantics(xmux):
    schema = json.loads((ROOT / "secrets/schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(xmux, schema["properties"]["xray"]["properties"]["xhttp_xmux"])
    assert any(path == "xray.xhttp_xmux" for path, _ in xhttp_errors({"xray": {"xhttp_xmux": xmux}}, {}))


def test_invalid_mode_refuses_before_artifact_publication(monkeypatch):
    with pytest.raises(ValueError, match="invalid-transport-input"):
        materialize(monkeypatch, mode="unsupported-private-marker")


@pytest.mark.parametrize("version", ["v26.5.3", "v1.0.0", "unknown"])
def test_unverified_tuning_engine_refuses_before_publication(monkeypatch, version):
    with pytest.raises(ValueError, match="invalid-transport-input"):
        materialize(monkeypatch, xmux={"maxConnections": 2}, version=version)


@pytest.mark.parametrize("frontend,context", [
    ({"fallback_enabled": "false"}, {}),
    ({"fallback_enabled": True, "fallback_server_name": "invalid private marker"}, {}),
    ({"fallback_enabled": True, "server_name": "owned.example"}, {"nginx_xhttp_fallback_port": 8443}),
])
def test_ambiguous_or_invalid_alternate_refuses(frontend, context):
    assert xhttp_errors({"xray": {}, "nginx_xhttp": frontend}, context)
