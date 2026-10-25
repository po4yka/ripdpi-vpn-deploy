"""Cloud state and pinned SSH boundaries; no fixture is live provider proof."""
from __future__ import annotations

import copy
import base64
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import cloud_promotion_scope as scope
import install_liveness_sentinel as installer
from recovery_io import canonical


def state_file(root, provider, environment, alias, address):
    kind, name = scope.PROVIDERS[provider]
    server = {'id': '00000000-0000-4000-8000-000000000001', name: alias}
    if provider == 'upcloud':
        server['network_interface'] = [{'type': 'public', 'ip_address_family': 'IPv4', 'ip_address': address}]
    elif provider == 'scaleway':
        server['public_ips'] = [{'family': 'inet', 'address': address}]
    else:
        server['main_ip'] = address
    data = {'version': 4, 'resources': [{'mode': 'managed', 'type': kind, 'name': 'vpn', 'instances': [{'attributes': server}]}],
            'outputs': {key: {'value': value} for key, value in
                        {'server_ipv4': address, 'server_hostname': alias, 'ssh_port': 22, 'admin_user': 'deploy'}.items()}}
    path = root / 'terraform/providers' / provider / ('terraform.tfstate' if environment == 'prod'
             else f'terraform.tfstate.d/{environment}/terraform.tfstate')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(data))
    path.chmod(0o600)
    row = {'provider': provider, 'environment': environment, 'inventory_alias': alias,
           'server_id': server['id'], 'state_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return row, path, data


@pytest.mark.parametrize('provider', ['upcloud', 'scaleway', 'vultr'])
def test_canonical_state_binds_exact_resource_and_public_address(tmp_path, monkeypatch, provider):
    monkeypatch.setattr(scope, 'ROOT', tmp_path)
    row, path, data = state_file(tmp_path, provider, 'prod', 'probe-node', '1.1.1.1')
    actual = scope._state(row)
    assert actual == {'id': row['server_id'], 'provider': provider, 'public_ipv4': ['1.1.1.1'],
                      'ssh_port': 22, 'admin_user': 'deploy'}
    data['outputs']['server_ipv4']['value'] = '8.8.8.8'
    path.write_bytes(canonical(data))
    with pytest.raises(ValueError):
        scope._state(row)
    row['state_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        scope._state(row)


@pytest.mark.parametrize('fault', ['deposed', 'tainted', 'old-version'])
def test_ambiguous_replacement_state_cannot_authorize_onboarding(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(scope, 'ROOT', tmp_path)
    row, path, data = state_file(tmp_path, 'upcloud', 'prod', 'probe-node', '1.1.1.1')
    if fault == 'old-version':
        data['version'] = 3
    elif fault == 'tainted':
        data['resources'][0]['instances'][0]['status'] = 'tainted'
    else:
        data['resources'][0]['instances'].append({**copy.deepcopy(data['resources'][0]['instances'][0]), 'deposed': 'deadbeef'})
    path.write_bytes(canonical(data))
    row['state_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        scope._state(row)


@pytest.mark.parametrize('fault', ['state-list', 'resource-null', 'instance-null', 'interface-null'])
def test_malformed_state_shapes_are_categorical(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(scope, 'ROOT', tmp_path)
    row, path, data = state_file(tmp_path, 'upcloud', 'prod', 'probe-node', '1.1.1.1')
    if fault == 'state-list':
        data = []
    elif fault == 'resource-null':
        data['resources'] = [None]
    elif fault == 'instance-null':
        data['resources'][0]['instances'] = [None]
    else:
        data['resources'][0]['instances'][0]['attributes']['network_interface'] = [None]
    path.write_bytes(canonical(data))
    row['state_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='cloud-state-refused'):
        scope._state(row)


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'ROOT', tmp_path)
    target, _, _ = state_file(tmp_path, 'upcloud', 'p0-node', 'node-a', '1.1.1.1')
    sentinel, _, _ = state_file(tmp_path, 'scaleway', 'p1-node', 'node-b', '8.8.8.8')
    key = tmp_path / 'identity'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True, capture_output=True)
    public = key.with_suffix('.pub').read_text().split()
    pins = tmp_path / 'known_hosts'
    pins.write_text('8.8.8.8 ' + ' '.join(public[:2]) + '\n')
    pins.chmod(0o600)
    fingerprint = subprocess.check_output(['ssh-keygen', '-lf', str(key.with_suffix('.pub')), '-E', 'sha256'], text=True).split()[1]
    fingerprint = base64.b64decode(fingerprint.split(':')[1] + '=').hex()
    manifest = {'schema_version': 1, 'source_revision': 'a' * 40, 'target': target, 'sentinel': sentinel,
                'state_directory': str(tmp_path / 'outputs'), 'sops_file': str(tmp_path / 'source.sops.yaml'),
                'age_key_file': str(tmp_path / 'age.key'), 'cleanup_manifest': None,
                'sentinel_known_hosts': str(pins), 'sentinel_identity': str(key)}
    path = tmp_path / 'provisioning.json'
    path.write_bytes(canonical(manifest))
    path.chmod(0o600)
    identity = {'DEPLOY_SOURCE_REVISION': 'a' * 40, 'DEPLOYABLE_SOURCE_DIGEST': 'b' * 64}
    original_module = scope.module
    monkeypatch.setattr(scope, 'module', lambda name: SimpleNamespace(source_identity=lambda *a, **kw: identity)
                        if name == 'deploy-controller' else original_module(name))
    value = {'host': 'upcloud:p0-node', 'target_identity': {'inventory_alias': 'node-a',
             'public_service_address_sha256': hashlib.sha256(b'1.1.1.1').hexdigest(), 'deployable_digest': 'b' * 64},
             'inputs': {'provisioning_manifest': str(path), 'sops_file': manifest['sops_file'],
                        'age_key_file': manifest['age_key_file']},
             'liveness': {'sentinels': [{'ssh_target': 'probe-cloud', 'ssh_transport_host': '8.8.8.8',
                                       'ssh_host_key_alias': '8.8.8.8', 'vantage': 'external'}]}}
    settings = {'hostname': '8.8.8.8', 'hostkeyalias': '8.8.8.8', 'user': 'deploy', 'port': '22',
                'identityfile': str(key), 'userknownhostsfile': str(pins), 'identitiesonly': 'yes',
                'identityagent': 'none', 'globalknownhostsfile': '/dev/null'}
    probe = {'hostname': 'node-b', 'host_key_sha256': fingerprint, 'build_environment': 'prod', 'bootstrap_ready': True}
    calls = []
    def run(argv, *, environment, **kwargs):
        assert 'PROVIDER_TOKEN' not in environment
        calls.append(argv)
        if argv[0] == 'ssh-keygen':
            return subprocess.check_output(argv)
        assert 'StrictHostKeyChecking=yes' in argv
        if '-G' in argv:
            return ''.join(f'{key} {v}\n' for key, v in settings.items()).encode()
        assert 'IdentityAgent=none' in argv and 'ProxyCommand=none' in argv
        return canonical(probe)
    monkeypatch.setattr(installer, '_run', run)
    return value, manifest, path, settings, probe, calls


def test_cloud_scope_requires_distinct_state_bound_resources_and_live_original_pin(cloud):
    value, manifest, _, _, _, calls = cloud
    actual, server, outputs = scope.scope(value, {'PROVIDER_TOKEN': 'must-not-leave-controller'})
    assert actual == manifest
    assert server['sentinel_identity']['hostname'] == 'node-b'
    assert server['sentinel_identity']['provider'] == 'scaleway'
    assert set(outputs) == {'authority', 'liveness', 'registry', 'proof'}
    assert len(calls) == 3


def test_nested_cleanup_authority_path_must_be_absolute(cloud):
    value, manifest, path, _, _, calls = cloud
    manifest['cleanup_manifest'] = 'cleanup.json'
    path.write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match='path-refused'):
        scope.scope(value, {})
    assert calls == []


@pytest.mark.parametrize('fault', ['same-resource', 'same-address', 'source', 'wrong-pin', 'wrong-build',
                                  'wrong-host', 'local-transport', 'foreign-identity', 'unscoped-key', 'global-pins'])
def test_cloud_scope_refuses_changed_or_local_sentinel(cloud, fault):
    value, manifest, path, settings, probe, _ = cloud
    if fault == 'same-resource':
        manifest['sentinel'] = copy.deepcopy(manifest['target'])
    elif fault == 'same-address':
        value['liveness']['sentinels'][0]['ssh_transport_host'] = '1.1.1.1'
    elif fault == 'source':
        manifest['source_revision'] = 'c' * 40
    elif fault == 'wrong-pin':
        probe['host_key_sha256'] = 'c' * 64
    elif fault == 'wrong-build':
        probe['build_environment'] = 'staging'
    elif fault == 'wrong-host':
        probe['hostname'] = 'personal-device'
    elif fault == 'local-transport':
        value['liveness']['sentinels'][0]['ssh_transport_host'] = '127.0.0.1'
    elif fault == 'foreign-identity':
        settings['identityfile'] = '/unrelated/private-key'
    elif fault == 'unscoped-key':
        settings['identitiesonly'] = 'no'
    else:
        settings['globalknownhostsfile'] = '/etc/ssh/ssh_known_hosts'
    path.write_bytes(canonical(manifest))
    with pytest.raises(ValueError):
        scope.scope(value, {})


def test_tilde_identity_resolves_to_the_exact_admitted_key(cloud, monkeypatch):
    value, manifest, _, settings, _, _ = cloud
    key = Path(manifest['sentinel_identity'])
    monkeypatch.setenv('HOME', str(key.parent))
    settings['identityfile'] = '~/' + key.name
    assert scope.scope(value, {})[1]['sentinel_identity']['hostname'] == 'node-b'


def test_nondefault_sentinel_port_uses_one_canonical_pin_alias(cloud):
    value, manifest, path, settings, _, _ = cloud
    state_path = scope.ROOT / 'terraform/providers/scaleway/terraform.tfstate.d/p1-node/terraform.tfstate'
    data = json.loads(state_path.read_bytes())
    data['outputs']['ssh_port']['value'] = 2222
    state_path.write_bytes(canonical(data))
    manifest['sentinel']['state_sha256'] = hashlib.sha256(state_path.read_bytes()).hexdigest()
    path.write_bytes(canonical(manifest))
    alias = '[8.8.8.8]:2222'
    value['liveness']['sentinels'][0]['ssh_host_key_alias'] = alias
    settings.update(port='2222', hostkeyalias=alias)
    pins = Path(manifest['sentinel_known_hosts'])
    pins.write_text(pins.read_text().replace('8.8.8.8 ', alias + ' '))
    _, observed, _ = scope.scope(value, {})
    assert observed['sentinel_identity']['hostname'] == 'node-b'


def test_source_errors_are_categorical_before_any_ssh(cloud, monkeypatch):
    value, _, _, _, _, calls = cloud
    class SourceError(Exception):
        pass
    def fail(*a, **kw):
        raise SourceError('private-path-and-diagnostic')
    original = scope.module
    monkeypatch.setattr(scope, 'module', lambda name: SimpleNamespace(source_identity=fail, DeployError=SourceError)
                        if name == 'deploy-controller' else original(name))
    with pytest.raises(ValueError, match='cloud-source-identity-refused') as error:
        scope.scope(value, {})
    assert error.value.__cause__ is None and calls == []


@pytest.mark.parametrize(('marker', 'expected'), [('provisioned_by=cloud-init\nnext_stage=ansible\nbuild_env=prod\n', 'prod'),
                                               ('build_env=prod\nbuild_env=staging\n', '')])
def test_live_probe_parses_the_real_cloud_init_build_marker(tmp_path, monkeypatch, capsys, marker, expected):
    import pathlib
    import socket
    public = 'ssh-ed25519 ' + base64.b64encode(b'fixture-key-blob').decode()
    original_read = pathlib.Path.read_text
    original_file = pathlib.Path.is_file
    def read(path, *a, **kw):
        if str(path) == '/etc/vpn-build-id':
            return marker
        if str(path) == '/etc/ssh/ssh_host_ed25519_key.pub':
            return public
        return original_read(path, *a, **kw)
    monkeypatch.setattr(pathlib.Path, 'read_text', read)
    monkeypatch.setattr(pathlib.Path, 'is_file', lambda p: True if str(p) == '/var/lib/cloud-init-vpn-bootstrap.done' else original_file(p))
    monkeypatch.setattr(socket, 'gethostname', lambda: 'probe-node')
    exec(compile(scope.SENTINEL_PROBE, 'fixed-sentinel-probe', 'exec'), {})
    result = json.loads(capsys.readouterr().out)
    assert result['build_environment'] == expected
    assert result['bootstrap_ready'] is True
