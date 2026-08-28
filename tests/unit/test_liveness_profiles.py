"""Pure materialization fixtures; parser and external traffic gates are separate."""
from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("liveness_profiles", ROOT / "scripts/liveness_profiles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def key(value):
    return base64.b64encode(bytes([value]) * 32).decode()


def inputs():
    xray = {"name": "sentinel", "uuid": "00000000-0000-4000-8000-000000000001", "short_id": "0011223344556677"}
    peer = {"name": "sentinel", "public_key": key(2), "preshared_key": key(3), "allowed_ips": "10.66.66.2/32"}
    secrets = {
        "client_registry": {"sentinel": {"status": "active", "hosts": ["vultr:probe"]}},
        "xray": {"clients": [xray], "reality_public_key": "public-reality-key", "server_names": ["cover.example"], "xhttp_path": "/sync"},
        "nginx_xhttp": {"server_name": "origin.example"},
        "hysteria": {"clients": [{"name": "sentinel", "password": "private-password"}]},
        "amneziawg_secrets": {"server_private_key": key(4), "peers": [peer], "instances": [],
                              "jc": 0, "h1": 11, "h2": 12, "h3": 13, "h4": 14},
    }
    p0 = {"type": "vless", "tag": "p0-reality-upcloud-probe", "server": "192.0.2.1", "server_port": 443,
          "uuid": xray["uuid"], "flow": "xtls-rprx-vision", "tls": {"enabled": True, "server_name": "cover.example",
          "utls": {"enabled": True, "fingerprint": "chrome"},
          "reality": {"enabled": True, "public_key": "public-reality-key", "short_id": xray["short_id"]}}}
    p1 = {"type": "vless", "tag": "p1-xhttp-scaleway-probe", "server": "192.0.2.2", "server_port": 443,
          "uuid": xray["uuid"], "tls": {"enabled": True, "server_name": "origin.example",
          "utls": {"enabled": True, "fingerprint": "chrome"}},
          "transport": {"type": "xhttp", "host": "origin.example", "path": "/sync"}}
    p2 = {"type": "hysteria2", "tag": "p2-hysteria2-vultr-probe", "server": "192.0.2.3", "server_port": 443,
          "password": "sentinel:private-password", "tls": {"enabled": True, "server_name": "origin.example"}}
    standard = {"outbounds": [p0, p2, {"type": "direct", "tag": "direct"}]}
    ripdpi = {"outbounds": [copy.deepcopy(p0), p1, copy.deepcopy(p2)]}
    return dict(standard_doc=standard, ripdpi_doc=ripdpi, secrets_doc=secrets, client="sentinel",
                required_profiles=["p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"],
                awg_binding={"provider": "vultr", "environment": "probe", "instance": "awg0"},
                endpoint="192.0.2.3", private_key=key(1),
                derive_public_key=lambda private: {key(1): key(2), key(4): key(5)}[private],
                generation_root="/etc/vpn-liveness/generations/example",
                awg_defaults={"interface": "awg0", "listen_port": 51820, "address_v4": "10.66.66.1/24"},
                awg_cohort={"jc": 9, "jmin": 21})


def test_four_profiles_are_materialized_with_only_named_client_material():
    module = load()
    args = inputs()
    before = copy.deepcopy({k: v for k, v in args.items() if k != "derive_public_key"})
    built = module.build_profiles(**args)
    standard = built["files"]["sing-box.json"]
    xray = built["files"]["xray.json"]
    awg = built["files"]["awg.conf"]
    assert {o["type"] for o in standard["outbounds"]} == {"vless", "hysteria2"}
    assert all(i["listen"] == "127.0.0.1" and i["type"] == "socks" for i in standard["inbounds"])
    assert not any("transport" in o and o["transport"]["type"] == "xhttp" for o in standard["outbounds"])
    assert xray["outbounds"][0]["streamSettings"]["network"] == "xhttp"
    assert xray["outbounds"][0]["streamSettings"]["tlsSettings"]["allowInsecure"] is False
    assert xray["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] == args["secrets_doc"]["xray"]["clients"][0]["uuid"]
    assert f"PrivateKey = {key(1)}" in awg and f"PublicKey = {key(5)}" in awg
    assert f"PresharedKey = {key(3)}" in awg and key(4) not in awg
    assert "Jc = 0" in awg and "Jmin = 21" in awg and "Jmax = 70" in awg
    assert "Endpoint = 192.0.2.3:51820" in awg
    assert built["runtime"]["amneziawg"]["address"] == "10.66.66.2/32"
    assert before == {k: v for k, v in args.items() if k != "derive_public_key"}
    public = json.dumps(built["public_profiles"])
    for private in (key(1), key(2), key(3), key(4), key(5), "private-password", "0011223344556677", args["secrets_doc"]["xray"]["clients"][0]["uuid"]):
        assert private not in public


def test_real_canonical_emitter_outputs_materialize_for_both_runtimes(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("liveness_compatibility", ROOT / "scripts/check-liveness-profile-compatibility.py")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        profiles = helper.render_profiles(tmp_path)
    finally:
        sys.path.pop(0)
    assert set(profiles) == {"sing-box.json", "xray.json"}
    singbox = json.loads(profiles["sing-box.json"].read_text())
    xray = json.loads(profiles["xray.json"].read_text())
    assert {outbound["type"] for outbound in singbox["outbounds"]} == {"vless", "hysteria2"}
    assert xray["outbounds"][0]["streamSettings"]["network"] == "xhttp"
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in profiles.values())


@pytest.mark.parametrize("kind", ["xhttp-host", "xhttp-path", "reality-sni", "hysteria-sni"])
def test_emitter_tls_and_path_must_match_canonical_server_material(kind):
    m = load()
    args = inputs()
    if kind.startswith("xhttp"):
        outbound = args["ripdpi_doc"]["outbounds"][1]
        if kind == "xhttp-host":
            outbound["tls"]["server_name"] = "unapproved.example"
            outbound["transport"]["host"] = "unapproved.example"
        else:
            outbound["transport"]["path"] = "/wrong-path"
    else:
        args["standard_doc"]["outbounds"][0 if kind == "reality-sni" else 1]["tls"]["server_name"] = "unapproved.example"
    with pytest.raises(m.ProfileError):
        m.build_profiles(**args)


def test_public_digest_is_credential_independent_but_changes_with_endpoint():
    module = load()
    args = inputs()
    first = module.build_profiles(**args)
    args["secrets_doc"]["hysteria"]["clients"][0]["password"] = "rotated-password"
    args["standard_doc"]["outbounds"][1]["password"] = "sentinel:rotated-password"
    assert module.build_profiles(**args)["public_profile_digest"] == first["public_profile_digest"]
    args["endpoint"] = "192.0.2.4"
    assert module.build_profiles(**args)["public_profile_digest"] != first["public_profile_digest"]


@pytest.mark.parametrize("status", [None, "revoked", "burned", "stale", "unknown"])
def test_unusable_enrollment_is_rejected_before_key_callback(status):
    module = load()
    args = inputs()
    args["secrets_doc"]["client_registry"]["sentinel"]["status"] = status
    args["derive_public_key"] = lambda _: pytest.fail("no key derivation for rejected identity")
    with pytest.raises(module.ProfileError, match="client-not-active"):
        module.build_profiles(**args)


@pytest.mark.parametrize("field", ["provider", "environment", "instance"])
def test_awg_binding_is_complete_and_explicit(field):
    module = load()
    args = inputs()
    del args["awg_binding"][field]
    with pytest.raises(module.ProfileError, match="awg-binding"):
        module.build_profiles(**args)


def test_wrong_client_private_key_does_not_emit_or_derive_server_material():
    module = load()
    args = inputs()
    calls = []
    def derive(private):
        calls.append(private)
        return key(99)
    args["derive_public_key"] = derive
    with pytest.raises(module.ProfileError, match="awg-key-mismatch"):
        module.build_profiles(**args)
    assert calls == [key(1)]


@pytest.mark.parametrize("address", ["10.77.0.2/32", "10.66.66.2/24", "fd00::2/128", "10.66.66.1/32", "10.66.66.0/32", "10.66.66.255/32"])
def test_awg_client_requires_unique_host_address_inside_selected_subnet(address):
    module = load()
    args = inputs()
    args["secrets_doc"]["amneziawg_secrets"]["peers"][0]["allowed_ips"] = address
    with pytest.raises(module.ProfileError, match="awg-address"):
        module.build_profiles(**args)


@pytest.mark.parametrize("kind", ["xray-name", "xray-uuid", "hysteria-name", "awg-name", "awg-key", "awg-address"])
def test_duplicate_client_identity_is_rejected(kind):
    module = load()
    args = inputs()
    if kind.startswith("xray"):
        peers = args["secrets_doc"]["xray"]["clients"]
        duplicate = copy.deepcopy(peers[0])
        if kind.endswith("uuid"):
            duplicate["name"] = "other"
    elif kind.startswith("hysteria"):
        peers = args["secrets_doc"]["hysteria"]["clients"]
        duplicate = copy.deepcopy(peers[0])
    else:
        peers = args["secrets_doc"]["amneziawg_secrets"]["peers"]
        duplicate = copy.deepcopy(peers[0])
        if kind != "awg-name":
            duplicate["name"] = "other"
        if kind == "awg-address":
            duplicate["public_key"] = key(99)
    peers.append(duplicate)
    with pytest.raises(module.ProfileError, match="duplicate"):
        module.build_profiles(**args)


def test_multi_instance_binding_uses_only_selected_instance_not_cohort_or_top_level():
    module = load()
    args = inputs()
    awg = args["secrets_doc"]["amneziawg_secrets"]
    instance = {**awg, "name": "awg-selected", "listen_port": 51999, "address_v4": "10.66.66.1/24"}
    del instance["instances"]
    instance.pop("jc")
    awg["instances"] = [{**instance, "name": "awg-other", "peers": []}, instance]
    args["awg_binding"]["instance"] = "awg-selected"
    built = module.build_profiles(**args)
    assert "Endpoint = 192.0.2.3:51999" in built["files"]["awg.conf"]
    assert "Jc = 4" in built["files"]["awg.conf"]


@pytest.mark.parametrize("parameter,value", [("s3", 1), ("s4", 1), ("i1", "<b 0x01>"), ("h2", 11)])
def test_unsupported_or_ambiguous_awg_parameters_fail_closed(parameter, value):
    module = load()
    args = inputs()
    args["secrets_doc"]["amneziawg_secrets"][parameter] = value
    with pytest.raises(module.ProfileError, match="awg-parameters"):
        module.build_profiles(**args)


@pytest.mark.parametrize("mutation", ["missing", "wrong-uuid", "insecure", "direct-detour", "duplicate-tag"])
def test_invalid_xhttp_material_is_rejected(mutation):
    module = load()
    args = inputs()
    p1 = args["ripdpi_doc"]["outbounds"][1]
    if mutation == "missing":
        args["ripdpi_doc"]["outbounds"].remove(p1)
    elif mutation == "wrong-uuid":
        p1["uuid"] = "00000000-0000-4000-8000-000000000002"
    elif mutation == "insecure":
        p1["tls"]["insecure"] = True
    elif mutation == "direct-detour":
        p1["detour"] = "direct"
    else:
        args["ripdpi_doc"]["outbounds"].append(copy.deepcopy(p1))
    with pytest.raises(module.ProfileError):
        module.build_profiles(**args)


@pytest.mark.parametrize("mutation", ["unknown-tls-key", "obfs-other-password", "obfs-extra-secret", "invalid-hop-range", "wrong-flow"])
def test_nested_emitter_fields_cannot_carry_other_material(mutation):
    module = load()
    args = inputs()
    p0, p2 = args["standard_doc"]["outbounds"][:2]
    if mutation == "unknown-tls-key":
        p0["tls"]["client_key"] = "other-private-key"
    elif mutation.startswith("obfs"):
        args["secrets_doc"]["hysteria"].update(salamander_enabled=True, salamander_password="own-obfs-password")
        p2["obfs"] = {"type": "salamander", "password": "own-obfs-password"}
        if mutation == "obfs-other-password":
            p2["obfs"]["password"] = "other-obfs-password"
        else:
            p2["obfs"]["other-key"] = "other-private-key"
    elif mutation == "invalid-hop-range":
        p2.update(server_ports=["1:99999"], hop_interval="30s")
    else:
        p0["flow"] = "other-private-key"
    with pytest.raises(module.ProfileError):
        module.build_profiles(**args)


def test_hysteria_hop_ports_are_preserved_and_bound_in_public_digest():
    module = load()
    args = inputs()
    p2 = args["standard_doc"]["outbounds"][1]
    p2.update(server_ports=["50000:50010"], hop_interval="30s")
    first = module.build_profiles(**args)
    assert first["files"]["sing-box.json"]["outbounds"][1]["server_ports"] == ["50000:50010"]
    p2["server_ports"] = ["50000:50011"]
    assert first["public_profile_digest"] != module.build_profiles(**args)["public_profile_digest"]


def test_awg_single_network_defaults_override_top_level_secret_listen_port():
    module = load()
    args = inputs()
    args["secrets_doc"]["amneziawg_secrets"]["listen_port"] = 60000
    args["awg_defaults"]["listen_port"] = 51999
    assert "Endpoint = 192.0.2.3:51999" in module.build_profiles(**args)["files"]["awg.conf"]


def test_equivalent_awg_peer_address_is_not_a_second_identity():
    module = load()
    args = inputs()
    args["secrets_doc"]["amneziawg_secrets"]["peers"].append({
        "name": "other", "public_key": key(99), "preshared_key": key(98), "allowed_ips": "10.66.66.2/255.255.255.255",
    })
    with pytest.raises(module.ProfileError, match="duplicate"):
        module.build_profiles(**args)


def test_key_callback_failure_is_categorical_not_secret_bearing():
    module = load()
    args = inputs()
    def failure(_private):
        raise RuntimeError("private-key-content-do-not-emit")
    args["derive_public_key"] = failure
    with pytest.raises(module.ProfileError) as caught:
        module.build_profiles(**args)
    assert str(caught.value) == "awg-key-derivation"
    assert caught.value.__suppress_context__


def test_profile_variants_preserve_every_endpoint_and_port():
    module = load()
    args = inputs()
    p1 = copy.deepcopy(args["ripdpi_doc"]["outbounds"][1])
    p1.update(tag="p1-xhttp-scaleway-probe-fallback", server_port=8443)
    args["ripdpi_doc"]["outbounds"].append(p1)
    built = module.build_profiles(**args)
    assert built["runtime"]["xray"]["profiles"]["p1-xhttp"] == [18181, 18182]
    assert [o["settings"]["vnext"][0]["port"] for o in built["files"]["xray.json"]["outbounds"]] == [443, 8443]


def test_non_awg_selection_does_not_derive_or_emit_awg_material():
    module = load()
    args = inputs()
    args["required_profiles"] = ["p0-reality"]
    args["derive_public_key"] = lambda _: pytest.fail("no AWG operation")
    args["awg_binding"] = None
    built = module.build_profiles(**args)
    assert set(built["files"]) == {"sing-box.json"}
    assert set(built["runtime"]) == {"sing_box"}


@pytest.mark.parametrize("mutation", ["status-type", "profile-type", "xray-type", "hysteria-type"])
def test_malformed_document_has_only_categorical_error(mutation):
    module = load()
    args = inputs()
    if mutation == "status-type":
        args["secrets_doc"]["client_registry"]["sentinel"]["status"] = {"secret": "do-not-emit"}
    elif mutation == "profile-type":
        args["required_profiles"] = [{"secret": "do-not-emit"}]
    else:
        args["secrets_doc"][mutation.removesuffix("-type")] = ["do-not-emit"]
    with pytest.raises(module.ProfileError) as caught:
        module.build_profiles(**args)
    assert "do-not-emit" not in str(caught.value)


def test_other_clients_never_reach_runtime_files_or_public_report():
    module = load()
    args = inputs()
    other_uuid, other_short = "00000000-0000-4000-8000-000000000002", "aabbccddeeff0011"
    args["secrets_doc"]["xray"]["clients"].append({"name": "other", "uuid": other_uuid, "short_id": other_short})
    args["secrets_doc"]["hysteria"]["clients"].append({"name": "other", "password": "other-password-do-not-emit"})
    args["secrets_doc"]["amneziawg_secrets"]["peers"].append({
        "name": "other", "public_key": key(98), "preshared_key": key(99), "allowed_ips": "10.66.66.3/32",
    })
    result = json.dumps(module.build_profiles(**args))
    for private in (other_uuid, other_short, "other-password-do-not-emit", key(98), key(99), key(4)):
        assert private not in result
