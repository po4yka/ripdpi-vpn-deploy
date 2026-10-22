"""Migration selection, explicit IO budgets and exact canonical verification."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import device_migration_io as io
import pytest
import yaml
from fleet_inspection import InspectionError, bounded_command, select_hosts
from test_fleet_inspection import inventory


@pytest.fixture
def plan(tmp_path):
    tmp_path.chmod(0o700)
    path = inventory(tmp_path, 'provider=upcloud env=blue')
    path.write_text(path.read_text().replace('node-b ansible_host', 'node-b provider=upcloud env=green ansible_host') + '\n[vpn-test]\nnode-b\n')
    pins = tmp_path / 'known_hosts'
    pins.write_text('synthetic pinned hosts\n')
    source = {'host': 'upcloud:blue', 'alias': 'node-a', 'cohort': 'test', 'secrets_file': str(tmp_path / 'blue.yaml')}
    target = {'host': 'upcloud:green', 'alias': 'node-b', 'cohort': 'test', 'secrets_file': str(tmp_path / 'green.yaml'), 'awg_instances': {}}
    for node in (source, target):
        Path(node['secrets_file']).write_text('synthetic private authority')
        Path(node['secrets_file']).chmod(0o600)
    document = {'schema_version': 1, 'id': '11111111-1111-4111-8111-111111111111', 'inventory': str(path), 'known_hosts': str(pins),
                'source': source, 'target': target, 'publication': {'source_alias': 'node-a', 'target_alias': 'node-b',
                                                                'directory': '/var/lib/vpn-subscription', 'origin': 'https://delivery.example:8444'}}
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(document))
    plan_path.chmod(0o600)
    return document, plan_path


def test_private_plan_and_exact_inventory_cohort_binding(plan):
    document, path = plan
    assert io.load_plan(path) == document
    admitted = io.LocalIO(document)
    assert admitted.hosts['node-a']['cohorts'] == ['test']
    assert admitted.endpoint('upcloud:green') == '192.0.2.2'
    changed = copy.deepcopy(document)
    changed['target']['cohort'] = 'other'
    with pytest.raises(ValueError, match='identity-mismatch'):
        io.LocalIO(changed)
    Path(document['known_hosts']).write_text('changed pins\n')
    with pytest.raises(ValueError, match='pins-changed'):
        admitted.revalidate()


@pytest.mark.parametrize('fault', ['mode', 'symlink', 'duplicate', 'unknown', 'origin-user', 'path-expansion', 'retiring-publisher'])
def test_plan_refuses_unsafe_inputs_before_runtime_io(plan, fault):
    document, path = plan
    if fault == 'mode':
        path.chmod(0o644)
    elif fault == 'symlink':
        target = path.with_name('actual.json')
        path.rename(target)
        path.symlink_to(target)
    elif fault == 'duplicate':
        path.write_text(path.read_text().replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
    else:
        if fault == 'unknown':
            document['unknown'] = True
        elif fault == 'origin-user':
            document['publication']['origin'] = 'https://secret@delivery.example'
        elif fault == 'path-expansion':
            document['target']['secrets_file'] = '/tmp/$(touch owned).yaml'
        else:
            document['publication']['target_alias'] = document['source']['alias']
        path.write_text(json.dumps(document))
    with pytest.raises((ValueError, OSError)):
        io.load_plan(path)


def test_migration_lock_is_exclusive_and_never_follows_foreign_links(plan):
    document, _ = plan
    with io.migration_lock(document):
        with pytest.raises(BlockingIOError):
            with io.migration_lock(document):
                pytest.fail('second writer acquired the same authority')
    lock = Path(document['source']['secrets_file'] + '.migration.lock')
    lock.unlink()
    lock.symlink_to(document['known_hosts'])
    with pytest.raises(OSError):
        with io.migration_lock(document):
            pytest.fail('followed a foreign lock')


def test_publisher_uses_strict_pins_and_bounded_stdin_not_secret_argv(plan, monkeypatch):
    document, _ = plan
    admitted = io.LocalIO(document)
    calls = []
    def command(argv, **kwargs):
        calls.append((argv, kwargs))
        return b'{"schema_version":1}'
    monkeypatch.setattr(io, 'bounded_command', command)
    admitted.publisher('node-b', 'publish', 'a' * 64, None, b'private-payload-marker')
    argv, kwargs = calls[0]
    assert 'StrictHostKeyChecking=yes' in argv and 'ProxyCommand=none' in argv
    assert 'private-payload-marker' not in ' '.join(argv)
    assert kwargs['input_limit'] == 4 * 1024 * 1024
    assert json.loads(kwargs['input_bytes'])['expected_document_sha256'] is None


def test_gate_scopes_exact_target_and_cleans_plaintext_on_failure(plan, monkeypatch):
    document, _ = plan
    admitted = io.LocalIO(document)
    monkeypatch.setenv('MAKEFLAGS', '--eval=bad')
    monkeypatch.setenv('ANSIBLE_SKIP_TAGS', 'all')
    monkeypatch.setenv('TAG_ON_SUCCESS', '1')
    calls, paths = [], []
    secret = {'synthetic': 'private-target-value'}
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        path = Path(next(a.split('=', 1)[1] for a in argv if a.startswith('SECRETS_FILE=')))
        paths.append(path)
        assert path.stat().st_mode & 0o777 == 0o600
        assert yaml.safe_load(path.read_text()) == secret
        assert 'ANSIBLE_LIMIT=node-b' in argv and 'ENV=green' in argv and 'TAG_ON_SUCCESS=0' in argv
        assert 'MAKEFLAGS' not in kwargs['environment'] and 'ANSIBLE_SKIP_TAGS' not in kwargs['environment']
        frozen = Path(kwargs['environment']['ANSIBLE_INVENTORY'])
        assert frozen != Path(document['inventory']) and frozen.stat().st_mode & 0o777 == 0o600
        assert 'StrictHostKeyChecking=yes' in frozen.read_text()
        assert 'ControlMaster=no' in frozen.read_text()
        assert 'ProxyCommand=none' in frozen.read_text()
        assert (frozen.parent / 'known_hosts').read_bytes() == Path(document['known_hosts']).read_bytes()
        assert (frozen.parent / 'identity').read_bytes() == (Path(document['inventory']).parent / 'key').read_bytes()
        assert 'UserKnownHostsFile=' in kwargs['environment']['ANSIBLE_SSH_ARGS']
        return (0 if len(calls) == 1 else 1), b'private-error-not-propagated'
    monkeypatch.setattr(io, 'run_command', run)
    with pytest.raises(ValueError, match='verification-failed'):
        admitted.verify_target(secret)
    assert [argv[3] for argv, _ in calls] == ['verify', 'smoke-test']
    assert all(not path.exists() for path in paths)


def test_explicit_large_stdin_keeps_default_budget_and_absolute_ceiling():
    raw = b'x' * 200000
    command = [sys.executable, '-c', 'import sys; print(len(sys.stdin.buffer.read()))']
    with pytest.raises(InspectionError, match='input-limit'):
        bounded_command(command, input_bytes=raw)
    assert bounded_command(command, input_bytes=raw, input_limit=300000).strip() == b'200000'
    with pytest.raises(InspectionError, match='input-limit'):
        bounded_command(command, input_limit=4 * 1024 * 1024 + 1)


def test_optional_cohort_projection_leaves_existing_inventory_contract_unchanged(plan):
    document, _ = plan
    normal = select_hosts(document['inventory'], ['node-a'])
    projected = select_hosts(document['inventory'], ['node-a'], include_cohorts=True)
    assert projected == [dict(normal[0], cohorts=['test'])]


@pytest.mark.parametrize('same_publisher', [False, True])
def test_public_origin_must_resolve_only_to_admitted_publisher(plan, monkeypatch, same_publisher):
    document, _ = plan
    if same_publisher:
        document['publication']['source_alias'] = 'node-b'
    admitted = io.LocalIO(document)
    addresses = ['192.0.2.2']
    def resolve(host, port, **kwargs):
        assert host == 'delivery.example' and port == 8444
        return [(io.socket.AF_INET, io.socket.SOCK_STREAM, 6, '', (address, port)) for address in addresses]
    monkeypatch.setattr(io.socket, 'getaddrinfo', resolve)
    admitted.pivot_ready()
    addresses.append('192.0.2.99')
    with pytest.raises(ValueError, match='origin-pivot-unconfirmed'):
        admitted.pivot_ready()
    addresses[:] = ['192.0.2.99']
    with pytest.raises(ValueError, match='origin-pivot-unconfirmed'):
        admitted.pivot_ready()


@pytest.mark.parametrize('changed', ['inventory', 'known_hosts', 'key'])
def test_verification_refuses_changed_authority_between_gates(plan, monkeypatch, changed):
    document, _ = plan
    admitted = io.LocalIO(document)
    calls = []
    original = Path(document[changed]) if changed != 'key' else Path(document['inventory']).parent / 'key'
    frozen_paths = []
    def run(argv, **kwargs):
        calls.append(argv)
        frozen = Path(kwargs['environment']['ANSIBLE_INVENTORY'])
        frozen_paths.append(frozen)
        original.write_bytes(original.read_bytes() + b'\nchanged')
        return 0, b''
    monkeypatch.setattr(io, 'run_command', run)
    with pytest.raises(io.MigrationRefused, match='verification-input-changed'):
        admitted.verify_target({'synthetic': 'private'})
    assert len(calls) == 1
    assert all(not path.exists() for path in frozen_paths)


def test_native_ansible_inventory_consumes_exact_frozen_transport(plan, monkeypatch):
    document, _ = plan
    admitted = io.LocalIO(document)
    checked = []
    def run(argv, **kwargs):
        environment = kwargs['environment']
        snapshot = Path(environment['ANSIBLE_INVENTORY'])
        result = subprocess.run(['ansible-inventory', '-i', str(snapshot), '--host', 'node-b'],
                                env=environment, capture_output=True, check=True, timeout=15)
        selected = json.loads(result.stdout)
        assert selected['ansible_host'] == '192.0.2.2'
        assert selected['ansible_user'] == 'deploy' and selected['ansible_port'] == 22
        assert selected['ansible_ssh_private_key_file'] == str(snapshot.parent / 'identity')
        assert selected['ansible_ssh_common_args'] == '' and selected['ansible_ssh_extra_args'] == ''
        args = selected['ansible_ssh_args']
        for value in ('StrictHostKeyChecking=yes', 'IdentityAgent=none', 'ProxyCommand=none',
                      'ControlMaster=no', 'GlobalKnownHostsFile=/dev/null', str(snapshot.parent / 'known_hosts')):
            assert value in args
        assert selected['ansible_ssh_executable'] == '/usr/bin/ssh'
        checked.append(snapshot)
        return 0, b''
    monkeypatch.setattr(io, 'run_command', run)
    admitted.verify_target({'synthetic': 'private'})
    assert len(checked) == 2 and all(not path.exists() for path in checked)
