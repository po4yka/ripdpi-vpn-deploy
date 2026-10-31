"""Repository policy preserves branch integrity and the owner-only CI exception."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('repository_policy', ROOT / 'scripts/configure-repository.py')
policy_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy_tool)
POLICY = json.loads((ROOT / '.github/repository-policy.json').read_text())
BASE = 'repos/po4yka/ripdpi-vpn-deploy'


@pytest.fixture
def github(monkeypatch):
    metadata = {'full_name': POLICY['repository'], 'owner': {'id': 42894392, 'type': 'User'},
                'permissions': {'admin': True}, **POLICY['settings']}
    metadata['allow_merge_commit'] = True
    rules = {7: {'id': 7, 'name': 'main', 'target': 'branch', 'enforcement': 'active',
                 'source_type': 'Repository', 'conditions': {}, 'rules': [], 'bypass_actors': []},
             8: {'id': 8, 'name': 'unrelated', 'source_type': 'Repository'}}
    state = {'metadata': metadata, 'rules': rules, 'immutable': {'enabled': False},
             'classic': None, 'writes': []}

    def api(endpoint, method='GET', payload=None, allow_missing=False):
        if method != 'GET':
            state['writes'].append((method, endpoint, deepcopy(payload)))
        if endpoint == BASE:
            if method == 'PATCH':
                metadata.update(payload)
            return deepcopy(metadata)
        if endpoint.endswith('/branches/main/protection'):
            assert allow_missing
            return state['classic']
        if endpoint.endswith('/immutable-releases'):
            if method == 'PUT':
                state['immutable']['enabled'] = True
            return deepcopy(state['immutable'])
        if endpoint.endswith('/rulesets?per_page=100'):
            return deepcopy(list(rules.values()))
        if endpoint.endswith('/rulesets') and method == 'POST':
            identity = max(rules, default=0) + 1
            rules[identity] = {'id': identity, 'source_type': 'Repository', **deepcopy(payload)}
            return deepcopy(rules[identity])
        identity = int(endpoint.rsplit('/', 1)[1])
        if method == 'PUT':
            rules[identity] = {'id': identity, 'source_type': 'Repository', **deepcopy(payload)}
        return deepcopy(rules[identity])

    monkeypatch.setattr(policy_tool, 'api', api)
    return state


def test_policy_has_separate_integrity_ci_and_tag_rules():
    integrity, ci, tags = POLICY['rulesets']
    assert integrity['name'] == 'main-integrity'
    assert integrity['bypass_actors'] == []
    assert {r['type'] for r in integrity['rules']} == {
        'deletion', 'non_fast_forward', 'required_linear_history', 'pull_request'}
    pr = integrity['rules'][-1]['parameters']
    assert pr['required_approving_review_count'] == 0
    assert pr['require_code_owner_review'] is False
    assert pr['require_last_push_approval'] is False
    assert pr['required_review_thread_resolution'] is True
    assert pr['allowed_merge_methods'] == ['rebase']
    assert ci['name'] == 'main-ci'
    assert ci['bypass_actors'] == [{'actor_id': 42894392, 'actor_type': 'User', 'bypass_mode': 'pull_request'}]
    assert [r['type'] for r in ci['rules']] == ['required_status_checks']
    checks = ci['rules'][0]['parameters']
    assert checks['strict_required_status_checks_policy'] is True
    assert checks['required_status_checks'] == [
        {'context': c, 'integration_id': 15368}
        for c in ('required checks', 'codeql (python)', 'codeql (actions)')]
    assert tags['target'] == 'tag' and tags['bypass_actors'] == []
    assert tags['conditions']['ref_name'] == {'include': ['refs/tags/vpnd-v*'], 'exclude': []}
    assert {r['type'] for r in tags['rules']} == {'update', 'deletion'}
    for item in (integrity, ci):
        assert item['conditions']['ref_name'] == {'include': ['refs/heads/main'], 'exclude': []}
    assert all(item['enforcement'] == 'active' for item in POLICY['rulesets'])
    assert POLICY['settings'] == {
        'allow_merge_commit': False, 'allow_squash_merge': False, 'allow_rebase_merge': True,
        'delete_branch_on_merge': True, 'allow_auto_merge': True}
    assert POLICY['immutable_releases'] is True
    assert not (ROOT / '.github/workflows/branch-protection.yml').exists()


def test_preview_makes_no_writes_and_orders_integrity_before_ci_migration(github):
    changes = policy_tool.plan(POLICY)
    assert github['writes'] == []
    assert [(method, payload['name']) for method, _, payload in changes[:3]] == [
        ('POST', 'main-integrity'), ('PUT', 'main-ci'), ('POST', 'release-tags')]
    assert changes[1][1] == BASE + '/rulesets/7'
    assert changes[-1] == ('PUT', BASE + '/immutable-releases', None)


def test_apply_preserves_unrelated_rules_and_becomes_idempotent(github, monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['configure-repository.py', '--apply'])
    assert policy_tool.main() == 0
    assert github['rules'][8] == {'id': 8, 'name': 'unrelated', 'source_type': 'Repository'}
    assert github['rules'][7]['name'] == 'main-ci'
    assert 'verified' in capsys.readouterr().out
    assert policy_tool.plan(POLICY) == []
    writes = deepcopy(github['writes'])
    assert policy_tool.main() == 0
    assert github['writes'] == writes


@pytest.mark.parametrize('failure', ['foreign', 'owner', 'admin', 'classic', 'duplicate', 'inherited'])
def test_unsafe_or_ambiguous_remote_state_refuses_before_writes(github, failure):
    policy = deepcopy(POLICY)
    if failure == 'foreign':
        policy['repository'] = 'other/project'
    elif failure == 'owner':
        github['metadata']['owner']['id'] = 999
    elif failure == 'admin':
        github['metadata']['permissions']['admin'] = False
    elif failure == 'classic':
        github['classic'] = {'enabled': True}
    elif failure == 'duplicate':
        github['rules'][9] = {**github['rules'][7], 'id': 9, 'name': 'main-ci'}
    else:
        github['rules'][7]['source_type'] = 'Organization'
    with pytest.raises(ValueError):
        policy_tool.plan(policy)
    assert github['writes'] == []


def test_partial_api_failure_stops_apply_and_retry_reads_remaining_state(github, monkeypatch):
    api = policy_tool.api

    def failing(endpoint, method='GET', payload=None, **kwargs):
        if method == 'PUT' and endpoint.endswith('/rulesets/7'):
            raise RuntimeError('API unavailable')
        return api(endpoint, method, payload, **kwargs)

    monkeypatch.setattr(policy_tool, 'api', failing)
    monkeypatch.setattr('sys.argv', ['configure-repository.py', '--apply'])
    assert policy_tool.main() == 1
    assert len(github['writes']) == 1
    assert github['writes'][0][2]['name'] == 'main-integrity'
    assert not github['immutable']['enabled']
    monkeypatch.setattr(policy_tool, 'api', api)
    remaining = policy_tool.plan(POLICY)
    assert remaining[0][2]['name'] == 'main-ci'
    assert policy_tool.main() == 0


def test_failed_readback_is_not_reported_as_success(github, monkeypatch, capsys):
    api = policy_tool.api

    def stale(endpoint, method='GET', payload=None, **kwargs):
        if method == 'PUT' and endpoint.endswith('/immutable-releases'):
            return None
        return api(endpoint, method, payload, **kwargs)

    monkeypatch.setattr(policy_tool, 'api', stale)
    monkeypatch.setattr('sys.argv', ['configure-repository.py', '--apply'])
    assert policy_tool.main() == 1
    captured = capsys.readouterr()
    assert 'readback differs' in captured.err
    assert 'policy verified' not in captured.out


def test_api_treats_only_404_as_absent_and_does_not_print_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, '', 'private diagnostic (HTTP 403)')
    monkeypatch.setattr(policy_tool.subprocess, 'run', forbidden)
    with pytest.raises(RuntimeError, match='GitHub API failed') as error:
        policy_tool.api(BASE, allow_missing=True)
    assert 'private diagnostic' not in str(error.value)
    monkeypatch.setattr(policy_tool.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a, 1, '', 'gh: Not Found (HTTP 404)'))
    assert policy_tool.api(BASE, allow_missing=True) is None



@pytest.mark.parametrize('goal,command', [
    ('repository-policy-plan', 'python3 scripts/configure-repository.py'),
    ('repository-policy-apply', 'python3 scripts/configure-repository.py --apply'),
])
def test_make_policy_commands_do_not_load_fleet_configuration(tmp_path, goal, command):
    (tmp_path / '.fleet.mk').write_text('$(error fleet must not be read)\n')
    result = subprocess.run(['make', '-f', str(ROOT / 'Makefile'), '-n', goal],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == command
