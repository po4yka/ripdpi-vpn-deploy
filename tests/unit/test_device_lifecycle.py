"""Real encrypted intent and local publisher IO; runtime callbacks are orchestration only."""
import base64
import copy
import json
import subprocess
from pathlib import Path

import pytest
import yaml
from client_payload import read_document
from device_lifecycle import Lifecycle
from device_migration_io import encoded
from encrypted_client_document import operate
from test_device_migration import LocalPublisher
from test_device_migration_route import route_io
from test_device_migration_route import tls_server as tls_server  # noqa: PLC0414
from test_subscription_document import service as service  # noqa: PLC0414
from test_vpn_consumer_reliability import context as context, data  # noqa: PLC0414

ROOT = Path(__file__).resolve().parents[2]


class Runtime(LocalPublisher):
    def __init__(self, service):
        super().__init__(service)
        self.events = []
        self.probe_state = None
        self.fail_runtime = False
        self.revocations = []

    def revalidate(self):
        pass

    def verify_publisher_scope(self):
        pass

    def source_identity(self):
        return {"DEPLOY_SOURCE_REVISION": "a"*40, "DEPLOYABLE_SOURCE_DIGEST": "b"*64}

    def admit_output(self, path):
        from device_lifecycle_io import LocalIO
        LocalIO.admit_output(self, path)

    def verify_routes(self, host):
        self.events.append(('route', host))

    def runtime(self, host, document, *, check=False, verify_only=False, revocation=None):
        self.events.append(('check' if check else 'verify' if verify_only else 'adopt', host))
        self.revocations.append(copy.deepcopy(revocation))
        if self.fail_runtime:
            self.fail_runtime = False
            raise OSError('runtime acknowledgement lost')
        if not check and not verify_only and host == 'upcloud:prod':
            self.service.REVOKED_FILE.write_text('\n'.join(document.get('subscription', {}).get('revoked_tokens', [])))

    def probe(self, host, profiles, mode):
        self.events.append(('probe', host))
        return {'schema_version': 1, 'control': 'passed', 'cleanup': 'confirmed', 'profiles': [
            {'id': p['id'], 'state': self.probe_state or ('accepted' if mode == 'accept' else 'denied'),
             'control_ok': True, 'setup_ok': True, 'cleanup_ok': True, 'peer_absent': mode == 'deny', 'runtime_healthy': True}
            for p in profiles]}

    def read_route(self, host, token, payload, *, revoked=False):
        self.route.read_route('delivery', token, b'' if revoked else payload, expected_status=410 if revoked else 200)

    def output(self, path, data):
        from device_lifecycle_io import LocalIO
        LocalIO.output(self, path, data)


@pytest.fixture
def operation(service, tmp_path, monkeypatch, tls_server):
    tmp_path.chmod(0o700)
    key = tmp_path / 'test.age'
    subprocess.run(['age-keygen', '-o', str(key)], capture_output=True, check=True)
    recipient = subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip()
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(key))
    path = tmp_path / 'node.sops.yaml'
    doc = yaml.safe_load((ROOT / 'tests/fixtures/secrets-sample.yml').read_text())
    cipher = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'json', '--output-type', 'yaml', '/dev/stdin'],
                            input=encoded(doc), capture_output=True, check=True).stdout
    path.write_bytes(cipher)
    path.chmod(0o600)
    manifest = {'schema_version': 1, 'id': '11111111-1111-4111-8111-111111111111', 'action': 'issue', 'device': 'new-phone',
                'inventory': str(tmp_path / 'inventory.ini'), 'known_hosts': str(tmp_path / 'known_hosts'), 'journal_host': 'upcloud:prod',
                'nodes': [{'host': 'upcloud:prod', 'alias': 'node', 'cohort': 'device-full-tailnet',
                           'secrets_file': str(path), 'awg_instance': 'awg0', 'xray_cohorts': []}],
                'publishers': [{'host': 'upcloud:prod', 'origin': 'https://delivery.example:8444', 'directory': '/var/lib/vpn-subscription'}],
                'delivery': {'hosts': ['upcloud:prod'], 'awg_host': 'upcloud:prod', 'format': 'ripdpi', 'expires': '', 'output': str(tmp_path / 'recipient.json')},
                'probe': {'url': 'https://control.example/', 'status': 200, 'body_sha256': '1'*64, 'timeout_seconds': 3}}
    with tls_server(service.Handler) as (port, _):
        runtime = Runtime(service)
        runtime.route = route_io(port)
        yield Lifecycle(manifest, runtime)


def prepare(instance):
    review = instance.inspect()[-1]
    assert instance.prepare(review['approval'])['phase'] == 'prepared'


def test_issue_produces_real_encrypted_authority_grant_and_usable_private_output(operation):
    initial = read_document(operation.journal_path)
    prepare(operation)
    assert read_document(operation.journal_path)['xray'] == initial['xray']
    result = operation.run()
    assert result['phase'] == 'complete' and result['recipient_artifact']
    artifact = json.loads(Path(operation.manifest['delivery']['output']).read_bytes())
    assert artifact['subscription_url'].startswith('https://delivery.example:8444/sub/')
    assert '<CLIENT_PRIVATE_KEY>' not in artifact['amneziawg_configs']['upcloud:prod']
    assert 'PrivateKey = ' in artifact['amneziawg_configs']['upcloud:prod']
    doc = read_document(operation.journal_path)
    assert doc['client_registry']['phone'] == initial['client_registry']['phone']
    private = doc['client_registry']['new-phone']['awg_private_key']
    assert private.encode() not in Path(operation.journal_path).read_bytes()
    assert operation.run() == result


def test_unknown_probe_blocks_completion_without_rolling_credentials_back(operation):
    prepare(operation)
    operation.io.probe_state = 'unknown'
    with pytest.raises(ValueError, match='native-probe'):
        operation.run()
    assert operation.status()['phase'] != 'complete'
    assert 'new-phone' in read_document(operation.journal_path)['client_registry']
    operation.io.probe_state = None
    assert operation.run()['phase'] == 'complete'


def test_lost_publisher_ack_reuses_same_token_and_exact_artifact(operation):
    prepare(operation)
    intended = copy.deepcopy(operation._journal())
    operation.io.fail_after = True
    with pytest.raises(OSError):
        operation.run()
    assert operation.run()['phase'] == 'complete'
    actual = operation._journal()
    assert actual['grants'] == intended['grants'] and actual['artifact'] == intended['artifact']


def test_lost_encrypted_write_ack_recognizes_exact_committed_postimage(operation):
    prepare(operation)
    original = operation.writer
    first = True
    def lost(path, transform):
        nonlocal first
        result = original(path, transform)
        if first:
            first = False
            raise OSError('lost local acknowledgement')
        return result
    operation.writer = lost
    with pytest.raises(OSError):
        operation.run()
    assert operation.run()['phase'] == 'complete'


def test_approval_covers_full_current_authority(operation):
    approved = operation.inspect()[-1]['approval']
    operate(operation.journal_path, lambda doc: (dict(doc, timezone='UTC'), {}))
    with pytest.raises(ValueError, match='approval'):
        operation.prepare(approved)
    assert 'device_operations' not in read_document(operation.journal_path)


def test_revoke_all_real_grants_preserves_unrelated_user_and_confirms_policy(operation):
    prepare(operation)
    operation.run()
    original = read_document(operation.journal_path)
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(id='22222222-2222-4222-8222-222222222222', action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    prepare(revoke)
    expected = revoke._journal()['revocation']
    operation.io.revocations.clear()
    assert revoke.run()['phase'] == 'complete'
    assert operation.io.revocations and all(value == expected for value in operation.io.revocations)
    assert revoke._journal()['revocation'] == expected
    altered = revoke._journal()
    altered['source']['DEPLOYABLE_SOURCE_DIGEST'] = 'c'*64
    with pytest.raises(ValueError, match='intent-changed'):
        revoke._validate_journal(altered)
    doc = read_document(operation.journal_path)
    assert doc['client_registry']['new-phone']['status'] == 'revoked'
    assert doc['client_registry']['phone'] == original['client_registry']['phone']
    assert all(row['name'] != 'new-phone' for row in doc['xray']['clients'])
    assert all(row['revoked'] for row in revoke.snapshots()['upcloud:prod']['rows'].values())


def test_revoke_controller_resumes_real_awg_journal_through_check_then_apply(operation, context, monkeypatch):
    prepare(operation)
    operation.run()
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(id='22222222-2222-4222-8222-222222222222', action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    prepare(revoke)
    c = context
    candidate = b'[Interface]\nListenPort=51820\n# revoked peer removed\n'
    events = []
    runtime, ready = operation.io.runtime, c.awg.Adapter.ready
    failures = []
    def reject_once(self):
        if not failures:
            failures.append(True)
            raise c.tx.Refusal('injected-readiness-failure')
        return ready(self)
    monkeypatch.setattr(c.awg.Adapter, 'ready', reject_once)
    def reconcile(host, document, *, check=False, verify_only=False, revocation=None):
        if not verify_only:
            events.append('check' if check else 'apply')
            payload = {'check': check, 'revocation': revocation, 'candidates': [data(c.cfg, candidate)],
                       'firewall': base64.b64encode(c.fw.HEADER + b'table inet filter {}\n').decode()}
            c.awg.operate('recover', {'check': check, 'revocation': revocation})
            c.awg.operate('apply', payload)
        return runtime(host, document, check=check, verify_only=verify_only, revocation=revocation)
    monkeypatch.setattr(operation.io, 'runtime', reconcile)
    with pytest.raises(c.tx.Refusal, match='candidate-refused'):
        revoke.run()
    assert (c.awg.STATE / 'pending.json').exists()
    assert c.states['awg-quick@a0.service']['ActiveState'] == 'inactive'
    assert revoke.run()['phase'] == 'complete'
    assert events == ['check', 'apply', 'check', 'apply']
    assert c.cfg.read_bytes() == candidate
    assert not (c.awg.STATE / 'pending.json').exists()
    assert not (c.awg.STATE / 'firewall.json').exists()


def test_output_collision_retains_existing_bytes_and_incomplete_operation(operation):
    prepare(operation)
    output = Path(operation.manifest['delivery']['output'])
    output.write_bytes(b'owned-by-another-operation')
    output.chmod(0o600)
    with pytest.raises(ValueError, match='output-conflict'):
        operation.run()
    assert output.read_bytes() == b'owned-by-another-operation'
    assert operation.status()['phase'] != 'complete'


def test_existing_output_refuses_before_encrypted_intent(operation):
    output = Path(operation.manifest['delivery']['output'])
    output.write_bytes(b'keep')
    output.chmod(0o600)
    with pytest.raises(ValueError, match='already-exists'):
        operation.inspect()
    assert 'device_operations' not in read_document(operation.journal_path)


def test_source_change_after_review_refuses_mutation(operation, monkeypatch):
    review = operation.inspect()[-1]
    monkeypatch.setattr(operation.io, 'source_identity', lambda: {'DEPLOY_SOURCE_REVISION': 'c'*40, 'DEPLOYABLE_SOURCE_DIGEST': 'd'*64})
    with pytest.raises(ValueError, match='approval'):
        operation.prepare(review['approval'])
    assert 'device_operations' not in read_document(operation.journal_path)


def test_source_change_on_resume_preserves_pending_intent(operation, monkeypatch):
    prepare(operation)
    monkeypatch.setattr(operation.io, 'source_identity', lambda: {'DEPLOY_SOURCE_REVISION': 'c'*40, 'DEPLOYABLE_SOURCE_DIGEST': 'd'*64})
    with pytest.raises(ValueError, match='source-changed'):
        operation.run()
    assert operation.status()['phase'] == 'prepared'


def test_forged_terminal_phase_without_evidence_is_rejected(operation):
    prepare(operation)
    def corrupt(doc):
        doc['device_operations'][operation.manifest['id']]['phase'] = 'complete'
        return doc, {}
    operate(operation.journal_path, corrupt)
    with pytest.raises(ValueError, match='incomplete-device-operation'):
        operation.status()


def test_completed_run_rechecks_actual_runtime_and_native_access(operation):
    prepare(operation)
    operation.run()
    operation.io.probe_state = 'unknown'
    with pytest.raises(ValueError, match='native-probe'):
        operation.run()


def test_refresh_keeps_all_existing_links_and_expiry(operation):
    prepare(operation)
    operation.run()
    snapshots = operation.snapshots()['upcloud:prod']['rows']
    first_token, first = next(iter(snapshots.items()))
    other = json.loads(base64.b64decode(first['document_b64']))
    other['expires'] = '2099-01-01T00:00:00Z'
    second_token = 'f'*64
    operation.io.publisher('upcloud:prod', 'publish', second_token, None, encoded(other))
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(id='33333333-3333-4333-8333-333333333333', action='refresh')
    manifest['delivery']['output'] = None
    refresh = Lifecycle(manifest, operation.io)
    prepare(refresh)
    assert refresh.run()['phase'] == 'complete'
    after = refresh.snapshots()['upcloud:prod']['rows']
    assert set(after) == {first_token, second_token}
    assert json.loads(base64.b64decode(after[second_token]['document_b64']))['expires'] == other['expires']
    assert read_document(operation.journal_path)['client_registry']['new-phone']['awg_private_key'] == read_document(operation.journal_path)['device_operations'][operation.manifest['id']]['after']['upcloud:prod']['client_registry']['new-phone']['awg_private_key']


def test_running_publisher_must_actually_deny_revoked_canary(operation, monkeypatch):
    prepare(operation)
    operation.run()
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(id='44444444-4444-4444-8444-444444444444', action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    prepare(revoke)
    # Snapshot reads the real file, while an obsolete HTTP reader ignores it.
    monkeypatch.setattr(operation.io.service, '_is_revoked', lambda token: False)
    with pytest.raises(ValueError, match='route-mismatch'):
        revoke.run()
    assert revoke.status()['phase'] != 'complete'


def test_revoke_rechecks_running_policy_after_final_native_probes(operation, monkeypatch):
    prepare(operation)
    operation.run()
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(id='55555555-5555-4555-8555-555555555555', action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    prepare(revoke)
    original = operation.io.probe
    count = 0
    def change_after_probe(*args):
        nonlocal count
        result = original(*args)
        count += 1
        if count == 2:
            operation.io.service.REVOKED_FILE.write_text('')
        return result
    monkeypatch.setattr(operation.io, 'probe', change_after_probe)
    with pytest.raises(ValueError, match='final-publication'):
        revoke.run()
    assert revoke.status()['phase'] != 'complete'


@pytest.mark.parametrize('engine', ['naive', 'amneziawg'])
def test_native_only_issue_refresh_and_revoke_have_usable_private_artifacts(operation, monkeypatch, engine):
    import client_payload
    import device_lifecycle_credentials
    import device_lifecycle_probe
    settings = client_payload.context('device-full-tailnet')
    settings['vpn'] = {name: False for name in settings['vpn']}
    settings['vpn']['enable_' + engine] = True
    for module in (client_payload, device_lifecycle_credentials, device_lifecycle_probe):
        monkeypatch.setattr(module, 'context', lambda _: copy.deepcopy(settings))
    def add_naive(doc):
        doc['naive_secrets'] = {'server_name': 'native.example', 'clients': []}
        return doc, {}
    operate(operation.journal_path, add_naive)
    manifest = copy.deepcopy(operation.manifest)
    manifest['publishers'] = []
    manifest['delivery'].update(format='native', awg_host='')
    issue = Lifecycle(manifest, operation.io)
    prepare(issue)
    assert issue.run()['phase'] == 'complete'
    artifact = json.loads(Path(manifest['delivery']['output']).read_bytes())
    assert artifact['subscription_url'] is None and artifact['profile'] is None
    if engine == 'naive':
        assert artifact['naive_uris']['upcloud:prod'].startswith('naive+https://new-phone:')
    else:
        config = artifact['amneziawg_configs']['upcloud:prod']
        assert '<CLIENT_PRIVATE_KEY>' not in config and '[Interface]' in config and '[Peer]' in config
        assert read_document(issue.journal_path)['client_registry']['new-phone']['awg_private_key'] in config
    original = read_document(issue.journal_path)
    identity = original['client_registry']['new-phone']['last_payload_identity']
    manifest = copy.deepcopy(manifest)
    manifest.update(id='66666666-6666-4666-8666-666666666666', action='refresh')
    manifest['delivery']['output'] = str(Path(manifest['delivery']['output']).with_name('refreshed.json'))
    refresh = Lifecycle(manifest, operation.io)
    prepare(refresh)
    assert refresh.run()['phase'] == 'complete'
    assert json.loads(Path(manifest['delivery']['output']).read_bytes()) == artifact
    assert read_document(issue.journal_path)['client_registry']['new-phone']['last_payload_identity'] == identity
    manifest.update(id='77777777-7777-4777-8777-777777777777', action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    prepare(revoke)
    assert revoke.run()['phase'] == 'complete'
    final = read_document(issue.journal_path)
    assert final['naive_secrets']['clients'] == []
    assert all(row['name'] != 'new-phone' for item in final['amneziawg_secrets']['instances'] for row in item['peers'])


def test_revocation_cleanup_lost_ack_does_not_leak_probe_documents(operation, monkeypatch):
    prepare(operation)
    operation.run()
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(id='88888888-8888-4888-8888-888888888888', action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    prepare(revoke)
    original = operation.io.publisher
    first = True
    def lose_cleanup(*args, **kwargs):
        nonlocal first
        result = original(*args, **kwargs)
        if len(args) == 5 and args[1] == 'publish' and args[4] is None and first:
            first = False
            raise OSError('cleanup acknowledgement lost')
        return result
    monkeypatch.setattr(operation.io, 'publisher', lose_cleanup)
    with pytest.raises(OSError):
        revoke.run()
    assert revoke.run()['phase'] == 'complete'
    assert len(revoke.snapshots()['upcloud:prod']['rows']) == 1
    assert all(row['cleaned'] for row in revoke._journal()['canaries'].values())


def test_grant_only_revoke_reconciles_every_node_and_resumes_actual_tls_denial(operation):
    from device_lifecycle_credentials import revoke as remove_credentials
    prepare(operation)
    operation.run()
    artifact = json.loads(Path(operation.manifest['delivery']['output']).read_bytes())
    token = artifact['subscription_url'].rsplit('/', 1)[1]
    def remove_authority(document):
        result = remove_credentials({'node': document}, operation.name)['node']
        del result['client_registry'][operation.name]
        return result, {}
    operate(operation.journal_path, remove_authority)
    second_path = Path(operation.journal_path).with_name('second.sops.yaml')
    second_path.write_bytes(Path(operation.journal_path).read_bytes())
    second_path.chmod(0o600)
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(id='dddddddd-dddd-4ddd-8ddd-dddddddddddd', action='revoke', delivery=None)
    second = copy.deepcopy(manifest['nodes'][0])
    second.update(host='upcloud:secondary', alias='secondary', secrets_file=str(second_path))
    manifest['nodes'].append(second)
    revoke = Lifecycle(manifest, operation.io)
    assert not any(revoke.inspect()[-1]['nodes'].values())
    assert revoke.inspect()[-1]['grants'] == {'upcloud:prod': 1}
    prepare(revoke)
    assert revoke._journal()['profiles'] == {}
    operation.io.events.clear()
    operation.io.fail_runtime = True
    with pytest.raises(OSError, match='acknowledgement'):
        revoke.run()
    assert revoke.status()['phase'] != 'complete'
    result = revoke.run()
    assert result['phase'] == 'complete' and result['native_credential_profiles'] == 0
    assert result['nodes_adopted'] == 2 and result['grants_confirmed'] == 1
    assert {host for event, host in operation.io.events if event == 'adopt'} == {'upcloud:prod', 'upcloud:secondary'}
    assert {host for event, host in operation.io.events if event == 'verify'} == {'upcloud:prod', 'upcloud:secondary'}
    operation.io.read_route('upcloud:prod', token, b'', revoked=True)
    assert revoke.run() == result


def test_revoke_requires_device_authority_or_an_exact_published_grant(operation):
    manifest = copy.deepcopy(operation.manifest)
    manifest.update(action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    with pytest.raises(ValueError, match='device-not-found'):
        revoke.inspect()
    assert 'device_operations' not in read_document(operation.journal_path)


def test_real_device_may_share_internal_canary_client_name(operation):
    manifest = copy.deepcopy(operation.manifest)
    manifest['device'] = 'device-revocation-check'
    issue = Lifecycle(manifest, operation.io)
    prepare(issue)
    issue.run()
    manifest.update(id='eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', action='revoke', delivery=None)
    revoke = Lifecycle(manifest, operation.io)
    prepare(revoke)
    from hashlib import sha256
    canary = revoke._journal()['canaries']['upcloud:prod']
    token_hash = sha256(canary['token'].encode()).hexdigest()
    altered = json.loads(base64.b64decode(canary['document_b64']))
    altered['payload_b64'] = base64.b64encode(encoded({'foreign': True})).decode()
    raw = encoded(altered)
    operation.io.publisher('upcloud:prod', 'publish', token_hash, None, raw)
    with pytest.raises(ValueError, match='new-device-grant'):
        revoke._fence(revoke._journal())
    operation.io.publisher('upcloud:prod', 'publish', token_hash, sha256(raw).hexdigest(), None)
    assert revoke.run()['phase'] == 'complete'
    rows = revoke.snapshots()['upcloud:prod']['rows']
    assert len(rows) == 1 and all(row['revoked'] for row in rows.values())
    assert revoke.run()['phase'] == 'complete'
