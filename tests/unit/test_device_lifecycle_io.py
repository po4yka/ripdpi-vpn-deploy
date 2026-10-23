"""Private operation admission, exact pinned runtime execution and literal Make IO."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import device_lifecycle_io as io
import pytest
import yaml
from test_device_migration_io import plan as plan  # noqa: PLC0414

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def manifest(plan, monkeypatch):
    old, path = plan
    for item in (old['inventory'], old['known_hosts']):
        Path(item).chmod(0o600)
    value = {'schema_version': 1, 'id': old['id'], 'action': 'issue', 'device': 'new-phone',
             'inventory': old['inventory'], 'known_hosts': old['known_hosts'], 'journal_host': old['source']['host'],
             'nodes': [{**{key: row[key] for key in ('host','alias','cohort','secrets_file')}, 'awg_instance': None, 'xray_cohorts': []}
                       for row in (old['source'], old['target'])],
             'publishers': [{'host': row['host'], 'directory': '/var/lib/vpn-subscription', 'origin': 'https://delivery.example:8444'}
                            for row in (old['source'], old['target'])],
             'delivery': {'hosts': [old['source']['host']], 'awg_host': '', 'format': 'ripdpi', 'expires': '',
                          'output': str(path.parent / 'recipient.json')},
             'probe': {'url': 'https://probe.example/', 'status': 200, 'body_sha256': '1'*64, 'timeout_seconds': 5}}
    path.write_text(json.dumps(value))
    monkeypatch.setattr(io, 'context', lambda name: {'vpn': {'enable_subscription_host': True}})
    return value, path


def test_private_manifest_complete_inventory_and_publisher_admission(manifest):
    value, path = manifest
    assert io.load_manifest(path) == value
    admitted = io.LocalIO(value, path)
    assert admitted.endpoint('upcloud:green') == '192.0.2.2'
    missing = copy.deepcopy(value)
    missing['publishers'].pop()
    with pytest.raises(ValueError, match='all-configured-publishers'):
        io.LocalIO(missing, path)
    missing = copy.deepcopy(value)
    missing['nodes'].pop()
    with pytest.raises(ValueError, match='complete-inventory'):
        io.LocalIO(missing, path)
    Path(value['known_hosts']).write_text('changed authority')
    with pytest.raises(ValueError, match='reviewed-input'):
        admitted.revalidate()


@pytest.mark.parametrize('fault', ['mode','symlink','unknown','duplicate','source-alias','origin','output-path','probe'])
def test_manifest_refuses_unsafe_inputs(manifest, fault):
    value, path = manifest
    if fault == 'mode':
        path.chmod(0o644)
    elif fault == 'symlink':
        original = path.with_name('original.json')
        path.rename(original)
        path.symlink_to(original)
    elif fault == 'duplicate':
        path.write_text(path.read_text().replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
    else:
        if fault == 'unknown':
            value['extra'] = True
        elif fault == 'source-alias':
            value['nodes'][1]['secrets_file'] = value['nodes'][0]['secrets_file']
        elif fault == 'origin':
            value['publishers'][0]['origin'] = 'https://secret@delivery.example'
        elif fault == 'output-path':
            value['delivery']['output'] = '/tmp/$(touch unsafe)'
        else:
            value['probe']['url'] = 'https://secret@control.example'
        path.write_text(json.dumps(value))
    with pytest.raises((ValueError, OSError)):
        io.load_manifest(path)


def test_operation_lock_excludes_other_writers_and_foreign_symlinks(manifest):
    value, _ = manifest
    path = value['nodes'][0]['secrets_file']
    with io.operation_lock(path), pytest.raises(BlockingIOError), io.operation_lock(path):
        pytest.fail('concurrent lock acquired')
    lock = Path(path + '.device-operation.lock')
    lock.unlink()
    lock.symlink_to(value['known_hosts'])
    with pytest.raises(OSError), io.operation_lock(path):
        pytest.fail('foreign lock followed')


def test_runtime_uses_exact_private_inventory_and_removes_plaintext_after_failure(manifest, monkeypatch):
    value, path = manifest
    admitted = io.LocalIO(value, path)
    monkeypatch.setenv('MAKEFLAGS', '--eval=unsafe')
    monkeypatch.setenv('ANSIBLE_SKIP_TAGS', 'all')
    calls, outputs = [], []
    revocation = {'operation_id': value['id'], 'intent_sha256': 'a'*64}
    def execute(argv, **kwargs):
        calls.append(argv)
        assert 'ENV=green' in argv and 'ANSIBLE_LIMIT=node-b' in argv and 'TAG_ON_SUCCESS=0' in argv
        env = kwargs['environment']
        assert 'MAKEFLAGS' not in env and 'ANSIBLE_SKIP_TAGS' not in env
        secret = Path(next(arg.split('=',1)[1] for arg in argv if arg.startswith('SECRETS_FILE=')))
        extra = Path(next(arg.split('=',1)[1] for arg in argv if arg.startswith('ANSIBLE_EXTRA_VARS_FILE=')))
        assert yaml.safe_load(extra.read_text()) == {'vpn_device_revocation': revocation}
        assert extra.stat().st_mode & 0o777 == 0o600
        outputs.extend([secret, extra])
        assert secret.stat().st_mode & 0o777 == 0o600
        assert yaml.safe_load(secret.read_text()) == {'private': 'test-only-secret'}
        frozen = Path(env['ANSIBLE_INVENTORY'])
        assert 'StrictHostKeyChecking=yes' in frozen.read_text() and 'ProxyCommand=none' in frozen.read_text()
        assert (frozen.parent / 'known_hosts').read_bytes() == Path(value['known_hosts']).read_bytes()
        return 1, b'private diagnostics never exported'
    monkeypatch.setattr(io, 'run_command', execute)
    with pytest.raises(ValueError, match='adoption-unconfirmed'):
        admitted.runtime('upcloud:green', {'private': 'test-only-secret'}, revocation=revocation)
    assert calls[0][3] == 'rotate-credentials' and all(not path.exists() for path in outputs)


@pytest.mark.parametrize('action', ['plan', 'prepare', 'run', 'resume', 'status'])
def test_make_dispatches_literal_inputs_without_operator_configuration(tmp_path, action):
    shutil.copy2(ROOT / 'Makefile', tmp_path / 'Makefile')
    (tmp_path / '.fleet.mk').write_text('$(error must not parse operator configuration)\n')
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/device-lifecycle.py').write_text('import json,pathlib,sys\npathlib.Path("argv.json").write_text(json.dumps(sys.argv[1:]))\n')
    marker = tmp_path / 'injected'
    path = f'/private/$(shell touch {marker})/plan;literal.json'
    result = subprocess.run(['make', 'device-lifecycle', 'ACTION='+action, 'DEVICE_MANIFEST='+path], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10, check=False,
                            env={key: value for key,value in os.environ.items() if key not in {'MAKEFILES','MAKEFLAGS','GNUMAKEFLAGS','MFLAGS'}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert json.loads((tmp_path / 'argv.json').read_text()) == [action, '--manifest='+path]


def test_shared_publisher_io_runs_owner_fence_and_passes_private_stdin(manifest, monkeypatch):
    import device_migration_io as publication
    value, path = manifest
    admitted = io.LocalIO(value, path)
    calls = []
    def execute(argv, **kwargs):
        calls.append((argv, kwargs))
        return b'migration-publisher-v1\n'
    monkeypatch.setattr(publication, 'bounded_command', execute)
    admitted.publisher('upcloud:blue', 'ready')
    assert len(calls) == 1
    assert 'StrictHostKeyChecking=yes' in calls[0][0] and '--migration-ready' in calls[0][0][-1]
    Path(value['known_hosts']).write_text('changed pins')
    with pytest.raises(ValueError, match='reviewed-input'):
        admitted.publication_io('upcloud:blue').publisher('upcloud:blue', 'ready')
    assert len(calls) == 1


def test_scope_discovery_refuses_retained_publisher_and_unknown_transport(manifest, monkeypatch):
    value, path = manifest
    value['nodes'][1]['cohort'] = 'second'
    inventory = Path(value['inventory'])
    inventory.write_text(inventory.read_text().replace('[vpn-test]\nnode-b', '[vpn-second]\nnode-b'))
    value['publishers'].pop()
    path.write_text(json.dumps(value))
    monkeypatch.setattr(io, 'context', lambda name: {'vpn': {'enable_subscription_host': name == 'test'}})
    admitted = io.LocalIO(value, path)
    calls = []
    def probe(host, command):
        calls.append((host, command))
        return False
    monkeypatch.setattr(io, 'publisher_probe', probe)
    admitted.verify_publisher_scope()
    assert len(calls) == 1 and calls[0][0]['name'] == 'node-b'
    monkeypatch.setattr(io, 'publisher_probe', lambda *_: True)
    with pytest.raises(ValueError, match='undeclared-retained'):
        admitted.verify_publisher_scope()
    def unknown(*_):
        raise ValueError('transport unknown')
    monkeypatch.setattr(io, 'publisher_probe', unknown)
    with pytest.raises(ValueError, match='transport unknown'):
        admitted.verify_publisher_scope()


@pytest.mark.parametrize('variable', ['vpn={}', 'subscription={}', 'vpn_subscription_only=maybe'])
def test_inventory_cannot_override_reviewed_transport_context(manifest, variable):
    value, path = manifest
    inventory = Path(value['inventory'])
    inventory.write_text(inventory.read_text().replace('node-a ', 'node-a ' + variable + ' ', 1))
    with pytest.raises(ValueError, match='override'):
        io.LocalIO(value, path)


def test_overlapping_fleets_serialize_independently_of_journal_host(manifest):
    value, _ = manifest
    first, second = [node['secrets_file'] for node in value['nodes']]
    with io.operation_locks([second, first]), pytest.raises(BlockingIOError), io.operation_locks([first]):
        pytest.fail('overlapping operation acquired a different journal host')
    with io.operation_lock(second):
        with pytest.raises(BlockingIOError), io.operation_locks([first, second]):
            pytest.fail('partly acquired fleet lock remained active')
        # A failed second acquisition releases the first owned lock.
        with io.operation_lock(first):
            pass


def test_retained_publisher_can_be_declared_after_profile_disable(manifest, monkeypatch):
    value, path = manifest
    monkeypatch.setattr(io, 'context', lambda name: {'vpn': {'enable_subscription_host': False}})
    admitted = io.LocalIO(value, path)
    assert set(admitted.publications) == {row['host'] for row in value['publishers']}
    calls = []
    monkeypatch.setattr(io, 'publisher_probe', lambda *args: calls.append(args) or True)
    admitted.verify_publisher_scope()
    assert calls == []
    value['publishers'].pop()
    missing = io.LocalIO(value, path)
    with pytest.raises(ValueError, match='undeclared-retained'):
        missing.verify_publisher_scope()
