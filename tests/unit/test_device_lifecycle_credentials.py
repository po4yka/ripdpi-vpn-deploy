"""Complete device authority changes retain unrelated users and server keys."""
import copy
from pathlib import Path

import device_lifecycle_credentials as lifecycle
import pytest
import yaml
from awg_device_binding import registry_errors, resolve_binding

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fleet():
    doc = yaml.safe_load((ROOT / 'tests/fixtures/secrets-sample.yml').read_text())
    nodes = {'upcloud:prod': {'cohort': 'device-full-tailnet'},
             'vultr:standby': {'cohort': 'p0-minimal'}}
    return {host: copy.deepcopy(doc) for host in nodes}, nodes


def test_issue_enabled_credentials_and_per_node_binding(fleet):
    docs, nodes = fleet
    before = copy.deepcopy(docs)
    result = lifecycle.issue(docs, nodes, 'new-phone', list(nodes), '2026-10-22T00:00:00Z')
    assert docs == before
    first, second = result.values()
    entry = first['client_registry']['new-phone']
    assert entry['hosts'] == list(nodes)
    assert entry['awg_binding'] == {'provider': 'upcloud', 'environment': 'prod', 'instance': 'awg0'}
    assert second['client_registry']['new-phone']['awg_binding'] is None
    assert not registry_errors(first, context=lifecycle.profile(nodes['upcloud:prod']['cohort']))
    for host, doc in result.items():
        assert doc['client_registry']['phone'] == before[host]['client_registry']['phone']
        assert doc['xray']['reality_private_key'] == before[host]['xray']['reality_private_key']
        assert doc['hysteria']['key_pem'] == before[host]['hysteria']['key_pem']
    assert first['xray']['clients'][-1] == second['xray']['clients'][-1]
    assert second['hysteria'] == before['vultr:standby']['hysteria']
    assert second['amneziawg_secrets'] == before['vultr:standby']['amneziawg_secrets']
    assert resolve_binding(first, lifecycle.profile('device-full-tailnet'), 'new-phone', 'upcloud:prod').peer['allowed_ips'] == {
        'ipv4': '10.66.66.3/32', 'ipv6': 'fd42:42:42::3/128'}


def test_p0_only_without_awg_or_hysteria_authority(fleet):
    docs, _ = fleet
    doc = docs['upcloud:prod']
    del doc['amneziawg_secrets'], doc['hysteria']
    doc['client_registry'] = {}
    result = lifecycle.issue({'upcloud:prod': doc}, {'upcloud:prod': {'cohort': 'p0-minimal'}},
                             'new', ['upcloud:prod'], '2026-10-22T00:00:00Z')['upcloud:prod']
    assert 'amneziawg_secrets' not in result and result['client_registry']['new']['awg_binding'] is None


def test_revoke_finds_old_nodes_and_all_variants_independent_of_registry(fleet):
    docs, _nodes = fleet
    for doc in docs.values():
        doc['client_registry']['phone']['hosts'] = ['upcloud:retired']
        doc['xray']['cohorts'] = [{'name': 'test', 'clients': ['phone', 'survivor']}]
        doc['snell_secrets'] = {'variants': [{'id': n, 'psk': str(n), 'users': [
            {'name': 'phone', 'userkey': 'old' + str(n)}, {'name': 'other', 'userkey': 'keep' + str(n)}]} for n in (1, 2)]}
        doc['naive_secrets'] = {'clients': [{'name': 'phone', 'username': 'private-identity', 'password': 'old'},
                                          {'name': 'other', 'username': 'retained', 'password': 'keep'}]}
    before = copy.deepcopy(docs)
    result = lifecycle.revoke(docs, 'phone')
    assert docs == before
    for host, doc in result.items():
        assert lifecycle.discover(doc, 'phone') == {'registry': 1}
        assert doc['client_registry']['phone']['status'] == 'revoked'
        assert doc['client_registry']['phone']['awg_binding'] is None
        assert doc['xray']['cohorts'][0]['clients'] == ['survivor']
        assert doc['naive_secrets']['clients'] == before[host]['naive_secrets']['clients'][1:]
        assert all(len(variant['users']) == 1 for variant in doc['snell_secrets']['variants'])
    assert lifecycle.revoke(result, 'phone') == result


def test_issuance_refuses_existing_hidden_authority(fleet):
    docs, nodes = fleet
    docs['vultr:standby']['client_registry'] = {}
    before = copy.deepcopy(docs)
    with pytest.raises(ValueError, match='already-exists'):
        lifecycle.issue(docs, nodes, 'phone', ['upcloud:prod'], '2026-10-22T00:00:00Z')
    assert docs == before


def test_xray_cohort_membership_must_be_explicit(fleet):
    docs, nodes = fleet
    docs['upcloud:prod']['xray']['cohorts'] = [{'name': 'raw', 'clients': ['phone']}]
    before = copy.deepcopy(docs)
    with pytest.raises(ValueError):
        lifecycle.issue(docs, nodes, 'fresh', ['upcloud:prod'], '2026-10-22T00:00:00Z')
    assert docs == before


@pytest.mark.parametrize('fault', ['duplicate', 'routed', 'invalid-name'])
def test_discovery_refuses_ambiguous_or_non_device_rows(fleet, fault):
    docs, _ = fleet
    doc = docs['upcloud:prod']
    name = 'phone'
    if fault == 'duplicate':
        doc['xray']['clients'].append(copy.deepcopy(doc['xray']['clients'][0]))
    elif fault == 'routed':
        doc['amneziawg_secrets']['instances'][0]['peers'][0]['address_kind'] = 'routed'
    else:
        name = '../phone'
    with pytest.raises(ValueError):
        lifecycle.revoke(docs, name)


def test_revoke_transformation_is_idempotent_without_remaining_device_authority(fleet):
    docs, _ = fleet
    before = copy.deepcopy(docs)
    assert lifecycle.revoke(docs, 'missing') == before
    assert docs == before
