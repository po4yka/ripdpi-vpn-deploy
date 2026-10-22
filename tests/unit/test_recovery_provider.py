"""Provider plan/state boundaries using recorded-shape synthetic cloud documents."""
from __future__ import annotations

import copy

import pytest
import recovery_provider as provider
from recovery_io import RecoveryError
from test_recovery_io import manifest as manifest  # noqa: PLC0414

UUID = '11111111-1111-4111-8111-111111111111'


@pytest.fixture
def cloud(manifest):
    value, _ = manifest
    server = {'uuid': UUID, 'hostname': value['hostname'], 'created': 1000, 'zone': 'test-zone',
              'plan': 'test-plan', 'state': 'started',
              'labels': {'label': [{'key': 'recovery_id', 'value': value['id']},
                                   {'key': 'managed_by', 'value': 'terraform'}]},
              'ip_addresses': {'ip_address': [{'access': 'public', 'family': 'IPv4', 'address': '192.0.2.10'}]}}
    attributes = {'id': UUID, 'hostname': value['hostname'], 'zone': server['zone'], 'plan': server['plan'],
                  'labels': {'recovery_id': value['id'], 'managed_by': 'terraform'}, 'storage_devices': []}
    state = {'resources': [{'mode': 'managed', 'type': 'upcloud_server', 'name': 'vpn',
                            'instances': [{'attributes': attributes}]}]}
    plan = {'complete': True, 'resource_changes': [{'mode': 'managed', 'address': 'upcloud_server.vpn',
                'change': {'actions': ['create'], 'before': None, 'after': attributes}}]}
    return value, server, state, plan


def test_positive_plan_state_and_live_identity_agree(cloud):
    manifest, server, state, plan = cloud
    assert provider.server_from_state({}, manifest) is None
    assert provider.server_from_state(state, manifest)['id'] == UUID
    assert provider.review_plan(plan, manifest)['changes'] == [{'address': 'upcloud_server.vpn', 'actions': ['create']}]
    live = provider.server_identity(server, manifest)
    assert live['uuid'] == UUID and live['public_ipv4'] == ['192.0.2.10']
    plan['resource_changes'][0]['change']['actions'] = ['no-op']
    plan['resource_changes'][0]['change']['before'] = copy.deepcopy(plan['resource_changes'][0]['change']['after'])
    assert provider.review_plan(plan, manifest, existing=provider.server_from_state(state, manifest))['changes'] == []


@pytest.mark.parametrize('fault', ['foreign-resource', 'delete', 'replace', 'hostname', 'label', 'seed', 'incomplete'])
def test_saved_plan_refuses_changes_outside_exact_replacement(cloud, fault):
    manifest, _, _, plan = cloud
    change = plan['resource_changes'][0]
    if fault == 'foreign-resource':
        change['address'] = 'upcloud_server.other'
    elif fault == 'delete':
        change['change']['actions'] = ['delete']
    elif fault == 'replace':
        change['change']['actions'] = ['delete', 'create']
    elif fault == 'hostname':
        change['change']['after']['hostname'] = 'other'
    elif fault == 'label':
        change['change']['after']['labels'].pop('recovery_id')
    elif fault == 'seed':
        change['change']['after']['storage_devices'] = [{'storage': UUID}]
    else:
        plan['complete'] = False
    with pytest.raises(RecoveryError, match='outside-scope'):
        provider.review_plan(plan, manifest)


@pytest.mark.parametrize('fault', ['foreign', 'duplicate', 'wrong-id'])
def test_state_refuses_foreign_or_ambiguous_authority(cloud, fault):
    manifest, _, state, _ = cloud
    if fault == 'foreign':
        state['resources'][0]['name'] = 'other'
    elif fault == 'duplicate':
        state['resources'][0]['instances'] *= 2
    else:
        state['resources'][0]['instances'][0]['attributes']['id'] = 'invalid'
    with pytest.raises(RecoveryError, match='state-mismatch'):
        provider.server_from_state(state, manifest)


@pytest.mark.parametrize('fault', ['hostname', 'label', 'created', 'address'])
def test_live_identity_refuses_unowned_or_invalid_server(cloud, fault):
    manifest, server, _, _ = cloud
    if fault == 'hostname':
        server['hostname'] = 'other'
    elif fault == 'label':
        server['labels']['label'][0]['value'] = 'other'
    elif fault == 'created':
        server['created'] = True
    else:
        server['ip_addresses']['ip_address'][0]['address'] = 'not-an-ip'
    with pytest.raises(RecoveryError, match='live-resource-mismatch'):
        provider.server_identity(server, manifest)


def test_output_only_reconciliation_still_requires_saved_plan_apply(cloud):
    manifest, _, state, plan = cloud
    plan['resource_changes'] = []
    plan['output_changes'] = {'server_ipv4': {'actions': ['create'], 'after': '192.0.2.10'}}
    result = provider.review_plan(plan, manifest, existing=provider.server_from_state(state, manifest))
    assert result['changes'] == [{'output': 'server_ipv4', 'actions': ['create']}]


def test_duplicate_live_labels_refuse(cloud):
    manifest, server, _, _ = cloud
    server['labels']['label'].append(copy.deepcopy(server['labels']['label'][0]))
    with pytest.raises(RecoveryError):
        provider.server_identity(server, manifest)


def test_provider_observation_checks_account_before_resource_lookup(cloud, monkeypatch):
    from types import SimpleNamespace
    manifest, server, _, _ = cloud
    paths = []
    def request(path):
        paths.append(path)
        if path == '/1.3/server':
            return 200, {'servers': {'server': [{'hostname': server['hostname'], 'uuid': server['uuid']}]}}
        return 200, {'server': server}
    guard = SimpleNamespace(_provider_authorization=lambda: 'fixture-credential',
        _upcloud_request=lambda _: request, _authenticated_account_username=lambda _: manifest['account'])
    monkeypatch.setattr(provider, 'module', lambda _: guard)
    observed = provider.observe(manifest)
    assert observed['servers'][0]['uuid'] == server['uuid']
    assert paths == ['/1.3/server', '/1.3/server/' + server['uuid']]
    paths.clear()
    guard._authenticated_account_username = lambda _: 'different-account'
    with pytest.raises(RecoveryError, match='account-changed'):
        provider.observe(manifest)
    assert not paths
