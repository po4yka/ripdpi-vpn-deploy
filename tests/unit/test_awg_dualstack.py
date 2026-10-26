"""Dual-stack authority and deterministic MTU contract regressions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from awg_client import config, enroll, export
from awg_device_binding import BindingError, allocate_address, resolve_binding
from awg_uplink import admit
import awg_uplink
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


@pytest.fixture
def networkd_state():
    return {
        'Name': 'eth7', 'Index': 7, 'AdministrativeState': 'configured',
        'OperationalState': 'routable', 'AddressState': 'routable',
        'IPv6AddressState': 'routable',
        'Addresses': [{
            'ConfigSource': 'NDisc', 'Family': 10, 'Scope': 0,
            'ConfigState': 'configured', 'PrefixLength': 64,
            'Address': [32, 1, 72, 96, 72, 96, 0, 0, 0, 0, 0, 0, 0, 0, 136, 136],
        }],
        'Routes': [{
            'ConfigSource': 'NDisc', 'Family': 10, 'DestinationPrefixLength': 0,
            'Protocol': 9, 'ConfigState': 'configuring,configured',
            'LifetimeUSec': 60000000,
            'Gateway': [254, 128, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        }],
    }


@pytest.fixture
def selected_ra_route():
    return {'dev': 'eth7', 'prefsrc': '2001:4860:4860::8888', 'gateway': 'fe80::1'}


def test_networkd_owns_selected_ndisc_source_and_default_with_kernel_ra_disabled(
        networkd_state, selected_ra_route):
    assert awg_uplink.networkd_ra_owner(networkd_state, 'eth7', 7, selected_ra_route, '0')


@pytest.mark.parametrize('accept_ra', ['1', '2', '', 'false'])
def test_networkd_refuses_a_second_kernel_ra_owner(networkd_state, selected_ra_route, accept_ra):
    with pytest.raises(ValueError, match='ownership'):
        awg_uplink.networkd_ra_owner(networkd_state, 'eth7', 7, selected_ra_route, accept_ra)


@pytest.mark.parametrize('section,field,value', [
    (None, 'Name', 'eth8'), (None, 'Index', 8), (None, 'Index', True),
    (None, 'AdministrativeState', 'configuring'), (None, 'OperationalState', 'degraded'),
    (None, 'IPv6AddressState', 'degraded'), (None, 'Addresses', {}), (None, 'Routes', None),
    ('Addresses', 'Family', 2), ('Addresses', 'Family', 10.0),
    ('Addresses', 'Scope', False), ('Addresses', 'Scope', 253),
    ('Addresses', 'PrefixLength', 0), ('Addresses', 'PrefixLength', True),
    ('Addresses', 'ConfigState', 'tentative'), ('Addresses', 'Address', [0] * 16),
    ('Addresses', 'Address', [32, 1]), ('Addresses', 'Address', [False] * 16),
    ('Routes', 'Family', 2), ('Routes', 'DestinationPrefixLength', False),
    ('Routes', 'DestinationPrefixLength', 64), ('Routes', 'Protocol', 9.0),
    ('Routes', 'Protocol', 4), ('Routes', 'ConfigState', 'configuring'),
    ('Routes', 'LifetimeUSec', 0), ('Routes', 'LifetimeUSec', 2**64),
    ('Routes', 'LifetimeUSec', True), ('Routes', 'Gateway', [0] * 16),
    ('Routes', 'Gateway', [256] * 16), ('Routes', 'ConfigSource', None),
])
def test_networkd_refuses_incomplete_malformed_or_foreign_route_authority(
        networkd_state, selected_ra_route, section, field, value):
    target = networkd_state if section is None else networkd_state[section][0]
    target[field] = value
    with pytest.raises((ValueError, TypeError)):
        awg_uplink.networkd_ra_owner(networkd_state, 'eth7', 7, selected_ra_route, '0')


@pytest.mark.parametrize('section', ['Addresses', 'Routes'])
def test_networkd_refuses_missing_or_ambiguous_selected_authority(
        networkd_state, selected_ra_route, section):
    networkd_state[section] *= 2
    with pytest.raises(ValueError, match='selected-route'):
        awg_uplink.networkd_ra_owner(networkd_state, 'eth7', 7, selected_ra_route, '0')
    networkd_state[section] = []
    with pytest.raises(ValueError, match='selected-route'):
        awg_uplink.networkd_ra_owner(networkd_state, 'eth7', 7, selected_ra_route, '0')


@pytest.mark.parametrize('active,ndisc,accept_ra,allowed', [
    ('active', True, '0', True), ('active', True, '2', False),
    ('active', False, '2', True), ('active', False, '0', False),
    ('inactive', False, '2', True), ('inactive', False, '0', False),
    ('activating', False, '2', False), ('failed', False, '2', False),
])
def test_ra_owner_admission_selects_one_live_owner(
        monkeypatch, networkd_state, selected_ra_route, active, ndisc, accept_ra, allowed):
    calls = []
    if not ndisc:
        for row in networkd_state['Addresses'] + networkd_state['Routes']:
            row['ConfigSource'] = 'static'

    def run(argv, **kwargs):
        calls.append(argv)
        assert kwargs == {'check': True, 'capture_output': True, 'text': True, 'timeout': 5}
        return SimpleNamespace(stdout=active if argv[0] == 'systemctl' else json.dumps(networkd_state))

    monkeypatch.setattr(awg_uplink.subprocess, 'run', run)
    monkeypatch.setattr(awg_uplink.Path, 'read_text', lambda path: '7\n')
    if allowed:
        awg_uplink.admit_ra_owner('eth7', selected_ra_route, accept_ra)
    else:
        with pytest.raises(ValueError):
            awg_uplink.admit_ra_owner('eth7', selected_ra_route, accept_ra)
    assert calls[0] == ['systemctl', 'show', 'systemd-networkd.service', '--property=ActiveState', '--value']
    assert calls[1:] == ([['networkctl', '--json=short', 'status', 'eth7']] if active == 'active' else [])


@pytest.mark.parametrize("tail,safe", [("table inet filter {}\n", True),
                                       ("flush ruleset\n", False),
                                       ("\tflush\truleset;\n", False)])
def test_firewall_compensation_recognizes_owned_bytes_and_refuses_global_flush(tail, safe):
    import base64
    import yaml
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template
    tasks = yaml.safe_load((ROOT / "ansible/roles/firewall/tasks/awg-retain.yml").read_text())
    identify = next(task for task in tasks if task["name"] == "Identify accepted role-owned firewall generation")
    guard = next(task for task in tasks if task["name"] == "Refuse unsafe global-flush firewall recovery authority")
    text = "#!/usr/sbin/nft -f\n# Managed by Ansible role `firewall`. Hand edits will be overwritten.\n" + tail
    templar = Templar(loader=DataLoader(), variables={
        "_firewall_awg_owned": True, "_firewall_awg_before": {"stat": {"exists": True}},
        "_firewall_awg_bytes": {"content": base64.b64encode(text.encode()).decode()}})
    assert templar.template(trust_as_template(identify["ansible.builtin.set_fact"]["_firewall_awg_owned"])) is True
    assert templar.template(trust_as_template("{{ " + guard["ansible.builtin.assert"]["that"][0] + " }}")) is safe


@pytest.mark.parametrize('mode,owned,admitted', [
    ('0600', True, True), ('0644', True, True), ('0755', False, True),
    ('0755', True, False), ('0664', False, False), ('0775', False, False),
])
def test_firewall_retention_admits_distro_starter_without_executable_owned_authority(mode, owned, admitted):
    import yaml
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template
    tasks = yaml.safe_load((ROOT / 'ansible/roles/firewall/tasks/awg-retain.yml').read_text())
    names = ('Require bounded owned firewall configuration before AWG publication',
             'Require nonexecutable role-owned firewall recovery authority')
    templar = Templar(loader=DataLoader(), variables={
        '_firewall_awg_owned': owned,
        '_firewall_awg_before': {'stat': {'exists': True, 'isreg': True, 'uid': 0,
                                        'nlink': 1, 'mode': mode, 'size': 243}},
    })
    conditions = [condition for task in tasks if task['name'] in names
                  for condition in task['ansible.builtin.assert']['that']]
    assert len(conditions) == 2
    assert all(templar.template(trust_as_template('{{ ' + condition + ' }}'))
               for condition in conditions) is admitted
