"""Real private-file queue copies preserve preimages through publisher interruption."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name, source):
    spec = importlib.util.spec_from_file_location(name, ROOT / source)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


core = module('transport_runtime_transaction', 'ansible/roles/runtime-release/files/transport_runtime_transaction.py')
module('observability_queue_boundary', 'ansible/roles/observability_agent/files/observability-queue-boundary.py')
queue = module('observability_runtime_queue', 'ansible/roles/observability_agent/files/observability_runtime_queue.py')


@pytest.fixture
def area(private_authority_path, monkeypatch):
    root = private_authority_path.resolve()
    data = root / 'queue'
    data.mkdir(mode=0o700)
    sub = data / 'persistent-queue' / '1_0123456789ABCDEF'
    sub.mkdir(parents=True, mode=0o700)
    sub.parent.chmod(0o700)
    for name, content in {'flock.lock': b'', '0000000000000000': b'historical sample A',
                          'metainfo.json': json.dumps({'Name': '1:secret-url', 'ReaderOffset': 0,
                                                      'WriterOffset': 19}).encode()}.items():
        path = sub / name
        path.write_bytes(content)
        path.chmod(0o600)
    # Space admission is a separate test; ordinary copy cases use a controlled
    # statvfs response without substituting any queue file operation.
    original = queue.os.fstatvfs
    def capacity(fd):
        actual = original(fd)
        return os.statvfs_result((actual.f_bsize, actual.f_frsize, 20 * 1024**3 // actual.f_frsize,
                                 15 * 1024**3 // actual.f_frsize, 15 * 1024**3 // actual.f_frsize,
                                 actual.f_files, actual.f_ffree, actual.f_favail, actual.f_flag, actual.f_namemax))
    monkeypatch.setattr(queue.os, 'fstatvfs', capacity)
    intent = {'entries': [], 'before_receipt': None, 'after_receipt': {'nodes': {}}}
    return root / 'state', data, sub, intent


def snapshot(area, tx, **kwargs):
    return queue.QueueSnapshot(tx, area[1], os.getuid(), **kwargs)


def test_copy_compensates_consumed_metadata_and_preserves_root_inode(area):
    state, data, sub, intent = area
    inode = data.stat().st_ino
    before = {path.name: path.read_bytes() for path in sub.iterdir()}
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.capture(intent)
        retained = (state / 'queue-snapshot.json').read_bytes()
        (sub / '0000000000000000').write_bytes(b'candidate consumed A')
        (sub / 'metainfo.json').write_bytes(b'{"ReaderOffset":19}')
        saved.capture(intent)
        assert (state / 'queue-snapshot.json').read_bytes() == retained
        saved.restore()
        assert data.stat().st_ino == inode
        assert {path.name: path.read_bytes() for path in sub.iterdir()} == before
        (sub / '0000000000000000').write_bytes(b'A resumed and produced B')
        saved.restore()
        assert (sub / '0000000000000000').read_bytes() == b'A resumed and produced B'
        saved.cleanup()
        assert not (state / 'queue-snapshot.json').exists()


@pytest.mark.parametrize('stage', ['queue-intent', 'queue-retained', 'queue-restore-copied',
                                  'queue-restored-entry', 'queue-restored'])
def test_interrupted_copy_or_restore_reconciles_original_bytes(area, stage):
    state, data, sub, intent = area
    before = (sub / '0000000000000000').read_bytes()
    def kill(value):
        if value == stage:
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        with core.Transaction(state, uid=os.getuid()) as tx:
            saved = snapshot(area, tx, checkpoint=kill)
            saved.capture(intent)
            (sub / '0000000000000000').write_bytes(b'rejected')
            saved.restore()
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.restore()
        assert (sub / '0000000000000000').read_bytes() == before
        saved.cleanup()


@pytest.mark.parametrize('death_index', range(1, 5))
def test_cleanup_interruption_permits_only_recorded_absence(area, monkeypatch, death_index):
    state, _, _, intent = area
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.capture(intent)
        saved.restore()
        original = os.unlink
        count = 0
        def kill(name, *args, **kwargs):
            nonlocal count
            original(name, *args, **kwargs)
            count += 1
            if count == death_index:
                raise SystemExit(99)
        with monkeypatch.context() as patch:
            patch.setattr(os, 'unlink', kill)
            with pytest.raises(SystemExit):
                saved.cleanup()
    with core.Transaction(state, uid=os.getuid()) as tx:
        snapshot(area, tx).cleanup()
        assert not (state / 'queue-snapshot.json').exists()


@pytest.mark.parametrize('fault', ['symlink', 'hardlink', 'unknown', 'metadata', 'offset'])
def test_unsafe_native_queue_is_preserved_before_any_backup(area, fault):
    state, data, sub, intent = area
    if fault == 'symlink':
        (sub / 'unexpected').symlink_to(sub / '0000000000000000')
    elif fault == 'hardlink':
        os.link(sub / '0000000000000000', sub / 'unexpected')
    elif fault == 'unknown':
        (sub / 'unexpected').write_text('foreign')
    elif fault == 'metadata':
        (sub / 'metainfo.json').write_text('{"ReaderOffset":true}')
    else:
        (sub / '0000000000000000').rename(sub / '0000000000000001')
    before = {path.name: path.lstat().st_ino for path in sub.iterdir()}
    with core.Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(core.Refusal):
            snapshot(area, tx).capture(intent)
    assert {path.name: path.lstat().st_ino for path in sub.iterdir()} == before
    assert not (state / 'queue-snapshot.json').exists()


def test_insufficient_space_refuses_without_queue_mutation(area, monkeypatch):
    state, _, sub, intent = area
    original = queue.os.fstatvfs
    def low(fd):
        actual = list(original(fd))
        actual[4] = 1
        return os.statvfs_result(actual)
    monkeypatch.setattr(queue.os, 'fstatvfs', low)
    with core.Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(core.Refusal, match='capacity'):
            snapshot(area, tx).capture(intent)
    assert (sub / '0000000000000000').read_bytes() == b'historical sample A'


def test_foreign_backup_inode_with_identical_bytes_is_preserved(area):
    state, _, _, intent = area
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.capture(intent)
        record = saved.saved()
        target = state / record['directory'] / 'persistent-queue/1_0123456789ABCDEF/0000000000000000'
        replacement = target.with_name('replacement')
        replacement.write_bytes(target.read_bytes())
        replacement.chmod(0o600)
        replacement.replace(target)
        inode = target.stat().st_ino
        with pytest.raises(core.Refusal, match='backup-shape'):
            saved.restore()
        assert target.stat().st_ino == inode


def test_malformed_restore_claim_refuses_before_live_deletion(area):
    state, _, sub, intent = area
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.capture(intent)
        record = saved.saved()
        record['restore'] = {'name': '../foreign'}
        tx.record('queue-snapshot.json', record)
        before = (sub / '0000000000000000').read_bytes()
        with pytest.raises(core.Refusal, match='restore-record'):
            saved.restore()
        assert (sub / '0000000000000000').read_bytes() == before


def test_empty_preclaim_directory_is_retained_without_stranding_retry(area):
    state, _, _, intent = area
    with core.Transaction(state, uid=os.getuid()) as tx:
        orphan = state / ('.queue-' + 'a' * 32)
        orphan.mkdir(mode=0o700)
        saved = snapshot(area, tx)
        saved.capture(intent)
        saved.restore()
        saved.cleanup()
        assert orphan.is_dir()
        assert not list(orphan.iterdir())


def test_empty_restore_preclaim_directory_is_retained_and_original_recovers(area):
    state, data, sub, intent = area
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.capture(intent)
        storage = data / queue.STORE
        storage.mkdir(mode=0o700)
        orphan = storage / ('restore-' + 'a' * 32)
        orphan.mkdir(mode=0o700)
        (sub / '0000000000000000').write_bytes(b'rejected')
        saved.restore()
        assert (sub / '0000000000000000').read_bytes() == b'historical sample A'
        saved.cleanup()
        assert orphan.is_dir()


def test_preflight_rejects_foreign_helper_before_chmod_or_replacement(private_authority_path):
    authority = module('observability_runtime_authority',
                       'ansible/roles/observability_agent/files/observability_runtime_authority.py')
    root = private_authority_path.resolve()
    helper = root / 'helper'
    helper.mkdir(mode=0o755)
    helper.chmod(0o755)
    original = helper.stat()
    with pytest.raises(ValueError, match='directory-authority'):
        authority.validate(core.TrustedDirectory, uid=os.getuid(), helper=helper,
                           state=root / 'state', guard=root / 'guard')
    assert helper.stat() == original


@pytest.fixture
def sender_area(area, monkeypatch):
    module('observability_agent_readiness', 'ansible/roles/observability_agent/files/observability-agent-readiness.py')
    sender = module('observability_runtime_accept', 'ansible/roles/observability_agent/files/observability_runtime_accept.py')
    state, data, sub, intent = area
    unit = state.parent / 'sender.service'
    unit.write_text('ExecStart=/usr/local/bin/vmagent-observability-agent -httpListenAddr=127.0.0.1:19098\n#A\n')
    unit.chmod(0o644)
    monkeypatch.setattr(sender, 'UNIT', unit)
    active = {'running': True, 'reject': False}
    def fields():
        return {'LoadState': 'loaded' if unit.exists() else 'not-found',
                'ActiveState': 'active' if active['running'] else 'inactive',
                'UnitFileState': 'enabled' if unit.exists() else '',
                'MainPID': '123' if active['running'] else '0', 'Result': 'success', 'ControlGroup': ''}
    monkeypatch.setattr(sender, 'fields', fields)
    def control(argv):
        if argv[1] == 'stop':
            active['running'] = False
        if argv[1] == 'start':
            active['running'] = True
            if '#B' in unit.read_text():
                (sub / '0000000000000000').write_bytes(b'candidate advanced its queue')
        return ''
    monkeypatch.setattr(sender, 'run', control)
    def ready(_listener, _runtime):
        if active['reject'] and '#B' in unit.read_text():
            raise ValueError('fixture candidate failed listener')
        assert active['running']
    monkeypatch.setattr(sender.readiness, 'ready', ready)
    monkeypatch.setattr(sender.time, 'sleep', lambda _duration: None)
    ticks = iter(range(1000))
    monkeypatch.setattr(sender.time, 'monotonic', lambda: next(ticks))
    def make(tx):
        value = sender.Sender(tx, queue=data, agent_uid=os.getuid())
        # Native parser validation is exercised by Molecule; this unit fixture
        # substitutes only service/parser calls, retaining the real publisher.
        monkeypatch.setattr(value, 'validate', lambda: None)
        return value
    return sender, unit, active, make


def test_sender_publication_failure_restores_queue_before_old_readiness(area, sender_area):
    import base64
    state, data, sub, _ = area
    sender, unit, active, make = sender_area
    inode = data.stat().st_ino
    old_unit = unit.stat().st_ino
    before = (sub / '0000000000000000').read_bytes()
    content = unit.read_text().replace('#A', '#B')
    candidates = [{'path': str(unit), 'data': base64.b64encode(content.encode()).decode(),
                   'mode': 0o644, 'gid': os.getgid()}]
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        adapter.capture = True
        active['reject'] = True
        with pytest.raises(core.Refusal, match='candidate-refused'):
            tx.apply(candidates, adapter)
        assert adapter.restored_ready
        assert adapter.queue_proven
        assert active['running']
        assert data.stat().st_ino == inode
        assert unit.stat().st_ino == old_unit
        assert (sub / '0000000000000000').read_bytes() == before
        assert tx.journal() is None
        adapter.snapshot.cleanup()


@pytest.mark.parametrize('stage', ['intent', 'stopped', 'published-0', 'adopted'])
def test_sender_interrupted_publication_recovers_bound_queue(area, sender_area, stage):
    import base64
    state, data, sub, _ = area
    sender, unit, active, make = sender_area
    before = (sub / '0000000000000000').read_bytes()
    candidate = [{'path': str(unit), 'data': base64.b64encode(unit.read_bytes().replace(b'#A', b'#B')).decode(),
                  'mode': 0o644, 'gid': os.getgid()}]
    def death(value):
        if value == stage:
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        with core.Transaction(state, uid=os.getuid()) as tx:
            adapter = make(tx)
            adapter.capture = True
            tx.apply(candidate, adapter, checkpoint=death)
    with core.Transaction(state, uid=os.getuid()) as tx:
        sender.reconcile(tx, make(tx))
        assert b'#A' in unit.read_bytes()
        assert (sub / '0000000000000000').read_bytes() == before
        assert active['running']
        assert tx.journal() is None


def test_wrong_snapshot_intent_refuses_before_queue_or_selector_mutation(area, sender_area):
    import base64
    state, _, sub, _ = area
    sender, unit, _, make = sender_area
    candidate = [{'path': str(unit), 'data': base64.b64encode(unit.read_bytes().replace(b'#A', b'#B')).decode(),
                  'mode': 0o644, 'gid': os.getgid()}]
    def death(value):
        if value == 'published-0':
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        with core.Transaction(state, uid=os.getuid()) as tx:
            adapter = make(tx)
            adapter.capture = True
            tx.apply(candidate, adapter, checkpoint=death)
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        record = adapter.snapshot.saved()
        record['intent'] = '0' * 64
        tx.record('queue-snapshot.json', record)
        current = unit.read_bytes()
        data = (sub / '0000000000000000').read_bytes()
        with pytest.raises(core.Refusal, match='snapshot-owner'):
            sender.reconcile(tx, adapter)
        assert unit.read_bytes() == current
        assert (sub / '0000000000000000').read_bytes() == data


@pytest.mark.parametrize('stage', ['queue-intent', 'queue-retained', 'queue-restore-copied',
                                  'queue-restored-entry', 'queue-restored'])
def test_real_publisher_sigkill_preserves_original_queue(area, stage):
    import signal
    import subprocess
    state, data, sub, _ = area
    code = r'''
import importlib.util, json, os, signal, sys
from pathlib import Path
root, state, data, stage = sys.argv[1:]
def load(name, source):
    spec = importlib.util.spec_from_file_location(name, Path(root) / source)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value
core = load('transport_runtime_transaction', 'ansible/roles/runtime-release/files/transport_runtime_transaction.py')
load('observability_queue_boundary', 'ansible/roles/observability_agent/files/observability-queue-boundary.py')
queue = load('observability_runtime_queue', 'ansible/roles/observability_agent/files/observability_runtime_queue.py')
original = os.fstatvfs
def capacity(fd):
    value = list(original(fd))
    value[2:5] = [20 * 1024**3 // value[1], 15 * 1024**3 // value[1], 15 * 1024**3 // value[1]]
    return os.statvfs_result(value)
os.fstatvfs = capacity
def death(value):
    if value == stage:
        os.kill(os.getpid(), signal.SIGKILL)
with core.Transaction(Path(state), uid=os.getuid()) as tx:
    snapshot = queue.QueueSnapshot(tx, Path(data), os.getuid(), checkpoint=death)
    snapshot.capture({'entries': [], 'before_receipt': None, 'after_receipt': {'nodes': {}}})
    (Path(data) / 'persistent-queue/1_0123456789ABCDEF/0000000000000000').write_bytes(b'rejected')
    snapshot.restore()
'''
    result = subprocess.run([sys.executable, '-c', code, str(ROOT), str(state), str(data), stage],
                            capture_output=True, timeout=15)
    assert result.returncode == -signal.SIGKILL, result.stderr.decode()
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.restore()
        assert (sub / '0000000000000000').read_bytes() == b'historical sample A'
        saved.cleanup()


@pytest.mark.parametrize('capture_record', [2, 3, 4])
def test_death_between_backup_node_creation_and_inode_record_preserves_empty_orphan(area, monkeypatch, capture_record):
    state, _, sub, intent = area
    with pytest.raises(SystemExit):
        with core.Transaction(state, uid=os.getuid()) as tx:
            saved = snapshot(area, tx)
            original = saved.record
            count = 0
            def death(value):
                nonlocal count
                count += 1
                if count == capture_record:
                    raise SystemExit(99)
                original(value)
            monkeypatch.setattr(saved, 'record', death)
            saved.capture(intent)
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.restore()
        saved.cleanup()
        assert (sub / '0000000000000000').read_bytes() == b'historical sample A'
        saved.capture(intent)
        saved.restore()
        saved.cleanup()


@pytest.mark.parametrize('restore_record', [3, 4, 5])
def test_death_between_restore_node_creation_and_inode_record_recovers_original(area, monkeypatch, restore_record):
    state, _, sub, intent = area
    with pytest.raises(SystemExit):
        with core.Transaction(state, uid=os.getuid()) as tx:
            saved = snapshot(area, tx)
            saved.capture(intent)
            original = saved.record
            count = 0
            def death(value):
                nonlocal count
                count += 1
                if count == restore_record:
                    raise SystemExit(99)
                original(value)
            monkeypatch.setattr(saved, 'record', death)
            saved.restore()
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.restore()
        saved.cleanup()
        assert (sub / '0000000000000000').read_bytes() == b'historical sample A'
        saved.capture(intent)
        saved.restore()
        saved.cleanup()


def test_retirement_recovery_keeps_commit_proof_until_queue_cleanup(area, sender_area):
    import base64
    state, _, sub, _ = area
    sender, unit, active, make = sender_area
    before = (sub / '0000000000000000').read_bytes()
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        adapter.capture = True
        tx.apply([{'path': str(unit), 'data': base64.b64encode(unit.read_bytes()).decode(),
                   'mode': 0o644, 'gid': os.getgid()}], adapter)
        adapter.snapshot.cleanup()
        adapter = make(tx)
        adapter.capture = True
        adapter.plan = {'retire': True}
        tx.apply([{'path': str(unit), 'absent': True}], adapter)
        # Simulate death after core commit/cleanup, before queue cleanup.
        assert tx.journal() is None
        assert adapter.snapshot.saved()['phase'] == 'retained'
    with core.Transaction(state, uid=os.getuid()) as tx:
        sender.reconcile(tx, make(tx))
        assert not (state / 'accepted.json').exists()
        assert not (state / 'queue-snapshot.json').exists()
        assert not unit.exists()
        assert not active['running']
        assert (sub / '0000000000000000').read_bytes() == before


def test_interrupted_unchanged_startup_recovers_queue_before_next_start(area, sender_area):
    import base64
    state, _, sub, _ = area
    sender, unit, active, make = sender_area
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        adapter.capture = True
        tx.apply([{'path': str(unit), 'data': base64.b64encode(unit.read_bytes()).decode(),
                   'mode': 0o644, 'gid': os.getgid()}], adapter)
        adapter.snapshot.cleanup()
    active['running'] = False
    with pytest.raises(SystemExit):
        with core.Transaction(state, uid=os.getuid()) as tx:
            adapter = make(tx)
            def death(value):
                if value == 'queue-retained':
                    raise SystemExit(99)
            adapter.snapshot.checkpoint = death
            adapter.ensure()
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        sender.reconcile(tx, adapter)
        assert not active['running']
        assert (sub / '0000000000000000').read_bytes() == b'historical sample A'
        assert adapter.ensure()
        assert active['running']
        assert not (state / 'startup.json').exists()


def test_pre_snapshot_refusal_cannot_report_proven_queue_compensation(area, sender_area, monkeypatch):
    import base64
    state, _, sub, _ = area
    _, unit, active, make = sender_area
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        adapter.capture = True
        def refuse(_intent):
            raise core.Refusal('fixture capacity refusal')
        monkeypatch.setattr(adapter.snapshot, 'capture', refuse)
        with pytest.raises(core.Refusal, match='candidate-refused'):
            tx.apply([{'path': str(unit), 'data': base64.b64encode(unit.read_bytes().replace(b'#A', b'#B')).decode(),
                       'mode': 0o644, 'gid': os.getgid()}], adapter)
        assert adapter.restored_ready
        assert not adapter.queue_proven
        assert active['running']
        assert b'#A' in unit.read_bytes()
        assert (sub / '0000000000000000').read_bytes() == b'historical sample A'


@pytest.mark.parametrize('binary_changed', [False, True])
def test_binary_only_sender_selection_controls_adoption_from_actual_plan(area, sender_area, monkeypatch, binary_changed):
    import base64
    state, _, _, _ = area
    _, unit, _, make = sender_area
    link = state.parent / 'current'
    link.symlink_to(state.parent / 'runtime-A')
    def candidates(target):
        return [{'path': str(unit), 'data': base64.b64encode(unit.read_bytes()).decode(),
                 'mode': 0o644, 'gid': os.getgid()}, {'path': str(link), 'target': str(target)}]
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        adapter.capture = True
        tx.apply(candidates(state.parent / 'runtime-A'), adapter)
        adapter.snapshot.cleanup()
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        adapter.capture = True
        starts = []
        actual = adapter.start
        def start():
            starts.append(True)
            actual()
        monkeypatch.setattr(adapter, 'start', start)
        result = tx.apply(candidates(state.parent / ('runtime-B' if binary_changed else 'runtime-A')), adapter)
        assert result['changed'] == binary_changed
        assert bool(starts) == binary_changed
        assert link.resolve().name == ('runtime-B' if binary_changed else 'runtime-A')
        adapter.snapshot.cleanup()


@pytest.mark.parametrize('previous', [False, True])
def test_sender_accepts_installer_previous_selector_without_widening_write_authority(sender_area, previous):
    sender, _, _, _ = sender_area
    profile = {'install_root': '/opt/observability-vmagent'}
    paths = ['/opt/observability-vmagent/current', '/usr/local/bin/vmagent-observability-agent',
             str(sender.UNIT), '/etc/observability-agent/credentials/current', str(sender.PARAMETERS)]
    if previous:
        paths.append('/opt/observability-vmagent/previous')
    sender.validate_write_set(profile, [{'path': path} for path in paths])
    with pytest.raises(core.Refusal, match='write-set'):
        sender.validate_write_set(profile, [{'path': path} for path in paths + ['/etc/unowned']])
    with pytest.raises(core.Refusal, match='write-set'):
        sender.validate_write_set(profile, [{'path': path} for path in paths + [paths[0]]])


@pytest.mark.parametrize('fault,category', [('refusal', 'sender-write-set'),
                                           ('value', 'sender-activation-refused')])
def test_refusals_return_typed_categories_without_private_values(sender_area, monkeypatch, capsys, fault, category):
    sender, _, _, _ = sender_area
    monkeypatch.setattr(sender.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(sender.sys, 'argv', ['accept', 'recover'])
    def fail(*_args):
        if fault == 'refusal':
            raise core.Refusal('sender-write-set')
        raise ValueError('synthetic-private-input-must-not-escape')
    monkeypatch.setattr(sender, 'execute', fail)
    rc = sender.main()
    output = capsys.readouterr()
    assert rc == 1
    assert json.loads(output.out) == {'status': 'refused', 'changed': False, 'category': category}
    assert output.err.strip() == category
    assert 'synthetic-private-input' not in output.out + output.err


@pytest.mark.parametrize('fault', [None, 'symlink', 'hardlink', 'writable', 'oversized'])
def test_staged_binary_admission_has_its_own_bounded_authority(sender_area, private_authority_path, fault):
    sender, _, _, _ = sender_area
    binary = private_authority_path / 'vmagent-prod'
    with binary.open('wb') as stream:
        stream.truncate(2 * 1024**2)
    binary.chmod(0o755)
    path = binary
    if fault == 'symlink':
        path = binary.with_name('redirect')
        path.symlink_to(binary)
    elif fault == 'hardlink':
        os.link(binary, binary.with_name('other'))
    elif fault == 'writable':
        binary.chmod(0o775)
    elif fault == 'oversized':
        with binary.open('wb') as stream:
            stream.truncate(128 * 1024**2 + 1)
    if fault is None:
        sender.validate_binary(path, os.getuid())
    else:
        with pytest.raises((OSError, core.Refusal)):
            sender.validate_binary(path, os.getuid())


def test_binary_fifo_refuses_without_waiting_for_a_writer(private_authority_path):
    import subprocess
    fifo = private_authority_path / 'fifo'
    os.mkfifo(fifo, 0o755)
    fifo.chmod(0o755)
    code = r'''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import importlib.util
for name, file in [('observability_agent_readiness','observability-agent-readiness.py'),
                   ('observability_queue_boundary','observability-queue-boundary.py')]:
    spec=importlib.util.spec_from_file_location(name,Path(sys.argv[1])/file)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value)
from observability_runtime_accept import validate_binary, Refusal
try:
    validate_binary(Path(sys.argv[3]), os.getuid())
except Refusal:
    raise SystemExit(0)
raise SystemExit(9)
'''
    result = subprocess.run([sys.executable, '-c', code,
        str(ROOT / 'ansible/roles/observability_agent/files'),
        str(ROOT / 'ansible/roles/runtime-release/files'), str(fifo)],
        capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize('name,content', [
    ('metainfo.json.tmp.1', b'{"Name":"1:secret-url"}'),
    ('0000000000000000.tmp.2', b''),
])
def test_native_atomic_staging_survives_snapshot_and_compensation(area, name, content):
    state, data, sub, intent = area
    path = sub / name
    path.write_bytes(content)
    path.chmod(0o600)
    before = {item.name: item.read_bytes() for item in sub.iterdir()}
    inode = data.stat().st_ino
    with core.Transaction(state, uid=os.getuid()) as tx:
        saved = snapshot(area, tx)
        saved.capture(intent)
        extra = sub / 'metainfo.json.tmp.3'
        extra.write_bytes(b'interrupted candidate metadata')
        extra.chmod(0o600)
        saved.restore()
        assert data.stat().st_ino == inode
        assert {item.name: item.read_bytes() for item in sub.iterdir()} == before
        saved.cleanup()


@pytest.mark.parametrize('name,size', [
    ('metainfo.json.tmp.1', 16385),
    ('0000000000000000.tmp.1', 1),
    ('metainfo.json.tmp.18446744073709551616', 0),
    ('metainfo.json.tmp.01', 0),
    ('0000000000000001.tmp.1', 0),
])
def test_atomic_staging_admission_rejects_non_native_names_and_sizes(area, name, size):
    state, _, sub, intent = area
    path = sub / name
    path.write_bytes(b'x' * size)
    path.chmod(0o600)
    original = path.stat().st_ino
    with core.Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(core.Refusal, match='queue-native-layout'):
            snapshot(area, tx).capture(intent)
    assert path.stat().st_ino == original
    assert path.read_bytes() == b'x' * size


@pytest.mark.parametrize('race', ['once', 'persistent', 'foreign'])
def test_live_readiness_bounds_native_inode_races_and_keeps_authority_refusals(area, sender_area, monkeypatch, race):
    state, _, _, _ = area
    sender, _, _, make = sender_area
    actual = sender.tree
    calls = []
    def scan(*args, **kwargs):
        calls.append(1)
        if race == 'foreign':
            raise core.Refusal('queue-entry-authority')
        if len(calls) == 1 or race == 'persistent':
            raise core.Refusal('queue-entry-changed')
        return actual(*args, **kwargs)
    monkeypatch.setattr(sender, 'tree', scan)
    with core.Transaction(state, uid=os.getuid()) as tx:
        adapter = make(tx)
        if race == 'once':
            adapter.ready()
            assert len(calls) == 2
        else:
            with pytest.raises(core.Refusal, match='sender-not-ready' if race == 'persistent' else 'queue-entry-authority'):
                adapter.ready()
            assert len(calls) == (25 if race == 'persistent' else 1)
