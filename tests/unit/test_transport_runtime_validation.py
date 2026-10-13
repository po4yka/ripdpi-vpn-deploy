"""Exact native validation leases refuse foreign state before cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys

import pytest


@pytest.fixture
def tmp_path(private_authority_path):
    return private_authority_path

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / 'ansible/roles/runtime-release/files'
sys.path.insert(0, str(LIBRARY))
spec = importlib.util.spec_from_file_location('transport_validation_test', LIBRARY / 'transport_runtime_validate.py')
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
from transport_runtime_transaction import Transaction, identity, node, Refusal
import transport_runtime_probe as probe


@pytest.fixture
def leased(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    root.chmod(0o755)
    for name in ('units', 'namespaces', 'staging'):
        (root / name).mkdir()
        (root / name).chmod(0o755)
    monkeypatch.setattr(validation, 'UNIT_ROOT', root / 'units')
    monkeypatch.setattr(validation, 'NAMESPACE_ROOT', root / 'namespaces')
    monkeypatch.setattr(validation, 'STAGING_ROOT', root / 'staging')
    token = 'ripdpi-candidate-' + 'a' * 16
    unit = root / 'units' / (token + '.service')
    unit.write_text('ExecStart=/owned/synthetic-runtime\n')
    unit.chmod(0o600)
    namespace = root / 'namespaces' / token
    namespace.write_text('synthetic-namespace-inode')
    namespace.chmod(0o444)
    directory = root / 'staging' / (token + '-owned')
    directory.mkdir()
    directory.chmod(0o750)
    for name in validation.FILES:
        (directory / name).write_text('synthetic-' + name)
        (directory / name).chmod(0o640)
    state = root / 'state'
    uid = os.getuid()
    monkeypatch.setattr(validation, 'boot_id', lambda: '00000000-0000-0000-0000-000000000001')
    claim = {'schema': 1, 'boot_id': validation.boot_id(), 'phase': 'prepared',
             'unit': {'name': unit.name, **node(unit, uid)},
             'namespace': {'name': namespace.name, 'identity': identity(namespace.lstat())},
             'directory': {'name': directory.name, 'identity': identity(directory.lstat())},
             'files': {name: node(directory / name, uid) for name in validation.FILES}}
    with Transaction(state, uid=uid) as tx:
        tx.record('validation.json', claim)
    calls = []
    active = [True]
    def run(argv, _timeout):
        calls.append(argv)
        if argv[1] == 'show':
            return ('LoadState=loaded\nFragmentPath=' + str(unit) + '\nActiveState='
                    + ('active' if active[0] else 'inactive') + '\nMainPID='
                    + ('42' if active[0] else '0') + '\n').encode()
        if argv[1] == 'stop':
            active[0] = False
        if argv[1:3] == ['netns', 'delete']:
            namespace.unlink()
        return b''
    monkeypatch.setattr(validation, 'run', run)
    return root, state, unit, namespace, directory, claim, calls


def test_validation_lease_stops_exact_unit_and_retires_claimed_resources(leased):
    _root, state, unit, namespace, directory, _claim, calls = leased
    with Transaction(state, uid=os.getuid()) as tx:
        assert validation.recover_validation(tx)
        assert not validation.recover_validation(tx)
    assert any(argv[1] == 'stop' for argv in calls)
    assert not unit.exists() and not namespace.exists() and not directory.exists()
    assert not (state / 'validation.json').exists()


def test_public_validation_unit_refuses_even_when_its_exact_claim_matches(leased):
    _root, state, unit, _namespace, _directory, claim, calls = leased
    unit.chmod(0o644)
    claim['unit'] = {'name': unit.name, **node(unit, os.getuid())}
    original = unit.stat().st_ino
    with Transaction(state, uid=os.getuid()) as tx:
        tx.record('validation.json', claim)
        with pytest.raises(Refusal, match='validation-lease-invalid'):
            validation.recover_validation(tx)
    assert not calls
    assert unit.stat().st_ino == original and unit.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize('kind', ['unit-bytes', 'unit-inode', 'namespace-inode',
                                   'directory-inode', 'file-inode', 'extra-file', 'malformed-lease'])
def test_foreign_validation_authority_refuses_before_stop_or_deletion(leased, kind):
    root, state, unit, namespace, directory, _claim, calls = leased
    if kind == 'unit-bytes':
        unit.write_text('ExecStart=/foreign/runtime\n')
    elif kind in {'unit-inode', 'namespace-inode', 'file-inode'}:
        selected = unit if kind == 'unit-inode' else namespace if kind == 'namespace-inode' else directory / 'server.key'
        foreign = root / 'foreign'
        foreign.write_bytes(selected.read_bytes())
        foreign.chmod(selected.stat().st_mode & 0o777)
        os.replace(foreign, selected)
    elif kind == 'directory-inode':
        os.rename(directory, root / 'retained-original')
        directory.mkdir()
        directory.chmod(0o750)
    elif kind == 'extra-file':
        (directory / 'foreign').write_text('foreign')
    else:
        (state / 'validation.json').write_text('{"schema":1,"foreign":true}')
    before = (state / 'validation.json').read_bytes()
    identities = {str(path): identity(path.lstat()) for path in (unit, namespace, directory)}
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(Refusal):
            validation.recover_validation(tx)
    assert calls == []
    assert (state / 'validation.json').read_bytes() == before
    assert {str(path): identity(path.lstat()) for path in (unit, namespace, directory)} == identities


def test_interrupted_validation_cleanup_recognizes_recorded_absence(leased, monkeypatch):
    _root, state, unit, namespace, directory, _claim, _calls = leased
    original = validation.run
    def interrupted(argv, timeout):
        if argv[1:3] == ['netns', 'delete']:
            raise SystemExit(99)
        return original(argv, timeout)
    monkeypatch.setattr(validation, 'run', interrupted)
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(SystemExit):
            validation.recover_validation(tx)
    assert not unit.exists() and namespace.exists() and directory.exists()
    assert json.loads((state / 'validation.json').read_text())['phase'] == 'cleaning'
    monkeypatch.setattr(validation, 'run', original)
    with Transaction(state, uid=os.getuid()) as tx:
        assert validation.recover_validation(tx)
    assert not namespace.exists() and not directory.exists()


def test_loaded_foreign_fragment_is_never_stopped(leased, monkeypatch):
    _root, state, unit, namespace, directory, _claim, calls = leased
    original = validation.run
    def foreign(argv, timeout):
        result = original(argv, timeout)
        return result.replace(str(unit).encode(), b'/foreign/unit.service') if argv[1] == 'show' else result
    monkeypatch.setattr(validation, 'run', foreign)
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(Refusal, match='validation-foreign-unit'):
            validation.recover_validation(tx)
    assert not any(argv[1] == 'stop' for argv in calls)
    assert unit.exists() and namespace.exists() and directory.exists()


def test_foreground_parent_death_signal_and_start_race_are_explicit(monkeypatch):
    calls = []
    class Libc:
        def prctl(self, *args):
            calls.append(args)
            return 0
    monkeypatch.setattr(probe.ctypes, 'CDLL', lambda *_args, **_kwargs: Libc())
    monkeypatch.setattr(probe.os, 'getppid', lambda: 123)
    monkeypatch.setattr(probe.os, 'kill', lambda pid, sig: calls.append(('kill', pid, sig)))
    probe.parent_death(123)
    assert calls == [(1, signal.SIGKILL, 0, 0, 0)]
    probe.parent_death(122)
    assert calls[-1] == ('kill', os.getpid(), signal.SIGKILL)


def test_unknown_namespace_process_is_not_killed_or_deleted(leased, monkeypatch):
    _root, state, unit, namespace, directory, _claim, calls = leased
    original = validation.run
    def joined(argv, timeout):
        if argv[1:3] == ['netns', 'pids']:
            calls.append(argv)
            return b'99999\n'
        return original(argv, timeout)
    monkeypatch.setattr(validation, 'run', joined)
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises(Refusal, match='validation-namespace-not-empty'):
            validation.recover_validation(tx)
    assert unit.exists() and namespace.exists() and directory.exists()
    assert not any(argv[1:3] == ['netns', 'delete'] for argv in calls)
    assert json.loads((state / 'validation.json').read_text())['phase'] == 'prepared'


@pytest.mark.parametrize('foreign_manager', [False, True])
def test_proven_reboot_recovers_volatile_absence_without_adopting_new_unit(leased, monkeypatch, foreign_manager):
    _root, state, unit, namespace, directory, _claim, calls = leased
    unit.unlink()
    namespace.unlink()
    namespace.parent.rmdir()
    monkeypatch.setattr(validation, 'boot_id', lambda: '00000000-0000-0000-0000-000000000002')
    def manager(argv, _timeout):
        calls.append(argv)
        if argv[1] == 'show':
            return (b'LoadState=loaded\nFragmentPath=/foreign/new.service\nActiveState=active\nMainPID=43\n'
                    if foreign_manager else b'LoadState=not-found\nFragmentPath=\nActiveState=inactive\nMainPID=0\n')
        return b''
    monkeypatch.setattr(validation, 'run', manager)
    before = (state / 'validation.json').read_bytes()
    with Transaction(state, uid=os.getuid()) as tx:
        if foreign_manager:
            with pytest.raises(Refusal, match='validation-foreign-unit'):
                validation.recover_validation(tx)
            assert directory.exists() and (state / 'validation.json').read_bytes() == before
        else:
            assert validation.recover_validation(tx)
            assert not directory.exists() and not (state / 'validation.json').exists()
    assert all(argv[1] == 'show' for argv in calls)


def test_proven_reboot_preserves_dangling_volatile_root(leased, monkeypatch):
    root, state, unit, namespace, directory, _claim, calls = leased
    unit.unlink()
    namespace.unlink()
    namespace.parent.rmdir()
    namespace.parent.symlink_to(root/'foreign-missing-root', target_is_directory=True)
    monkeypatch.setattr(validation, 'boot_id', lambda: '00000000-0000-0000-0000-000000000002')
    before = (state/'validation.json').read_bytes()
    with Transaction(state, uid=os.getuid()) as tx:
        with pytest.raises((OSError, Refusal)):
            validation.recover_validation(tx)
    assert namespace.parent.is_symlink() and directory.exists()
    assert (state/'validation.json').read_bytes() == before
    assert calls == []
