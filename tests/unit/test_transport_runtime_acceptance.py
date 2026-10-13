"""Consumer transaction preserves live authority through refusal and interruption."""
import base64
import importlib.util
import os
from pathlib import Path
import json
import signal
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'ansible/roles/runtime-release/files/transport_runtime_transaction.py'
spec = importlib.util.spec_from_file_location('transport_runtime_transaction', SOURCE)
transaction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transaction)


@pytest.fixture
def tmp_path(private_authority_path):
    return private_authority_path


class Adapter:
    def __init__(self):
        self.running = False
        self.reject = False
        self.events = []

    def retained(self, receipt):
        pass

    def validate_units(self, value):
        if not isinstance(value, dict) or set(value) != {'running'} or type(value['running']) is not bool:
            raise transaction.Refusal('unit-state-invalid')

    def validate(self):
        self.events.append('validate')
        if self.reject == 'validate':
            raise RuntimeError('synthetic-private-input')

    def inspect(self):
        return {'running': self.running}

    def stop(self):
        self.events.append('stop')
        self.running = False

    def start(self):
        self.events.append('start')
        self.running = True

    def ensure(self):
        if not self.running:
            self.start()
            return True
        return False

    def restore(self, units):
        self.events.append('restore')
        self.running = units['running'] if units is not None else False
        self.reject = False

    def ready(self):
        self.events.append('ready')
        if not self.running or self.reject:
            raise RuntimeError('synthetic-private-input')


@pytest.fixture
def area(tmp_path):
    # /private/var on macOS has symlink aliases; the publisher requires canonical paths.
    tmp_path = tmp_path.resolve()
    live = tmp_path / 'live'
    live.mkdir()
    live.chmod(0o755)
    state = tmp_path / 'state'
    adapter = Adapter()
    def candidates(version):
        return [{'path': str(live / 'config'), 'data': base64.b64encode(version.encode()).decode(),
                 'mode': 0o600, 'gid': os.getgid()},
                {'path': str(live / 'current'), 'target': str(live / version)}]
    return state, live, adapter, candidates


def apply(area, version, **kwargs):
    state, _, adapter, candidates = area
    with transaction.Transaction(state, uid=os.getuid(), check=kwargs.get("check", False)) as tx:
        return tx.apply(candidates(version), adapter, **kwargs)


def test_world_writable_parent_refuses_before_state_creation(tmp_path):
    parent = tmp_path / 'unsafe'
    parent.mkdir()
    parent.chmod(0o777)
    state = parent / 'state'
    with pytest.raises(transaction.Refusal, match='unsafe-parent'):
        with transaction.Transaction(state, uid=os.getuid()):
            pytest.fail('unsafe ancestry was admitted')
    assert not state.exists()


def test_complete_candidate_precedes_selection_and_retry_preserves_previous(area):
    state, live, adapter, _ = area
    apply(area, 'A')
    apply(area, 'B')
    before = (state / 'accepted.json').read_bytes()
    info = (live / 'config').stat()
    result = apply(area, 'B')
    assert not result['changed']
    assert (state / 'accepted.json').read_bytes() == before
    assert (live / 'config').stat().st_ino == info.st_ino
    assert adapter.events.index('validate') < adapter.events.index('stop')
    assert (live / 'config').read_text() == 'B'


@pytest.mark.parametrize('failure', ['validate', 'ready'])
def test_candidate_failure_preserves_exact_accepted_nodes(area, failure):
    state, live, adapter, _ = area
    apply(area, 'A')
    inode = (live / 'config').stat().st_ino
    link_inode = (live / 'current').lstat().st_ino
    receipt = (state / 'accepted.json').read_bytes()
    adapter.reject = failure
    with pytest.raises((RuntimeError, transaction.Refusal)):
        apply(area, 'B')
    assert (live / 'config').read_text() == 'A'
    assert (live / 'config').stat().st_ino == inode
    assert (live / 'current').lstat().st_ino == link_inode
    assert (state / 'accepted.json').read_bytes() == receipt
    assert adapter.running


@pytest.mark.parametrize('stage', ['intent', 'stopped', 'published-0', 'published-1', 'adopted', 'ready', 'committed'])
def test_process_death_reconciles_before_unchanged_retry(area, stage):
    state, live, adapter, _ = area
    apply(area, 'A')
    def checkpoint(value):
        if value == stage:
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        apply(area, 'B', checkpoint=checkpoint)
    result = apply(area, 'B')
    assert result['status'] == 'accepted'
    assert adapter.running
    assert (live / 'config').read_text() == 'B'
    assert not (state / 'pending.json').exists()
    assert not apply(area, 'B')['changed']


def test_foreign_inode_after_interruption_is_retained(area):
    state, live, adapter, _ = area
    apply(area, 'A')
    def checkpoint(value):
        if value == 'published-0':
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        apply(area, 'B', checkpoint=checkpoint)
    foreign = live / 'foreign'
    foreign.write_text('foreign')
    foreign.chmod(0o600)
    os.replace(foreign, live / 'config')
    with pytest.raises(transaction.Refusal, match='foreign-publication'):
        apply(area, 'B')
    assert (live / 'config').read_text() == 'foreign'
    assert (state / 'pending.json').exists()


def test_check_mode_does_not_publish_or_start_existing(area):
    state, live, adapter, _ = area
    apply(area, 'A')
    before = (state / 'accepted.json').read_bytes()
    adapter.events.clear()
    result = apply(area, 'B', check=True)
    assert result == {'status': 'predicted', 'changed': True, 'published': False}
    assert (live / 'config').read_text() == 'A'
    assert (state / 'accepted.json').read_bytes() == before
    assert adapter.events == []


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'malformed'])
def test_unsafe_journal_refuses_without_cleanup(area, kind):
    state, live, _, _ = area
    apply(area, 'A')
    foreign = live / 'foreign'
    foreign.write_text('foreign')
    foreign.chmod(0o600)
    journal = state / 'pending.json'
    if kind == 'symlink':
        journal.symlink_to(foreign)
    elif kind == 'hardlink':
        os.link(foreign, journal)
    else:
        journal.write_text('{}')
        journal.chmod(0o600)
    with pytest.raises((transaction.Refusal, ValueError)):
        apply(area, 'B')
    assert foreign.read_text() == 'foreign'
    assert journal.exists()


def test_fresh_check_mode_leaves_state_absent(area):
    state, live, adapter, _ = area
    result = apply(area, 'A', check=True)
    assert result == {'status': 'predicted', 'changed': True, 'published': False}
    assert not state.exists()
    assert list(live.iterdir()) == []
    assert adapter.events == []


def test_prior_complete_generation_retained_across_unchanged_retry(area):
    state, live, _, _ = area
    apply(area, 'A')
    apply(area, 'B')
    saved = sorted(transaction.storage_path(live / 'config').glob('rollback-*'))
    assert len(saved) == 2
    saved_inode = {path.name: path.lstat().st_ino for path in saved}
    assert any(path.is_file() and path.read_text() == 'A' for path in saved)
    apply(area, 'B')
    assert {path.name: path.lstat().st_ino for path in transaction.storage_path(live / 'config').glob('rollback-*')} == saved_inode
    apply(area, 'C')
    assert any(path.is_file() and path.read_text() == 'B' for path in transaction.storage_path(live / 'config').glob('rollback-*'))


def test_large_staged_asset_and_deferred_receipt_share_acceptance(area):
    state, live, adapter, candidates = area
    apply(area, 'A')
    cache = live / 'staged'
    cache.mkdir()
    cache.chmod(0o755)
    source = cache / 'geoip.dat'
    source.write_bytes(b'owned-asset-' * 200000)
    source.chmod(0o644)
    import hashlib
    plan = candidates('B') + [
        {'path': str(live / 'geoip.dat'), 'source': str(source),
         'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'mode': 0o644, 'gid': os.getgid()},
        {'path': str(live / 'receipt'), 'data': base64.b64encode(b'accepted-B').decode(),
         'mode': 0o600, 'gid': os.getgid(), 'deferred': True}]
    def checkpoint(stage):
        if stage == 'ready':
            assert not (live / 'receipt').exists()
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        result = tx.apply(plan, adapter, checkpoint=checkpoint)
    assert result['status'] == 'accepted'
    assert (live / 'geoip.dat').read_bytes() == source.read_bytes()
    assert (live / 'receipt').read_bytes() == b'accepted-B'


def killed_child(area, stage, *, compensation=False):
    state, _live, _adapter, candidates = area
    code = '''import json,os,runpy,signal,sys
module=runpy.run_path(sys.argv[1])
tx=module['transaction']; adapter=module['Adapter'](); adapter.running=True
request=json.loads(sys.argv[2])
def checkpoint(stage):
 if stage == request['stage']: os.kill(os.getpid(),signal.SIGKILL)
with tx.Transaction(request['state'],uid=os.getuid()) as owned:
 if request['compensation']: owned.compensate_latest(adapter,checkpoint=checkpoint)
 else: owned.apply(request['candidates'],adapter,checkpoint=checkpoint)
'''
    request = {'state': str(state), 'stage': stage, 'compensation': compensation,
               'candidates': candidates('B')}
    result = subprocess.run([sys.executable, '-c', code, str(Path(__file__).resolve()),
                             json.dumps(request)], capture_output=True, timeout=10)
    assert result.returncode == -signal.SIGKILL, result.stderr.decode()


@pytest.mark.parametrize('stage', ['staged-0', 'prepared', 'linked-0', 'linked-1', 'materialized-0', 'materialized-1'])
def test_real_sigkill_during_preparation_can_retry_without_foreign_cleanup(area, stage):
    state, live, _adapter, _candidates = area
    apply(area, 'A')
    before_inode = (live / 'config').stat().st_ino
    killed_child(area, stage)
    assert (live / 'config').read_text() == 'A'
    assert (live / 'config').stat().st_ino == before_inode
    if stage == 'staged-0':
        orphan = next(state.glob('.prepare-*'))
        orphan_inode = orphan.stat().st_ino
        assert not (state / 'preparation.json').exists()
    result = apply(area, 'B')
    assert result['published'] and result['status'] == 'accepted'
    assert (live / 'config').read_text() == 'B'
    assert not (state / 'preparation.json').exists()
    assert not (state / 'pending.json').exists()
    if stage == 'staged-0':
        # No persisted inode claim exists for this scratch directory. Retaining
        # it cannot block a retry and must not authorize speculative cleanup.
        assert orphan.stat().st_ino == orphan_inode
        assert (transaction.storage_path(live / 'config') / ('staged-' + orphan.name[1:] + '-0')).read_text() == 'B'


def test_preparation_rejects_foreign_identical_inode_before_any_cleanup(area):
    state, live, _adapter, _candidates = area
    apply(area, 'A')
    killed_child(area, 'prepared')
    intent = json.loads((state / 'preparation.json').read_text())
    directory = state / intent['directory']
    staged = transaction.staged_path(intent, 0, intent['intent']['entries'][0])
    foreign = staged.parent / 'foreign'
    foreign.write_bytes(staged.read_bytes())
    foreign.chmod(0o600)
    os.replace(foreign, staged)
    inode = staged.stat().st_ino
    receipt = (state / 'accepted.json').read_bytes()
    with pytest.raises(transaction.Refusal, match='preparation-node-changed'):
        apply(area, 'B')
    assert staged.stat().st_ino == inode
    assert (live / 'config').read_text() == 'A'
    assert (state / 'accepted.json').read_bytes() == receipt
    assert (state / 'preparation.json').exists()


def test_preparation_check_mode_is_read_only_with_partial_backups(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    killed_child(area, 'materialized-0')
    before = (state / 'preparation.json').read_bytes()
    inode = (live / 'config').stat().st_ino
    adapter.events.clear()
    result = apply(area, 'B', check=True)
    assert result == {'status': 'predicted', 'changed': True, 'published': False}
    assert (state / 'preparation.json').read_bytes() == before
    assert (live / 'config').stat().st_ino == inode
    assert adapter.events == []


def test_latest_compensation_restores_exact_previous_receipt_and_absence(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    original = (state / 'accepted.json').read_bytes()
    inode = (live / 'config').stat().st_ino
    extra = live / 'new-file'
    plan = _candidates('B') + [{'path': str(extra), 'data': base64.b64encode(b'new').decode(),
                               'mode': 0o600, 'gid': os.getgid()}]
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.apply(plan, adapter)
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        result = tx.compensate_latest(adapter)
    assert result['status'] == 'compensated' and result['changed']
    assert not extra.exists()
    assert (live / 'config').stat().st_ino == inode
    assert (state / 'accepted.json').read_bytes() == original
    assert adapter.running
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        assert not tx.compensate_latest(adapter)['changed']
    assert not (state / 'last.json').exists()
    assert not (state / 'compensating.json').exists()


@pytest.mark.parametrize('stage', ['compensation-intent', 'compensation-stopped',
                                   'compensated-0', 'compensated-1',
                                   'compensation-ready', 'compensation-committed'])
def test_real_sigkill_compensation_recovers_previous_exact_inodes(area, stage):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    original = (state / 'accepted.json').read_bytes()
    inode = (live / 'config').stat().st_ino
    apply(area, 'B')
    killed_child(area, stage, compensation=True)
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        assert tx.recover(adapter)
    assert (state / 'accepted.json').read_bytes() == original
    assert (live / 'config').stat().st_ino == inode
    assert (live / 'config').read_text() == 'A'
    assert adapter.running
    assert not (state / 'compensating.json').exists()


def test_first_compensation_removes_receipt_and_keeps_frontend_stopped(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.compensate_latest(adapter)
    assert not (live / 'config').exists()
    assert not (live / 'current').exists()
    assert not (state / 'accepted.json').exists()
    assert not adapter.running


def test_compensation_refuses_foreign_inode_without_mutation(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    apply(area, 'B')
    before = (state / 'accepted.json').read_bytes()
    foreign = live / 'foreign'
    foreign.write_text('B')
    foreign.chmod(0o600)
    os.replace(foreign, live / 'config')
    inode = (live / 'config').stat().st_ino
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(transaction.Refusal, match='foreign-publication'):
            tx.compensate_latest(adapter)
    assert (live / 'config').stat().st_ino == inode
    assert (state / 'accepted.json').read_bytes() == before
    assert not (state / 'compensating.json').exists()


def test_outer_compensation_defers_receipt_commit_until_positive_readiness(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    original = (state / 'accepted.json').read_bytes()
    apply(area, 'B')
    current = (state / 'accepted.json').read_bytes()
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        result = tx.compensate_latest(adapter, restore_only=True)
    assert result['status'] == 'restored-awaiting-outer-owner'
    assert result['units'] == {'running': True}
    assert (live / 'config').read_text() == 'A'
    assert (state / 'accepted.json').read_bytes() == current
    assert not adapter.running
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.compensate_latest(adapter)
    assert (state / 'accepted.json').read_bytes() == original
    assert adapter.running


def test_outer_pending_recovery_defers_activation_until_owner_restores_route(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    original = (state / 'accepted.json').read_bytes()
    def interrupt(stage):
        if stage == 'published-0':
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        apply(area, 'B', checkpoint=interrupt)
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        result = tx.recover(adapter, restore_only=True)
    assert result['status'] == 'restored-awaiting-outer-owner'
    assert (live / 'config').read_text() == 'A'
    assert (state / 'pending.json').exists()
    assert (state / 'accepted.json').read_bytes() == original
    assert not adapter.running
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        assert tx.recover(adapter)
    assert adapter.running
    assert not (state / 'pending.json').exists()


def test_absence_candidates_retire_and_readmit_exact_owned_nodes(area):
    state, live, adapter, candidates = area
    apply(area, 'A')
    original = (state / 'accepted.json').read_bytes()
    plan = [{'path': item['path'], 'absent': True} for item in candidates('A')]
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        assert tx.apply(plan, adapter)['published']
        assert not tx.apply(plan, adapter)['published']
    receipt = json.loads((state / 'accepted.json').read_text())
    assert receipt['nodes'] == {item['path']: None for item in plan}
    assert not (live / 'config').exists() and not (live / 'current').exists()
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.compensate_latest(adapter)
    assert (state / 'accepted.json').read_bytes() == original
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.apply(plan, adapter)
    assert apply(area, 'B')['published']
    assert (live / 'config').read_text() == 'B'


def load_probe():
    spec = importlib.util.spec_from_file_location('transport_runtime_probe', SOURCE.with_name('transport_runtime_probe.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_command_output_stream_limit_stops_owned_child(area):
    _state, live, _adapter, _candidates = area
    probe = load_probe()
    pid_path = live / 'producer-pid'
    code = '''import os,sys
open(sys.argv[1],'w').write(str(os.getpid()))
while True: os.write(1,b'x'*65536)
'''
    with pytest.raises(probe.ProbeRefused, match='native-command-output-limit'):
        probe.run([sys.executable, '-c', code, str(pid_path)], 5)
    pid = int(pid_path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_native_command_duplex_input_deadline_and_child_cleanup(area):
    _state, live, _adapter, _candidates = area
    probe = load_probe()
    payload = b'dedicated-private-input' * 20000
    result = probe.run([sys.executable, '-c', 'import sys;data=sys.stdin.buffer.read();sys.stdout.buffer.write(data)'],
                       5, data=payload)
    assert result == payload
    pid_path = live / 'blocked-pid'
    code = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(30)"
    with pytest.raises(probe.ProbeRefused, match='native-command-timeout'):
        probe.run([sys.executable, '-c', code, str(pid_path)], .3)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_path.read_text()), 0)


def test_matching_new_candidate_authority_is_enrolled_before_unchanged_fast_path(area):
    state, live, adapter, candidates = area
    apply(area, 'A')
    extra = live/'new-authority'
    extra.write_bytes(b'already-matching-private-authority'); extra.chmod(0o600)
    plan = candidates('A') + [{'path':str(extra), 'data':base64.b64encode(extra.read_bytes()).decode(),
                                'mode':0o600, 'gid':os.getgid()}]
    before = (state/'accepted.json').read_bytes()
    adapter.events.clear()
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        result = tx.apply(plan, adapter)
        accepted = tx.accepted()
    assert result['changed'] and result['published']
    assert 'validate' in adapter.events and adapter.events.index('validate') < adapter.events.index('stop')
    assert str(extra) in accepted['nodes']
    assert (state/'accepted.json').read_bytes() != before
    adapter.events.clear()
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        retry = tx.apply(plan, adapter)
    assert not retry['changed'] and not retry['published']
    assert 'validate' not in adapter.events


def test_backup_map_tracks_preexisting_unaccepted_and_partial_plan_lineage(area):
    state, live, adapter, candidates = area
    state.mkdir(mode=0o700)
    state.chmod(0o700)
    parameters = state / 'parameters.json'
    parameters.write_bytes(b'bootstrap-before-any-accepted-receipt')
    parameters.chmod(0o600)
    bootstrap_inode = parameters.stat().st_ino
    def full(version):
        return candidates(version) + [{'path': str(parameters), 'data': base64.b64encode(version.encode()).decode(),
                                       'mode': 0o600, 'gid': os.getgid()}]
    def publish(plan):
        with transaction.Transaction(state, uid=os.getuid()) as tx:
            return tx.apply(plan, adapter)
    publish(full('A'))
    backup = transaction.storage_path(parameters) / ('rollback-' + __import__('hashlib').sha256(str(parameters).encode()).hexdigest())
    assert backup.stat().st_ino == bootstrap_inode
    first_inode = parameters.stat().st_ino
    publish(full('B'))
    assert backup.stat().st_ino == first_inode
    second_inode = parameters.stat().st_ino
    before_partial = (state / 'backups.json').read_bytes()
    publish(candidates('C')[:1])
    assert parameters.read_bytes() == b'B' and parameters.stat().st_ino == second_inode
    assert backup.stat().st_ino == first_inode
    partial_map = json.loads((state / 'backups.json').read_bytes())
    assert partial_map['nodes'][str(parameters)]['identity'][1] == first_inode
    assert (state / 'backups.json').read_bytes() != before_partial
    previous_receipt = (state / 'accepted.json').read_bytes()
    publish(full('D'))
    assert backup.stat().st_ino == second_inode
    stable_map = (state / 'backups.json').read_bytes()
    assert not publish(full('D'))['published']
    assert (state / 'backups.json').read_bytes() == stable_map
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.compensate_latest(adapter)
    assert (state / 'accepted.json').read_bytes() == previous_receipt
    assert parameters.stat().st_ino == second_inode and parameters.read_bytes() == b'B'
    assert not backup.exists()
    assert json.loads((state / 'backups.json').read_bytes())['nodes'][str(parameters)] is None
    assert publish(full('E'))['published']


def test_partial_compensation_preserves_untouched_exact_backup_claims(area):
    state, live, adapter, candidates = area
    apply(area, 'A')
    apply(area, 'B')
    before_map = json.loads((state / 'backups.json').read_bytes())
    link_backup = transaction.storage_path(live / 'current') / ('rollback-' + __import__('hashlib').sha256(str(live / 'current').encode()).hexdigest())
    inode = link_backup.lstat().st_ino
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.apply(candidates('C')[:1], adapter)
        tx.compensate_latest(adapter)
    after_map = json.loads((state / 'backups.json').read_bytes())
    assert after_map['nodes'][str(live / 'current')] == before_map['nodes'][str(live / 'current')]
    assert link_backup.lstat().st_ino == inode
    assert after_map['nodes'][str(live / 'config')] is None
    assert (live / 'config').read_text() == 'B'


def test_foreign_identical_backup_prevents_all_cleanup_mutation(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    apply(area, 'B')
    def interrupted(stage):
        if stage == 'committed':
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        apply(area, 'C', checkpoint=interrupted)
    digest = __import__('hashlib').sha256(str(live / 'current').encode()).hexdigest()
    backup = transaction.storage_path(live / 'current') / ('rollback-' + digest)
    foreign = state / 'foreign-identical-backup'
    foreign.symlink_to(os.readlink(backup))
    os.replace(foreign, backup)
    before = {path.name: transaction.node(path, os.getuid(), links=2)
              for path in transaction.storage_path(live / 'current').iterdir() if path.name.startswith(('rollback-', 'before-', 'after-'))}
    mapping = (state / 'backups.json').read_bytes()
    adapter.events.clear()
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(transaction.Refusal, match='foreign-rollback'):
            tx.recover(adapter)
    assert {path.name: transaction.node(path, os.getuid(), links=2)
            for path in transaction.storage_path(live / 'current').iterdir() if path.name.startswith(('rollback-', 'before-', 'after-'))} == before
    assert (state / 'backups.json').read_bytes() == mapping
    assert (state / 'pending.json').exists()
    assert adapter.events == []


@pytest.mark.parametrize('phase', ['before-map', 'after-map', 'after-last'])
def test_backup_cleanup_record_interruption_recognizes_only_old_or_new_map(area, phase, monkeypatch):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    apply(area, 'B')
    original = transaction.Transaction.record
    def interrupted(self, name, value):
        if phase == 'before-map' and name == 'backups.json':
            raise SystemExit(99)
        result = original(self, name, value)
        if phase == 'after-map' and name == 'backups.json' or phase == 'after-last' and name == 'last.json':
            raise SystemExit(99)
        return result
    monkeypatch.setattr(transaction.Transaction, 'record', interrupted)
    with pytest.raises(SystemExit):
        apply(area, 'C')
    monkeypatch.setattr(transaction.Transaction, 'record', original)
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        assert tx.recover(adapter)
    assert (live / 'config').read_text() == 'C'
    assert not (state / 'pending.json').exists()
    assert not apply(area, 'C')['published']


@pytest.mark.parametrize('kind', ['malformed', 'null', 'third-map'])
def test_unknown_backup_map_is_retained_without_mutation(area, kind):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    apply(area, 'B')
    path = state / 'backups.json'
    if kind == 'malformed':
        path.write_text('{"schema":1,"foreign":true}')
    elif kind == 'null':
        path.write_text('null')
    else:
        value = json.loads(path.read_bytes())
        value['nodes'][str(live / 'config')]['sha256'] = 'f' * 64
        path.write_text(json.dumps(value))
    before = path.read_bytes()
    inode = (live / 'config').stat().st_ino
    adapter.events.clear()
    with pytest.raises(transaction.Refusal):
        apply(area, 'C')
    assert path.read_bytes() == before
    assert (live / 'config').stat().st_ino == inode
    assert adapter.events == []
    assert not (state / 'pending.json').exists()


def test_final_receipt_union_limit_refuses_before_durable_intent_or_quiescence(area):
    state, live, adapter, _candidates = area
    plan = [{'path': str(live / ('authority-' + str(index))), 'data': base64.b64encode(b'owned').decode(),
             'mode': 0o600, 'gid': os.getgid()} for index in range(64)]
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.apply(plan, adapter)
    candidate = [{'path': str(live / 'authority-65'), 'data': base64.b64encode(b'new').decode(),
                  'mode': 0o600, 'gid': os.getgid()}]
    before = (state / 'accepted.json').read_bytes()
    adapter.events.clear()
    for check in (True, False):
        with transaction.Transaction(state, uid=os.getuid(), check=check) as tx:
            with pytest.raises(transaction.Refusal, match='receipt-node-limit'):
                tx.apply(candidate, adapter, check=check)
    assert (state / 'accepted.json').read_bytes() == before
    assert not (state / 'pending.json').exists()
    assert not (state / 'preparation.json').exists()
    assert not (live / 'authority-65').exists()
    assert adapter.events == []


@pytest.mark.parametrize('record', ['preparation.json', 'pending.json', 'compensating.json'])
def test_unfinished_controller_admission_requires_live_retained_publisher(area, record):
    state, _live, _adapter, _candidates = area
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.record(record, {'schema': 1})
        transaction.admission(state, uid=os.getuid())
    with pytest.raises(transaction.Refusal, match='unfinished-runtime-without-publisher'):
        transaction.admission(state, uid=os.getuid())
    (state / record).unlink()
    transaction.admission(state, uid=os.getuid())


def test_identical_replaced_private_storage_refuses_before_any_mutation(area):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    apply(area, 'B')
    slot = transaction.storage_path(live / 'config')
    retained = slot.with_name('retained-exact-slot')
    slot.rename(retained)
    slot.mkdir(mode=0o700)
    before = (state / 'accepted.json').read_bytes()
    adapter.events.clear()
    with pytest.raises(transaction.Refusal, match='storage-directory-changed'):
        apply(area, 'C')
    assert (state / 'accepted.json').read_bytes() == before
    assert (live / 'config').read_text() == 'B'
    assert not list(slot.iterdir()) and list(retained.iterdir())
    assert adapter.events == []


def test_private_storage_is_never_selectable_authority(area):
    state, live, adapter, candidates = area
    plan = candidates('A')
    plan[0]['path'] = str(transaction.storage_path(live / 'config') / 'selected')
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(transaction.Refusal, match='candidate-invalid'):
            tx.apply(plan, adapter)
    assert list(live.iterdir()) == [] and adapter.events == []


def test_outer_coordination_does_not_revoke_completed_consumer_admission(area):
    state, _live, _adapter, _candidates = area
    apply(area, 'A')
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.record('outer.json', {'schema': 1, 'receipt': tx.accepted(), 'consumer_receipt': None})
    with pytest.raises(transaction.Refusal, match='unfinished-runtime-without-publisher'):
        transaction.admission(state, uid=os.getuid())
    assert not apply(area, 'A')['published']
    transaction.admission(state, uid=os.getuid())
    apply(area, 'B')
    transaction.admission(state, uid=os.getuid())


@pytest.mark.parametrize('record', ['pending.json','preparation.json','compensating.json','outer.json'])
def test_predictive_reader_cannot_authorize_unfinished_process_admission(area, record):
    state, _live, _adapter, _candidates = area
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        if record == 'outer.json':
            tx.record(record, {'schema':1,'receipt':None,'consumer_receipt':None})
        else:
            tx.record(record, {'schema':1})
    before = (state / record).read_bytes()
    with transaction.Transaction(state, uid=os.getuid(), check=True):
        with pytest.raises(transaction.Refusal, match='unfinished-runtime-without-publisher'):
            transaction.admission(state, uid=os.getuid())
    assert (state / record).read_bytes() == before


@pytest.mark.parametrize('stage', ['intent','stopped'])
def test_prepublication_recovery_consumes_owned_hardlinks_before_runtime_restore(area, stage):
    state, live, adapter, _candidates = area
    apply(area, 'A')
    original = (live / 'config').stat().st_ino
    killed_child(area, stage)
    original_restore = adapter.restore
    def strict_restore(units):
        assert (live / 'config').stat().st_nlink == 1
        assert (live / 'current').lstat().st_nlink == 1
        original_restore(units)
    adapter.restore = strict_restore
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        assert tx.recover(adapter)
    assert (live / 'config').stat().st_ino == original
    assert (live / 'config').read_text() == 'A'


def test_relative_legacy_preimage_restores_verbatim_and_same_inode(area):
    state, live, adapter, candidates = area
    (live / 'current').symlink_to('generation-A')
    inode = (live / 'current').lstat().st_ino
    adapter.reject = 'ready'
    with pytest.raises(transaction.Refusal):
        apply(area, 'B')
    assert os.readlink(live / 'current') == 'generation-A'
    assert (live / 'current').lstat().st_ino == inode


def test_distinct_consumers_serialize_shared_publication_storage(area):
    state, live, _, candidates = area
    apply(area, 'A')
    with transaction.Transaction(state, uid=os.getuid()) as first:
        first.validate(candidates('B'))
        other = state.parent / 'other-state'
        with transaction.Transaction(other, uid=os.getuid()) as second:
            with pytest.raises(BlockingIOError):
                second.validate(candidates('C'))
    assert (live / 'config').read_text() == 'A'
