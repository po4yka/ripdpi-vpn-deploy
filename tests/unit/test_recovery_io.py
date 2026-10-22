"""Real private journal publication and subprocess interruption; no live cloud IO."""
from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest
import recovery_io as io

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def manifest(tmp_path):
    tmp_path.chmod(0o700)
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    value = {'schema_version': 1, 'id': 'recovery-one', 'provider': 'upcloud', 'environment': 'replacement',
                 'source_revision': 'a' * 40, 'account': 'test-account', 'hostname': 'node-replacement', 'cohort': 'p0-minimal',
                 'inventory': [{'host': 'upcloud:prod', 'cohort': 'p0-minimal', 'handoff': None},
                            {'host': 'upcloud:publisher', 'cohort': 'p0-minimal', 'handoff': None},
                            {'host': 'upcloud:replacement', 'cohort': 'p0-minimal', 'handoff': None}]}
    for name in io.PATH_FIELDS:
        value[name] = str(state if name == 'state_directory' else tmp_path / name)
    path = tmp_path / 'manifest.json'
    path.write_bytes(io.canonical(value))
    path.chmod(0o600)
    return value, path


def test_positive_manifest_and_private_durable_challenge(manifest):
    value, path = manifest
    assert io.load_manifest(path) == value
    with io.Journal(value) as journal:
        with pytest.raises(io.ActionRequired) as challenge:
            journal.approve('apply', {'plan': 'a' * 64}, None)
        journal.approve('apply', {'plan': 'a' * 64}, challenge.value.digest)
        with journal.operation('apply', {'plan': 'a' * 64}):
            retained = io.document(journal.directory / 'journal.json')
            assert retained['intent']['name'] == 'apply'
        journal.observe('server', {'uuid': 'fixture-server'})
    with io.Journal(value) as resumed:
        assert resumed.state['intent'] is None
        assert resumed.state['observed']['server'] == {'uuid': 'fixture-server'}
        resumed.approve('apply', {'plan': 'a' * 64}, None)
        with pytest.raises(io.ActionRequired):
            resumed.approve('apply', {'plan': 'b' * 64}, None)
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in Path(value['state_directory']).iterdir())


@pytest.mark.parametrize('fault', ['provider', 'prod', 'same-host', 'mode', 'symlink', 'duplicate', 'relative'])
def test_manifest_refuses_unsupported_or_unsafe_inputs(manifest, fault):
    value, path = manifest
    if fault == 'provider':
        value['provider'] = 'vultr'
    elif fault == 'prod':
        value['environment'] = 'prod'
    elif fault == 'same-host':
        value['inventory'][2] = copy.deepcopy(value['inventory'][0])
    elif fault == 'relative':
        value['sops_file'] = 'relative'
    path.write_bytes(io.canonical(value))
    if fault == 'mode':
        path.chmod(0o644)
    elif fault == 'symlink':
        target = path.with_name('actual.json')
        path.rename(target)
        path.symlink_to(target)
    elif fault == 'duplicate':
        path.write_text(path.read_text().replace('"schema_version":1', '"schema_version":1,"schema_version":1'))
    with pytest.raises(io.RecoveryError):
        io.load_manifest(path)


def test_real_process_death_retains_pre_operation_intent(manifest):
    value, path = manifest
    program = '''import os, signal, sys
from recovery_io import Journal, load_manifest
with Journal(load_manifest(sys.argv[1])) as state:
    with state.operation("apply", {"plan": "fixture"}):
        os.kill(os.getpid(), signal.SIGKILL)
'''
    result = subprocess.run([sys.executable, '-c', program, str(path)], check=False,
                            env=os.environ | {'PYTHONPATH': str(ROOT / 'scripts')}, timeout=10)
    assert result.returncode < 0
    with io.Journal(value) as resumed:
        assert resumed.state['intent'] == {'name': 'apply', 'binding': {'plan': 'fixture'}, 'sequence': 1}
        with resumed.operation('observe-provider', {}):
            pass
    assert io.document(Path(value['state_directory']) / 'journal.json')['intent'] is None


def test_concurrent_invocation_and_changed_manifest_refuse(manifest):
    value, _ = manifest
    with io.Journal(value) as state:
        state.save()
        with pytest.raises(BlockingIOError), io.Journal(value):
            pytest.fail('second writer admitted')
    other = copy.deepcopy(value)
    other['hostname'] = 'different'
    with pytest.raises(io.RecoveryError, match='journal-mismatch'), io.Journal(other):
        pytest.fail('changed recovery admitted')


def test_journal_write_failure_preserves_prior_complete_record(manifest, monkeypatch):
    value, _ = manifest
    with io.Journal(value) as state:
        state.save()
        prior = (state.directory / 'journal.json').read_bytes()
        def failed_replace(*_args, **_kwargs):
            raise OSError('synthetic publication failure')
        monkeypatch.setattr(io.os, 'replace', failed_replace)
        with pytest.raises(OSError), state.operation('apply', {}):
            pytest.fail('operation started before durable intent')
        assert (state.directory / 'journal.json').read_bytes() == prior
        assert not list(state.directory.glob('.pending-*'))


def test_foreign_artifact_directory_is_not_adopted(manifest):
    value, _ = manifest
    foreign = Path(value['state_directory']) / 'review.json'
    foreign.write_text('unrelated')
    with pytest.raises(io.RecoveryError, match='not-empty'), io.Journal(value):
        pytest.fail('adopted unrelated artifacts')
    assert foreign.read_text() == 'unrelated'


def test_first_pending_review_survives_new_invocation(manifest):
    value, _ = manifest
    with pytest.raises(io.ActionRequired) as challenge, io.Journal(value) as state:
        state.approve('apply', {'exact': 'plan'}, None)
    with io.Journal(value) as resumed:
        resumed.approve('apply', {'exact': 'plan'}, challenge.value.digest)


@pytest.mark.parametrize('field', ['sops_file', 'handoff'])
@pytest.mark.parametrize('suffix', ['/../private', '/$(shell malicious)', '/two words', '/file,other'])
def test_command_paths_refuse_make_expansion_and_ambiguous_selectors(manifest, field, suffix):
    value, path = manifest
    if field == 'handoff':
        value['inventory'][0]['handoff'] = '/private' + suffix
    else:
        value[field] = '/private' + suffix
    path.write_bytes(io.canonical(value))
    with pytest.raises(io.RecoveryError):
        io.load_manifest(path)


def test_new_journal_refuses_writable_parent_before_creation(manifest):
    value, path = manifest
    path.parent.chmod(0o777)
    try:
        with pytest.raises(io.RecoveryError, match='unsafe-recovery-parent'), io.Journal(value):
            pytest.fail('unsafe parent admitted')
        assert not (Path(value['state_directory']) / 'journal.json').exists()
    finally:
        path.parent.chmod(0o700)
