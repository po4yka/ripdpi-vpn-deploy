"""Real-file forward recovery; service observations are portable adapter evidence."""
import os

import pytest
import test_transport_runtime_acceptance as base

AUTH = {'operation_id': '3fbb2baa-3a76-4f03-ae92-8ed9513fe268', 'intent_sha256': 'a' * 64}


@pytest.fixture
def area(private_authority_path):
    return base.area.__wrapped__(private_authority_path)


def revoke(area, version='B', *, authority=AUTH, **options):
    state, _, adapter, candidates = area
    with base.transaction.Transaction(state, uid=os.getuid(), check=options.get('check', False), revocation=authority) as tx:
        return tx.apply(candidates(version), adapter, **options)


@pytest.mark.parametrize('failure', ['validate', 'ready'])
def test_failed_revoke_never_restores_old_runtime_and_same_candidate_resumes(area, failure):
    state, live, adapter, _ = area
    base.apply(area, 'A')
    adapter.events.clear()
    adapter.reject = failure
    with pytest.raises((RuntimeError, base.transaction.Refusal)):
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
    base.apply(area, 'A')
    adapter.events.clear()
    def interrupt(current):
        if current == stage:
            raise SystemExit(99)
    with pytest.raises(SystemExit):
        revoke(area, checkpoint=interrupt)
    with pytest.raises(base.transaction.Refusal, match='unfinished-runtime-without-publisher'):
        base.transaction.admission(state, uid=os.getuid())
    observed = list(adapter.events)
    with pytest.raises(base.transaction.Refusal, match='revocation-resume-required'):
        base.apply(area, 'A')
    assert observed == adapter.events
    with pytest.raises(base.transaction.Refusal, match='revocation-candidate-changed'):
        revoke(area, 'C')
    assert observed == adapter.events
    assert revoke(area)['status'] == 'accepted'
    assert (live / 'config').read_text() == 'B'
    assert 'restore' not in adapter.events
    base.transaction.admission(state, uid=os.getuid())


def test_revoke_commit_lost_ack_cannot_be_compensated_to_old_credentials(area):
    state, live, adapter, _ = area
    base.apply(area, 'A')
    revoke(area)
    adapter.events.clear()
    with base.transaction.Transaction(state, uid=os.getuid()) as tx, pytest.raises(base.transaction.Refusal, match='revocation-rollback-forbidden'):
        tx.compensate_latest(adapter)
    assert not adapter.events
    assert (live / 'config').read_text() == 'B'
    # A later ordinary candidate may compensate to the revoked baseline.
    base.apply(area, 'C')
    with base.transaction.Transaction(state, uid=os.getuid()) as tx:
        tx.compensate_latest(adapter)
    assert (live / 'config').read_text() == 'B'


def test_revoke_check_does_not_stop_or_create_authority(area):
    state, live, adapter, _ = area
    base.apply(area, 'A')
    adapter.events.clear()
    assert revoke(area, check=True)['status'] == 'predicted'
    with base.transaction.Transaction(state, uid=os.getuid(), revocation=AUTH) as tx:
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

    state, live, adapter, candidates = area
    base.apply(area, 'A')
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
    with pytest.raises(base.transaction.Refusal, match='unfinished-runtime-without-publisher'):
        base.transaction.admission(state, uid=os.getuid())
    adapter.events.clear()
    assert revoke(area)['status'] == 'accepted'
    assert 'restore' not in adapter.events
    assert (live / 'config').read_text() == 'B'


def test_recovered_retirement_retains_omitted_absence_candidates(area):
    state, live, adapter, candidates = area
    base.apply(area, 'A')
    retired = candidates('B') + [{'path': str(live / 'obsolete'), 'absent': True}]
    with base.transaction.Transaction(state, uid=os.getuid(), revocation=AUTH) as tx:
        tx.apply(retired, adapter)
    # A role retry cannot rediscover the name from its retired membership file.
    with base.transaction.Transaction(state, uid=os.getuid(), revocation=AUTH) as tx:
        assert not tx.apply(candidates('B'), adapter)['changed']


def test_outer_route_failure_after_consumer_commit_never_restores_revoked_generation(area, monkeypatch):
    import importlib.util
    import io
    import json
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    state, live, adapter, _ = area
    base.apply(area, 'A')
    library = Path(__file__).resolve().parents[2] / 'ansible/roles/runtime-release/files'
    monkeypatch.syspath_prepend(str(library))
    spec = importlib.util.spec_from_file_location('revocation_outer_test', library / 'transport_runtime_outer.py')
    outer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(outer)
    monkeypatch.setattr(outer, 'STATE', state)
    monkeypatch.setattr(outer, 'Transaction', lambda root, **kwargs: base.transaction.Transaction(root, uid=os.getuid(), **kwargs))
    monkeypatch.setattr(outer, 'adapter', lambda: adapter)
    monkeypatch.setattr(outer, 'read_private', lambda path, _uid: base.transaction.read_private(path, os.getuid()))
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
    with pytest.raises(RuntimeError, match='revocation-resume-required'):
        invoke('finish', {**AUTH, 'intent_sha256': 'b' * 64})
    assert revoke(area)['status'] == 'accepted'
    invoke('finish')
    invoke('finish')  # Lost finish acknowledgement is an unchanged retry.
    assert not (state / 'outer.json').exists()
    assert adapter.running and 'restore' not in adapter.events


def test_production_full_retirement_closes_exact_outer_authority(area):
    """Real Ansible orchestration and transaction files; daemon adapters are portable."""
    import copy
    import json
    from pathlib import Path
    import subprocess
    import sys
    import yaml

    state, live, adapter, candidates = area
    base.apply(area, 'A')
    retired = [{'path': item['path'], 'absent': True} for item in candidates('A')]
    with base.transaction.Transaction(state, uid=os.getuid(), revocation=AUTH) as tx:
        tx.arm_revocation()
        tx.record('outer.json', {'schema': 1, 'receipt': tx.accepted(), 'consumer_receipt': None, 'revocation': AUTH})
    root = state.parent
    source = Path(__file__).resolve().parents[2]
    driver = root / 'outer-driver.py'
    driver.write_text('''import json,os,runpy,sys
from pathlib import Path
from types import SimpleNamespace
base=runpy.run_path(sys.argv[1]); tx=base['transaction']; state=Path(sys.argv[2]); action=sys.argv[3]
request=json.loads(Path(sys.argv[4]).read_text()); adapter=base['Adapter']()
if action=='accept':
 with tx.Transaction(state,uid=os.getuid(),revocation=request['authority']) as current:
  current.apply(request['retired'],adapter)
elif action=='retire':
 assert all(not Path(item['path']).exists() for item in request['retired'])
else:
 sys.path.insert(0,sys.argv[5]); import transport_runtime_outer as outer
 outer.STATE=state; outer.Transaction=lambda root,**kwargs:tx.Transaction(root,uid=os.getuid(),**kwargs)
 outer.read_private=lambda path,_uid:tx.read_private(path,os.getuid())
 outer.adapter=lambda:adapter; outer.recover_validation=lambda _tx:None; outer.inspect_lease=lambda _tx:None
 outer.os=SimpleNamespace(geteuid=lambda:0)
 sys.argv=['outer',*sys.argv[6:]]; outer.main()
''')
    request = root / 'request.json'
    request.write_text(json.dumps({'authority': AUTH, 'retired': retired}))
    def argv(action):
        return [sys.executable, str(driver), str(Path(base.__file__)), str(state), action, str(request),
                str(source / 'ansible/roles/runtime-release/files')]
    tasks = copy.deepcopy(yaml.safe_load((source / 'ansible/playbooks/tasks/transport-egress-activate.yml').read_text()))
    for task in tasks[0]['block']:
        role = task.get('ansible.builtin.include_role')
        if role and role['tasks_from'] in ('runtime-acceptance', 'retire'):
            del task['ansible.builtin.include_role']
            task['ansible.builtin.command'] = {'argv': argv('accept' if role['tasks_from'] == 'runtime-acceptance' else 'retire')}
    finish = yaml.safe_load((source / 'ansible/playbooks/tasks/transport-egress-finish.yml').read_text())
    finish[0]['ansible.builtin.command']['argv'] = argv('finish') + finish[0]['ansible.builtin.command']['argv'][3:]
    (root / 'transport-egress-finish.yml').write_text(yaml.safe_dump(finish))
    play = root / 'retirement.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'become': False, 'vars': {'ansible_python_interpreter': sys.executable,
            'transport_egress_role_enabled': False, 'transport_runtime_candidates': retired,
            '_transport_egress_full_retirement': True, 'vpn_device_revocation': AUTH}, 'tasks': tasks}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)],
        capture_output=True, text=True, timeout=60, env={**os.environ, 'ANSIBLE_BECOME': 'false'})
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (state / 'outer.json').exists()
    assert all(not Path(item['path']).exists() for item in retired)
    with base.transaction.Transaction(state, uid=os.getuid()) as tx:
        assert tx.apply(retired, adapter)['status'] == 'accepted'
