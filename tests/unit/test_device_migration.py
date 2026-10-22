"""Real encrypted migration and publisher transactions; no live deployment claim."""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import importlib.util
import json
import subprocess
from pathlib import Path

import jsonschema
import pytest
from client_delivery_identity import authority, digest
from client_payload import materialize, read_document
from device_migration import Migration, envelope, un64
from device_migration_io import encoded
from device_migration_receipt import signing_bytes
from encrypted_client_document import operate
from test_device_migration_credentials import authorities as authorities  # noqa: PLC0414
from test_subscription_document import delivery
from test_subscription_document import service as service  # noqa: PLC0414


class LocalPublisherBase:
    """Use the real installed service functions with an isolated filesystem."""
    admission = {'fixture': 'local-publisher-only'}

    def __init__(self, service):
        self.service = service
        self.verified = 0
        self.fail_after = False

    def read(self, path):
        return read_document(path)

    def endpoint(self, host):
        return '192.0.2.10' if host == 'upcloud:prod' else '192.0.2.20'

    def origin(self, alias):
        pass

    def pivot_ready(self):
        pass

    def verify_target(self, document):
        self.verified += 1

    def publisher(self, alias, action, token_hash=None, expected=None, document=None):
        if action == 'ready':
            return None
        if action == 'snapshot':
            return self.service._migration_snapshot()
        request = encoded({'schema_version': 1, 'expected_document_sha256': expected,
                           'document_b64': base64.b64encode(document).decode() if document is not None else None})
        result = self.service._migration_publish(token_hash, request)
        if self.fail_after:
            self.fail_after = False
            raise OSError('lost acknowledgement after real publication')
        return result


class LocalPublisher(LocalPublisherBase):
    def verify_routes(self):
        pass


@pytest.fixture
def migration(authorities, service, tmp_path, monkeypatch):
    source, target, source_node, target_node = copy.deepcopy(authorities)
    source.pop('unrelated', None)
    target.pop('unrelated', None)
    tmp_path.chmod(0o700)
    key = tmp_path / 'test.age'
    subprocess.run(['age-keygen', '-o', str(key)], capture_output=True, check=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip()
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(key))
    source_node.update(secrets_file=str(tmp_path / 'source.sops.yaml'), alias='blue')
    target_node.update(secrets_file=str(tmp_path / 'target.sops.yaml'), alias='green')
    source['client_registry']['phone']['delivery_sources'] = [source_node['secrets_file']]
    source['client_registry']['phone']['status'] = 'delivered'
    source['client_registry']['phone']['token_expires'] = ''
    source['client_registry']['phone']['delivery_options']['expires'] = ''
    authority(source, create=True)
    with delivery(service) as (token, get):
        source['client_registry']['phone']['token_hash_prefix'] = token[:8]
        payload, bindings = materialize('phone', source['client_registry']['phone']['delivery_options'],
                                 documents={source_node['secrets_file']: source}, source_paths=[source_node['secrets_file']],
                                 extended=True, endpoints={'upcloud:prod': '192.0.2.10'})
        source['client_registry']['phone']['last_payload_identity'] = digest('phone', source['client_registry']['phone']['delivery_options'], payload, bindings, authority(source))
        service._publish_subscription(token, encoded({'schema_version': 1, 'client': 'phone', 'expires': '',
                                                     'payload_b64': base64.b64encode(encoded(payload)).decode()}))
        for node, document in ((source_node, source), (target_node, target)):
            cipher = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json', '--output-type', 'yaml', '/dev/stdin'],
                                    input=encoded(document), capture_output=True, check=True).stdout
            path = Path(node['secrets_file'])
            path.write_bytes(cipher)
            path.chmod(0o600)
        plan = {'schema_version': 1, 'id': '11111111-1111-4111-8111-111111111111',
                'inventory': str(tmp_path / 'inventory.ini'), 'known_hosts': str(tmp_path / 'known_hosts'),
                'source': source_node, 'target': target_node,
                'publication': {'source_alias': 'delivery', 'target_alias': 'delivery',
                                'directory': '/var/lib/vpn-subscription', 'origin': 'https://delivery.example:8444'}}
        instance = Migration(plan, LocalPublisher(service), now=lambda: 1_800_000_000_000)
        yield instance, token, get


def prepare(migration):
    instance, _, _ = migration
    review = instance.inspect()[-1]
    assert review['devices'] == ['phone'] and review['active_grants'] == 1
    result = instance.prepare(review['approval'])
    assert result['phase'] == 'prepared'
    return instance


def signed_receipt(instance, token, state='path-tested'):
    source = instance.io.read(instance.source_path)
    journal = instance.load(source)
    grant = journal['grants'][token]
    proof = grant['metadata']
    receipt = {'schema_version': 1, 'migration_id': proof['migration_id'], 'delivery_id': proof['delivery_id'],
               'payload_sha256': grant['payload_sha256'], 'state': state, 'received_at_ms': instance.now(),
               'tested_at_ms': instance.now() if state == 'path-tested' else 0,
               'tested_tag': proof['target_tags'][0] if state == 'path-tested' else '', 'mac': '0' * 64}
    receipt['mac'] = hmac.new(bytes.fromhex(proof['receipt_key']), signing_bytes(receipt), hashlib.sha256).hexdigest()
    return encoded(receipt)


def test_full_migration_preserves_url_exact_expiry_keys_and_requires_new_path(migration):
    instance, token, get = migration
    original_source = instance.io.read(instance.source_path)
    original_target = instance.io.read(instance.target_path)
    old_http = get()
    prepare(migration)
    assert get() == old_http
    target = instance.io.read(instance.target_path)
    assert target['client_registry']['phone']['awg_private_key'] == original_source['client_registry']['phone']['awg_private_key']
    assert target['amneziawg_secrets']['instances'][0]['server_private_key'] == original_target['amneziawg_secrets']['instances'][0]['server_private_key']
    result = instance.publish()
    assert result['devices'][0]['state'] == 'published'
    assert instance.io.verified == 1
    status, raw = get()
    payload = json.loads(raw)
    assert status == 200 and raw != old_http[1]
    assert all(outbound['server'] == '192.0.2.20' for outbound in payload['outbounds'] if 'server' in outbound)
    assert payload['ripdpi']['amneziawg'][0]['tag'].startswith('migration-awg-')
    assert 'phone' not in payload['ripdpi']['migration']['target_tags']
    with pytest.raises(ValueError, match='evidence-incomplete'):
        instance.ready()
    received = instance.evidence(signed_receipt(instance, token, 'received'))
    assert received['devices'][0]['state'] == 'received'
    with pytest.raises(ValueError, match='evidence-incomplete'):
        instance.ready()
    instance.evidence(signed_receipt(instance, token))
    assert instance.ready()['ready'] is True
    before = get()
    assert instance.publish()['phase'] == 'published'
    assert get() == before
    source = instance.io.read(instance.source_path)
    assert source['xray'] == original_source['xray']
    assert source['amneziawg_secrets'] == original_source['amneziawg_secrets']
    assert source['client_registry']['phone']['hosts'] == ['upcloud:green']
    for path in (instance.source_path, instance.target_path):
        raw_cipher = Path(path).read_bytes()
        assert payload['ripdpi']['migration']['receipt_key'].encode() not in raw_cipher
        assert not list(Path(path).parent.glob('.*.client.*'))


def test_lost_remote_ack_resumes_same_exact_delivery(migration):
    instance = prepare(migration)
    _, token, get = migration
    instance.io.fail_after = True
    with pytest.raises(OSError, match='lost acknowledgement'):
        instance.publish()
    published = get()
    assert instance.status()['phase'] == 'publishing'
    result = instance.publish()
    assert result['phase'] == 'published' and get() == published
    instance.evidence(signed_receipt(instance, token))
    assert instance.ready()['ready']


def test_rollback_restores_exact_http_and_registry_but_retains_target_peer(migration):
    instance, _, get = migration
    old = get()
    original = instance.io.read(instance.source_path)['client_registry']['phone']
    prepare(migration)
    instance.publish()
    result = instance.rollback()
    assert result['phase'] == 'rolled-back' and get() == old
    assert instance.io.read(instance.source_path)['client_registry']['phone'] == original
    target = instance.io.read(instance.target_path)
    assert 'phone' in target['client_registry']
    assert target['client_registry']['phone']['status'] == 'issued'


def test_wrong_review_and_changed_target_preserve_all_authorities(migration):
    instance, _, get = migration
    originals = {p: Path(p).read_bytes() for p in (instance.source_path, instance.target_path)}
    old = get()
    with pytest.raises(ValueError, match='review-required'):
        instance.prepare('0' * 64)
    assert get() == old
    assert all(Path(p).read_bytes() == raw for p, raw in originals.items())
    prepare(migration)
    def change(doc):
        doc['xray']['reality_public_key'] = 'changed-target-key'
        return doc, None
    operate(instance.target_path, change)
    with pytest.raises(ValueError, match='target-changed'):
        instance.publish()
    assert get() == old


def test_conflicting_grant_is_never_overwritten(migration):
    instance = prepare(migration)
    _, token, get = migration
    current, _ = envelope(un64(instance.io.publisher('delivery', 'snapshot')['documents'][0]['document_b64']))
    changed = encoded(dict(current, payload_b64=base64.b64encode(b'{"different":true}').decode()))
    instance.io.service._publish_subscription(token, changed)
    with pytest.raises(ValueError, match='publication-conflict'):
        instance.publish()
    assert get()[1] == b'{"different":true}'


def test_freshness_and_receipt_forgery_are_not_publication_acceptance(migration):
    instance = prepare(migration)
    _, token, _ = migration
    instance.publish()
    receipt = signed_receipt(instance, token)
    forged = json.loads(receipt)
    forged['mac'] = '0' * 64
    with pytest.raises(ValueError, match='authentication-failed'):
        instance.evidence(encoded(forged))
    instance.evidence(receipt)
    instance.now = lambda: 1_800_000_000_000 + 86_400_001
    with pytest.raises(ValueError, match='evidence-incomplete'):
        instance.ready()


def test_publisher_move_prepares_before_green_exists_copies_all_grants_and_rolls_back_owned_only(migration, tmp_path):
    from test_subscription_retention import service as render_service
    instance, token, source_get = migration
    source_service = instance.io.service
    unrelated = hashlib.sha256(b'unrelated-grant').hexdigest()
    unrelated_document = encoded({'schema_version': 1, 'client': 'unrelated', 'expires': '',
                                  'payload_b64': base64.b64encode(b'{"unrelated":true}').decode()})
    source_service._publish_subscription(unrelated, unrelated_document)
    original = source_get()
    class Pair(LocalPublisher):
        green = None
        def publisher(self, alias, *args, **kwargs):
            selected = source_service if alias == 'delivery' else self.green
            if selected is None:
                raise OSError('green publisher has not been deployed yet')
            before = self.service
            self.service = selected
            try:
                return super().publisher(alias, *args, **kwargs)
            finally:
                self.service = before
    instance.plan['publication']['target_alias'] = 'green'
    instance.publishers = ['delivery', 'green']
    instance.io = Pair(source_service)
    review = instance.inspect()[-1]
    assert review['publisher_move'] and review['preserved_other_grants'] == 1
    instance.prepare(review['approval'])
    assert source_get() == original and instance.io.green is None
    instance.io.green = render_service.__wrapped__(tmp_path / 'green-publisher')
    # A pre-existing identical unrelated grant remains owned by that publisher.
    instance.io.green._publish_subscription(unrelated, unrelated_document)
    with delivery(instance.io.green) as (_, green_get):
        instance.publish()
        assert source_get()[0] == 200 and source_get() == green_get()
        target_rows = instance.io.green._migration_snapshot()['documents']
        assert {r['token_hash'] for r in target_rows} == {token, unrelated}
        instance.rollback()
        assert source_get() == original and green_get()[0] == 410
        remaining = instance.io.green._migration_snapshot()['documents']
        assert [r['token_hash'] for r in remaining] == [unrelated]
        assert un64(remaining[0]['document_b64']) == unrelated_document


@pytest.mark.parametrize('phase', ['prepare-target', 'publish-target', 'rollback-target'])
def test_interrupted_cross_document_commit_resumes_without_reallocation_or_lost_authority(migration, phase):
    instance, token, get = migration
    old = get()
    original_writer = instance.writer
    interrupted = False
    def writer(path, transform, **kwargs):
        nonlocal interrupted
        result = original_writer(path, transform, **kwargs)
        if path == instance.target_path and not interrupted:
            interrupted = True
            raise OSError('lost local target commit acknowledgement')
        return result
    review = instance.inspect()[-1]
    if phase == 'prepare-target':
        instance.writer = writer
        with pytest.raises(OSError, match='lost local'):
            instance.prepare(review['approval'])
        first = instance.io.read(instance.target_path)
        instance.writer = original_writer
        instance.prepare(review['approval'])
        assert instance.io.read(instance.target_path) == first
        assert get() == old
    else:
        instance.prepare(review['approval'])
        if phase == 'rollback-target':
            instance.publish()
        instance.writer = writer
        action = instance.rollback if phase == 'rollback-target' else instance.publish
        with pytest.raises(OSError, match='lost local'):
            action()
        first = instance.io.read(instance.target_path)
        instance.writer = original_writer
        action()
        assert instance.io.read(instance.target_path) == first
        assert get() == old if phase == 'rollback-target' else get() != old
    if phase != 'rollback-target':
        instance.publish()
        instance.evidence(signed_receipt(instance, token))
        assert instance.ready()['ready']


def test_multiple_active_urls_preserve_each_expiry_and_include_exact_new_delivery(migration):
    instance, first, get = migration
    second = hashlib.sha256(b'second-active-url').hexdigest()
    old = instance.io.service._migration_snapshot()['documents'][0]
    grant, payload = envelope(un64(old['document_b64']))
    grant.update(expires='2099-01-01T00:00:00Z')
    payload['ripdpi']['expires'] = grant['expires']
    grant['payload_b64'] = base64.b64encode(encoded(payload)).decode()
    instance.io.service._publish_subscription(second, encoded(grant))
    review = instance.inspect()[-1]
    assert review['active_grants'] == 2
    instance.prepare(review['approval'])
    instance.publish()
    rows = {row['token_hash']: envelope(un64(row['document_b64'])) for row in instance.io.service._migration_snapshot()['documents']}
    assert rows[first][0]['expires'] == '' and rows[second][0]['expires'] == '2099-01-01T00:00:00Z'
    assert rows[first][1]['ripdpi']['migration']['delivery_id'] != rows[second][1]['ripdpi']['migration']['delivery_id']
    for _, bundle in rows.values():
        assert all(outbound['server'] == '192.0.2.20' for outbound in bundle['outbounds'] if 'server' in outbound)
    instance.evidence(signed_receipt(instance, second))
    assert instance.ready()['ready']


def test_official_client_retains_plain_format_and_requires_generation_bound_manual_path(migration):
    instance, token, _ = migration
    def change(document):
        entry = document['client_registry']['phone']
        entry['delivery_options']['format'] = 'singbox'
        entry['formats'] = ['singbox']
        payload, bindings = materialize('phone', entry['delivery_options'], documents={instance.source_path: document},
                                       source_paths=[instance.source_path], endpoints={'upcloud:prod': '192.0.2.10'})
        entry['last_payload_identity'] = digest('phone', entry['delivery_options'], payload, bindings, authority(document))
        return document, payload
    old_payload = operate(instance.source_path, change)
    instance.io.service._publish_subscription(token, encoded({'schema_version': 1, 'client': 'phone', 'expires': '',
                                                             'payload_b64': base64.b64encode(encoded(old_payload)).decode()}))
    prepare(migration)
    instance.publish()
    row = instance.io.service._migration_snapshot()['documents'][0]
    assert 'ripdpi' not in envelope(un64(row['document_b64']))[1]
    with pytest.raises(ValueError, match='evidence-incomplete'):
        instance.ready()
    instance.evidence(client='phone', reason='Verified new endpoint with the official client')
    assert instance.ready()['devices'][0]['state'] == 'operator-confirmed'


def test_encrypted_journal_and_delivery_validate_at_every_committed_phase(migration):
    instance, token, _ = migration
    root = Path(__file__).resolve().parents[2]
    validator = jsonschema.Draft202012Validator(json.loads((root / 'secrets/schema.json').read_text()))
    phases = []
    original_writer = instance.writer
    def writer(path, transform, **kwargs):
        def validated(document):
            result, value = transform(document)
            # Validate the complete authority, including the nested candidate.
            errors = list(validator.iter_errors(result))
            assert not errors, [(list(error.path), error.validator) for error in errors]
            if path == instance.source_path:
                phases.append(result['device_migrations'][instance.plan['id']]['phase'])
            return result, value
        return original_writer(path, validated, **kwargs)
    instance.writer = writer
    prepare(migration)
    instance.publish()
    instance.evidence(signed_receipt(instance, token))
    instance.rollback()
    assert {'preparing', 'prepared', 'publishing', 'published', 'rolling-back', 'rolled-back'} <= set(phases)


def test_drift_reconstructs_migration_metadata_and_detects_consumed_change(migration, monkeypatch):
    instance = prepare(migration)
    instance.publish()
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('migration_drift_test', root / 'scripts/client-drift.py')
    drift = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift)
    real_materialize = drift.materialize
    def pinned_materialize(*args, **kwargs):
        return real_materialize(*args, **kwargs, endpoints={'upcloud:green': '192.0.2.20'})
    monkeypatch.setattr(drift, 'materialize', pinned_materialize)
    for path in (instance.source_path, instance.target_path):
        monkeypatch.setenv('SOPS_FILE', path)
        assert drift._verdict('phone')[0] == 'current'
    def change(document):
        next(client for client in document['xray']['clients'] if client['name'] == 'phone')['uuid'] = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        return document, None
    operate(instance.target_path, change)
    assert drift._verdict('phone')[0] == 'stale'
