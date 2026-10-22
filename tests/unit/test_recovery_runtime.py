"""Recovery reconciliation fixtures exercise decisions, never claim live proof."""
from __future__ import annotations

import copy
import sys

import pytest
import recovery
from recovery_io import ActionRequired, Journal, RecoveryError, digest, document
from recovery_runtime import Runtime
from test_recovery_io import manifest as manifest  # noqa: PLC0414


class Model:
    """Stateful provider/guest model with explicit lost acknowledgements."""
    def __init__(self, manifest):
        self.manifest = manifest
        self.calls = []
        self.state_value = None
        self.server_value = None
        self.lost = None
        self.pending = True
        self.phase = 'prepared'
        self.counter = 0
        self.input_value = {'source': 'fixture', 'tfvars_sha256': 'a' * 64}

    def source(self):
        return {'DEPLOY_SOURCE_REVISION': self.manifest['source_revision']}

    def inputs(self):
        return copy.deepcopy(self.input_value)

    def state(self):
        return copy.deepcopy(self.state_value)

    def observe(self):
        return {'account_sha256': 'b' * 64, 'servers': [copy.deepcopy(self.server_value)] if self.server_value else []}

    def make(self, goal):
        self.calls.append(goal)

    def plan(self, existing):
        self.calls.append('plan')
        self.counter += 1
        return {'plan_sha256': str(self.counter) * 64, 'inputs': self.inputs(), 'state_sha256': digest(existing),
            'review': {'changes': ['create'] if existing is None else [], 'server': {
            'hostname': self.manifest['hostname'], 'zone': 'test-zone', 'plan': 'test-plan',
            'labels': {'managed_by': 'terraform', 'recovery_id': self.manifest['id']}}}}

    def create(self):
        self.server_value = {'uuid': 'fixture-uuid', 'hostname': self.manifest['hostname'], 'created': int(recovery.time.time()),
            'zone': 'test-zone', 'plan': 'test-plan', 'state': 'started', 'public_ipv4': ['192.0.2.10'],
            'labels': {'managed_by': 'terraform', 'recovery_id': self.manifest['id']}}
        self.state_value = {key: copy.deepcopy(value) for key, value in self.server_value.items()
                            if key in ('hostname', 'zone', 'plan', 'labels')}
        self.state_value['id'] = self.server_value['uuid']

    def apply(self, retained):
        self.calls.append('apply')
        self.create()
        if self.lost == 'orphan':
            self.state_value = None
        if self.lost:
            raise RecoveryError('lost-ack')

    def import_server(self, server):
        self.calls.append('import')
        self.state_value = {key: copy.deepcopy(value) for key, value in server.items()
                            if key in ('hostname', 'zone', 'plan', 'labels')}
        self.state_value['id'] = server['uuid']

    def migration_contract(self):
        return {}

    def inventory_render(self):
        self.calls.append('inventory')
        return {'name': 'fixture'}

    def pin_binding(self, server, host):
        return {'server': server, 'pin': 'fixture-authenticated'}

    def management(self, host):
        self.calls.append('management')
        return 'fixture-contexts'

    def migration(self, action, approval=None, allowed=(0,)):
        self.calls.append('migration-' + action)
        if action == 'plan':
            return {'approval': 'c' * 64, 'devices': ['fixture-device']}
        if action == 'publish':
            self.phase = 'published'
        return {'phase': self.phase, 'ready': not self.pending}

    def converge(self, contexts, journal, approval):
        self.calls.append('converge')


def approve_next(call):
    with pytest.raises(ActionRequired) as challenge:
        call(None)
    return challenge.value.digest


def test_positive_approval_resume_then_fresh_device_acceptance(manifest):
    value, _ = manifest
    runtime = Model(value)
    with Journal(value) as journal:
        call = lambda approval: recovery.recover(value, runtime, journal, approval)
        apply = approve_next(call)
        pin = approve_next(lambda _: call(apply))
        migration = approve_next(lambda _: call(pin))
        pending = call(migration)
        assert pending['ready'] is False and pending['status'] == 'awaiting-device-acceptance'
        runtime.pending = False
        assert call(None)['ready'] is True
    assert runtime.calls.count('apply') == 1
    assert runtime.calls.count('converge') == 1
    assert runtime.calls.count('management') >= 3
    assert runtime.calls[-1] == 'migration-ready'


@pytest.mark.parametrize('lost', ['state-written', 'orphan'])
def test_lost_apply_response_never_creates_duplicate(manifest, lost):
    value, _ = manifest
    runtime = Model(value)
    with Journal(value) as journal:
        call = lambda approval: recovery.provision(value, runtime, journal, approval)
        approval = approve_next(call)
        runtime.lost = lost
        with pytest.raises(RecoveryError, match='lost-ack'):
            call(approval)
    with Journal(value) as resumed:
        call = lambda approval: recovery.provision(value, runtime, resumed, approval)
        if lost == 'orphan':
            approval = approve_next(call)
            server = call(approval)
            assert runtime.calls.count('import') == 1
        else:
            server = call(None)
        assert server['uuid'] == 'fixture-uuid'
    assert runtime.calls.count('apply') == 1


def test_approval_survives_invocation_without_replanning(manifest):
    value, _ = manifest
    runtime = Model(value)
    with Journal(value) as journal:
        approval = approve_next(lambda a: recovery.provision(value, runtime, journal, a))
    with Journal(value) as resumed:
        assert recovery.provision(value, runtime, resumed, approval)['uuid'] == 'fixture-uuid'
    assert runtime.calls.count('plan') == 1


@pytest.mark.parametrize('fault', ['unowned', 'changed-resource', 'changed-input'])
def test_foreign_or_changed_authority_never_mutates(manifest, fault):
    value, _ = manifest
    runtime = Model(value)
    with Journal(value) as journal:
        call = lambda approval: recovery.provision(value, runtime, journal, approval)
        if fault == 'unowned':
            runtime.create()
        else:
            approval = approve_next(call)
            if fault == 'changed-input':
                runtime.input_value['tfvars_sha256'] = 'd' * 64
            else:
                call(approval)
                runtime.server_value['uuid'] = 'different'
        before = list(runtime.calls)
        with pytest.raises(RecoveryError):
            call(None)
        assert runtime.calls == before


def test_runtime_real_child_failure_retains_intent_and_private_diagnostics(manifest):
    value, path = manifest
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        with pytest.raises(RecoveryError, match='child-failed'):
            runtime.command('fixture', [sys.executable, '-c', 'import sys; print("private-fixture"); sys.exit(7)'])
        assert journal.state['intent']['name'] == 'fixture'
        assert (journal.directory / 'command-1.stdout').read_text() == 'private-fixture\n'
        assert (journal.directory / 'command-1.stdout').stat().st_mode & 0o777 == 0o600
    assert document(journal.directory / 'journal.json')['intent']['name'] == 'fixture'


def test_runtime_cleans_ambient_execution_overrides(manifest, monkeypatch):
    value, path = manifest
    for key in ('MAKEFLAGS', 'MAKEFILES', 'ANSIBLE_CONFIG', 'ANSIBLE_SKIP_TAGS', 'GIT_CONFIG_GLOBAL', 'SOPS_AGE_KEY'):
        monkeypatch.setenv(key, 'must-not-survive')
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        _, output = runtime.command('environment', [sys.executable, '-c',
            'import os; print(any(v == "must-not-survive" for v in os.environ.values()))'])
        assert output.strip() == b'False'
        assert runtime.environment['SOPS_AGE_KEY_FILE'] == value['age_key_file']


def test_runtime_timeout_is_bounded_and_keeps_intent(manifest):
    value, path = manifest
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        with pytest.raises(RecoveryError, match='interrupted'):
            runtime.command('timeout', [sys.executable, '-c', 'import time; time.sleep(10)'], timeout=0.2)
        assert journal.state['intent']['name'] == 'timeout'


def test_runtime_never_forwards_tailnet_enrollment_key_to_other_children(manifest, monkeypatch):
    value, path = manifest
    monkeypatch.setenv('TAILSCALE_AUTH_KEY', 'synthetic-fixture-enrollment-key')
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        _, output = runtime.command('fixture', [sys.executable, '-c',
            'import os; print("TAILSCALE_AUTH_KEY" in os.environ)'])
        assert output.strip() == b'False'
        _, output = runtime.command('bootstrap-tailnet', [sys.executable, '-c',
            'import os; print("TAILSCALE_AUTH_KEY" in os.environ)'])
        assert output.strip() == b'True'


def test_provider_credentials_reach_only_provider_operations(manifest, monkeypatch):
    value, path = manifest
    monkeypatch.setenv('UPCLOUD_TOKEN', 'synthetic-provider-capability')
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        command = [sys.executable, '-c', 'import os; print("UPCLOUD_TOKEN" in os.environ)']
        for name, expected in (('observe-provider', b'True'), ('apply', b'True'), ('decrypt', b'False'),
                               ('deploy', b'False'), ('bootstrap-tailnet', b'False'), ('migration-publish', b'False')):
            _, output = runtime.command(name, command)
            assert output.strip() == expected


def test_runtime_changed_manifest_refuses_before_child(manifest):
    value, path = manifest
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        path.write_text('{}')
        with pytest.raises(RecoveryError, match='manifest-changed'):
            runtime.command('fixture', [sys.executable, '-c', 'raise AssertionError'])
        assert journal.state['sequence'] == 0


def test_resume_cleans_only_owned_plaintext_and_preserves_failure_evidence(manifest):
    value, path = manifest
    with Journal(value) as journal:
        journal.observe('plaintext_owned', True)
        plaintext = journal.write('runtime-secrets.yaml', b'synthetic-fixture-plaintext')
        temporary = journal.directory / '.vpn-replacement.secrets.random'
        temporary.write_bytes(b'synthetic-fixture-staging')
        temporary.chmod(0o600)
        evidence = journal.write('failure-42.json', b'fixture-receipt')
    with Journal(value) as resumed:
        Runtime(value, path, resumed)
        assert not plaintext.exists() and not temporary.exists()
        assert evidence.read_bytes() == b'fixture-receipt'
        assert resumed.state['observed']['plaintext_owned'] is False


def test_plaintext_cleanup_refuses_link_without_touching_target(manifest):
    value, path = manifest
    with Journal(value) as journal:
        journal.observe('plaintext_owned', True)
        outside = path.parent / 'unrelated'
        outside.write_bytes(b'preserve')
        (journal.directory / 'runtime-secrets.yaml').symlink_to(outside)
        with pytest.raises(RecoveryError, match='plaintext-output-changed'):
            Runtime(value, path, journal)
        assert outside.read_bytes() == b'preserve'


def test_make_fields_bind_target_and_respect_bootstrap_whitelist(manifest, monkeypatch):
    value, path = manifest
    recorded = []
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        monkeypatch.setattr(runtime, 'command', lambda name, argv, **kw: recorded.append((name, argv, kw)))
        runtime.make('bootstrap-tailnet', extra={'ANSIBLE_LIMIT': 'vpn-replacement', 'TAILNET_BOOTSTRAP_CONFIG': '/private/input.json'})
        fields = {arg.split('=', 1)[0] for arg in recorded[-1][1] if '=' in arg}
        assert fields == {'ANSIBLE_LIMIT', 'TAILNET_BOOTSTRAP_CONFIG'}
        runtime.make('deploy', extra={'ANSIBLE_LIMIT': 'vpn-replacement', 'ANSIBLE_TAGS': ''})
        fields = dict(arg.split('=', 1) for arg in recorded[-1][1] if '=' in arg)
        assert fields['ENV'] == value['environment'] and fields['PROVIDER'] == 'upcloud'
        assert fields['SOPS_FILE'] == value['sops_file']
        assert fields['ANSIBLE_SSH_PRIVATE_KEY_FILE'] == value['ssh_key_file']
        assert fields['INSPECT_KNOWN_HOSTS'] == value['known_hosts_file']
        assert recorded[-1][2]['timeout'] == 4200


def concrete_convergence(manifest, monkeypatch, journal):
    from pathlib import Path
    value, path = manifest
    runtime = Runtime(value, path, journal)
    runtime.inventory = path.parent / 'inventory.ini'
    runtime.inventory.write_bytes(b'fixture inventory')
    for name in ('sops_file', 'known_hosts_file', 'promotion_configs_file'):
        item = Path(value[name])
        item.write_bytes(b'fixture ' + name.encode())
        item.chmod(0o600)
    contexts = journal.write('contexts.json', b'{"fixture": "observed"}')
    monkeypatch.setattr(runtime, 'source', lambda: {'revision': 'fixture'})
    monkeypatch.setattr(runtime, 'migration_contract', lambda: {'target': {'alias': 'vpn-replacement'}})
    calls = []
    def make(goal, *, extra=None, allowed=(0,)):
        calls.append(goal)
        if goal == 'decrypt':
            output = Path(extra['SECRETS_FILE'])
            output.write_bytes(b'fixture plaintext')
            output.chmod(0o600)
        if goal in ('dry-run', 'deploy'):
            assert Path(extra['SECRETS_FILE']).read_bytes() == b'fixture plaintext'
            sinks = document(extra['DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE'])
            assert set(sinks) == {'vpn-replacement'} and not Path(sinks['vpn-replacement']).exists()
            # A real command increments the journal sequence before launch.
            with journal.operation(goal, {}):
                if goal == 'deploy':
                    runtime.deploy_result()
        return 0, b'fixture reviewed diff'
    runtime.deploy_result = lambda: None
    monkeypatch.setattr(runtime, 'make', make)
    monkeypatch.setattr(runtime, 'verify_target', lambda **kwargs: (calls.append('verify') or 0, b'fixture verified'))
    return runtime, contexts, calls


def test_converge_approval_resume_plaintext_cleanup_and_lost_ack(manifest, monkeypatch):
    value, _ = manifest
    with Journal(value) as journal:
        runtime, contexts, calls = concrete_convergence(manifest, monkeypatch, journal)
        call = lambda approval: runtime.converge(contexts, journal, approval)
        approval = approve_next(call)
        assert not (journal.directory / 'runtime-secrets.yaml').exists()
        def lose_ack():
            raise RecoveryError('lost-deploy-ack')
        runtime.deploy_result = lose_ack
        with pytest.raises(RecoveryError, match='lost-deploy-ack'):
            call(approval)
        assert not (journal.directory / 'runtime-secrets.yaml').exists()
        runtime.deploy_result = lambda: pytest.fail('must reconcile successful remote deployment')
        call(None)
        assert calls.count('deploy') == 1
        assert calls.count('dry-run') == 1
        assert calls[-1] == 'verify'


def test_expired_dry_run_requires_new_review(manifest, monkeypatch):
    value, _ = manifest
    with Journal(value) as journal:
        runtime, contexts, calls = concrete_convergence(manifest, monkeypatch, journal)
        previous = approve_next(lambda a: runtime.converge(contexts, journal, a))
        journal.state['observed']['dry_run']['observed_at'] -= 901
        current = approve_next(lambda _: runtime.converge(contexts, journal, previous))
        assert previous != current
        assert calls.count('dry-run') == 2 and 'deploy' not in calls


def test_ciphertext_change_during_decrypt_never_reaches_review_or_deploy(manifest, monkeypatch):
    from pathlib import Path
    value, _ = manifest
    with Journal(value) as journal:
        runtime, contexts, calls = concrete_convergence(manifest, monkeypatch, journal)
        make = runtime.make
        def changed(goal, **kwargs):
            result = make(goal, **kwargs)
            if goal == 'decrypt':
                Path(value['sops_file']).write_bytes(b'changed ciphertext')
            return result
        monkeypatch.setattr(runtime, 'make', changed)
        with pytest.raises(RecoveryError, match='decrypt-input-changed'):
            runtime.converge(contexts, journal, None)
        assert calls == ['decrypt']
        assert not (journal.directory / 'runtime-secrets.yaml').exists()


def test_plan_change_while_terraform_runs_never_becomes_reviewable(manifest, monkeypatch):
    from recovery_io import canonical
    value, path = manifest
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        runtime.tfroot = path.parent
        saved = path.parent / (value['environment'] + '.tfplan')
        saved.write_bytes(b'synthetic binary plan')
        original = {'source': 'original'}
        monkeypatch.setattr(runtime, 'inputs', lambda: dict(original))
        monkeypatch.setattr(runtime, 'make', lambda _: original.update(source='changed'))
        monkeypatch.setattr(runtime, 'terraform', lambda *args, **kwargs: (0, canonical({})))
        monkeypatch.setattr('recovery_runtime.review_plan', lambda *args, **kwargs: {'changes': []})
        monkeypatch.setattr(runtime, 'command', lambda *args, **kwargs: (0, b''))
        with pytest.raises(RecoveryError, match='plan-input-changed'):
            runtime.plan(None)


def test_apply_consumes_same_private_reviewed_bytes_after_retained_file_replaced(manifest, monkeypatch):
    import hashlib
    from pathlib import Path

    from recovery_io import canonical
    value, path = manifest
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        original = journal.write('approved.tfplan', b'reviewed plan bytes')
        retained = {'plan_sha256': hashlib.sha256(original.read_bytes()).hexdigest(), 'inputs': {'source': 'fixed'}}
        monkeypatch.setattr(runtime, 'inputs', lambda: {'source': 'fixed'})
        monkeypatch.setattr(runtime, 'state', lambda: None)
        monkeypatch.setattr('recovery_runtime.review_plan', lambda *args, **kwargs: {})
        calls = []
        def terraform(*args, **kwargs):
            frozen = Path(args[-1])
            assert frozen != original and frozen.read_bytes() == b'reviewed plan bytes'
            assert frozen.stat().st_mode & 0o777 == 0o600
            calls.append((args[0], frozen))
            return 0, canonical({})
        def policy(*args, **kwargs):
            original.write_bytes(b'unreviewed replacement')
            return 0, b''
        monkeypatch.setattr(runtime, 'terraform', terraform)
        monkeypatch.setattr(runtime, 'command', policy)
        runtime.apply(retained)
        assert [call[0] for call in calls] == ['show', 'apply']
        assert calls[0][1] == calls[1][1] and not calls[0][1].exists()


def test_authenticated_pin_uses_real_ssh_keygen_and_hashed_known_hosts(manifest, monkeypatch):
    import hashlib
    import subprocess
    from pathlib import Path

    from recovery_io import canonical
    value, path = manifest
    private = Path(value['ssh_key_file'])
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(private)], check=True, timeout=10)
    public = private.with_suffix('.pub').read_text().split()
    import base64
    key_sha = hashlib.sha256(base64.b64decode(public[1])).hexdigest()
    pins = Path(value['known_hosts_file'])
    pins.write_text('[192.0.2.10]:2222 ' + ' '.join(public[:2]) + '\n')
    pins.chmod(0o600)
    subprocess.run(['ssh-keygen', '-q', '-H', '-f', str(pins)], check=True, timeout=10, capture_output=True)
    config = {'provider': 'upcloud', 'environment': value['environment'], 'inventory_alias': 'vpn-replacement',
              'public_address': '192.0.2.10', 'ssh_port': 2222, 'source_revision': value['source_revision'],
              'deployable_digest': 'a' * 64, 'known_hosts': str(pins), 'host_key_sha256': key_sha}
    configuration = Path(value['bootstrap_config'])
    configuration.write_bytes(canonical(config))
    configuration.chmod(0o600)
    host = {'name': 'vpn-replacement', 'alias': '192.0.2.10', 'address': '192.0.2.10', 'port': 2222}
    with Journal(value) as journal:
        runtime = Runtime(value, path, journal)
        monkeypatch.setattr(runtime, 'source', lambda: {'DEPLOYABLE_SOURCE_DIGEST': 'a' * 64})
        result = runtime.pin_binding({'public_ipv4': ['192.0.2.10']}, host)
        assert result['known_hosts_sha256'] == hashlib.sha256(pins.read_bytes()).hexdigest()
        assert (journal.directory / 'reviewed-known-hosts').read_bytes() == pins.read_bytes()
        config['host_key_sha256'] = 'b' * 64
        configuration.write_bytes(canonical(config))
        with pytest.raises(RecoveryError, match='authenticated-host-pin-required'):
            runtime.pin_binding({'public_ipv4': ['192.0.2.10']}, host)


def test_empty_or_changed_pins_never_reach_remote_management(manifest, monkeypatch):
    value, _ = manifest
    runtime = Model(value)
    with Journal(value) as journal:
        call = lambda approval: recovery.recover(value, runtime, journal, approval)
        apply = approve_next(call)
        approve_next(lambda _: call(apply))
        monkeypatch.setattr(runtime, 'pin_binding', lambda *_: (_ for _ in ()).throw(RecoveryError('bad-pin')))
        with pytest.raises(RecoveryError, match='bad-pin'):
            call(None)
        assert 'management' not in runtime.calls


def test_status_cli_reads_only_retained_state_and_reports_no_live_validation(manifest):
    import json
    import subprocess

    from recovery_io import ROOT
    value, path = manifest
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/recovery.py'), 'status', '--manifest', str(path)],
                            check=False, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {'status': 'retained-state-only', 'sequence': 0,
        'interrupted_operation': None, 'last_acceptance': None, 'live_revalidated': False}
    assert value['account'] not in result.stdout


def test_cli_refusal_is_categorical_without_private_values(manifest):
    import subprocess

    from recovery_io import ROOT, canonical
    value, path = manifest
    value['provider'] = 'unsupported-private-value'
    path.write_bytes(canonical(value))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/recovery.py'), 'run', '--manifest', str(path)],
                            check=False, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert 'unsupported-or-invalid-recovery-manifest' in result.stdout
    assert value['provider'] not in result.stdout + result.stderr
    assert value['account'] not in result.stdout + result.stderr


@pytest.mark.parametrize('extra', [['--path-b'], ['--env', 'prod'], ['--dry-run'], ['--provider', 'vultr']])
def test_restore_manifest_cannot_mix_alternate_target_or_restic(manifest, extra):
    import subprocess

    from recovery_io import ROOT
    _, path = manifest
    result = subprocess.run(['sh', str(ROOT / 'scripts/restore.sh'), '--manifest', str(path), *extra],
                            check=False, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert 'exact UpCloud Path A only' in result.stderr
