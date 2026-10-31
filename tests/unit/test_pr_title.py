"""PR titles and every PR commit subject become release-please inputs after rebase merging."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/check-pr-title.py'
spec = importlib.util.spec_from_file_location('pr_title', SCRIPT)
titles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(titles)


@pytest.mark.parametrize('title,expected', [
    ('ci: improve repository policy', True), ('fix(vpnd)!: reject invalid input', True),
    ('chore(deps): bump the routine group with 4 updates', True),
    ('chore(main): release vpn-deploy 2.0.1', True),
    ('Update repository', False), ('fix: ', False), ('fix: invalid\nsubject', False),
    ('fix: trailing period.', False), ('fix: disallow CoDeX metadata', False),
    (' fix: extra space', False),
])
def test_conventional_subjects(title, expected):
    assert titles.valid(title) is expected


def _git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                          text=True, env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@x',
                                          'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x'}).stdout.strip()


def _commit(repo, message, name='file'):
    (repo / name).write_text(message)
    _git(repo, 'add', name)
    _git(repo, 'commit', '-q', '-m', message)
    return _git(repo, 'rev-parse', 'HEAD')


def _check(repo, title, base, head):
    event = repo / 'event.json'
    event.write_text(json.dumps({'pull_request': {'title': title, 'base': {'sha': base}, 'head': {'sha': head}}}))
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=repo,
                          env={**os.environ, 'GITHUB_EVENT_NAME': 'pull_request',
                               'GITHUB_EVENT_PATH': str(event)}, capture_output=True, text=True, timeout=10)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, 'init', '-q')
    base = _commit(tmp_path, 'chore: base')
    return tmp_path, base


def test_valid_title_and_commit_range_pass(repo):
    root, base = repo
    head = _commit(root, 'fix(vpnd): reject invalid input\n\nBody text.')
    head = _commit(root, 'docs: explain the flag')
    result = _check(root, 'fix(vpnd): reject invalid input', base, head)
    assert result.returncode == 0, result.stderr


def test_merge_commits_in_the_range_are_ignored(repo):
    root, base = repo
    _git(root, 'checkout', '-q', '-b', 'topic')
    _commit(root, 'feat: topic work', name='topic-file')
    _git(root, 'checkout', '-q', '-')
    _commit(root, 'fix: main work')
    _git(root, 'merge', '-q', '--no-ff', '-m', "Merge branch 'topic'", 'topic')
    head = _git(root, 'rev-parse', 'HEAD')
    result = _check(root, 'feat: topic work', base, head)
    assert result.returncode == 0, result.stderr


def test_actual_event_title_is_checked_without_shell_interpolation(repo):
    root, base = repo
    head = _commit(root, 'ci: update policy')
    for title, expected in [('ci: update policy', 0), ('$(touch unexpected)', 1)]:
        assert _check(root, title, base, head).returncode == expected
    assert not (root / 'unexpected').exists()


@pytest.mark.parametrize('message,fragment', [
    ('wip', 'not a Conventional Commit'),
    ('fix: trailing period.', 'not a Conventional Commit'),
    ('fix: ok subject\n\nCo-authored-by: Someone <x@y>', 'Co-authored-by'),
    ('fix: ok subject\n\nco-authored-by: lower case <x@y>', 'Co-authored-by'),
])
def test_offending_commit_in_range_fails_and_is_named(repo, message, fragment):
    root, base = repo
    _commit(root, 'feat: first')
    offender = _commit(root, message)
    head = _commit(root, 'test: last')
    result = _check(root, 'feat: first', base, head)
    assert result.returncode == 1
    assert offender[:12] in result.stderr and fragment in result.stderr


def test_title_edits_trigger_read_only_ci_and_title_result_reaches_aggregate():
    ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
    assert 'edited' in ci[True]['pull_request']['types']
    assert 'pr-title' in ci['jobs']['required']['needs']
    assert ci['permissions'] == {'contents': 'read'}
    job = ci['jobs']['pr-title']
    assert 'if' not in job and 'continue-on-error' not in job
    assert job['steps'][0]['with']['fetch-depth'] == 0  # the commit range needs both PR parents
    assert job['steps'][-1]['run'] == 'python3 scripts/check-pr-title.py'
