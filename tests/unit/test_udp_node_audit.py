"""UDP transport node: TCP masquerade listeners, congestion default, MSS clamp and split-hop defaults."""
import importlib.util
import json
from pathlib import Path
import re
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from template_render import merge_render_vars, render_template  # noqa: E402
from transport_semantics import AWG_MTU_DEFAULT  # noqa: E402

ROLES = ROOT / "ansible/roles"
PROFILE = yaml.safe_load((ROOT / "ansible/group_vars/vpn-p2-udp.yml").read_text())
ACME = {"domains": ["udp.example.test"], "email": "ops@example.test"}


def hysteria_config(*, acme=False, stated=None, **overrides):
    values = merge_render_vars()
    values.update(overrides)
    values["hysteria"] = {**values["hysteria"], "clients": [{"name": "device", "password": "fixture-password"}]}
    values["hysteria"].pop("resource_profile", None)  # the example secrets document states one
    if stated:
        values["hysteria"]["resource_profile"] = stated
    if acme:
        values["hysteria"]["acme"] = ACME
    return yaml.safe_load(render_template(ROLES / "hysteria/templates/config.yaml.j2", values))


def test_masquerade_site_answers_tcp_only_where_the_profile_selects_it():
    assert set(hysteria_config()["masquerade"]) == {"type", "proxy"}
    masquerade = hysteria_config(hysteria_masquerade_tcp=PROFILE["hysteria_masquerade_tcp"])["masquerade"]
    assert {key: masquerade.get(key) for key in ("listenHTTP", "listenHTTPS", "forceHTTPS")} == {
        "listenHTTP": ":80", "listenHTTPS": ":443", "forceHTTPS": True}


def test_native_acme_keeps_tcp_80_for_its_challenge():
    masquerade = hysteria_config(acme=True, hysteria_masquerade_tcp=True)["masquerade"]
    assert masquerade["listenHTTPS"] == ":443"
    assert "listenHTTP" not in masquerade and "forceHTTPS" not in masquerade


@pytest.mark.parametrize("acme", [False, True])
def test_installed_validator_admits_the_tcp_masquerade_configuration(acme):
    spec = importlib.util.spec_from_file_location(
        "hysteria_yaml_validator", ROLES / "runtime-release/files/validate_yaml_mapping.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator._validate_hysteria(hysteria_config(
        acme=acme, hysteria_masquerade_tcp=True, hysteria_resource_profile_default="bbr-conservative"))


@pytest.mark.parametrize(("acme", "expected"), [(False, {80, 443}), (True, {443})])
def test_listener_manifest_names_the_masquerade_ports(acme, expected):
    values = merge_render_vars()
    values["vpn"] = {**values["vpn"], **PROFILE["vpn"]}
    values["hysteria_masquerade_tcp"] = True
    if acme:
        values["hysteria"] = {**values["hysteria"], "acme": ACME}
    manifest = json.loads(render_template(ROOT / "ansible/templates/listener-manifest.json.j2", values))
    ports = {item["port"] for item in manifest if item["role"] == "hysteria-masquerade" and item["enabled"]}
    assert ports == expected
    assert all(item["protocol"] == "tcp" for item in manifest if item["role"] == "hysteria-masquerade")
    values["hysteria_masquerade_tcp"] = False
    manifest = json.loads(render_template(ROOT / "ansible/templates/listener-manifest.json.j2", values))
    assert not [item for item in manifest if item["role"] == "hysteria-masquerade" and item["enabled"]]


def test_udp_profile_default_is_bbr_and_a_stated_profile_wins():
    assert "congestion" not in hysteria_config()
    default = PROFILE["hysteria_resource_profile_default"]
    config = hysteria_config(hysteria_resource_profile_default=default)
    assert config["congestion"] == {"type": "bbr", "bbrProfile": "conservative"}
    assert config["ignoreClientBandwidth"] is True
    assert "congestion" not in hysteria_config(hysteria_resource_profile_default=default, stated="bandwidth-capped")


def firewall(**overrides):
    values = merge_render_vars()
    values.update(overrides)
    return render_template(ROLES / "firewall/templates/nftables.conf.j2", values)


def awg_values(mtu=None):
    values = merge_render_vars()
    instance = dict(values["amneziawg_secrets"]["instances"][0])
    instance.pop("mtu", None)
    if mtu is not None:
        instance["mtu"] = mtu
    return {"vpn": {**values["vpn"], "enable_amneziawg": True}, "amneziawg_secrets": {"instances": [instance]}}, instance["name"]


@pytest.mark.parametrize(("mtu", "v4", "v6"), [(None, AWG_MTU_DEFAULT - 40, AWG_MTU_DEFAULT - 60), (1420, 1380, 1360)])
def test_forwarded_awg_tcp_is_clamped_to_the_instance_mtu_before_conntrack_accepts(mtu, v4, v6):
    values, name = awg_values(mtu)
    forward = firewall(**values).split("chain forward {")[1].split("chain output {")[0]
    clamp = forward.index(f'iifname "{name}" meta nfproto ipv4 tcp flags syn tcp option maxseg size set {v4} ')
    assert f'iifname "{name}" meta nfproto ipv6 tcp flags syn tcp option maxseg size set {v6} ' in forward
    reply = forward.index(f'oifname "{name}" tcp flags syn tcp option maxseg size set rt mtu ')
    assert max(clamp, reply) < forward.index("ct state established,related accept")


def test_default_mtu_has_one_value_across_role_admission_and_firewall():
    role = yaml.safe_load((ROLES / "amneziawg/defaults/main.yml").read_text())["amneziawg"]["mtu"]
    template = (ROLES / "firewall/templates/nftables.conf.j2").read_text()
    fallback = int(re.search(r"set awg_default_mtu = .*default\((\d+)\)\) %}", template)[1])
    assert role == AWG_MTU_DEFAULT == fallback == 1280


@pytest.mark.parametrize(("facts", "expected"), [
    ({"default_ipv4": {"interface": "ens2"}}, 'iifname "ens2" meta nfproto ipv4 udp sport 67 udp dport 68 counter accept'),
    ({}, None),
])
def test_dhcpv4_reply_is_scoped_to_the_ipv4_uplink_before_conntrack(facts, expected):
    chain = firewall(ansible_facts=facts).split("chain input {")[1].split("chain forward {")[0]
    if expected is None:
        assert "dport 68" not in chain
    else:
        assert chain.index(expected) < chain.index("ct state established,related accept")


def split_hop_values(**egress):
    values = merge_render_vars()
    values["vpn"] = {**values["vpn"], "enable_split_hop_egress": True}
    values["split_hop_egress"] = {**values["split_hop_egress"], **egress}
    values["ansible_facts"] = {"default_ipv4": {"interface": "enp1s0"}}
    values["split_hop_ingress_listen_port"] = 24680
    values["firewall_egress_policy"] = "strict"
    return values


def test_split_hop_egress_follows_the_observed_uplink_and_the_ingress_port():
    values = split_hop_values()
    nat = render_template(ROLES / "split-hop-egress/templates/split-hop-egress.nft.j2", values)
    assert 'iifname "shop0" oifname "enp1s0" masquerade' in nat
    tunnel = render_template(ROLES / "split-hop-egress/templates/split-hop-egress.conf.j2", values)
    assert re.search(r"^Endpoint = .*:24680$", tunnel, re.M)
    rules = render_template(ROLES / "firewall/templates/nftables.conf.j2", values)
    assert 'ct state new iifname "shop0" oifname "enp1s0" accept' in rules
    assert "udp dport 24680 accept" in rules


def test_explicit_split_hop_interface_and_port_still_win():
    values = split_hop_values(forward_iface="toe", peer_listen_port=51999)
    assert 'oifname "toe" masquerade' in render_template(ROLES / "split-hop-egress/templates/split-hop-egress.nft.j2", values)
    assert ":51999\n" in render_template(ROLES / "split-hop-egress/templates/split-hop-egress.conf.j2", values)


def test_split_hop_egress_refuses_private_destinations_before_its_forward_accept():
    forward = render_template(ROLES / "firewall/templates/nftables.conf.j2", split_hop_values()).split("chain forward {")[1]
    deny = forward.index('iifname "shop0" ip daddr { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16,')
    assert "counter drop" in forward[deny:forward.index("\n", deny)]
    assert deny < forward.index('ct state new iifname "shop0"')
