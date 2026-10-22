"""Real device authority preparation preserves identity and independent target state."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import device_migration_credentials as migration
import pytest
import yaml
from awg_client import enroll, host_context
from awg_device_binding import public_key, registry_errors, resolve_binding
from encrypted_client_document import operate

ROOT = Path(__file__).resolve().parents[2]


def key(number):
    return base64.b64encode(bytes([number]) * 32).decode()


@pytest.fixture
def authorities():
    source = yaml.safe_load((ROOT / 'tests/fixtures/secrets-sample.yml').read_text())
    source_node = {'host': 'upcloud:prod', 'cohort': 'device-full-tailnet', 'secrets_file': '/private/source.sops.yaml'}
    target_node = {'host': 'upcloud:green', 'cohort': 'device-full-tailnet', 'secrets_file': '/private/target.sops.yaml',
                   'awg_instances': {'awg0': 'awg1'}}
    entry = source['client_registry']['phone']
    entry['cohorts'] = [source_node['cohort']]
    entry['delivery_sources'] = [source_node['secrets_file']]
    entry['awg_delivery_host'] = source_node['host']
    entry['delivery_options'] = {'hosts': list(entry['hosts']), 'cohorts': list(entry['cohorts']),
                                 'awg_host': entry['awg_delivery_host'], 'format': 'ripdpi',
                                 'expires': entry['token_expires'], 'utls': ''}
    target = copy.deepcopy(source)
    target['client_registry'] = {}
    target['xray']['clients'] = [item for item in target['xray']['clients'] if item['name'] != 'phone']
    target['xray']['reality_private_key'] = 'independent-target-server-authority'
    target['hysteria']['clients'] = [item for item in target['hysteria']['clients'] if item['name'] != 'phone']
    target['hysteria']['key_pem'] = 'independent-target-tls-authority'
    instance = target['amneziawg_secrets']['instances'][0]
    instance.update(name='awg1', server_private_key=key(21), address_v4='10.88.0.1/29', address_v6='fd42:88::1/120', peers=[])
    target, _ = enroll(target, host_context(target_node['cohort']), 'other', target_node['host'], 'awg1')
    target['unrelated'] = {'private': 'synthetic-retained-target-marker'}
    return source, target, source_node, target_node


def prepare(authorities, clients=None):
    source, target, source_node, target_node = authorities
    return migration.prepare_credentials(source, target, clients or ['phone'], source_node, target_node)


def test_four_baseline_preparation_keeps_device_keys_and_target_server_authority(authorities):
    source, target, source_node, target_node = authorities
    source['client_registry']['phone']['migration_delivery'] = {'prior': 'receipt-context'}
    originals = copy.deepcopy(authorities)
    result = prepare(authorities)
    assert authorities == originals
    assert result['xray']['clients'][-1] == source['xray']['clients'][0]
    assert result['hysteria']['clients'][-1] == source['hysteria']['clients'][0]
    assert {k: v for k, v in result['xray'].items() if k != 'clients'} == {k: v for k, v in target['xray'].items() if k != 'clients'}
    assert {k: v for k, v in result['hysteria'].items() if k != 'clients'} == {k: v for k, v in target['hysteria'].items() if k != 'clients'}
    assert result['unrelated'] == target['unrelated']
    assert result['client_registry']['other'] == target['client_registry']['other']
    original = resolve_binding(source, host_context(source_node['cohort']), 'phone', source_node['host'])
    moved = resolve_binding(result, host_context(target_node['cohort']), 'phone', target_node['host'])
    assert moved.instance['server_private_key'] == target['amneziawg_secrets']['instances'][0]['server_private_key']
    assert moved.peer['public_key'] == original.peer['public_key']
    assert moved.peer['preshared_key'] == original.peer['preshared_key']
    assert moved.peer['allowed_ips'] == {'ipv4': '10.88.0.3/32', 'ipv6': 'fd42:88::3/128'}
    entry = result['client_registry']['phone']
    assert entry['awg_private_key'] == source['client_registry']['phone']['awg_private_key']
    assert entry['awg_binding'] == {'provider': 'upcloud', 'environment': 'green', 'instance': 'awg1'}
    assert entry['hosts'] == [target_node['host']] and entry['cohorts'] == [target_node['cohort']]
    assert entry['delivery_sources'] == [target_node['secrets_file']]
    assert entry['delivery_options']['awg_host'] == target_node['host']
    assert entry['status'] == 'issued' and entry['formats'] == [] and entry['last_payload_identity'] == {}
    assert entry['token_hash_prefix'] == '' and 'migration_delivery' not in entry
    assert not registry_errors(result, context=host_context(target_node['cohort']))


def test_repeat_reuses_exact_peer_addresses_and_existing_delivery_metadata(authorities):
    source, _, source_node, target_node = authorities
    prepared = prepare(authorities)
    prepared['client_registry']['phone'].update(status='delivered', token_hash_prefix='ab12cd34', formats=['ripdpi'])
    before = copy.deepcopy(prepared)
    assert migration.prepare_credentials(source, prepared, ['phone'], source_node, target_node) == before
    assert prepared == before


@pytest.mark.parametrize('cohort', ['p0-minimal', 'p2-udp', 'device-full-tailnet'])
def test_subset_profiles_transfer_only_consumed_transports(authorities, cohort):
    source, target, source_node, target_node = authorities
    source_node['cohort'] = target_node['cohort'] = cohort
    source['client_registry']['phone']['cohorts'] = [cohort]
    source['client_registry']['phone']['delivery_options']['cohorts'] = [cohort]
    result = prepare(authorities)
    if cohort == 'p0-minimal':
        assert result['hysteria'] == target['hysteria']
        assert result['amneziawg_secrets'] == target['amneziawg_secrets']
        assert result['client_registry']['phone']['awg_binding'] is None
    if cohort == 'p2-udp':
        assert result['xray'] == target['xray']


def test_alternate_hosts_sources_and_selections_remain_exact(authorities):
    source, _, _, target_node = authorities
    entry = source['client_registry']['phone']
    entry['hosts'].append('vultr:alternate')
    entry['cohorts'].append('p0-minimal')
    entry['delivery_sources'].append('/private/alternate.sops.yaml')
    entry['delivery_options'].update(hosts=list(entry['hosts']), cohorts=list(entry['cohorts']))
    result = prepare(authorities)['client_registry']['phone']
    assert result['hosts'] == [target_node['host'], 'vultr:alternate']
    assert result['cohorts'] == [target_node['cohort'], 'p0-minimal']
    assert result['delivery_sources'] == [target_node['secrets_file'], '/private/alternate.sops.yaml']


@pytest.mark.parametrize('fault', ['xray-conflict', 'hy-conflict', 'xray-duplicate', 'hy-missing', 'awg-key',
    'awg-psk', 'pool-v4', 'pool-v6', 'source-binding', 'source-key', 'source-status', 'registry-status',
    'missing-instance', 'profile-downgrade', 'name', 'duplicate-selection', 'invalid-source-path'])
def test_refusal_preserves_both_authorities(authorities, fault):
    source, target, source_node, target_node = authorities
    clients = ['phone']
    if fault in {'xray-conflict', 'hy-conflict', 'xray-duplicate'}:
        section = 'hysteria' if fault == 'hy-conflict' else 'xray'
        item = copy.deepcopy(source[section]['clients'][0])
        if fault == 'xray-duplicate':
            source[section]['clients'].append(item)
        else:
            item['password' if section == 'hysteria' else 'uuid'] = 'conflicting-device-authority'
            target[section]['clients'].append(item)
    elif fault == 'hy-missing':
        source['hysteria']['clients'] = []
    elif fault in {'awg-key', 'awg-psk', 'registry-status'}:
        target = prepare(authorities)
        authorities = (source, target, source_node, target_node)
        peer = target['amneziawg_secrets']['instances'][0]['peers'][-1]
        if fault == 'awg-psk':
            peer['preshared_key'] = key(30)
        elif fault == 'awg-key':
            peer['public_key'] = public_key(key(31))
            target['client_registry']['phone']['awg_private_key'] = key(31)
            target['client_registry']['phone']['awg_public_key_fingerprint'] = 'sha256:' + hashlib.sha256(peer['public_key'].encode()).hexdigest()[:16]
        else:
            target['client_registry']['phone']['status'] = 'revoked'
    elif fault.startswith('pool-'):
        instance = target['amneziawg_secrets']['instances'][0]
        instance['address_v4' if fault == 'pool-v4' else 'address_v6'] = '10.88.0.1/30' if fault == 'pool-v4' else 'fd42:88::1/127'
        if fault == 'pool-v6':
            instance['peers'] = []
            target['client_registry'] = {}
    elif fault == 'source-binding':
        source['client_registry']['phone']['awg_binding']['environment'] = 'other'
    elif fault == 'source-key':
        source['client_registry']['phone']['awg_private_key'] = key(29)
    elif fault == 'source-status':
        source['client_registry']['phone']['status'] = 'revoked'
    elif fault == 'missing-instance':
        target_node['awg_instances'] = {'awg0': 'missing'}
    elif fault == 'profile-downgrade':
        target_node['cohort'] = 'p0-minimal'
    elif fault == 'name':
        clients = ['../../private-marker']
    elif fault == 'duplicate-selection':
        clients = ['phone', 'phone']
    elif fault == 'invalid-source-path':
        source['client_registry']['phone']['delivery_sources'] = ['/private/other.sops.yaml']
    before = copy.deepcopy(authorities)
    with pytest.raises(ValueError):
        migration.prepare_credentials(source, target, clients, source_node, target_node)
    assert authorities == before


def test_xray_memberships_preserve_exact_named_target_listeners(authorities):
    source, target, _, _ = authorities
    source['xray']['cohorts'] = [{'name': 'vision', 'clients': ['phone'], 'port': 443, 'flow_mode': 'vision'}]
    target['xray']['cohorts'] = [{'name': 'vision', 'clients': ['watchdog'], 'port': 8443, 'flow_mode': 'vision'}]
    result = prepare(authorities)
    assert result['xray']['cohorts'] == [{'name': 'vision', 'clients': ['watchdog', 'phone'], 'port': 8443, 'flow_mode': 'vision'}]
    assert prepare((source, result, authorities[2], authorities[3])) == result
    target['xray']['cohorts'][0]['name'] = 'unrelated'
    before = copy.deepcopy(target)
    with pytest.raises(ValueError):
        prepare(authorities)
    assert target == before


def test_optional_snell_and_naive_retain_target_server_values(authorities, monkeypatch):
    source, target, _, _ = authorities
    original_context = migration.context
    def context(cohort):
        result = original_context(cohort)
        result['vpn'].update(enable_snell=True, enable_naive=True)
        return result
    monkeypatch.setattr(migration, 'context', context)
    variants = context('device-full-tailnet')['snell']['variants']
    source['snell_secrets'] = {'variants': [{'id': v['id'], 'psk': f'source-server-key-{i}',
        'users': [{'name': 'phone', 'userkey': f'physical-device-userkey-{i}'}]} for i, v in enumerate(variants)]}
    target['snell_secrets'] = {'variants': [{'id': v['id'], 'psk': f'target-server-key-{i}', 'users': []}
        for i, v in enumerate(variants)]}
    source['naive_secrets'] = {'server_name': 'source.example.test', 'clients': [
        {'name': 'phone', 'username': 'device-account', 'password': 'synthetic-naive-password-123456'}]}
    target['naive_secrets'] = {'server_name': 'target.example.test', 'clients': []}
    result = prepare(authorities)
    assert result['naive_secrets'] == {**target['naive_secrets'], 'clients': source['naive_secrets']['clients']}
    for original, prepared, target_variant in zip(source['snell_secrets']['variants'], result['snell_secrets']['variants'], target['snell_secrets']['variants'], strict=True):
        assert prepared['users'] == original['users'] and prepared['psk'] == target_variant['psk']


def test_encrypted_preparation_commit_and_failed_callback_preserve_source(authorities, tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    identity = tmp_path / 'age.key'
    subprocess.run(['age-keygen', '-o', str(identity)], capture_output=True, check=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(identity))
    source, target, source_node, target_node = authorities
    path = tmp_path / 'target.sops.yaml'
    cipher = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json', '--output-type', 'yaml', '/dev/stdin'],
                            input=json.dumps(target).encode(), capture_output=True, check=True).stdout
    path.write_bytes(cipher)
    path.chmod(0o600)
    before_source = copy.deepcopy(source)
    def transform(document):
        return migration.prepare_credentials(source, document, ['phone'], source_node, target_node), {}
    def fail(_mark):
        raise ValueError('synthetic-transaction-refusal')
    with pytest.raises(ValueError):
        operate(path, transform, before_publish=fail)
    assert path.read_bytes() == cipher
    operate(path, transform)
    actual = json.loads(subprocess.check_output(['sops', '--decrypt', '--output-type', 'json', str(path)]))
    assert actual == prepare(authorities) and source == before_source
    assert target['unrelated']['private'].encode() not in path.read_bytes()
    committed = path.read_bytes()
    operate(path, transform)
    assert path.read_bytes() == committed
    assert stat_mode(path) == 0o600
    assert not list(tmp_path.glob('.target.sops.yaml.client.*'))


def stat_mode(path):
    return os.stat(path).st_mode & 0o777


def test_multiple_devices_allocate_once_without_replacing_identity(authorities):
    source, target, source_node, target_node = authorities
    source, _ = enroll(source, host_context(source_node['cohort']), 'tablet', source_node['host'], 'awg0', all_profiles=True)
    original = copy.deepcopy(source)
    result = migration.prepare_credentials(source, target, ['phone', 'tablet'], source_node, target_node)
    peers = result['amneziawg_secrets']['instances'][0]['peers']
    assert [item['allowed_ips']['ipv4'] for item in peers] == ['10.88.0.2/32', '10.88.0.3/32', '10.88.0.4/32']
    assert [item['allowed_ips']['ipv6'] for item in peers] == ['fd42:88::2/128', 'fd42:88::3/128', 'fd42:88::4/128']
    assert source == original
    assert migration.prepare_credentials(source, result, ['phone', 'tablet'], source_node, target_node) == result


def test_target_allocator_reserves_other_instance_server_and_peer_claims(authorities):
    source, target, _, target_node = authorities
    second = copy.deepcopy(target['amneziawg_secrets']['instances'][0])
    second.update(name='awg2', listen_port=51822, server_private_key=key(26),
                  address_v4='10.89.0.1/29', address_v6='fd42:89::1/120', peers=[])
    target['amneziawg_secrets']['instances'].append(second)
    target, _ = enroll(target, host_context(target_node['cohort']), 'second', target_node['host'], 'awg2')
    target['amneziawg_secrets']['instances'][1].update(address_v4='10.88.0.4/29', address_v6='fd42:88::4/120')
    second_peer = target['amneziawg_secrets']['instances'][1]['peers'][0]
    second_peer['allowed_ips'] = {'ipv4': '10.88.0.3/32', 'ipv6': 'fd42:88::3/128'}
    result = prepare((source, target, authorities[2], target_node))
    moved = resolve_binding(result, host_context(target_node['cohort']), 'phone', target_node['host'])
    assert moved.peer['allowed_ips'] == {'ipv4': '10.88.0.5/32', 'ipv6': 'fd42:88::5/128'}


def test_missing_source_uuid_cannot_prepare_invalid_authentication(authorities):
    source, _, _, _ = authorities
    source['xray']['clients'][0]['uuid'] = 'not-an-authentication-uuid'
    with pytest.raises(ValueError):
        prepare(authorities)
