"""Real-file forward recovery; service observations are portable adapter evidence."""
import os

import pytest
from test_transport_runtime_acceptance import apply, transaction
from test_transport_runtime_acceptance import area as base_area

AUTH = {'operation_id': '3fbb2baa-3a76-4f03-ae92-8ed9513fe268', 'intent_sha256': 'a' * 64}


@pytest.fixture
def area(private_authority_path):
    return base_area.__wrapped__(private_authority_path)


def revoke(area, version='B', *, authority=AUTH, **options):
    state, _, adapter, candidates = area
    with transaction.Transaction(state, uid=os.getuid(), check=options.get('check', False), revocation=authority) as tx:
        return tx.apply(candidates(version), adapter, **options)


@pytest.mark.parametrize('failure', ['validate', 'ready'])
def test_failed_revoke_never_restores_old_runtime_and_same_candidate_resumes(area, failure):
    state, live, adapter, _ = area
    apply(area, 'A')
    adapter.events.clear()
    adapter.reject = failure
    with pytest.raises((RuntimeError, transaction.Refusal)):
        revoke(area)
    assert not adapter.running
    assert 'restore' not in adapter.events
    adapter.reject = False
    result = revoke(area)
    assert result['status'] == 'accepted'
    assert adapter.running and (live / 'config').read_text() == 'B'
    assert not (state / 'pending.json').exists()
    assert not revoke(area)['changed']


@pytest.mark.parametrize('stage', ['prepared', 'intent', 'stopped', 'published-0', 'published-1', 'adopted', 'ready', 'committed'])
def test_revoke_interruption_fences_boot_and_only_same_intent_rolls_forward(area, stage):
    state, live, adapter, _ = area
    apply(area, 'A')
    adapter.events.clear()
    def interrupt(current):
        if current == stage:
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        revoke(area, checkpoint=interrupt)
    with pytest.raises(transaction.Refusal, match='unfinished-runtime-without-publisher'):
        transaction.admission(state, uid=os.getuid())
    observed = list(adapter.events)
    with pytest.raises(transaction.Refusal, match='revocation-resume-required'):
        apply(area, 'A')
    assert observed == adapter.events
    with pytest.raises(transaction.Refusal, match='revocation-candidate-changed'):
        revoke(area, 'C')
    assert observed == adapter.events
    assert revoke(area)['status'] == 'accepted'
    assert (live / 'config').read_text() == 'B'
    assert 'restore' not in adapter.events
    transaction.admission(state, uid=os.getuid())


def test_revoke_commit_lost_ack_cannot_be_compensated_to_old_credentials(area):
    state, live, adapter, _ = area
    apply(area, 'A')
    revoke(area)
    adapter.events.clear()
    with transaction.Transaction(state, uid=os.getuid()) as tx, pytest.raises(transaction.Refusal, match='revocation-rollback-forbidden'):
        tx.compensate_latest(adapter)
    assert not adapter.events
    assert (live / 'config').read_text() == 'B'
    # A later ordinary candidate may compensate to the revoked baseline.
    apply(area, 'C')
    with transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.compensate_latest(adapter)
    assert (live / 'config').read_text() == 'B'


def test_revoke_check_does_not_stop_or_create_authority(area):
    state, live, adapter, _ = area
    apply(area, 'A')
    adapter.events.clear()
    assert revoke(area, check=True)['status'] == 'predicted'
    with transaction.Transaction(state, uid=os.getuid(), revocation=AUTH) as tx:
        assert tx.apply(area[3]('B'), adapter, check=True)['status'] == 'predicted'
    assert not adapter.events
    assert not (state / 'revocation.json').exists()
    assert (live / 'config').read_text() == 'A'


@pytest.mark.parametrize('stage', ['intent', 'published-0', 'adopted', 'committed'])
def test_real_publisher_sigkill_keeps_revocation_resume_authority(area, stage):
    import json
    import signal
    import subprocess
    import sys
    from pathlib import Path

    import test_transport_runtime_acceptance as base
    state, live, adapter, candidates = area
    apply(area, 'A')
    code = '''import json,os,runpy,signal,sys
m=runpy.run_path(sys.argv[1]); request=json.loads(sys.argv[2])
a=m['Adapter'](); a.running=True
with m['transaction'].Transaction(request['state'],uid=os.getuid(),revocation=request['authority']) as tx:
 def checkpoint(stage):
  if stage == request['stage']: os.kill(os.getpid(),signal.SIGKILL)
 tx.apply(request['candidates'],a,checkpoint=checkpoint)
'''
    result = subprocess.run([sys.executable, '-c', code, str(Path(base.__file__)), json.dumps({
        'state': str(state), 'authority': AUTH, 'stage': stage, 'candidates': candidates('B')})], capture_output=True, timeout=20, check=False)
    assert result.returncode == -signal.SIGKILL, result.stderr.decode()
    with pytest.raises(transaction.Refusal, match='unfinished-runtime-without-publisher'):
        transaction.admission(state, uid=os.getuid())
    adapter.events.clear()
    assert revoke(area)['status'] == 'accepted'
    assert 'restore' not in adapter.events
    assert (live / 'config').read_text() == 'B'


def test_recovered_retirement_retains_omitted_absence_candidates(area):
    state, live, adapter, candidates = area
    apply(area, 'A')
    retired = candidates('B') + [{'path': str(live / 'obsolete'), 'absent': True}]
    with transaction.Transaction(state, uid=os.getuid(), revocation=AUTH) as tx:
        tx.apply(retired, adapter)
    # A role retry cannot rediscover the name from its retired membership file.
    with transaction.Transaction(state, uid=os.getuid(), revocation=AUTH) as tx:
        assert not tx.apply(candidates('B'), adapter)['changed']


def test_outer_route_failure_after_consumer_commit_never_restores_revoked_generation(area, monkeypatch):
    import importlib.util
    import io
    import json
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    state, live, adapter, _ = area
    apply(area, 'A')
    library = Path(__file__).resolve().parents[2] / 'ansible/roles/runtime-release/files'
    monkeypatch.syspath_prepend(str(library))
    spec = importlib.util.spec_from_file_location('revocation_outer_test', library / 'transport_runtime_outer.py')
    outer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(outer)
    monkeypatch.setattr(outer, 'STATE', state)
    monkeypatch.setattr(outer, 'Transaction', lambda root, **kwargs: transaction.Transaction(root, uid=os.getuid(), **kwargs))
    monkeypatch.setattr(outer, 'adapter', lambda: adapter)
    monkeypatch.setattr(outer, 'read_private', lambda path, _uid: transaction.read_private(path, os.getuid()))
    monkeypatch.setattr(outer, 'recover_validation', lambda _tx: None)
    monkeypatch.setattr(outer, 'inspect_lease', lambda _tx: None)
    monkeypatch.setattr(outer.os, 'geteuid', lambda: 0)
    def invoke(action, authority=AUTH):
        monkeypatch.setattr(sys, 'argv', ['outer', action, '--revocation-stdin'])
        monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(json.dumps(authority).encode())))
        outer.main()
    invoke('begin')
    revoke(area)
    adapter.stop()  # Canonical outer rescue quiesces before asking to restore.
    adapter.events.clear()
    with pytest.raises(RuntimeError, match='revocation-rollback-forbidden'):
        invoke('restore')
    assert not adapter.running and (live / 'config').read_text() == 'B'
    assert (state / 'outer.json').exists() and 'restore' not in adapter.events
    with pytest.raises(RuntimeError, match='revocation-resume-required'):
        invoke('finish', None)
    assert revoke(area)['status'] == 'accepted'
    invoke('finish')
    invoke('finish')  # Lost finish acknowledgement is an unchanged retry.
    assert not (state / 'outer.json').exists()
    assert adapter.running and 'restore' not in adapter.events
