"""Typed production onboarding boundaries; fixture results are not live proof."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import recovery_promotion as promotion
import yaml
from recovery_io import canonical, document
from test_recovery_io import manifest as manifest  # noqa: PLC0414
from test_recovery_provider import cloud as cloud  # noqa: PLC0414
from test_sshd_promotion_proof import _config


@pytest.fixture
def intent(tmp_path, request):
    proof = json.loads(_config(tmp_path).read_text())
    config = yaml.safe_load(Path(proof['liveness_config']).read_bytes())
    target = {key: proof['target_identity'][key] for key in promotion.TARGET}
    config['sentinels'][0]['target'] = target
    config['sentinels'][0].pop('awg_target', None)
    config['policies'][0]['required_profiles'] = ['p0-reality']
    value = {'schema_version': 1, 'kind': promotion.KIND, 'target_identity': target,
            'host': 'upcloud:replacement', 'cohort': 'p0-minimal', 'client': 'dedicated-probe',
            'liveness': config, 'inputs': {name: str(tmp_path / name) if name != 'awg_key_file' else None
                                         for name in promotion.INPUTS}}
    if getattr(request, 'param', 'recovery') == 'cloud':
        value['kind'] = promotion.CLOUD_KIND
        value['inputs']['provisioning_manifest'] = value['inputs'].pop('recovery_manifest')
        config['sentinels'][0].update(ssh_transport_host='192.0.2.44', ssh_host_key_alias='192.0.2.44')
    return value


def test_draft_requires_no_manufactured_epoch_or_private_file_reads(intent):
    original = copy.deepcopy(intent)
    assert promotion.validate_intent(intent) == original
    assert intent == original
    assert 'applied_at' not in intent['liveness']['sentinels'][0]['target']
    assert all(path is None or not Path(path).exists() for path in intent['inputs'].values())


@pytest.mark.parametrize('intent', ['cloud'], indirect=True)
@pytest.mark.parametrize(('host', 'cohort', 'profiles'), [
    ('upcloud:p0-node', 'p0-minimal', ['p0-reality']),
    ('scaleway:p1-node', 'p1-web', ['p1-xhttp']),
    ('vultr:p2-node', 'p2-udp', ['p2-amneziawg', 'p2-hysteria2']),
    ('upcloud:ci-staging-full', 'device-full-staging', ['p0-reality', 'p1-xhttp', 'p2-amneziawg', 'p2-hysteria2']),
])
def test_cloud_intent_requires_exact_target_profile_subset(intent, host, cohort, profiles, tmp_path):
    intent.update(host=host, cohort=cohort)
    intent['liveness']['policies'][0]['required_profiles'] = profiles
    if 'p2-amneziawg' in profiles:
        provider, environment = host.split(':')
        intent['inputs']['awg_key_file'] = str(tmp_path / 'awg-private')
        intent['liveness']['sentinels'][0]['awg_target'] = {'provider': provider, 'environment': environment, 'instance': 'awg0'}
        intent['liveness']['expected_runtime']['awg_toolchain'] = 'a' * 64
    assert promotion.validate_intent(intent) == intent
    intent['liveness']['policies'][0]['required_profiles'] = ['p1-xhttp'] if profiles == ['p0-reality'] else ['p0-reality']
    with pytest.raises(promotion.PromotionError):
        promotion.validate_intent(intent)


@pytest.mark.parametrize('intent', ['cloud'], indirect=True)
def test_cloud_draft_schema_admits_canonical_nondefault_host_key_alias(intent):
    intent['liveness']['sentinels'][0]['ssh_host_key_alias'] = '[192.0.2.44]:2222'
    assert promotion.validate_intent(intent) == intent


@pytest.mark.parametrize('intent', ['cloud'], indirect=True)
@pytest.mark.parametrize('change_at', [2, 3])
def test_cloud_first_install_rechecks_resource_scope_before_publishing_proof(installation, monkeypatch, change_at):
    value, outputs, state = installation
    manifest, server, _ = promotion._scope(value, {})
    calls = []
    def scope(*_):
        calls.append(1)
        return manifest, (server if len(calls) < change_at else {'public_ipv4': ['192.0.2.99']}), outputs
    monkeypatch.setattr(promotion, '_scope', scope)
    with pytest.raises(promotion.PromotionError):
        promotion.finalize(value, {}, clock=lambda: 1_800_000_001)
    assert state['installs'] == (1 if change_at == 3 else 0)
    assert not Path(outputs['proof']).exists()
    if change_at == 2:
        assert not any(Path(path).exists() for path in outputs.values())


@pytest.mark.parametrize('fault', ['prod', 'staging', 'foreign-provider', 'epoch', 'missing-profile',
                                 'extra-sentinel', 'unbound-target', 'relative-path', 'missing-client', 'bool-version'])
def test_draft_refuses_scope_expansion_or_fake_epoch(intent, fault):
    if fault == 'prod':
        intent['host'] = 'upcloud:prod'
    elif fault == 'staging':
        intent['host'] = 'upcloud:ci-staging-test'
    elif fault == 'foreign-provider':
        intent['host'] = 'vultr:replacement'
    elif fault == 'epoch':
        intent['liveness']['sentinels'][0]['target']['applied_at'] = 123
    elif fault == 'missing-profile':
        intent['liveness']['policies'][0]['required_profiles'] = []
    elif fault == 'extra-sentinel':
        intent['liveness']['sentinels'].append(copy.deepcopy(intent['liveness']['sentinels'][0]))
    elif fault == 'unbound-target':
        intent['target_identity'] = dict(intent['target_identity'], deployable_digest='f' * 64)
    elif fault == 'relative-path':
        intent['inputs']['sops_file'] = 'relative'
    elif fault == 'missing-client':
        del intent['client']
    elif fault == 'bool-version':
        intent['schema_version'] = True
    with pytest.raises(promotion.PromotionError):
        promotion.validate_intent(intent)


@pytest.fixture
def prepared(intent, tmp_path, monkeypatch):
    import disposable_promotion
    directory = tmp_path / 'transaction'
    directory.mkdir(mode=0o700)
    outputs = {key: str(tmp_path / ('owned-' + key + '.json')) for key in promotion.OUTPUTS}
    manifest = {'source_revision': 'a' * 40}
    server = {'public_ipv4': ['192.0.2.10'], 'ssh_port': 22, 'admin_user': 'deploy'}
    monkeypatch.setattr(promotion, '_scope', lambda value, environment: (manifest, server, outputs))
    for name, path in intent['inputs'].items():
        if path:
            Path(path).write_bytes(('synthetic-' + name).encode())
            Path(path).chmod(0o600)
    plaintext = yaml.safe_dump({'client_registry': {intent['client']: {'status': 'issued'}}}).encode()
    def decrypt(_sops, _age, output, _environment):
        output.write_bytes(plaintext)
        output.chmod(0o600)
    monkeypatch.setattr(disposable_promotion, '_decrypt', decrypt)
    host = {'name': intent['target_identity']['inventory_alias'], 'address': '192.0.2.10', 'port': 22, 'user': 'deploy'}
    value = promotion.prepare_intent(intent, host, ['vpn-p0-minimal'], directory, plaintext, {})
    return value, outputs, directory, host, plaintext


def test_prepare_freezes_exact_capabilities_without_mutating_source(prepared):
    value, outputs, directory, _, _ = prepared
    for name in ('sops_file', 'age_key_file'):
        original = Path(value['prepared']['source_inputs'][name])
        frozen = Path(value['inputs'][name])
        assert frozen.parent == directory and frozen.read_bytes() == original.read_bytes()
        assert frozen.stat().st_mode & 0o777 == 0o600
    assert not (directory / 'recovery-promotion-plaintext.yaml').exists()
    assert not any(Path(path).exists() for path in outputs.values())


@pytest.mark.parametrize('intent', ['cloud'], indirect=True)
@pytest.mark.parametrize(('field', 'wrong'), [('port', 2222), ('user', 'root')])
def test_cloud_scope_binds_target_ssh_endpoint_before_freezing(prepared, field, wrong):
    value, _, parent, host, plain = prepared
    directory = parent / 'mismatched-target'
    directory.mkdir(mode=0o700)
    with pytest.raises(promotion.PromotionError, match='preflight-refused'):
        promotion.prepare_intent(promotion._original(value), {**host, field: wrong},
                                 ['vpn-p0-minimal'], directory, plain, {})
    assert not list(directory.iterdir())


def test_prepare_decrypts_actual_sops_and_cleans_owned_plaintext(intent, tmp_path, monkeypatch):
    key = Path(intent['inputs']['age_key_file'])
    subprocess.run(['age-keygen', '-o', str(key)], check=True, capture_output=True)
    recipient = subprocess.run(['age-keygen', '-y', str(key)], check=True, capture_output=True, text=True).stdout.strip()
    plain = yaml.safe_dump({'client_registry': {intent['client']: {'status': 'issued'}}}).encode()
    cipher = subprocess.run(['sops', '--encrypt', '--age', recipient, '--input-type', 'yaml',
        '--output-type', 'yaml', '/dev/stdin'], input=plain, check=True, capture_output=True).stdout
    source = Path(intent['inputs']['sops_file'])
    source.write_bytes(cipher)
    source.chmod(0o600)
    outputs = {key: str(tmp_path / ('real-' + key + '.json')) for key in promotion.OUTPUTS}
    monkeypatch.setattr(promotion, '_scope', lambda *_: ({'source_revision': 'a' * 40},
        {'public_ipv4': ['192.0.2.10']}, outputs))
    directory = tmp_path / 'real-sops-transaction'
    directory.mkdir(mode=0o700)
    host = {'name': intent['target_identity']['inventory_alias'], 'address': '192.0.2.10'}
    prepared = promotion.prepare_intent(intent, host, ['vpn-p0-minimal'], directory, plain, dict(os.environ))
    assert Path(prepared['inputs']['sops_file']).read_bytes() == source.read_bytes() == cipher
    assert not (directory / 'recovery-promotion-plaintext.yaml').exists()


def test_cleanup_failure_never_returns_capability_or_private_diagnostics(prepared, monkeypatch):
    import traceback
    value, _, parent, host, plain = prepared
    directory = parent / 'cleanup'
    directory.mkdir(mode=0o700)
    original = Path.unlink
    def unlink(path, **kwargs):
        if path == directory / 'recovery-promotion-plaintext.yaml':
            raise OSError('private-fixture ' + plain.decode())
        return original(path, **kwargs)
    monkeypatch.setattr(Path, 'unlink', unlink)
    with pytest.raises(promotion.PromotionError, match='cleanup-incomplete') as error:
        promotion.prepare_intent(promotion._original(value), host, ['vpn-p0-minimal'], directory, plain, {})
    assert 'private-fixture' not in ''.join(traceback.format_exception(error.value))


@pytest.mark.parametrize('fault', ['missing-hash', 'null-hash', 'source-alias', 'output-alias', 'wrong-manifest'])
def test_prepared_intent_refuses_ambiguous_capability(prepared, fault):
    value = copy.deepcopy(prepared[0])
    if fault == 'missing-hash':
        del value['prepared']['input_sha256']['sops_file']
    elif fault == 'null-hash':
        value['prepared']['input_sha256']['sops_file'] = None
    elif fault == 'source-alias':
        value['prepared']['source_inputs']['sops_file'] = value['inputs']['sops_file']
    elif fault == 'output-alias':
        value['prepared']['outputs']['proof'] = value['prepared']['source_inputs']['age_key_file']
    else:
        value['inputs']['recovery_manifest'] += '-other'
    with pytest.raises(promotion.PromotionError):
        promotion.validate_intent(value)


@pytest.fixture
def installation(prepared, monkeypatch):
    import install_liveness_sentinel as installer
    value, outputs, *_ = prepared
    state = {'installs': 0, 'reads': 0, 'lost_ack': False}
    monkeypatch.setattr(installer, '_source_identity', lambda _: ('a' * 40, b'runner', b'engine'))
    def install(config, sid, client, registry, **kwargs):
        state['installs'] += 1
        assert kwargs['environment']['HOSTS'] == value['host']
        assert kwargs['environment']['SOPS_FILE'] == value['inputs']['sops_file']
        assert kwargs['read_awg_stdin'] is False and kwargs['stdin'].read() == ''
        sentinel = document(config)['sentinels'][0]
        provenance = {'controller_revision': 'a' * 40, 'runner_sha256': hashlib.sha256(b'runner').hexdigest(),
            'client_generation_id': '00000000-0000-4000-8000-000000000001',
            'public_profile_digest': 'e' * 64, 'vantage': 'external'}
        target = sentinel['target'] | {'required_profiles': ['p0-reality'], 'source_revision': 'a' * 40,
            'runner_sha256': provenance['runner_sha256'], 'public_profile_digest': 'e' * 64}
        entry = {'client': client, **{k: sentinel[k] for k in ('ssh_target', 'ssh_transport_host', 'ssh_host_key_alias') if k in sentinel}, 'policy': sentinel['policy'],
            'vantage': sentinel['vantage'], 'generation_id': provenance['client_generation_id'],
            'provenance': provenance, 'required_profiles': ['p0-reality'], 'target_identity': target}
        installer._write(registry, canonical({'schema_version': 2, 'sentinels': {sid: entry}}))
        state['receipt'] = {'generation_id': entry['generation_id'], 'status': 'committed',
            'runner_sha256': target['runner_sha256'], 'provenance': provenance, 'target_identity': target}
        if state['lost_ack']:
            raise installer.InstallError('synthetic-lost-ack')
        return copy.deepcopy(state['receipt'])
    def receipt(*_args):
        state['reads'] += 1
        return copy.deepcopy(state['receipt'])
    monkeypatch.setattr(installer, 'install', install)
    monkeypatch.setattr(installer, '_receipt', receipt)
    return value, outputs, state


@pytest.mark.parametrize('lost_ack', [False, True])
@pytest.mark.parametrize('intent', ['recovery', 'cloud'], indirect=True)
def test_real_registry_resume_requires_exact_receipt_and_retains_epoch(installation, lost_ack):
    value, outputs, state = installation
    state['lost_ack'] = lost_ack
    if lost_ack:
        with pytest.raises(promotion.PromotionError):
            promotion.finalize(value, {}, clock=lambda: 1_800_000_001)
        assert not Path(outputs['proof']).exists()
    else:
        promotion.finalize(value, {}, clock=lambda: 1_800_000_001)
    result = promotion.finalize(value, {}, clock=lambda: 1_800_000_100)
    assert document(result)['target_identity']['applied_at'] == 1_800_000_001
    assert state['installs'] == 1 and state['reads'] == 1
    state['receipt']['generation_id'] = '00000000-0000-4000-8000-000000000002'
    with pytest.raises(promotion.PromotionError):
        promotion.finalize(value, {}, clock=lambda: 1_800_000_200)
    assert state['installs'] == 1


def test_interrupted_registry_publication_resumes_pending_generation(installation, monkeypatch):
    import install_liveness_sentinel as installer
    value, outputs, state = installation
    promotion.finalize(value, {}, clock=lambda: 1_800_000_001)
    registry = document(outputs['registry'])
    pending = Path(outputs['registry'] + '.pending.json')
    installer._write(pending, canonical({'schema_version': 2, 'pending': registry['sentinels']}))
    Path(outputs['proof']).unlink()
    calls = []
    def reconcile(config, sid, client, registry_path, **kwargs):
        assert document(pending)['pending'][sid] == document(registry_path)['sentinels'][sid]
        calls.append('resume-same-generation')
        installer._write(pending, canonical({'schema_version': 2, 'pending': {}}))
        return copy.deepcopy(state['receipt'])
    monkeypatch.setattr(installer, 'install', reconcile)
    result = promotion.finalize(value, {}, clock=lambda: 1_800_000_100)
    assert calls == ['resume-same-generation']
    assert document(result)['target_identity']['applied_at'] == 1_800_000_001


@pytest.mark.parametrize('fault', ['source', 'frozen', 'authority', 'orphan-output'])
def test_finalization_refuses_changed_authority_before_installer(installation, fault):
    value, outputs, state = installation
    if fault in ('source', 'frozen'):
        path = value['prepared']['source_inputs']['sops_file'] if fault == 'source' else value['inputs']['sops_file']
        Path(path).write_bytes(b'changed')
    else:
        path = Path(outputs['authority'] if fault == 'authority' else outputs['proof'])
        path.write_bytes(canonical({'unrelated': True}))
        path.chmod(0o600)
    with pytest.raises(promotion.PromotionError):
        promotion.finalize(value, {}, clock=lambda: 1_800_000_001)
    assert state['installs'] == 0


def test_cli_validates_draft_without_treating_it_as_live_proof(intent, tmp_path):
    path = tmp_path / 'draft.json'
    path.write_bytes(canonical(intent))
    path.chmod(0o600)
    command = [sys.executable, str(promotion.ROOT / 'scripts/sshd-promotion-proof.py'), '--config', str(path)]
    valid = subprocess.run(command + ['--validate-config'], check=False, capture_output=True, timeout=15)
    assert valid.returncode == 0, valid.stderr
    proof = subprocess.run(command, check=False, capture_output=True, timeout=15)
    assert proof.returncode != 0 and not proof.stdout


@pytest.mark.parametrize('intent', ['recovery', 'cloud'], indirect=True)
def test_baseline_dispatches_typed_recovery_intent(prepared, monkeypatch):
    value, _, directory, *_ = prepared
    source = directory / 'prepared.json'
    source.write_bytes(canonical(value))
    source.chmod(0o600)
    result = directory / 'real-proof.json'
    calls = []
    def finalize(intent, environment):
        calls.append((intent, environment))
        return result
    monkeypatch.setattr(promotion, 'finalize', finalize)
    controller = promotion.module('sshd-baseline-controller')
    assert controller.prepare_promotion(source, {'fixture': 'environment'}) == (result, True)
    assert calls == [(value, {'fixture': 'environment'})]


def test_scope_binds_real_journal_state_manifest_and_clean_source(cloud, manifest, intent, tmp_path, monkeypatch):
    from recovery_io import Journal
    from recovery_provider import server_identity
    value, path = manifest
    _, server, state, _ = cloud
    intent['inputs'].update(recovery_manifest=str(path), sops_file=value['sops_file'], age_key_file=value['age_key_file'])
    target = intent['target_identity']
    target.update(inventory_alias=value['hostname'], public_service_address_sha256=hashlib.sha256(b'192.0.2.10').hexdigest())
    root = tmp_path / 'checkout'
    state_path = root / 'terraform/providers/upcloud/terraform.tfstate.d/replacement/terraform.tfstate'
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(canonical(state))
    state_path.chmod(0o600)
    monkeypatch.setattr(promotion, 'ROOT', root)
    deploy = promotion.module('deploy-controller')
    identity = {'DEPLOY_SOURCE_REVISION': value['source_revision'], 'DEPLOYABLE_SOURCE_DIGEST': target['deployable_digest']}
    clean = []
    def source(_root, _environment, *, require_clean):
        clean.append(require_clean)
        return identity
    monkeypatch.setattr(deploy, 'source_identity', source)
    monkeypatch.setattr(promotion, 'module', lambda name: deploy)
    with Journal(value) as journal:
        journal.observe('server', server_identity(server, value))
        selected, observed, outputs = promotion._scope(intent, {})
        assert selected == value and observed['uuid'] == server['uuid']
        assert all(Path(output).parent == journal.directory for output in outputs.values())
        identity['DEPLOY_SOURCE_REVISION'] = 'b' * 40
        with pytest.raises(promotion.PromotionError, match='source-mismatch'):
            promotion._scope(intent, {})
        identity['DEPLOY_SOURCE_REVISION'] = value['source_revision']
        state['resources'][0]['instances'][0]['attributes']['id'] = '22222222-2222-4222-8222-222222222222'
        state_path.write_bytes(canonical(state))
        with pytest.raises(ValueError, match='identity-changed'):
            promotion._scope(intent, {})
    assert clean == [True, True, True]


@pytest.mark.parametrize('intent', ['recovery', 'cloud'], indirect=True)
def test_deploy_prepares_recovery_before_validation_or_remote_write(prepared, monkeypatch):
    value, _, directory, host, plaintext = prepared
    original = promotion._original(value)
    directory = directory / 'fresh'
    directory.mkdir(mode=0o700)
    controller = promotion.module('deploy-controller')
    host.update(transport='100.64.0.10', port=22)
    contexts = [{'user': 'deploy', 'host': 'mac', 'addr': source, 'laddr': destination, 'lport': 22}
        for source, destination in (('198.51.100.1', host['address']), ('100.64.0.1', host['transport']))]
    for variable, filename, data in (
        ('DEPLOY_SSH_CONTEXTS_FILE', 'contexts.json', {host['name']: contexts}),
        ('DEPLOY_PROMOTION_CONFIG_FILE', 'promotions.json', {host['name']: original}),
        ('DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE', 'failures.json', {host['name']: str(directory / 'failure.json')})):
        path = directory / filename
        path.write_bytes(canonical(data))
        path.chmod(0o600)
        monkeypatch.setenv(variable, str(path))
    # The target hash is the public endpoint, independently of its SSH transport.
    original['target_identity']['public_service_address_sha256'] = hashlib.sha256(host['address'].encode()).hexdigest()
    original['liveness']['sentinels'][0]['target'] = copy.deepcopy(original['target_identity'])
    (directory / 'promotions.json').write_bytes(canonical({host['name']: original}))
    monkeypatch.setattr(controller, 'bundle_manifest', lambda: ('b' * 64, {}))
    calls = []
    prepare = promotion.prepare_intent
    def real_prepare(*args):
        calls.append('prepare')
        return prepare(*args)
    def checked(argv, **kwargs):
        assert calls == ['prepare']
        calls.append('validate')
        promotion.validate_intent(document(argv[-1]))
    monkeypatch.setattr(promotion, 'prepare_intent', real_prepare)
    monkeypatch.setattr(controller, 'checked', checked)
    result = controller.transaction_inputs('deploy', [host],
        {'DEPLOYABLE_SOURCE_DIGEST': original['target_identity']['deployable_digest']}, directory,
        promotion.ROOT, {}, memberships={host['name']: ['vpn-p0-minimal']}, deployed_secrets=plaintext)
    assert calls == ['prepare', 'validate']
    assert result[host['name']]['ssh_transaction_promotion_config_path']
