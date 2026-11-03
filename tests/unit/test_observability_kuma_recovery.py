"""Real age, SQLite/WAL and cleanup behind an isolated storage boundary."""
import hashlib
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import runpy
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from operator_maintenance_io import private_directory, read_bytes

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/observability_kuma'


def private(path, value):
    path.write_bytes(value if isinstance(value, bytes) else value.encode())
    path.chmod(0o600)
    return path


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    spec = importlib.util.spec_from_file_location('kuma_recovery', ROLE / 'files/observability-kuma-recovery.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    work, health, archives, credentials = [tmp_path / name for name in ('work', 'health', 'archives', 'credentials')]
    for path in (work, health, archives, credentials):
        path.mkdir(mode=0o700)
    private(work / '.owner', module.OWNER)
    private(health / '.owner', module.OWNER)
    monkeypatch.setattr(module, 'WORK', work)
    monkeypatch.setattr(module, 'HEALTH', health / 'status.json')
    monkeypatch.setattr(module, 'CONFIG', tmp_path / 'config.json')
    # The live unit is root. Use the existing real portable authority checks for
    # this test's current-user files; no crypto or database operation is mocked.
    module.BACKUP['private_directory'] = private_directory
    def regular(path):
        read_bytes(path)
        return Path(path)
    module.BACKUP['private_regular'] = regular
    config = {'directory': str(archives), 'bucket_id': 'a' * 24, 'bucket_name': 'private-kuma-fixture',
              'max_backup_age_seconds': 93600,
              'restore_images': ['ghcr.io/example/kuma@sha256:' + char * 64 for char in ('a', 'b')]}
    private(credentials / 'storage', json.dumps({'B2_APPLICATION_KEY_ID': 'synthetic-id',
                                                'B2_APPLICATION_KEY': 'synthetic-key-00000000000'}))
    monkeypatch.setenv('CREDENTIALS_DIRECTORY', str(credentials))
    subprocess.run(['age-keygen', '-o', str(credentials / 'age-identity')], check=True, capture_output=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(credentials / 'age-identity')], text=True).strip()
    config.update(recipient=recipient, operator_recipients=['age1' + 'q' * 58])
    private(module.CONFIG, json.dumps(config))
    original = subprocess.Popen
    def process(argv, **kwargs):
        if argv[0] in ('/usr/bin/age', '/usr/bin/age-keygen'):
            argv = [shutil.which(Path(argv[0]).name), *argv[1:]]
        return original(argv, **kwargs)
    monkeypatch.setattr(module.subprocess, 'Popen', process)
    return module, config, credentials, recipient


def completed_backup(recovery, tmp_path, *, corrupt=False, missing_table=False, missing_wal=False):
    module, config, credentials, recipient = recovery
    data = tmp_path / 'source'
    data.mkdir(mode=0o700)
    connection = sqlite3.connect(data / 'kuma.db')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA wal_autocheckpoint=0')
    for name in ('user', 'monitor') + (() if missing_table else ('heartbeat',)):
        connection.execute('CREATE TABLE ' + name + '(id INTEGER)')
    connection.execute('INSERT INTO monitor VALUES(42)')
    connection.commit()
    files = {path.name: path.read_bytes() for path in data.iterdir()}
    assert 'kuma.db-wal' in files and len(files['kuma.db-wal']) > 0
    if corrupt:
        files['kuma.db'] = b'corrupt database'
    if missing_wal:
        files.pop('kuma.db-wal');files.pop('kuma.db-shm')
    entries = {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in files.items()}
    entries['uploads'] = None
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w') as output:
        directory = tarfile.TarInfo('./uploads');directory.type = tarfile.DIRTYPE
        output.addfile(directory)
        for name, value in files.items():
            member = tarfile.TarInfo('./' + name);member.size = len(value)
            output.addfile(member, io.BytesIO(value))
    cipher = subprocess.run(['age', '-r', recipient], input=raw.getvalue(), capture_output=True, check=True).stdout
    identity = '20261103T000000Z-' + 'c' * 32
    archive = private(Path(config['directory']) / (identity + '.tar.age'), cipher)
    manifest = {'schema_version': 1, 'created_at': time.time(), 'image': config['restore_images'][0],
                'recipient': recipient,
                'sha256': hashlib.sha256(cipher).hexdigest(),
                'contents_sha256': hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'entries': len(entries), 'plaintext_bytes': sum(len(v) for v in files.values())}
    private(archive.with_name(identity + '.json'), json.dumps(manifest))
    connection.close()
    return archive, manifest


@pytest.mark.parametrize('fault', [None, 'stale', 'image', 'manifest', 'cipher', 'database', 'recoverable-header',
                                 'schema', 'reserve', 'short-policy', 'completion-age'])
def test_downloaded_recovery_runs_real_age_sqlite_wal_and_cleanup(recovery, tmp_path, monkeypatch, fault):
    module, config, credentials, _ = recovery
    archive, manifest = completed_backup(recovery, tmp_path, corrupt=fault in ('database', 'recoverable-header'),
                                         missing_table=fault == 'schema', missing_wal=fault == 'database')
    metadata = archive.with_suffix('').with_suffix('.json')
    if fault == 'stale': manifest['created_at'] -= 100000
    if fault == 'image': manifest['image'] = 'ghcr.io/example/foreign@sha256:' + 'c' * 64
    if fault == 'manifest': manifest['contents_sha256'] = '0' * 64
    if fault in ('short-policy', 'completion-age'):
        config['max_backup_age_seconds'] = 3600
        private(module.CONFIG, json.dumps(config))
    if fault == 'completion-age':
        now = time.time()
        manifest['created_at'] = now - 3590
        clock = iter((now, now + 20))
        monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: next(clock)))
    private(metadata, json.dumps(manifest))
    monkeypatch.setattr(module.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1 if fault == 'reserve' else 20 * 1024**3))
    calls = []
    class Storage:
        def __init__(self, selected):
            assert selected == config
        def deliver(self, source, identity, selected):
            calls.append(identity)
            target = module.WORK / 'cipher.age'
            private(target, b'invalid age stream' if fault == 'cipher' else source.read_bytes())
            return target
    monkeypatch.setattr(module, 'Storage', Storage)
    monkeypatch.setattr(sys, 'argv', ['recovery', 'verify'])
    healthy = fault in (None, 'recoverable-header', 'short-policy')
    assert module.main() == (0 if healthy else 1)
    health = json.loads(module.HEALTH.read_bytes())
    assert health['status'] == ('ok' if healthy else 'failed')
    assert set(p.name for p in module.WORK.iterdir()) == {'.owner', '.lock'}
    assert archive.exists()
    if fault in ('stale', 'image', 'reserve'):
        assert not calls
    if healthy:
        assert health['backup_at'] == manifest['created_at'] and health['verified_at'] > 0
        assert health['verified_at'] < health['valid_until'] <= manifest['created_at'] + config['max_backup_age_seconds']


def test_finalizer_marks_failed_service_and_cleans_only_owned_work(recovery, monkeypatch):
    module, _, _, _ = recovery
    data = module.WORK / 'data';data.mkdir(mode=0o700)
    private(data / 'kuma.db', 'temporary plaintext')
    private(module.WORK / 'cipher.age', 'temporary cipher')
    monkeypatch.setenv('SERVICE_RESULT', 'timeout')
    monkeypatch.setattr(sys, 'argv', ['recovery', 'finalize'])
    assert module.main() == 0
    assert json.loads(module.HEALTH.read_bytes())['status'] == 'failed'
    assert set(path.name for path in module.WORK.iterdir()) == {'.owner', '.lock'}


@pytest.mark.parametrize('kind', ['foreign', 'symlink', 'hardlink'])
def test_cleanup_refuses_foreign_material_without_deleting_it(recovery, tmp_path, kind):
    module, _, _, _ = recovery
    protected = private(tmp_path / 'protected', 'preserve this')
    target = module.WORK / ('foreign' if kind == 'foreign' else 'cipher.age')
    if kind == 'foreign': private(target, 'foreign data')
    if kind == 'symlink': target.symlink_to(protected)
    if kind == 'hardlink': os.link(protected, target)
    with pytest.raises(ValueError): module.cleanup()
    assert protected.read_text() == 'preserve this' and os.path.lexists(target)


def storage_boundary(recovery, archive, monkeypatch, fault):
    module, config, _, _ = recovery
    monkeypatch.setenv('B2_APPLICATION_KEY_ID', 'synthetic-id')
    monkeypatch.setenv('B2_APPLICATION_KEY', 'synthetic-key')
    remote = []
    class Response(io.BytesIO):
        pass
    class Backend:
        def open(self, outbound, timeout):
            url = outbound if isinstance(outbound, str) else outbound.full_url
            if url.endswith('b2_authorize_account'):
                caps = sorted(module.CAPABILITIES | ({'deleteFiles'} if fault == 'caps' else set()))
                value = {'accountId': 'fixture', 'authorizationToken': 'fixture-token', 'apiInfo': {'storageApi': {
                    'apiUrl': 'https://api001.backblazeb2.com', 'downloadUrl': 'https://f001.backblazeb2.com',
                    'allowed': {'buckets': [{'id': config['bucket_id'], 'name': config['bucket_name']}],
                                'namePrefix': 'operator-kit/' if fault == 'prefix' else 'kuma/', 'capabilities': caps}}}}
            elif url.endswith('b2_list_buckets'):
                value = {'buckets': [{'bucketId': config['bucket_id'], 'bucketName': config['bucket_name'],
                         'bucketType': 'allPublic' if fault == 'public' else 'allPrivate',
                         'defaultServerSideEncryption': {'value': {'algorithm': 'AES256', 'mode': 'SSE-B2'}}}]}
            elif url.endswith('b2_get_upload_url'):
                value = {'uploadUrl': 'https://untrusted.example/upload' if fault == 'upload-origin' else
                         'https://pod-000-1000-01.backblaze.com/b2api/v4/b2_upload_file/fixture',
                         'authorizationToken': 'fixture-upload-token'}
            elif '/b2_upload_file/' in url:
                data = outbound.data.read()
                assert data == archive.read_bytes()
                headers = {key.lower(): value for key, value in outbound.headers.items()}
                assert headers['x-bz-file-name'].startswith('kuma/')
                assert headers['content-length'] == str(len(data))
                assert headers['x-bz-content-sha1'] == hashlib.sha1(data, usedforsecurity=False).hexdigest()
                remote.append(data);value = {'fileId': 'fixture-file'}
            elif url.endswith('b2_get_file_info'):
                value = {'fileId': 'fixture-file', 'fileName': 'kuma/' + archive.name, 'bucketId': config['bucket_id'],
                         'contentLength': len(remote[0]), 'serverSideEncryption': {'algorithm': 'AES256', 'mode': 'SSE-B2'}}
            elif '/b2_download_file_by_id?' in url:
                return Response(b'corrupt' if fault == 'cipher' else remote[0])
            elif isinstance(outbound, str):
                if fault == 'anonymous': return Response(b'public')
                raise HTTPError(url, 401, 'denied', {}, None)
            else:
                pytest.fail('unexpected storage request')
            return Response(json.dumps(value).encode())
    monkeypatch.setattr(module.request, 'build_opener', lambda *_: Backend())
    return remote


@pytest.mark.parametrize('fault', [None, 'prefix', 'caps', 'public', 'cipher', 'anonymous', 'upload-origin'])
def test_native_storage_protocol_binds_grant_private_bucket_and_exact_download(recovery, tmp_path, monkeypatch, fault):
    module, config, _, _ = recovery
    archive, manifest = completed_backup(recovery, tmp_path)
    storage_boundary(recovery, archive, monkeypatch, fault)
    if fault:
        with pytest.raises(ValueError):
            module.Storage(config).deliver(archive, archive.name.removesuffix('.tar.age'), manifest)
    else:
        downloaded = module.Storage(config).deliver(archive, archive.name.removesuffix('.tar.age'), manifest)
        assert downloaded.read_bytes() == archive.read_bytes()


@pytest.mark.parametrize('fault', [None, 'prefix', 'caps', 'public', 'operator-key', 'recipient', 'reader'])
def test_controller_admits_only_independent_identity_and_confirmed_narrow_grant(recovery, tmp_path, monkeypatch, fault):
    _, config, credentials, recipient = recovery
    archive, _ = completed_backup(recovery, tmp_path)
    remote = storage_boundary(recovery, archive, monkeypatch, fault)
    preflight = runpy.run_path(str(ROLE / 'files/observability-kuma-recovery-preflight.py'))
    values = {'scope': {'enabled': True, 'readers': ['100.64.0.1']}, 'config': config,
              'identity': (credentials / 'age-identity').read_text(),
              'storage': {'B2_APPLICATION_KEY_ID': 'synthetic-id', 'B2_APPLICATION_KEY': 'synthetic-key'}}
    if fault == 'operator-key':
        config['operator_recipients'] = [recipient]
    if fault == 'recipient':
        config['recipient'] = 'age1' + 'p' * 58
    if fault == 'reader':
        values['scope']['readers'] = ['0.0.0.0/0']
    if fault:
        with pytest.raises(ValueError):
            preflight['admit'](values)
    else:
        preflight['admit'](values)
    assert remote == []


def test_controller_admission_precedes_host_mutation_and_hides_credentials():
    import yaml
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    index = next(i for i, task in enumerate(tasks) if task.get('ansible.builtin.include_tasks') == 'recovery-contract.yml')
    assert all('ansible.builtin.assert' in task for task in tasks[:index])
    admission, = yaml.safe_load((ROLE / 'tasks/recovery-contract.yml').read_text())
    assert admission['delegate_to'] == 'localhost' and admission['become'] is False
    assert admission['no_log'] is True and admission['check_mode'] is False
    assert admission['ansible.builtin.command']['argv'][0] == '{{ ansible_playbook_python }}'


def test_foreign_health_directory_cannot_receive_success(recovery):
    module, _, _, _ = recovery
    (module.HEALTH.parent / '.owner').unlink()
    with pytest.raises((ValueError, OSError)):
        module.publish('ok', verified_at=1, backup_at=1)
    assert not module.HEALTH.exists()


def test_busy_recovery_keeps_existing_health_and_plaintext_owner(recovery, monkeypatch):
    module, _, _, _ = recovery
    module.publish('ok', verified_at=10, backup_at=9)
    before = module.HEALTH.read_bytes()
    retained = private(module.WORK / 'cipher.age', 'active recovery owns this')
    lock = private(module.WORK / '.lock', b'')
    with lock.open('rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(sys, 'argv', ['recovery', 'verify'])
        assert module.main() == 1
    assert module.HEALTH.read_bytes() == before and retained.exists()


@pytest.mark.parametrize('newest_corrupt', [False, True])
def test_interrupted_manifest_cannot_poison_a_later_completed_backup(recovery, tmp_path, monkeypatch, newest_corrupt):
    module, config, _, _ = recovery
    archive, manifest = completed_backup(recovery, tmp_path)
    directory = Path(config['directory'])
    completed = archive.with_suffix('').with_suffix('.json')
    completed.unlink()
    publish = module.BACKUP['publish_manifest']
    original = json.dump
    def interrupted(value, stream):
        stream.write('{')
        raise InterruptedError('simulated power loss')
    with monkeypatch.context() as patch:
        patch.setattr(json, 'dump', interrupted)
        with pytest.raises(InterruptedError):
            publish(directory, '20261102T000000Z-' + 'b' * 32, manifest)
    assert not (directory / ('20261102T000000Z-' + 'b' * 32 + '.json')).exists()
    assert any(path.read_bytes() == b'{' for path in directory.glob('*.pending'))
    historical = private(directory / ('20261101T000000Z-' + 'a' * 32 + '.json'), '{')
    publish(directory, archive.name.removesuffix('.tar.age'), manifest)
    if newest_corrupt:
        private(directory / ('20261104T000000Z-' + 'd' * 32 + '.json'), '{')
        with pytest.raises(ValueError):
            module.selected_backup(config, time.time())
    else:
        selected, _, actual = module.selected_backup(config, time.time())
        assert selected == archive and actual == manifest
    assert historical.read_bytes() == b'{' and json.dump is original


def test_inactive_persisted_workspace_is_cleaned_without_losing_backup(recovery, tmp_path, monkeypatch):
    module, _, _, _ = recovery
    archive, _ = completed_backup(recovery, tmp_path)
    before = archive.read_bytes()
    (module.WORK / 'data').mkdir(mode=0o700)
    private(module.WORK / 'data/kuma.db', 'plaintext retained after power loss')
    private(module.WORK / 'cipher.age', before)
    operation = module.WORKSPACE['main']
    monkeypatch.setitem(operation.__globals__, 'WORK', module.WORK)
    assert operation() == {'schema_version': 1, 'removed': 2}
    assert archive.read_bytes() == before
    assert {path.name for path in module.WORK.iterdir()} == {'.owner', '.lock'}
