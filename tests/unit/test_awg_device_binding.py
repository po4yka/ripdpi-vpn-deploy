"""Canonical AWG peer authority, pool allocation and private selection boundaries."""
from __future__ import annotations

import base64
import copy
import ipaddress
import hashlib

import pytest

from awg_device_binding import BindingError, allocate_address, public_key, resolve_binding


def key(number):
    return base64.b64encode(bytes([number]) * 32).decode()


def document():
    def instance(index):
        return {
            "name": f"awg{index}", "listen_port": 51820 + index,
            "address_v4": f"10.{70 + index}.0.1/29", "address_v6": f"fd42:{index + 10}::1/64",
            "server_private_key": key(index + 1), "jc": 4, "jmin": 10, "jmax": 50,
            "s1": 0, "s2": 0, "wire_profile": "awg-3.1-ranges-v1",
            **{f"h{i}": str(index * 10 + i) for i in range(1, 5)},
            "peers": [{"name": f"device{index}", "public_key": public_key(key(index + 10)),
                       "preshared_key": key(index + 20), "allowed_ips": {"ipv4": f"10.{70 + index}.0.2/32", "ipv6": f"fd42:{index + 10}::2/128"}}],
        }
    return {"amneziawg_secrets": {"instances": [instance(0), instance(1)]},
            "client_registry": {f"device{i}": {
                "status": "issued", "issued_at": "2026-10-10T00:00:00Z", "formats": [],
                "hosts": ["upcloud:fixture"], "cohorts": [], "token_hash_prefix": "", "token_expires": "",
                "awg_private_key": key(i + 10), "awg_delivery_host": "",
                "awg_public_key_fingerprint": "sha256:" + hashlib.sha256(public_key(key(i + 10)).encode()).hexdigest()[:16],
                "awg_binding": {"provider": "upcloud", "environment": "fixture", "instance": f"awg{i}"},
                "last_payload_identity": {}} for i in range(2)}}


@pytest.mark.parametrize("index", [0, 1])
def test_binding_uses_only_the_selected_effective_instance(index):
    source = document()
    before = copy.deepcopy(source)
    selected = resolve_binding(source, {}, f"device{index}", "upcloud:fixture", f"awg{index}")
    assert selected.instance["listen_port"] == 51820 + index
    assert selected.instance["server_private_key"] == key(index + 1)
    assert selected.peer["allowed_ips"] == {"ipv4": f"10.{70 + index}.0.2/32", "ipv6": f"fd42:{index + 10}::2/128"}
    assert source == before


def test_missing_peer_cannot_become_a_successful_partial_profile():
    with pytest.raises(BindingError, match="missing-device-binding"):
        resolve_binding(document(), {}, "absent", "upcloud:fixture", "awg0")


def test_duplicate_device_names_refuse_every_instance_selection():
    source = document()
    for instance in source["amneziawg_secrets"]["instances"]:
        instance["peers"][0]["name"] = "device"
    for selected in (None, 'awg0', 'awg1'):
        with pytest.raises(BindingError, match="invalid-awg-contract"):
            resolve_binding(source, {}, "device", "upcloud:fixture", selected)


def test_legacy_top_level_peer_authority_is_rejected():
    source = document()
    source["amneziawg_secrets"]["peers"] = []
    with pytest.raises(BindingError, match="invalid-awg-contract"):
        resolve_binding(source, {}, "device0", "upcloud:fixture")


def test_pool_allocation_excludes_server_network_broadcast_and_peers():
    selected = resolve_binding(document(), {}, "device0", "upcloud:fixture")
    assert allocate_address(selected.instance, 4) == "10.70.0.3/32"
    assert ipaddress.ip_interface(allocate_address(selected.instance, 4)).ip in ipaddress.ip_interface(
        selected.instance["address_v4"]).network


def test_routed_claims_reserve_the_complete_interval():
    instance = document()["amneziawg_secrets"]["instances"][0]
    instance["peers"] = [{"allowed_ips": {"ipv4": "10.70.0.0/30"}, "address_kind": "routed"}]
    assert allocate_address(instance, 4) == "10.70.0.4/32"


def test_exhausted_pool_refuses_without_mutation():
    instance = document()["amneziawg_secrets"]["instances"][0]
    instance["address_v4"] = "10.70.0.1/30"
    before = copy.deepcopy(instance)
    with pytest.raises(BindingError, match="address-pool-exhausted"):
        allocate_address(instance, 4)
    assert instance == before


@pytest.mark.parametrize("field,value", [("h2", 1), ("jmax", 9), ("name", "a" * 16), ("s3", 1)])
def test_parameter_refusal_is_shared_and_contains_no_private_input(field, value):
    source = document()
    source["amneziawg_secrets"]["instances"][0][field] = value
    with pytest.raises(BindingError) as failure:
        resolve_binding(source, {}, "device0", "upcloud:fixture")
    assert str(failure.value) == "invalid-awg-contract"
    assert key(1) not in str(failure.value)


@pytest.mark.parametrize('registry', [None, {}, {'other': {}}, {'device0': None}])
def test_existing_device_requires_persisted_registry_authority(registry):
    source = document()
    if registry is None:
        source.pop('client_registry', None)
    else:
        source['client_registry'] = registry
    with pytest.raises(BindingError, match='invalid-registry-binding'):
        resolve_binding(source, {}, 'device0', 'upcloud:fixture', 'awg0')


@pytest.mark.parametrize('instance', [None, 'awg0', 'awg1'])
@pytest.mark.parametrize('enrollment', [False, True])
@pytest.mark.parametrize('kind', ['device', 'routed'])
def test_duplicate_device_refuses_even_with_explicit_instance(instance, enrollment, kind):
    source = document()
    source['amneziawg_secrets']['instances'][1]['peers'][0].update(name='device0', address_kind=kind)
    with pytest.raises(BindingError):
        resolve_binding(source, {}, 'device0', 'upcloud:fixture', instance, enrollment=enrollment)


def test_existing_name_on_another_instance_cannot_be_enrolled_again():
    with pytest.raises(BindingError, match='device-already-enrolled'):
        resolve_binding(document(), {}, 'device0', 'upcloud:fixture', 'awg1', enrollment=True)


@pytest.mark.parametrize('host', ['upcloud:other', 'scaleway:fixture'])
def test_caller_host_cannot_replace_persisted_authority(host):
    with pytest.raises(BindingError, match='invalid-registry-binding'):
        resolve_binding(document(), {}, 'device0', host, 'awg0')
