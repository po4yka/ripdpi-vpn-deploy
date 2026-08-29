"""Filesystem/crash tests; injected runtime is not real SSH or reboot proof."""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / 'ansible/roles/baseline/files/sshd_transaction.py'
LIMITS = Path(__file__).resolve().parents[2] / 'scripts/sshd_transaction_limits.py'
NAMES = ('10-cloud-init-hardening.conf', '20-ansible-hardening.conf', '50-cloud-init.conf')


@pytest.fixture
def engine():
    spec = importlib.util.spec_from_file_location('sshd_transaction', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_remote_engine_timeout_matches_the_controller_budget(engine):
    spec = importlib.util.spec_from_file_location('sshd_transaction_limits', LIMITS)
    limits = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(limits)
    assert engine.MAX_TRANSACTION_TIMEOUT == limits.TRANSACTION_TIMEOUT_SECONDS == 960


def record(path, data=None):
    info = path.stat()
    data = path.read_bytes() if data is None else data
    return dict(exists=True, data_b64=base64.b64encode(data).decode(),
                sha256=hashlib.sha256(data).hexdigest(), mode=info.st_mode & 0o777,
                uid=info.st_uid, gid=info.st_gid)


@pytest.fixture
def fixture(tmp_path):
    config = tmp_path / 'ssh'
    (config / 'sshd_config.d').mkdir(parents=True)
    main = config / 'sshd_config'
    main_before = (b'Include /etc/ssh/sshd_config.d/*.conf\n'
                   b'KbdInteractiveAuthentication no\n'
                   b'X11Forwarding yes\n'
                   b'Subsystem sftp /usr/lib/openssh/sftp-server\n')
    main_after = (b'Include /etc/ssh/sshd_config.d/*.conf\n'
                  b'# normalized-shadowed KbdInteractiveAuthentication no\n'
                  b'# normalized-shadowed X11Forwarding yes\n'
                  b'Subsystem sftp /usr/lib/openssh/sftp-server\n')
    main.write_bytes(main_before)
    files = {'sshd_config': dict(before=record(main), after=record(main, main_after))}
    for i, name in enumerate(NAMES):
        path = config / 'sshd_config.d' / name
        path.write_bytes(f'# original {i}\n'.encode())
        path.chmod(0o640)
        files[f'sshd_config.d/{name}'] = dict(before=record(path), after=record(path, f'# migrated {i}\n'.encode()))
    reads = []
    for path in sorted(config.rglob('*')):
        if path.is_file():
            info = path.stat()
            reads.append(dict(relative_path=str(path.relative_to(config)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                              size=info.st_size, mode=info.st_mode & 0o777, uid=info.st_uid, gid=info.st_gid,
                              dev=info.st_dev, ino=info.st_ino))
    plan = dict(schema_version=2, operation='sshd-ownership', changed=True, read_set=reads,
                include_inventory=[dict(relative_directory='sshd_config.d', matched_names=list(NAMES))],
                files=files, effective=[dict(context=None, before_sha256='a'*64, after_sha256='a'*64),
                dict(context=dict(user='deploy',host='controller',addr='192.0.2.1',laddr='192.0.2.2',lport=2222), before_sha256='a'*64, after_sha256='a'*64)])
    plan['snapshot_digest'] = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return config, tmp_path / 'private-state', plan


class Runtime:
    def __init__(self, plan):
        self.plan = plan
        self.now = 1000
        self.boot = '00000000-0000-4000-8000-000000000001'
        self.calls = []
        self.ready = True
        self.fail_effective = False
        self.fail_reload = False

    def build_plan(self, config, contexts, *, intent, hardening):
        assert intent == 'sshd-ownership' and hardening is None
        return self.plan

    def assert_snapshot(self, plan, config):
        self.calls.append('snapshot')

    def assert_effective(self, plan, config, *, phase):
        assert phase in {'before', 'after'}
        self.calls.append('effective')
        if self.fail_effective:
            raise RuntimeError('fixture effective failure')

    def activation_recovery(self):
        return object() if self.ready else None

    def activation_fence(self, proof, acquired):
        return proof is not None and self.ready

    def activation_clock(self):
        return self.now * 1000000

    def reload(self):
        self.calls.append('reload')
        if self.fail_reload:
            raise RuntimeError('fixture reload failure')

    def clock(self):
        return self.now

    def monotonic(self):
        return self.now

    def boot_id(self):
        return self.boot


def transaction(engine, fixture):
    config, state, plan = fixture
    runtime = Runtime(plan)
    tx = engine.Transaction(config, state, runtime)
    receipt = tx.prepare(intent='sshd-ownership', contexts=[], timeout=120)
    return tx, runtime, receipt


def assert_contents(fixture, which):
    config, _, plan = fixture
    for name, pair in plan['files'].items():
        assert (config / name).read_bytes() == base64.b64decode(pair[which]['data_b64'])
        assert (config / name).stat().st_mode & 0o777 == pair[which]['mode']


def test_prepare_does_not_mutate_and_unarmed_apply_refuses(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    assert_contents(fixture, 'before')
    runtime.ready = False
    with pytest.raises(engine.TransactionError, match='recovery-not-ready'):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert_contents(fixture, 'before')
    assert 'reload' not in runtime.calls


def test_success_commit_and_idempotent_confirmation(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    prepared = json.loads((fixture[1] / 'transaction.json').read_text())
    assert prepared['schema_version'] == prepared['plan']['schema_version'] == 2
    tx.apply(receipt['generation'], receipt['nonce'])
    assert_contents(fixture, 'after')
    result = tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    assert result['status'] == 'committed'
    assert tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest']) == result
    runtime.now += 1000
    assert tx.recover()['status'] == 'committed'
    assert_contents(fixture, 'after')
    assert runtime.calls.count('reload') == 1


def install_historical_v1(engine, fixture, status):
    """Write the exact canonical shape emitted by the frozen ownership engine."""
    _, state_root, current = fixture
    plan = copy.deepcopy(current)
    plan['schema_version'] = 1
    plan['files'].pop('sshd_config')
    plan['snapshot_digest'] = engine._digest({key: value for key, value in plan.items()
                                              if key != 'snapshot_digest'})
    state = dict(schema_version=1,
                 generation='10000000-0000-4000-8000-000000000001',
                 nonce='1' * 64, created=1000, deadline=1120,
                 monotonic_created=1000, monotonic_deadline=1120,
                 boot_id='00000000-0000-4000-8000-000000000001',
                 status=status, plan=plan)
    state['checksum'] = engine._digest(state)
    state_root.mkdir(mode=0o700)
    (state_root / 'initialized').write_bytes(b'1\n')
    (state_root / 'initialized').chmod(0o600)
    encoded = engine._json(state)
    (state_root / 'transaction.json').write_bytes(encoded)
    (state_root / 'transaction.json').chmod(0o600)
    return state, encoded


@pytest.mark.parametrize('terminal', ['committed', 'rolled_back'])
def test_terminal_historical_v1_status_and_recovery_are_read_only(engine, fixture, terminal):
    historical, before = install_historical_v1(engine, fixture, terminal)
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))
    expected = tx._receipt(historical)

    assert tx.status() == expected
    assert tx.recover() == expected
    assert (fixture[1] / 'transaction.json').read_bytes() == before


@pytest.mark.parametrize('status', ['prepared', 'applying', 'applied', 'rolling_back',
                                    'recovery_failed'])
def test_nonterminal_historical_v1_is_never_loaded_for_recovery(engine, fixture, status):
    install_historical_v1(engine, fixture, status)
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))
    with pytest.raises(engine.TransactionError, match='historical-state-pending'):
        tx.recover()


def test_unknown_historical_v1_status_is_invalid(engine, fixture):
    install_historical_v1(engine, fixture, 'unknown')
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))
    with pytest.raises(engine.TransactionError, match='state-invalid'):
        tx.status()


@pytest.mark.parametrize('action', ['apply', 'confirm', 'rollback'])
def test_terminal_historical_v1_cannot_execute_transaction_actions(engine, fixture, action):
    historical, before = install_historical_v1(engine, fixture, 'rolled_back')
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))
    arguments = [historical['generation'], historical['nonce']]
    if action == 'confirm':
        arguments.append(historical['plan']['snapshot_digest'])
    with pytest.raises(engine.TransactionError, match='historical-state-terminal'):
        getattr(tx, action)(*arguments)
    assert (fixture[1] / 'transaction.json').read_bytes() == before


@pytest.mark.parametrize('fault', ['baseline-operation', 'four-files', 'noncanonical'])
def test_historical_decoder_accepts_only_exact_original_v1_shape(engine, fixture, fault):
    state, _ = install_historical_v1(engine, fixture, 'committed')
    if fault == 'baseline-operation':
        state['plan']['operation'] = 'sshd-baseline'
    elif fault == 'four-files':
        state['plan']['files']['sshd_config'] = copy.deepcopy(fixture[2]['files']['sshd_config'])
    state['plan']['snapshot_digest'] = engine._digest({key: value for key, value in state['plan'].items()
                                                       if key != 'snapshot_digest'})
    state['checksum'] = engine._digest({key: value for key, value in state.items() if key != 'checksum'})
    path = fixture[1] / 'transaction.json'
    encoded = engine._json(state)
    path.write_bytes(encoded + (b'\n' if fault == 'noncanonical' else b''))
    with pytest.raises(engine.TransactionError, match='state-invalid'):
        engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2])).status()


@pytest.mark.parametrize('terminal', ['committed', 'rolled_back'])
def test_prepare_archives_exact_terminal_v1_before_writing_new_v2(engine, fixture, terminal):
    historical, before = install_historical_v1(engine, fixture, terminal)
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))
    receipt = tx.prepare(intent='sshd-ownership', contexts=[], timeout=120)

    assert (fixture[1] / (historical['generation'] + '.json')).read_bytes() == before
    current = json.loads((fixture[1] / 'transaction.json').read_text())
    assert current['schema_version'] == current['plan']['schema_version'] == 2
    assert receipt['status'] == 'prepared'


def test_prepare_never_overwrites_a_conflicting_historical_archive(engine, fixture):
    historical, before = install_historical_v1(engine, fixture, 'committed')
    archive = fixture[1] / (historical['generation'] + '.json')
    archive.write_bytes(b'foreign archive')
    archive.chmod(0o600)
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))

    with pytest.raises(engine.TransactionError, match='state-invalid'):
        tx.prepare(intent='sshd-ownership', contexts=[], timeout=120)
    assert archive.read_bytes() == b'foreign archive'
    assert (fixture[1] / 'transaction.json').read_bytes() == before


@pytest.mark.parametrize('boundary', [1, 2, 3, 4])
def test_process_death_after_each_replace_recovers_all_original_bytes(engine, fixture, monkeypatch, boundary):
    tx, runtime, receipt = transaction(engine, fixture)
    original = tx._publish
    writes = 0

    def crash(name, value):
        nonlocal writes
        original(name, value)
        writes += 1
        if writes == boundary:
            raise SystemExit('simulated process death')

    monkeypatch.setattr(tx, '_publish', crash)
    with pytest.raises(SystemExit):
        tx.apply(receipt['generation'], receipt['nonce'])
    config, state, _ = fixture
    restarted = engine.Transaction(config, state, runtime)
    runtime.now += 121
    assert restarted.recover()['status'] == 'rolled_back'
    assert_contents(fixture, 'before')
    assert restarted.recover()['status'] == 'rolled_back'


def test_reboot_recovers_before_deadline_without_reload_of_not_started_ssh(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    runtime.boot = '00000000-0000-4000-8000-000000000002'
    assert tx.recover(boot=True)['status'] == 'rolled_back'
    assert_contents(fixture, 'before')
    assert runtime.calls.count('reload') == 1


def test_stale_nonce_and_expired_confirmation_never_commit(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    with pytest.raises(engine.TransactionError, match='identity'):
        tx.confirm(receipt['generation'], '0'*64, receipt['snapshot_digest'])
    runtime.now += 121
    with pytest.raises(engine.TransactionError, match='expired'):
        tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    assert tx.recover()['status'] == 'rolled_back'


@pytest.mark.parametrize('foreign', ['owned', 'main', 'new_fragment', 'metadata'])
def test_foreign_state_is_retained_without_partial_rollback(engine, fixture, foreign):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    config, state, _ = fixture
    if foreign == 'owned':
        (config / 'sshd_config.d' / NAMES[-1]).write_bytes(b'# foreign')
    elif foreign == 'main':
        (config / 'sshd_config').write_bytes(b'# foreign main')
    elif foreign == 'new_fragment':
        (config / 'sshd_config.d' / '99-foreign.conf').write_bytes(b'# foreign')
    else:
        (config / 'sshd_config.d' / NAMES[-1]).chmod(0o600)
    before = {p: p.read_bytes() for p in config.rglob('*') if p.is_file()}
    runtime.now += 121
    with pytest.raises(engine.TransactionError, match='drift'):
        tx.recover()
    assert {p: p.read_bytes() for p in before} == before
    assert (state / 'transaction.json').exists()


def test_corrupted_backup_fails_before_first_restore(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    _, state, _ = fixture
    record_path = state / 'transaction.json'
    record_data = json.loads(record_path.read_text())
    record_data['plan']['files'][f'sshd_config.d/{NAMES[-1]}']['before']['data_b64'] = 'broken'
    record_path.write_text(json.dumps(record_data))
    runtime.now += 121
    with pytest.raises(engine.TransactionError, match='state-invalid'):
        tx.recover()
    assert_contents(fixture, 'after')


def test_postcheck_failure_restores_every_file(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    runtime.fail_effective = True
    with pytest.raises(engine.TransactionError):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert_contents(fixture, 'before')
    # Failed validation of the restored configuration is an explicit failure.
    assert tx.status()['status'] == 'recovery_failed'


def test_reload_failure_retains_failed_recovery_and_evidence(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    runtime.fail_reload = True
    with pytest.raises(engine.TransactionError):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert_contents(fixture, 'before')
    assert tx.status()['status'] == 'recovery_failed'


def test_read_graph_race_prevents_first_write_even_if_runtime_validator_lies(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    (fixture[0] / 'sshd_config').write_bytes(b'# changed')
    with pytest.raises(engine.TransactionError, match='drift'):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert (fixture[0] / 'sshd_config').read_bytes() == b'# changed'
    for name, pair in fixture[2]['files'].items():
        if name != 'sshd_config':
            assert (fixture[0] / name).read_bytes() == base64.b64decode(pair['before']['data_b64'])


def test_private_state_and_symlink_lock_rejection(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    state = fixture[1]
    assert state.stat().st_mode & 0o777 == 0o700
    assert (state / 'transaction.json').stat().st_mode & 0o777 == 0o600
    (state / 'transaction.lock').unlink()
    (state / 'transaction.lock').symlink_to(state / 'transaction.json')
    with pytest.raises(engine.TransactionError):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert_contents(fixture, 'before')


def test_monotonic_expiry_cannot_be_extended_by_wall_clock_adjustment(engine, fixture):
    config, state, plan = fixture
    runtime = Runtime(plan)
    runtime.uptime = 500
    runtime.monotonic = lambda: runtime.uptime
    tx = engine.Transaction(config, state, runtime)
    receipt = tx.prepare(intent='sshd-ownership', contexts=[], timeout=120)
    tx.apply(receipt['generation'], receipt['nonce'])
    runtime.now += 30
    runtime.uptime += 121
    assert tx.recover()['status'] == 'rolled_back'
    assert_contents(fixture, 'before')


def test_verification_crossing_deadline_cannot_commit(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    def slow_check(plan, config, *, phase):
        assert phase in {'before', 'after'}
        runtime.now += 121
    runtime.assert_effective = slow_check
    with pytest.raises(engine.TransactionError, match='expired'):
        tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    assert tx.status()['status'] == 'applied'
    assert tx.recover()['status'] == 'rolled_back'


def test_missing_state_after_prepare_is_not_idle(engine, fixture):
    tx, _, _ = transaction(engine, fixture)
    (fixture[1] / 'transaction.json').unlink()
    with pytest.raises(engine.TransactionError, match='state-missing'):
        tx.recover(boot=True)


@pytest.mark.parametrize('crash_after_restore', [1, 2, 3, 4])
def test_interrupted_rollback_finishes_validation_and_reload(engine, fixture, monkeypatch, crash_after_restore):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    original = tx._publish
    count = 0
    def crash(name, value):
        nonlocal count
        original(name, value)
        count += 1
        if count == crash_after_restore:
            raise SystemExit('restore crash')
    monkeypatch.setattr(tx, '_publish', crash)
    runtime.now += 121
    with pytest.raises(SystemExit):
        tx.recover()
    restarted = engine.Transaction(fixture[0], fixture[1], runtime)
    assert restarted.recover()['status'] == 'rolled_back'
    assert_contents(fixture, 'before')
    assert runtime.calls.count('reload') == 2


def test_absent_50_stays_absent_through_activation_and_rollback(engine, fixture):
    config, state, plan = fixture
    name = f'sshd_config.d/{NAMES[-1]}'
    (config / name).unlink()
    absent = dict(exists=False, data_b64=None, sha256=None, mode=None, uid=None, gid=None)
    plan['files'][name] = dict(before=absent.copy(), after=absent.copy())
    plan['read_set'] = [item for item in plan['read_set'] if item['relative_path'] != name]
    plan['include_inventory'][0]['matched_names'].remove(NAMES[-1])
    plan['snapshot_digest'] = engine._digest({k:v for k,v in plan.items() if k != 'snapshot_digest'})
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    runtime.now += 121
    assert tx.recover()['status'] == 'rolled_back'
    assert not (config / name).exists()


def test_busy_operation_does_not_start_concurrent_recovery(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    with tx._locked():
        with pytest.raises(engine.TransactionError, match='busy'):
            tx.recover()
    assert_contents(fixture, 'before')


def test_read_ignores_access_time_changes(engine, fixture, monkeypatch):
    from types import SimpleNamespace
    real_fstat = engine.os.fstat
    calls = 0
    def accessed(fd):
        nonlocal calls
        calls += 1
        info = real_fstat(fd)
        values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
        values['st_atime'] += calls
        values['st_atime_ns'] += calls * 1000000000
        return SimpleNamespace(**values)
    monkeypatch.setattr(engine.os, 'fstat', accessed)
    data, _ = engine._read(fixture[0] / 'sshd_config')
    assert data.startswith(b'Include ')


def test_missing_whole_state_directory_after_apply_is_not_recreated_as_idle(engine, fixture):
    tx, _, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    fixture[1].rename(fixture[1].with_name('lost-private-state'))
    with pytest.raises(engine.TransactionError, match='state-missing'):
        tx.recover(boot=True)
    assert not fixture[1].exists()
    assert_contents(fixture, 'after')


def test_invalid_effective_context_with_consistent_checksums_never_writes(engine, fixture, monkeypatch):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    path = fixture[1] / 'transaction.json'
    state = json.loads(path.read_text())
    state['plan']['effective'].append(dict(context={'user':'malformed'}, before_sha256='a'*64, after_sha256='a'*64))
    state['plan']['snapshot_digest'] = engine._digest({k:v for k,v in state['plan'].items() if k != 'snapshot_digest'})
    state['checksum'] = engine._digest({k:v for k,v in state.items() if k != 'checksum'})
    path.write_text(json.dumps(state))
    runtime.now += 121
    with pytest.raises(engine.TransactionError, match='state-invalid'):
        tx.recover()
    assert_contents(fixture, 'after')


def test_apply_obtains_fresh_recovery_outside_lock_and_fences_after_relocking(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    runtime.ready = False  # Previous periodic execution deferred with busy.
    proof = object()
    events = []
    def fresh():
        # A real second flock succeeds only after apply releases its first lock.
        assert tx.status()['status'] == 'prepared'
        events.append('fresh-zero')
        return proof
    def fence(observed, acquired):
        assert observed is proof and acquired == 1000000000
        with pytest.raises(engine.TransactionError, match='busy'):
            tx.status()
        events.append('locked-fence')
        return True
    runtime.activation_recovery = fresh
    runtime.activation_clock = lambda: 1000000000
    runtime.activation_fence = fence
    assert tx.apply(receipt['generation'], receipt['nonce'])['status'] == 'applied'
    assert events == ['fresh-zero', 'locked-fence']
    assert_contents(fixture, 'after')


@pytest.mark.parametrize('fault', ['expiry', 'boot', 'rollback', 'replacement', 'missing-state',
                                  'same-identity-state-change', 'main-drift', 'metadata-drift', 'capability'])
def test_apply_rechecks_every_boundary_after_unlocked_fresh_execution(engine, fixture, monkeypatch, fault):
    tx, runtime, receipt = transaction(engine, fixture)
    observed = {}
    config, state_root, _ = fixture
    def snapshot():
        return {str(path.relative_to(config)):(path.read_bytes(), path.stat().st_mode & 0o777)
                for path in config.rglob('*') if path.is_file()}
    def fresh():
        assert tx.status()['status'] == 'prepared'
        if fault == 'expiry':
            runtime.now += 121
            assert tx.recover()['status'] == 'rolled_back'
        elif fault == 'boot':
            runtime.boot = '00000000-0000-4000-8000-000000000002'
        elif fault in {'rollback', 'replacement'}:
            tx.rollback(receipt['generation'], receipt['nonce'])
            if fault == 'replacement':
                assert tx.prepare(intent='sshd-ownership', contexts=[], timeout=120)['generation'] != receipt['generation']
        elif fault == 'missing-state':
            (state_root / 'transaction.json').unlink()
        elif fault == 'same-identity-state-change':
            value = json.loads((state_root / 'transaction.json').read_text())
            value['deadline'] += 1;value['monotonic_deadline'] += 1
            value['checksum'] = engine._digest({key:item for key,item in value.items() if key != 'checksum'})
            (state_root / 'transaction.json').write_text(json.dumps(value))
        elif fault == 'main-drift':
            (config / 'sshd_config').write_bytes(b'# foreign edit during unlocked phase\n')
        elif fault == 'metadata-drift':
            (config / 'sshd_config.d' / NAMES[0]).chmod(0o600)
        else:
            runtime.ready = False
        observed.update(snapshot())
        return object()
    runtime.activation_recovery = fresh
    def forbidden(*args):
        pytest.fail('invalid activation wrote SSH configuration')
    monkeypatch.setattr(tx, '_publish', forbidden)
    with pytest.raises(engine.TransactionError):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert observed and snapshot() == observed


def test_expiry_during_final_fence_refuses_before_first_write(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    def slow_fence(proof, acquired):
        runtime.now += 121
        return True
    runtime.activation_fence = slow_fence
    with pytest.raises(engine.TransactionError, match='expired'):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert_contents(fixture, 'before')
    assert tx.status()['status'] == 'prepared'


BASELINE_HARDENING = b'X11Forwarding no\nAllowTcpForwarding no\nSubsystem sftp internal-sftp\n'


def baseline_disk(config):
    """Capture fixture bytes and metadata without dereferencing foreign links."""
    import os
    result = {}
    for path in sorted(config.rglob('*')):
        if path.is_symlink() or path.is_file():
            info = path.lstat()
            value = ('symlink', os.readlink(path)) if path.is_symlink() else ('file', path.read_bytes())
            result[str(path.relative_to(config))] = (value, info.st_mode & 0o777, info.st_uid, info.st_gid)
    return result


def assert_baseline_phase(case, phase):
    config, _, plan, original = case
    expected = original.copy()
    for name, pair in plan['files'].items():
        value = pair[phase]
        if value['exists']:
            expected[name] = (('file', base64.b64decode(value['data_b64'])), value['mode'], value['uid'], value['gid'])
        else:
            expected.pop(name, None)
    assert baseline_disk(config) == expected


class BaselineRuntime(Runtime):
    """Filesystem transaction seam; effective policy is not an OpenSSH proof."""
    def __init__(self, case):
        super().__init__(case[2])
        self.case = case

    def build_plan(self, config, contexts, *, intent, hardening):
        assert config == self.case[0] and contexts == []
        assert intent == 'sshd-baseline' and hardening == BASELINE_HARDENING
        return self.plan

    def assert_effective(self, plan, config, *, phase):
        assert phase in {'before', 'after'}
        assert plan == self.plan and config == self.case[0]
        assert_baseline_phase(self.case, phase)
        self.calls.append(('effective', phase))


@pytest.fixture
def baseline_fixture(engine, fixture, monkeypatch):
    import os
    # Only the private fixture maps root-group creation to its actual owner.
    monkeypatch.setattr(engine, 'BASELINE_FILE_GID', os.getegid(), raising=False)

    def create(missing_20=False, absent_50=False):
        config, state, plan = fixture
        main = config / 'sshd_config'
        main.write_bytes(b'Include /etc/ssh/sshd_config.d/*.conf\nSubsystem sftp /usr/lib/openssh/sftp-server\n')
        (config / 'sshd_config.d' / NAMES[0]).write_bytes(
            b'Port 2222\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\n')
        (config / 'sshd_config.d' / NAMES[2]).write_bytes(b'# normalized cloud-init fixture\n')
        if absent_50:
            (config / 'sshd_config.d' / NAMES[2]).unlink()
        managed = config / 'sshd_config.d' / NAMES[1]
        managed.write_bytes(b'X11Forwarding no\nAllowTcpForwarding yes\n')
        if missing_20:
            managed.unlink()
            before = dict(exists=False, data_b64=None, sha256=None, mode=None, uid=None, gid=None)
            after = dict(exists=True, data_b64=base64.b64encode(BASELINE_HARDENING).decode(),
                         sha256=hashlib.sha256(BASELINE_HARDENING).hexdigest(), mode=0o644,
                         uid=os.geteuid(), gid=os.getegid())
        else:
            before, after = record(managed), record(managed, BASELINE_HARDENING)
        plan['operation'] = 'sshd-baseline'
        plan['files'] = {
            'sshd_config': dict(before=record(main), after=record(main,
                b'Include /etc/ssh/sshd_config.d/*.conf\n# Subsystem sftp /usr/lib/openssh/sftp-server\n')),
            'sshd_config.d/' + NAMES[1]: dict(before=before, after=after),
        }
        plan['read_set'] = []
        for path in sorted(config.rglob('*')):
            if path.is_file():
                info = path.stat()
                plan['read_set'].append(dict(relative_path=str(path.relative_to(config)),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=info.st_size,
                    mode=info.st_mode & 0o777, uid=info.st_uid, gid=info.st_gid, dev=info.st_dev, ino=info.st_ino))
        plan['include_inventory'][0]['matched_names'] = [name for name in NAMES
            if (name != NAMES[1] or not missing_20) and (name != NAMES[2] or not absent_50)]
        for value in plan['effective']:
            value['after_sha256'] = 'b' * 64
        plan['snapshot_digest'] = engine._digest({k: v for k, v in plan.items() if k != 'snapshot_digest'})
        case = config, state, plan, baseline_disk(config)
        runtime = BaselineRuntime(case)
        return case, runtime, engine.Transaction(config, state, runtime)

    return create


def prepare_baseline(tx):
    return tx.prepare(intent='sshd-baseline', contexts=[], hardening=BASELINE_HARDENING, timeout=120)


def test_baseline_preview_requires_preinstalled_state_root_and_creates_nothing(engine, baseline_fixture):
    case, _runtime, tx = baseline_fixture()
    with pytest.raises(engine.TransactionError, match='state-missing'):
        tx.preview(intent='sshd-baseline', contexts=[], hardening=BASELINE_HARDENING)
    assert not case[1].exists()


def test_baseline_preview_opens_existing_lock_without_durable_state(engine, baseline_fixture):
    case, runtime, tx = baseline_fixture()
    state = case[1]
    state.mkdir(mode=0o700)
    lock = state / 'transaction.lock'
    lock.touch(mode=0o600)
    before = {path.name: (path.read_bytes(), path.stat().st_mode & 0o777)
              for path in state.iterdir()}
    result = tx.preview(intent='sshd-baseline', contexts=[], hardening=BASELINE_HARDENING)
    assert result == {'status': 'would-change', 'snapshot_digest': case[2]['snapshot_digest']}
    assert {path.name: (path.read_bytes(), path.stat().st_mode & 0o777)
            for path in state.iterdir()} == before
    assert runtime.calls == ['snapshot']


def test_baseline_preview_refuses_a_nonterminal_transaction_without_mutation(engine, baseline_fixture):
    case, _runtime, tx = baseline_fixture()
    prepare_baseline(tx)
    before = {path.name: path.read_bytes() for path in case[1].iterdir() if path.is_file()}
    with pytest.raises(engine.TransactionError, match='transaction-pending'):
        tx.preview(intent='sshd-baseline', contexts=[], hardening=BASELINE_HARDENING)
    assert {path.name: path.read_bytes() for path in case[1].iterdir() if path.is_file()} == before


@pytest.mark.parametrize('missing_20', [False, True])
def test_baseline_commits_changed_policy_without_changing_bootstrap_owners(engine, baseline_fixture, missing_20):
    case, runtime, tx = baseline_fixture(missing_20)
    receipt = prepare_baseline(tx)
    prepared = json.loads((case[1] / 'transaction.json').read_text())
    assert prepared['schema_version'] == prepared['plan']['schema_version'] == 2
    assert_baseline_phase(case, 'before')
    assert tx.apply(receipt['generation'], receipt['nonce'])['status'] == 'applied'
    assert_baseline_phase(case, 'after')
    result = tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    assert result['status'] == 'committed'
    assert tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest']) == result
    runtime.now += 121
    assert tx.recover()['status'] == 'committed'
    assert_baseline_phase(case, 'after')
    assert [call for call in runtime.calls if isinstance(call, tuple)] == [('effective', 'after'), ('effective', 'after')]


@pytest.mark.parametrize('missing_20', [False, True])
@pytest.mark.parametrize('boot', [False, True])
def test_baseline_timeout_or_reboot_restores_before_policy_and_exact_membership(engine, baseline_fixture, missing_20, boot):
    case, runtime, tx = baseline_fixture(missing_20)
    receipt = prepare_baseline(tx)
    tx.apply(receipt['generation'], receipt['nonce'])
    if boot:
        runtime.boot = '00000000-0000-4000-8000-000000000002'
    else:
        runtime.now += 121
    restarted = engine.Transaction(case[0], case[1], runtime)
    assert restarted.recover(boot=boot)['status'] == 'rolled_back'
    assert_baseline_phase(case, 'before')
    assert runtime.calls[-1 if boot else -2] == ('effective', 'before')
    assert runtime.calls.count('reload') == (1 if boot else 2)
    assert restarted.recover(boot=boot)['status'] == 'rolled_back'


@pytest.mark.parametrize('missing_20', [False, True])
@pytest.mark.parametrize('boundary', [1, 2])
def test_baseline_process_death_after_each_main_or_managed_write_recovers(engine, baseline_fixture, monkeypatch, missing_20, boundary):
    case, runtime, tx = baseline_fixture(missing_20)
    receipt = prepare_baseline(tx)
    publish = tx._publish
    writes = 0

    def crash(name, value):
        nonlocal writes
        publish(name, value)
        writes += 1
        if writes == boundary:
            raise SystemExit('baseline fixture process death')

    monkeypatch.setattr(tx, '_publish', crash)
    with pytest.raises(SystemExit):
        tx.apply(receipt['generation'], receipt['nonce'])
    runtime.now += 121
    restarted = engine.Transaction(case[0], case[1], runtime)
    assert restarted.recover()['status'] == 'rolled_back'
    assert_baseline_phase(case, 'before')
    assert ('effective', 'before') in runtime.calls


@pytest.mark.parametrize('foreign', ['created-bytes', 'created-mode', 'created-symlink', 'readonly-bootstrap'])
def test_baseline_foreign_created_file_or_readonly_owner_prevents_partial_rollback(engine, baseline_fixture, foreign):
    case, runtime, tx = baseline_fixture(missing_20=True)
    receipt = prepare_baseline(tx)
    tx.apply(receipt['generation'], receipt['nonce'])
    config = case[0]
    managed = config / 'sshd_config.d' / NAMES[1]
    if foreign == 'created-bytes':
        managed.write_bytes(b'# foreign replacement must survive\n')
    elif foreign == 'created-mode':
        managed.chmod(0o600)
    elif foreign == 'created-symlink':
        managed.unlink()
        managed.symlink_to(config / 'sshd_config')
    else:
        (config / 'sshd_config.d' / NAMES[0]).write_bytes(b'# foreign bootstrap owner\n')
    observed = baseline_disk(config)
    runtime.now += 121
    with pytest.raises(engine.TransactionError):
        tx.recover()
    assert baseline_disk(config) == observed
    assert tx.status()['status'] == 'recovery_failed'


@pytest.mark.parametrize('intent,hardening', [('unknown', None), ('sshd-ownership', BASELINE_HARDENING)])
def test_prepare_refuses_unknown_intent_or_hardening_for_ownership(engine, fixture, intent, hardening):
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))
    with pytest.raises(engine.TransactionError):
        tx.prepare(intent=intent, contexts=[], hardening=hardening)
    assert not fixture[1].exists()
    assert_contents(fixture, 'before')


def test_prepare_requires_explicit_intent(engine, fixture):
    tx = engine.Transaction(fixture[0], fixture[1], Runtime(fixture[2]))
    with pytest.raises(TypeError):
        tx.prepare(contexts=[])
    assert not fixture[1].exists()


def test_baseline_minimum_main_and_bootstrap_graph_creates_then_removes_managed_file(engine, baseline_fixture):
    case, runtime, tx = baseline_fixture(missing_20=True, absent_50=True)
    receipt = prepare_baseline(tx)
    assert tx.apply(receipt['generation'], receipt['nonce'])['status'] == 'applied'
    assert_baseline_phase(case, 'after')
    runtime.now += 121
    assert tx.recover()['status'] == 'rolled_back'
    assert_baseline_phase(case, 'before')


@pytest.mark.parametrize('fault', ['wrong-owned-path', 'after-digest', 'created-mode', 'created-uid', 'created-gid'])
def test_baseline_rehashed_invalid_plan_is_rejected_before_any_config_write(engine, baseline_fixture, monkeypatch, fault):
    import os
    case, _, tx = baseline_fixture(missing_20=True)
    receipt = prepare_baseline(tx)
    state_path = case[1] / 'transaction.json'
    state = json.loads(state_path.read_text())
    plan = state['plan']
    if fault == 'wrong-owned-path':
        plan['files'].pop('sshd_config')
        name = 'sshd_config.d/' + NAMES[0]
        path = case[0] / name
        plan['files'][name] = dict(before=record(path), after=record(path, b'# forbidden bootstrap write\n'))
    elif fault == 'after-digest':
        plan['effective'][0]['after_sha256'] = 'not-a-digest'
    else:
        field, value = {'created-mode': ('mode', 0o600), 'created-uid': ('uid', os.geteuid() + 1),
                        'created-gid': ('gid', os.getegid() + 1)}[fault]
        plan['files']['sshd_config.d/' + NAMES[1]]['after'][field] = value
    plan['snapshot_digest'] = engine._digest({key: value for key, value in plan.items() if key != 'snapshot_digest'})
    state['checksum'] = engine._digest({key: value for key, value in state.items() if key != 'checksum'})
    state_path.write_text(json.dumps(state))
    observed = baseline_disk(case[0])

    def forbidden(*args):
        pytest.fail('invalid baseline plan reached config publication')

    monkeypatch.setattr(tx, '_publish', forbidden)
    with pytest.raises(engine.TransactionError, match='state-invalid'):
        tx.apply(receipt['generation'], receipt['nonce'])
    assert baseline_disk(case[0]) == observed
