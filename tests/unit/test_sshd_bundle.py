"""Real filesystem publication with injected systemd; not host or reboot proof."""
from __future__ import annotations

import hashlib
import copy
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles/baseline/files'
TEMPLATES = ROOT / 'ansible/roles/baseline/templates'
UNITS = ('vpn-sshd-boot-recover.service', 'vpn-sshd-recover.service', 'vpn-sshd-recover.timer')


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location('sshd_bundle', FILES / 'sshd_bundle.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Runtime:
    def __init__(self):
        self.calls = []
        self.state = 'idle'
        self.fail_activate = False

    def ready(self, generation):
        return not self.fail_activate

    def status(self, generation):
        self.calls.append(('status', generation))
        return {'status': self.state}

    def activate(self, generation):
        self.calls.append(('activate', generation))
        if self.fail_activate:
            raise RuntimeError('injected daemon-reload failure')


@pytest.fixture
def setup(module, tmp_path):
    root, state, units = (tmp_path / name for name in ('bundle', 'state', 'units'))
    root.mkdir(mode=0o755)
    (root / 'staging').mkdir(mode=0o700)
    (root / 'generations').mkdir(mode=0o755)
    (root / 'sshd_bundle.py').write_bytes((FILES / 'sshd_bundle.py').read_bytes())
    (root / 'sshd_bundle.py').chmod(0o644)
    units.mkdir(mode=0o755)
    runtime = Runtime()
    return module.Bundle(root, state, units, runtime), runtime


def stage(bundle, revision='one', *, transaction_source=None):
    contents = {name: (FILES / name).read_bytes() for name in
                ('sshd_migrate.py', 'sshd_transaction.py', 'sshd_ownership.py')}
    if transaction_source is not None:
        contents['sshd_transaction.py'] = transaction_source
    contents['sshd_migrate.py'] += f'\n# fixture revision {revision}\n'.encode()
    contents.update({'units/' + name: (TEMPLATES / name).read_bytes() for name in UNITS})
    manifest = {'schema_version': 1, 'files': {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    generation = hashlib.sha256(encoded).hexdigest()
    directory = bundle.root / 'staging' / generation
    directory.mkdir(mode=0o755)
    (directory / 'units').mkdir(mode=0o755)
    for name, data in {**contents, 'manifest.json': encoded}.items():
        (directory / name).write_bytes(data)
        (directory / name).chmod(0o644)
    return generation


def test_first_install_publishes_complete_generation_and_persistent_links(module, setup):
    bundle, runtime = setup
    generation = stage(bundle)
    assert bundle.publish(generation) == {'status': 'installed', 'generation': generation}
    assert os.readlink(bundle.root / 'current') == 'generations/' + generation
    assert not (bundle.root / 'install.json').exists()
    assert bundle.state.stat().st_mode & 0o777 == 0o700
    for name in UNITS:
        assert os.readlink(bundle.units / name) == str(bundle.root / 'current/units' / name)
    with bundle.selected('prepare') as selected:
        assert selected == bundle.root / 'generations' / generation
    assert ('activate', selected) in runtime.calls
    assert runtime.calls[-1] == ('status', selected)


def test_retry_installed_generation_is_idempotent_and_old_generation_retained(module, setup):
    bundle, runtime = setup
    first = stage(bundle)
    bundle.publish(first)
    second = stage(bundle, 'two')
    runtime.state = 'committed'
    bundle.publish(second)
    assert bundle.publish(second) == {'status': 'unchanged', 'generation': second}
    assert (bundle.root / 'generations' / first).is_dir()
    assert (bundle.root / 'generations' / second).is_dir()


def test_pending_transaction_prevents_publication_without_pointer_or_journal(module, setup):
    bundle, runtime = setup
    first = stage(bundle)
    bundle.publish(first)
    second = stage(bundle, 'two')
    runtime.state = 'applied'
    with pytest.raises(module.BundleError, match='transaction-pending'):
        bundle.publish(second)
    assert os.readlink(bundle.root / 'current') == 'generations/' + first
    assert not (bundle.root / 'install.json').exists()


@pytest.mark.parametrize('phase', ['journal', 'switch', 'links', 'activate'])
def test_interrupted_publication_blocks_mutations_and_same_generation_retry_finishes(module, setup, monkeypatch, phase):
    bundle, runtime = setup
    first = stage(bundle)
    bundle.publish(first)
    second = stage(bundle, 'two')
    owner, method = (runtime, 'activate') if phase == 'activate' else (bundle, '_' + phase)
    original = getattr(owner, method)
    def crash(*args):
        original(*args)
        raise SystemExit('injected publication death')
    monkeypatch.setattr(owner, method, crash)
    with pytest.raises(SystemExit):
        bundle.publish(second)
    assert (bundle.root / 'install.json').exists()
    for action in ('prepare', 'apply', 'confirm', 'rollback'):
        with pytest.raises(module.BundleError, match='installation-incomplete'):
            with bundle.selected(action):
                pytest.fail('mutation must not dispatch')
    with bundle.selected('recover') as selected:
        assert selected.name in {first, second}
    monkeypatch.setattr(owner, method, original)
    assert bundle.publish(second)['status'] == 'installed'
    assert not (bundle.root / 'install.json').exists()


@pytest.mark.parametrize('failure_index', range(7))
def test_activation_failure_is_journaled_and_retryable(module, setup, monkeypatch, failure_index):
    bundle, runtime = setup
    generation = stage(bundle)
    actual = module.Runtime()
    commands = []
    def command(args):
        commands.append(args)
        if len(commands) == failure_index + 1:
            raise module.BundleError('activation-failed')
    monkeypatch.setattr(actual, 'command', command)
    monkeypatch.setattr(runtime, 'activate', actual.activate)
    with pytest.raises(module.BundleError, match='activation-failed'):
        bundle.publish(generation)
    assert len(commands) == failure_index + 1
    assert bundle._pending()['generation'] == generation
    monkeypatch.setattr(actual, 'command', lambda args: commands.append(args))
    assert bundle.publish(generation)['status'] == 'installed'
    assert len(commands) == failure_index + 8
    assert not (bundle.root / 'install.json').exists()


def test_activation_workers_can_take_shared_bundle_and_transaction_locks(module, setup, monkeypatch):
    bundle, runtime = setup
    generation = stage(bundle)
    other = stage(bundle, 'other')
    entered = []
    def activate(directory):
        assert (bundle.root / 'install.json').exists()
        for action in ('boot-recover', 'recover', 'status'):
            with bundle.selected(action) as selected:
                assert selected == directory
                with module._lock(bundle.state / 'transaction.lock', True):
                    entered.append(action)
        for action in ('prepare', 'apply', 'confirm'):
            with pytest.raises(module.BundleError, match='installation-incomplete'):
                with bundle.selected(action):
                    pytest.fail('journal must block mutations during unlocked activation')
        for concurrent in (generation, other):
            with pytest.raises(module.BundleError, match='busy'):
                bundle.publish(concurrent)
    monkeypatch.setattr(runtime, 'activate', activate)
    assert bundle.publish(generation)['status'] == 'installed'
    assert entered == ['boot-recover', 'recover', 'status']


@pytest.mark.parametrize('fault', ['state', 'candidate', 'journal', 'current'])
def test_final_validation_refuses_changed_state_or_generation_and_keeps_journal(module, setup, monkeypatch, fault):
    bundle, runtime = setup
    first = stage(bundle)
    bundle.publish(first)
    second = stage(bundle, 'two')
    original = runtime.activate
    before = None
    def activate(directory):
        nonlocal before
        original(directory)
        if fault == 'state':
            runtime.state = 'applied'
        elif fault == 'candidate':
            path = directory / 'sshd_transaction.py'
            before = path.read_bytes()
            path.write_bytes(before + b'\n# changed after validation\n')
        elif fault == 'journal':
            value = bundle._pending()
            before = dict(value)
            value['previous'] = second
            bundle._journal(value)
        else:
            bundle._switch(first)
    monkeypatch.setattr(runtime, 'activate', activate)
    with pytest.raises(module.BundleError):
        bundle.publish(second)
    assert (bundle.root / 'install.json').exists()
    monkeypatch.setattr(runtime, 'activate', original)
    runtime.state = 'idle'
    if fault == 'candidate':
        (bundle.root / 'generations' / second / 'sshd_transaction.py').write_bytes(before)
    elif fault == 'journal':
        bundle._journal(before)
    assert bundle.publish(second)['status'] == 'installed'


def test_activation_quiesces_periodic_worker_before_ordered_timer_start(module, monkeypatch, tmp_path):
    commands = []
    runtime = module.Runtime()
    monkeypatch.setattr(runtime, 'command', lambda args: commands.append(args))
    runtime.activate(tmp_path)
    assert commands == [
        ['/usr/bin/systemctl', 'daemon-reload'],
        ['/usr/bin/systemctl', 'stop', 'vpn-sshd-recover.timer'],
        ['/usr/bin/systemctl', 'stop', 'vpn-sshd-recover.service'],
        ['/usr/bin/systemctl', 'enable', 'vpn-sshd-boot-recover.service'],
        ['/usr/bin/systemctl', 'enable', '--now', 'vpn-sshd-recover.timer'],
        ['/usr/bin/systemctl', 'start', 'vpn-sshd-recover.service'],
        ['/usr/bin/python3', '-I', '-B', str(tmp_path / 'sshd_migrate.py'), 'check-installation'],
    ]


def test_shared_selection_prevents_publisher_and_pins_immutable_path(module, setup):
    bundle, _ = setup
    first = stage(bundle)
    bundle.publish(first)
    second = stage(bundle, 'two')
    with bundle.selected('status') as selected:
        with pytest.raises(module.BundleError, match='busy'):
            bundle.publish(second)
        assert selected == bundle.root / 'generations' / first


@pytest.mark.parametrize('fault', ['bytes', 'symlink', 'extra', 'mode', 'manifest'])
def test_invalid_stage_never_changes_current_or_systemd(module, setup, fault):
    bundle, runtime = setup
    generation = stage(bundle)
    directory = bundle.root / 'staging' / generation
    path = directory / 'sshd_transaction.py'
    if fault == 'bytes':
        path.write_bytes(b'# corrupted\n')
    elif fault == 'symlink':
        path.unlink()
        path.symlink_to(directory / 'sshd_migrate.py')
    elif fault == 'extra':
        (directory / 'unapproved.py').write_text('pass')
    elif fault == 'mode':
        path.chmod(0o666)
    else:
        (directory / 'manifest.json').write_text('{}')
    with pytest.raises(module.BundleError):
        bundle.publish(generation)
    assert not (bundle.root / 'current').exists()
    assert not any(kind == 'activate' for kind, _ in runtime.calls)
    assert list(bundle.units.iterdir()) == []


def test_foreign_unit_and_current_symlinks_are_not_overwritten(module, setup):
    bundle, _ = setup
    generation = stage(bundle)
    foreign = bundle.units / UNITS[-1]
    foreign.symlink_to('/unapproved/unit')
    with pytest.raises(module.BundleError):
        bundle.publish(generation)
    assert os.readlink(foreign) == '/unapproved/unit'
    foreign.unlink()
    (bundle.root / 'current').symlink_to('/unapproved/generation')
    with pytest.raises(module.BundleError):
        bundle.publish(generation)
    assert os.readlink(bundle.root / 'current') == '/unapproved/generation'


def test_missing_state_or_corrupt_journal_never_dispatches_idle(module, setup):
    bundle, _ = setup
    generation = stage(bundle)
    bundle.publish(generation)
    (bundle.state / 'transaction.lock').unlink()
    bundle.state.rmdir()
    with pytest.raises(module.BundleError, match='state-missing'):
        with bundle.selected('recover'):
            pytest.fail('missing state is not idle')
    bundle.state.mkdir(mode=0o700)
    (bundle.root / 'install.json').write_text('{}')
    (bundle.root / 'install.json').chmod(0o600)
    with pytest.raises(module.BundleError, match='journal-invalid'):
        with bundle.selected('status'):
            pytest.fail('corrupt journal is not idle')


def test_shared_bundle_lock_survives_actual_exec(module, setup):
    bundle, _ = setup
    first = stage(bundle)
    bundle.publish(first)
    second = stage(bundle, 'two')
    code = '''import importlib.util,os,sys
spec=importlib.util.spec_from_file_location('bundle',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
bundle=module.Bundle(*sys.argv[2:5],None)
with bundle.selected('status'):
    os.execv(sys.executable,[sys.executable,'-c',"import sys;print('ready',flush=True);sys.stdin.read(1)"])
'''
    child = subprocess.Popen([sys.executable, '-c', code, str(FILES / 'sshd_bundle.py'),
                              str(bundle.root), str(bundle.state), str(bundle.units)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert select.select([child.stdout], [], [], 5)[0]
        assert child.stdout.readline() == b'ready\n'
        with pytest.raises(module.BundleError, match='busy'):
            bundle.publish(second)
        child.communicate(b'\n', timeout=5)
        assert child.returncode == 0
        assert bundle.publish(second)['status'] == 'installed'
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


@pytest.mark.parametrize('boundary', ['generation', 'pointer', 'journal-deletion'])
def test_directory_fsync_failure_never_reports_success_and_retry_completes(module, setup, monkeypatch, boundary):
    bundle, _ = setup
    generation = stage(bundle)
    original = module._sync
    failed = False
    def sync(path):
        nonlocal failed
        matches = (boundary == 'generation' and path == bundle.root / 'generations'
                   or boundary == 'pointer' and path == bundle.root and (bundle.root / 'current').exists()
                   or boundary == 'journal-deletion' and path == bundle.root
                   and (bundle.root / 'current').exists() and not (bundle.root / 'install.json').exists())
        if matches and not failed:
            failed = True
            raise OSError('injected fsync failure')
        return original(path)
    monkeypatch.setattr(module, '_sync', sync)
    with pytest.raises((module.BundleError, OSError)):
        bundle.publish(generation)
    assert failed
    if boundary != 'generation':
        assert (bundle.root / 'install.json').exists()
        with pytest.raises(module.BundleError, match='installation-incomplete'):
            with bundle.selected('prepare'):
                pytest.fail('failed activation cannot admit new migration')
    monkeypatch.setattr(module, '_sync', original)
    assert bundle.publish(generation)['status'] == 'installed'


def test_corrupt_journal_candidate_never_dispatches_old_idle_engine(module, setup):
    bundle, runtime = setup
    first = stage(bundle)
    bundle.publish(first)
    second = stage(bundle, 'two')
    runtime.fail_activate = True
    with pytest.raises(module.BundleError):
        bundle.publish(second)
    (bundle.root / 'generations' / second / 'sshd_transaction.py').unlink()
    with pytest.raises(module.BundleError, match='journal-invalid'):
        with bundle.selected('recover'):
            pytest.fail('unverifiable installation is not idle')


def test_actual_generation_state_parser_refuses_corruption_without_activation(module, setup, monkeypatch):
    bundle, _ = setup
    monkeypatch.setattr(module, 'STATE', bundle.state)
    runtime = module.Runtime()
    calls = []
    monkeypatch.setattr(runtime, 'command', lambda args: calls.append(args))
    bundle.runtime = runtime
    first = stage(bundle)
    assert bundle.publish(first)['status'] == 'installed'
    assert len(calls) == 7
    second = stage(bundle, 'two')
    (bundle.state / 'transaction.json').write_text('{}')
    (bundle.state / 'transaction.json').chmod(0o600)
    with pytest.raises(module.BundleError, match='state-unreadable'):
        bundle.publish(second)
    assert len(calls) == 7
    assert os.readlink(bundle.root / 'current') == 'generations/' + first


# Exercise real, distinct state parsers without requiring Git history in a
# shallow checkout. This immutable fixture is the exact ownership-only engine
# from 5f78b5e0bcddcb49099de3647b04fb11cea9a1ff, not a compatibility runtime.
from test_sshd_transaction import engine, fixture, baseline_fixture, Runtime as TransactionRuntime, prepare_baseline


def ownership_engine_source():
    source = (ROOT / 'tests/fixtures/sshd-ownership-engine-v1.py.txt').read_bytes()
    assert hashlib.sha256(source).hexdigest() == 'de81ff15006992bc7fe5eba96826925ba70d75d6bc435c8533ce34e0808b6d84'
    return source


def ownership_v1_plan(module, current):
    plan = copy.deepcopy(current)
    plan['schema_version'] = 1
    plan['files'].pop('sshd_config')
    plan['snapshot_digest'] = module._digest({key: value for key, value in plan.items()
                                               if key != 'snapshot_digest'})
    return plan


def actual_parser_runtime(module, bundle, monkeypatch):
    monkeypatch.setattr(module, 'STATE', bundle.state)
    runtime = module.Runtime()
    commands = []
    monkeypatch.setattr(runtime, 'command', lambda args: commands.append(args))
    bundle.runtime = runtime
    return runtime, commands


@pytest.mark.parametrize('terminal', ['committed', 'rolled_back'])
def test_baseline_engine_upgrade_reads_exact_terminal_ownership_state(module, setup, fixture, monkeypatch, terminal):
    bundle, _ = setup
    runtime, _ = actual_parser_runtime(module, bundle, monkeypatch)
    first = stage(bundle, 'ownership-only', transaction_source=ownership_engine_source())
    bundle.publish(first)
    old_path = bundle.root / 'generations' / first / 'sshd_transaction.py'
    spec = importlib.util.spec_from_file_location('old_ownership_engine', old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)

    class OldRuntime(TransactionRuntime):
        def build_plan(self, config, contexts):
            return self.plan

        def assert_effective(self, plan, config):
            self.calls.append('effective')

    tx = old.Transaction(fixture[0], bundle.state, OldRuntime(ownership_v1_plan(old, fixture[2])))
    receipt = tx.prepare(contexts=[], timeout=120)
    tx.apply(receipt['generation'], receipt['nonce'])
    if terminal == 'committed':
        expected = tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    else:
        expected = tx.rollback(receipt['generation'], receipt['nonce'])
    before = (bundle.state / 'transaction.json').read_bytes()
    assert runtime.status(old_path.parent) == expected
    second = stage(bundle, 'baseline-capable')
    assert bundle.publish(second)['status'] == 'installed'
    assert runtime.status(bundle.root / 'generations' / second) == expected
    assert (bundle.state / 'transaction.json').read_bytes() == before
    assert os.readlink(bundle.root / 'current') == 'generations/' + second


def test_terminal_v1_upgrade_interruption_keeps_receipt_and_same_generation_retry_finishes(
        module, setup, fixture, monkeypatch):
    bundle, _ = setup
    runtime, _ = actual_parser_runtime(module, bundle, monkeypatch)
    first = stage(bundle, 'ownership-only', transaction_source=ownership_engine_source())
    bundle.publish(first)
    old_path = bundle.root / 'generations' / first / 'sshd_transaction.py'
    spec = importlib.util.spec_from_file_location('interrupted_old_ownership_engine', old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)

    class OldRuntime(TransactionRuntime):
        def build_plan(self, config, contexts):
            return self.plan

        def assert_effective(self, plan, config):
            self.calls.append('effective')

    tx = old.Transaction(fixture[0], bundle.state, OldRuntime(ownership_v1_plan(old, fixture[2])))
    receipt = tx.prepare(contexts=[], timeout=120)
    tx.apply(receipt['generation'], receipt['nonce'])
    tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    before = (bundle.state / 'transaction.json').read_bytes()
    second = stage(bundle, 'schema-two')
    activate = runtime.activate

    def interrupted(directory):
        activate(directory)
        raise SystemExit('injected parser upgrade interruption')

    monkeypatch.setattr(runtime, 'activate', interrupted)
    with pytest.raises(SystemExit):
        bundle.publish(second)
    assert (bundle.state / 'transaction.json').read_bytes() == before
    assert (bundle.root / 'install.json').exists()
    monkeypatch.setattr(runtime, 'activate', activate)
    assert bundle.publish(second)['status'] == 'installed'
    assert (bundle.state / 'transaction.json').read_bytes() == before
    assert not (bundle.root / 'install.json').exists()


@pytest.mark.parametrize('terminal', ['committed', 'rolled_back'])
def test_ownership_only_downgrade_refuses_terminal_baseline_before_pointer_or_journal(module, setup, engine, baseline_fixture, monkeypatch, terminal):
    bundle, _ = setup
    runtime, commands = actual_parser_runtime(module, bundle, monkeypatch)
    first = stage(bundle, 'baseline-capable')
    bundle.publish(first)
    case, transaction_runtime, _ = baseline_fixture()
    tx = engine.Transaction(case[0], bundle.state, transaction_runtime)
    receipt = prepare_baseline(tx)
    tx.apply(receipt['generation'], receipt['nonce'])
    if terminal == 'committed':
        tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    else:
        tx.rollback(receipt['generation'], receipt['nonce'])
    assert runtime.status(bundle.root / 'generations' / first)['status'] == terminal
    before = (bundle.state / 'transaction.json').read_bytes()
    activated = len(commands)
    second = stage(bundle, 'ownership-only', transaction_source=ownership_engine_source())
    with pytest.raises(module.BundleError, match='state-unreadable'):
        bundle.publish(second)
    assert len(commands) == activated
    assert (bundle.state / 'transaction.json').read_bytes() == before
    assert os.readlink(bundle.root / 'current') == 'generations/' + first
    assert not (bundle.root / 'install.json').exists()
    assert (bundle.root / 'staging' / second).is_dir()


@pytest.mark.parametrize('terminal', ['committed', 'rolled_back'])
def test_v1_engine_downgrade_refuses_terminal_v2_ownership_before_publication(
        module, setup, engine, fixture, monkeypatch, terminal):
    bundle, _ = setup
    runtime, commands = actual_parser_runtime(module, bundle, monkeypatch)
    first = stage(bundle, 'schema-two')
    bundle.publish(first)
    tx = engine.Transaction(fixture[0], bundle.state, TransactionRuntime(fixture[2]))
    receipt = tx.prepare(intent='sshd-ownership', contexts=[], timeout=120)
    tx.apply(receipt['generation'], receipt['nonce'])
    if terminal == 'committed':
        tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    else:
        tx.rollback(receipt['generation'], receipt['nonce'])
    before = (bundle.state / 'transaction.json').read_bytes()
    activated = len(commands)
    second = stage(bundle, 'ownership-v1', transaction_source=ownership_engine_source())

    with pytest.raises(module.BundleError, match='state-unreadable'):
        bundle.publish(second)
    assert len(commands) == activated
    assert (bundle.state / 'transaction.json').read_bytes() == before
    assert os.readlink(bundle.root / 'current') == 'generations/' + first
    assert not (bundle.root / 'install.json').exists()


def test_activation_output_is_bounded_with_real_local_child(module):
    module.Runtime().command([sys.executable, '-c', 'pass'])
    with pytest.raises(module.BundleError, match='activation-output-limit'):
        module.Runtime().command([sys.executable, '-c', "import os;os.write(1,b'x'*1000000)"])


@pytest.mark.parametrize('action,reason,expected', [
    ('recover', 'busy', 75), ('boot-recover', 'busy', 1),
    ('status', 'busy', 1), ('recover', 'journal-invalid', 1),
])
def test_only_periodic_dispatcher_busy_is_a_categorical_deferral(module, monkeypatch, capsys, action, reason, expected):
    @contextmanager
    def selected(self, selected_action):
        assert selected_action == action
        raise module.BundleError(reason)
        yield
    monkeypatch.setattr(module.Bundle, 'selected', selected)
    monkeypatch.setattr(module.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(sys, 'argv', ['sshd_bundle.py', action])
    assert module.main() == expected
    assert json.loads(capsys.readouterr().out) == (
        {'status': 'deferred', 'reason': 'busy'} if expected == 75
        else {'status': 'error', 'reason': 'ssh-bundle-failed'})


def test_dispatcher_refuses_an_unexpected_exec_return(module, tmp_path, monkeypatch, capsys):
    @contextmanager
    def selected(self, action):
        assert action == 'status'
        yield tmp_path
    monkeypatch.setattr(module.Bundle, 'selected', selected)
    monkeypatch.setattr(module.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(module.os, 'execve', lambda *args: None)
    monkeypatch.setattr(sys, 'argv', ['sshd_bundle.py', 'status'])
    assert module.main() == 1
    assert json.loads(capsys.readouterr().out) == {'status': 'error', 'reason': 'ssh-bundle-failed'}


def test_installer_bootstrap_hash_guard_accepts_unchanged_and_refuses_drift(module, setup, monkeypatch):
    import io
    import yaml
    bundle, _ = setup
    generation = stage(bundle)
    manifest = (bundle.root / 'staging' / generation / 'manifest.json').read_bytes()
    path = ROOT / 'ansible/playbooks/install-sshd-recovery.yml'
    command = yaml.safe_load(path.read_text())[0]['pre_tasks'][1]['ansible.builtin.command']
    source = command['argv'][3]
    # Run the exact preflight on an owned filesystem fixture. Only the fixed
    # roots and root uid are translated to this test user's private directory.
    source = source.replace("'/usr/local/lib/vpn-sshd'", repr(str(bundle.root)))
    source = source.replace("'/var/lib/vpn-sshd-transaction'", repr(str(bundle.state)))
    source = source.replace('info.st_uid==0', 'info.st_uid in {0,' + str(os.geteuid()) + '}')
    # /tmp is a root-owned sticky ancestor on local fixture hosts, not production.
    source = source.replace('and not info.st_mode&0o022',
                            'and (not info.st_mode&0o022 or bool(info.st_mode&stat.S_ISVTX))')
    digest = hashlib.sha256((bundle.root / 'sshd_bundle.py').read_bytes()).hexdigest()
    monkeypatch.setattr(sys, 'argv', ['preflight', generation, digest])
    monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(manifest)))
    exec(compile(source, 'fixture-installation-preflight', 'exec'), {})
    original = (bundle.root / 'sshd_bundle.py').read_bytes()
    (bundle.root / 'sshd_bundle.py').write_bytes(original + b'\n# drift\n')
    monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(manifest)))
    with pytest.raises(AssertionError):
        exec(compile(source, 'fixture-installation-preflight', 'exec'), {})
    assert (bundle.root / 'sshd_bundle.py').read_bytes() == original + b'\n# drift\n'
