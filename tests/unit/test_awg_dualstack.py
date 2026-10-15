"""Dual-stack authority and deterministic MTU contract regressions."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from awg_client import config, enroll, export
from awg_device_binding import BindingError, allocate_address, resolve_binding
from awg_uplink import admit
from liveness_profiles import _awg
from template_render import merge_render_vars, render_template
from transport_semantics import awg_errors, effective_awg_instances
from test_awg_device_binding import document, public_key

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('mtu', [1280, 1320, 1420])
def test_server_standalone_bundle_and_liveness_share_both_addresses_and_mtu(mtu):
    doc = document()
    context = {'amneziawg': {'mtu': 1400}, 'amneziawg_cohort': {'mtu': 1360}}
    doc['amneziawg_secrets']['instances'][1]['mtu'] = mtu
    selected = resolve_binding(doc, context, 'device1', 'upcloud:fixture', 'awg1')
    block = export(doc, context, 'device1', 'upcloud:fixture', 'awg1', '192.0.2.1')
    assert block['address'] == ['10.71.0.2/32', 'fd42:11::2/128']
    assert block['mtu'] == mtu
    standalone = config(block)
    live, addresses, metadata = _awg(doc, 'device1', selected.identity, '192.0.2.1',
                                    doc['client_registry']['device1']['awg_private_key'], public_key,
                                    context['amneziawg'], context['amneziawg_cohort'])
    assert addresses == block['address'] and metadata['mtu'] == mtu
    for field in ('Address', 'MTU', 'DNS', 'AllowedIPs'):
        line = next(line for line in standalone.splitlines() if line.startswith(field + ' ='))
        assert line in live
    values = merge_render_vars(); values['_inst'] = selected.instance
    server = render_template(ROOT / 'ansible/roles/amneziawg/templates/awg0.conf.j2', values)
    assert f'MTU = {mtu}' in server
    assert 'AllowedIPs = 10.71.0.2/32, fd42:11::2/128' in server


def test_mtu_precedence_is_instance_then_cohort_then_role_then_baseline():
    raw = document()['amneziawg_secrets']
    def mtu(defaults=None, cohort=None):
        return effective_awg_instances(raw, defaults, cohort)[0]['mtu']
    assert mtu() == 1420
    assert mtu({'mtu': 1400}) == 1400
    assert mtu({'mtu': 1400}, {'mtu': 1360}) == 1360
    raw['instances'][0]['mtu'] = 1280
    assert mtu({'mtu': 1400}, {'mtu': 1360}) == 1280


@pytest.mark.parametrize('mtu', [1279, 1421, 0, True, 1280.0, '1280', None])
@pytest.mark.parametrize('source', ['instance', 'cohort', 'role'])
def test_invalid_mtu_refuses_before_export_or_enrollment(mtu, source):
    doc, context = document(), {'amneziawg': {}, 'amneziawg_cohort': {}}
    target = doc['amneziawg_secrets']['instances'][0] if source == 'instance' else context[
        'amneziawg_cohort' if source == 'cohort' else 'amneziawg']
    target['mtu'] = mtu
    before = copy.deepcopy(doc)
    with pytest.raises(BindingError, match='invalid-awg-contract'):
        enroll(doc, context, 'new', 'upcloud:fixture', 'awg0')
    with pytest.raises(BindingError, match='invalid-awg-contract'):
        export(doc, context, 'device0', 'upcloud:fixture', 'awg0', '192.0.2.1')
    assert doc == before


@pytest.mark.parametrize('addresses', [
    '10.70.0.2/32', ['10.70.0.2/32', 'fd42:10::2/128'], {'ipv4': '10.70.0.2/32'},
    {'ipv4': 'fd42:10::2/128', 'ipv6': '10.70.0.2/32'},
    {'ipv4': '10.70.0.2/32', 'ipv6': 'fd42:10::/64'},
    {'ipv4': '10.70.0.2/32', 'ipv6': 'fd42:11::2/128'},
    {'ipv4': '10.70.0.2/32', 'ipv6': 'fd42:10::1/128'},
    {'ipv4': '10.70.0.2/32', 'ipv6': 'fd42:10::/128'},
])
def test_untyped_missing_swapped_reserved_or_foreign_addresses_refuse(addresses):
    raw = document()['amneziawg_secrets']
    raw['instances'][0]['peers'][0]['allowed_ips'] = addresses
    assert awg_errors(raw)


def test_ipv6_allocator_jumps_routed_intervals_and_refuses_exhaustion():
    instance = document()['amneziawg_secrets']['instances'][0]
    instance['address_v6'] = 'fd42:10::1/64'
    instance['peers'] = [{'address_kind': 'routed', 'allowed_ips': {'ipv6': 'fd42:10::/65'}}]
    assert allocate_address(instance, 6) == 'fd42:10:0:0:8000::/128'
    instance['peers'][0]['allowed_ips']['ipv6'] = 'fd42:10::/64'
    with pytest.raises(BindingError, match='address-pool-exhausted'):
        allocate_address(instance, 6)


@pytest.mark.parametrize('version,source', [(4, '8.8.8.8'), (6, '2001:4860:4860::8888')])
def test_public_dualstack_uplink_admission(version, source):
    admit([{'dev': 'eth7', 'prefsrc': source}], 'eth7', version)


@pytest.mark.parametrize('routes', [[], [{'dev': 'other', 'prefsrc': '2001:4860:4860::8888'}],
                                     [{'dev': 'eth7', 'prefsrc': 'fd42::1'}],
                                     [{'dev': 'eth7', 'prefsrc': 'fe80::1'}],
                                     [{'dev': 'eth7', 'prefsrc': '8.8.8.8'}],
                                     [{'dev': 'eth7', 'type': 'blackhole'}]])
def test_missing_private_wrong_family_or_wrong_uplink_refuses(routes):
    with pytest.raises((ValueError, KeyError)):
        admit(routes, 'eth7', 6)
