"""Filesystem/crash tests; injected runtime is not real SSH or reboot proof."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / 'ansible/roles/baseline/files/sshd_transaction.py'
NAMES = ('10-cloud-init-hardening.conf', '20-ansible-hardening.conf', '50-cloud-init.conf')


@pytest.fixture
def engine():
    spec = importlib.util.spec_from_file_location('sshd_transaction', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    (config / 'sshd_config').write_text('Include /etc/ssh/sshd_config.d/*.conf\n')
    files = {}
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
    plan = dict(schema_version=1, operation='sshd-ownership', changed=True, read_set=reads,
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

    def build_plan(self, config, contexts):
        return self.plan

    def assert_snapshot(self, plan, config):
        self.calls.append('snapshot')

    def assert_effective(self, plan, config):
        self.calls.append('effective')
        if self.fail_effective:
            raise RuntimeError('fixture effective failure')

    def recovery_ready(self):
        return self.ready

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
    receipt = tx.prepare(contexts=[], timeout=120)
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
    tx.apply(receipt['generation'], receipt['nonce'])
    assert_contents(fixture, 'after')
    result = tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest'])
    assert result['status'] == 'committed'
    assert tx.confirm(receipt['generation'], receipt['nonce'], receipt['snapshot_digest']) == result
    runtime.now += 1000
    assert tx.recover()['status'] == 'committed'
    assert_contents(fixture, 'after')
    assert runtime.calls.count('reload') == 1


@pytest.mark.parametrize('boundary', [1, 2, 3])
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
    assert_contents(fixture, 'before')


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
    receipt = tx.prepare(contexts=[], timeout=120)
    tx.apply(receipt['generation'], receipt['nonce'])
    runtime.now += 30
    runtime.uptime += 121
    assert tx.recover()['status'] == 'rolled_back'
    assert_contents(fixture, 'before')


def test_verification_crossing_deadline_cannot_commit(engine, fixture):
    tx, runtime, receipt = transaction(engine, fixture)
    tx.apply(receipt['generation'], receipt['nonce'])
    def slow_check(plan, config):
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


@pytest.mark.parametrize('crash_after_restore', [1, 2, 3])
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
