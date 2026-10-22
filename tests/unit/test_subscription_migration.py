"""Migration uses the installed publisher, durable CAS and unchanged HTTP URLs."""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import os
import stat
import subprocess
import sys

import pytest
from test_subscription_document import delivery, envelope
from test_subscription_retention import service as service  # noqa: PLC0414


def sha(content):
    return hashlib.sha256(content).hexdigest()


def request(expected, document):
    return json.dumps({'schema_version': 1, 'expected_document_sha256': expected,
                           'document_b64': base64.b64encode(document).decode() if document is not None else None}).encode()


def cli(service, *args, data=None):
    return subprocess.run([sys.executable, service.__file__, *args, str(service.SUBSCRIPTION_DIR)],
                          input=data, capture_output=True, timeout=10, check=False)


def test_real_cli_snapshot_and_migration_keep_url_exact_payload_and_expiry(service):
    with delivery(service) as (token_hash, get):
        old = envelope(b'{"server":"192.0.2.1"}', expires='2099-01-01T00:00:00+00:00')
        new = envelope(b'{ "server": "192.0.2.2" }\n', expires='2099-01-01T00:00:00+00:00')
        service._publish_subscription(token_hash, old)
        ready = cli(service, '--migration-ready')
        assert ready.returncode == 0 and ready.stdout.strip() == b'migration-publisher-v1'
        snapshot = cli(service, '--migration-snapshot')
        assert snapshot.returncode == 0
        assert json.loads(snapshot.stdout) == {'schema_version': 1, 'active_bootstrap_count': 0, 'documents': [{
            'token_hash': token_hash, 'document_sha256': sha(old), 'document_b64': base64.b64encode(old).decode(),
            'revoked': False, 'expired': False}]}
        for result in ('applied', 'already-applied'):
            published = cli(service, '--migration-publish', token_hash, data=request(sha(old), new))
            assert published.returncode == 0
            assert json.loads(published.stdout) == {'schema_version': 1, 'token_hash': token_hash,
                'document_sha256': sha(new), 'result': result}
            assert get() == (200, b'{ "server": "192.0.2.2" }\n')
        # CAS rollback retains the same bearer URL and exact original bytes.
        assert service._migration_publish(token_hash, request(sha(new), old))['result'] == 'applied'
        assert get() == (200, b'{"server":"192.0.2.1"}')


def test_create_then_owned_delete_and_repeated_delete(service):
    with delivery(service) as (token_hash, get):
        document = envelope()
        assert service._migration_publish(token_hash, request(None, document))['result'] == 'applied'
        assert get()[0] == 200
        assert service._migration_publish(token_hash, request(None, document))['result'] == 'already-applied'
        for result in ('applied', 'already-applied'):
            receipt = service._migration_publish(token_hash, request(sha(document), None))
            assert receipt['result'] == result and receipt['document_sha256'] is None
            assert get()[0] == 410
        with pytest.raises(ValueError):
            service._migration_publish(token_hash, request(None, None))


@pytest.mark.parametrize('operation', ['create', 'replace', 'delete', 'already-applied', 'absent-delete'])
@pytest.mark.parametrize('authority', ['revoked', 'missing', 'malformed-tail', 'mode', 'symlink'])
def test_every_cas_action_rechecks_revocation(service, operation, authority, tmp_path):
    token_hash = sha(b'grant')
    old, new = envelope(b'{"old":true}'), envelope()
    existing = operation not in {'create', 'absent-delete'}
    if existing:
        service._publish_subscription(token_hash, old)
    desired = None if 'delete' in operation else old if operation == 'already-applied' else new
    expected = sha(old) if operation != 'create' else None
    if authority == 'missing':
        service.REVOKED_FILE.unlink()
    elif authority == 'symlink':
        service.REVOKED_FILE.unlink()
        service.REVOKED_FILE.symlink_to(tmp_path / 'unknown')
    else:
        service.REVOKED_FILE.write_text(token_hash + '\n' + ('invalid\n' if authority == 'malformed-tail' else ''))
        if authority == 'mode':
            service.REVOKED_FILE.chmod(0o644)
    with pytest.raises((ValueError, OSError)):
        service._migration_publish(token_hash, request(expected, desired))
    path = service.SUBSCRIPTION_DIR / 'sub' / (token_hash + '.document')
    assert (path.read_bytes() if existing else None) == (old if existing else None)
    assert path.exists() == existing


@pytest.mark.parametrize('operation', ['create', 'replace', 'delete', 'already-applied'])
def test_expired_grant_cannot_be_migrated_or_revived(service, operation):
    token_hash = sha(b'expired')
    old = envelope(expires='2000-01-01T00:00:00Z')
    if operation != 'create':
        service._publish_subscription(token_hash, old)
    new = None if operation == 'delete' else old if operation in {'create', 'already-applied'} else envelope()
    with pytest.raises(ValueError):
        service._migration_publish(token_hash, request(None if operation == 'create' else sha(old), new))
    if operation != 'create':
        assert service._migration_snapshot()['documents'][0]['expired'] is True


@pytest.mark.parametrize('fault', ['conflict', 'client', 'expiry', 'absent-expected', 'mirror', 'unsafe-document'])
def test_cas_preserves_conflicts_and_authority_boundaries(service, fault):
    token_hash = sha(b'grant')
    old, new = envelope(b'{"old":true}'), envelope()
    if fault != 'absent-expected':
        service._publish_subscription(token_hash, old)
    expected = sha(b'other') if fault == 'conflict' else sha(old)
    if fault in {'client', 'expiry'}:
        value = json.loads(new)
        value['client' if fault == 'client' else 'expires'] = 'other' if fault == 'client' else '2099-01-01T00:00:00Z'
        new = json.dumps(value).encode()
    elif fault == 'mirror':
        service.MIRROR_GENERATIONS.mkdir()
    elif fault == 'unsafe-document':
        (service.SUBSCRIPTION_DIR / 'sub' / (token_hash + '.document')).chmod(0o644)
    with pytest.raises((ValueError, OSError)):
        service._migration_publish(token_hash, request(expected, new))
    path = service.SUBSCRIPTION_DIR / 'sub' / (token_hash + '.document')
    assert not path.exists() if fault == 'absent-expected' else path.read_bytes() == old


@pytest.mark.parametrize('suffix', ['', '.json', '.meta'])
def test_legacy_grants_are_not_silently_omitted_or_revealed_by_delete(service, suffix):
    token_hash = sha(b'legacy')
    legacy = service.SUBSCRIPTION_DIR / 'sub' / (token_hash + suffix)
    legacy.write_bytes(b'{}')
    with pytest.raises(ValueError):
        service._migration_snapshot()
    old = envelope()
    with pytest.raises(ValueError):
        service._migration_publish(token_hash, request(None, old))
    service._publish_subscription(token_hash, old)
    assert len(service._migration_snapshot()['documents']) == 1
    new = envelope(b'{"migrated":true}')
    assert service._migration_publish(token_hash, request(sha(old), new))['result'] == 'applied'
    assert service._migration_publish(token_hash, request(sha(new), old))['result'] == 'applied'
    with pytest.raises(ValueError):
        service._migration_publish(token_hash, request(sha(old), None))
    assert legacy.read_bytes() == b'{}'


@pytest.mark.parametrize('limit', ['documents', 'bytes', 'mirror', 'malformed', 'symlink'])
def test_snapshot_bounds_and_malformed_authority_fail_closed(service, limit, monkeypatch):
    token_hash = sha(b'bounded')
    old = envelope()
    service._publish_subscription(token_hash, old)
    if limit == 'documents':
        monkeypatch.setattr(service, 'MIGRATION_MAX_DOCUMENTS', 1)
        service._publish_subscription(sha(b'second'), old)
    elif limit == 'bytes':
        monkeypatch.setattr(service, 'MIGRATION_MAX_BYTES', len(old) * 2 - 1)
        service._publish_subscription(sha(b'second'), old)
    elif limit == 'mirror':
        service.MIRROR_CURRENT.symlink_to('missing')
    else:
        path = service.SUBSCRIPTION_DIR / 'sub' / (token_hash + '.document')
        if limit == 'malformed':
            path.write_bytes(b'{"private-marker":true}')
        else:
            path.unlink()
            path.symlink_to('missing')
    with pytest.raises((ValueError, OSError)):
        service._migration_snapshot()


def test_snapshot_reports_all_grants_in_order_and_bootstrap_drain_without_copy(service):
    documents = [sha(b'b'), sha(b'a'), sha(b'c')]
    for token_hash in documents:
        service._publish_subscription(token_hash, envelope())
    service.REVOKED_FILE.write_text(documents[0] + '\n')
    bootstrap = service.SUBSCRIPTION_DIR / 'bootstrap'
    for index in range(4):
        token_hash = sha(str(index).encode())
        (bootstrap / token_hash).write_bytes(b'{}')
        if index == 1:
            (bootstrap / (token_hash + '.meta')).write_text('{"expires":"2000-01-01T00:00:00Z"}')
        if index == 2:
            assert service._record_bootstrap_consumption(token_hash, 1791590400)
        if index == 3:
            (bootstrap / (token_hash + '.meta')).write_text('invalid')
    before = {p.name: p.read_bytes() for p in bootstrap.iterdir()}
    value = service._migration_snapshot()
    assert [d['token_hash'] for d in value['documents']] == sorted(documents)
    assert [d['token_hash'] for d in value['documents'] if d['revoked']] == documents[:1]
    assert value['active_bootstrap_count'] == 2
    assert before == {p.name: p.read_bytes() for p in bootstrap.iterdir()}


@pytest.mark.parametrize('stage', ['file-sync', 'rename', 'directory-sync'])
def test_cas_failure_and_lost_ack_reconcile_exact_remote_state(service, monkeypatch, stage):
    token_hash = sha(b'grant')
    old, new = envelope(b'{"old":true}'), envelope()
    service._publish_subscription(token_hash, old)
    real_sync, real_replace = service.os.fsync, service.os.replace
    def sync(descriptor):
        directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        if stage == ('directory-sync' if directory else 'file-sync'):
            raise OSError('private-marker')
        return real_sync(descriptor)
    def replace(*args, **kwargs):
        if stage == 'rename':
            raise OSError('private-marker')
        return real_replace(*args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(service.os, 'fsync', sync)
        patch.setattr(service.os, 'replace', replace)
        with pytest.raises(OSError):
            service._migration_publish(token_hash, request(sha(old), new))
    observed = base64.b64decode(service._migration_snapshot()['documents'][0]['document_b64'])
    assert observed == (new if stage == 'directory-sync' else old)
    repaired = service._migration_publish(token_hash, request(sha(old), new))
    assert repaired['result'] == ('already-applied' if stage == 'directory-sync' else 'applied')
    assert not list((service.SUBSCRIPTION_DIR / 'sub').glob('.document-*'))


def test_concurrent_processes_cannot_both_overwrite_the_same_expected_generation(service):
    token_hash = sha(b'grant')
    old = envelope(b'{"old":true}')
    service._publish_subscription(token_hash, old)
    candidates = [envelope(b'{"candidate":1}'), envelope(b'{"candidate":2}')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda document: cli(service, '--migration-publish', token_hash,
            data=request(sha(old), document)), candidates))
    assert sorted(result.returncode for result in results) == [0, 2]
    successful = candidates[next(i for i, result in enumerate(results) if result.returncode == 0)]
    assert base64.b64decode(service._migration_snapshot()['documents'][0]['document_b64']) == successful
    assert all(b'candidate' not in result.stderr for result in results)


@pytest.mark.parametrize('data', [b'private-marker', b'{}', b'{"schema_version":true}',
    b'{"schema_version":1,"expected_document_sha256":null,"document_b64":"!"}',
    b'{"schema_version":1,"schema_version":1,"expected_document_sha256":null,"document_b64":null}'])
def test_cli_invalid_requests_are_categorical_and_do_not_leak_payload(service, data):
    result = cli(service, '--migration-publish', sha(b'grant'), data=data)
    assert result.returncode == 2 and not result.stdout
    assert result.stderr.strip() == b'subscription runtime: private authority or request refused'


def test_delete_lost_ack_resumes_absence_and_fsyncs_directory(service, monkeypatch):
    token_hash = sha(b'grant')
    old = envelope()
    service._publish_subscription(token_hash, old)
    real_sync = service.os.fsync
    with monkeypatch.context() as patch:
        def fail(descriptor):
            raise OSError('private-marker')
        patch.setattr(service.os, 'fsync', fail)
        with pytest.raises(OSError):
            service._migration_publish(token_hash, request(sha(old), None))
    synced = []
    def observe(descriptor):
        synced.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        return real_sync(descriptor)
    monkeypatch.setattr(service.os, 'fsync', observe)
    assert service._migration_publish(token_hash, request(sha(old), None))['result'] == 'already-applied'
    assert synced == [True]


def test_already_applied_repair_requires_file_and_directory_durability(service, monkeypatch):
    token_hash = sha(b'grant')
    old = envelope()
    service._publish_subscription(token_hash, old)
    observed = []
    real_sync = service.os.fsync
    def sync(descriptor):
        observed.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        return real_sync(descriptor)
    monkeypatch.setattr(service.os, 'fsync', sync)
    assert service._migration_publish(token_hash, request(sha(b'previous'), old))['result'] == 'already-applied'
    assert observed == [False, True]


def test_http_readers_only_observe_complete_cas_generations(service):
    with delivery(service) as (token_hash, get):
        first, second = envelope(b'{"generation":1}'), envelope(b'{ "generation": 2 }\n')
        service._publish_subscription(token_hash, first)
        def publish():
            current = first
            for _ in range(12):
                next_document = second if current == first else first
                service._migration_publish(token_hash, request(sha(current), next_document))
                current = next_document
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
            writer = workers.submit(publish)
            observations = [get() for _ in range(12)]
            writer.result(timeout=10)
        assert all(status == 200 and body in {b'{"generation":1}', b'{ "generation": 2 }\n'}
                   for status, body in observations)
