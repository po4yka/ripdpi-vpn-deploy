"""The CLAUDE.md coverage workflow must not parse a PR base ref as shell code."""

from pathlib import Path
import os
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/claude-md-touch.yml"


def test_base_ref_is_validated_and_used_only_as_data():
    source = WORKFLOW.read_text()

    assert "BASE_REF: ${{ github.base_ref }}" in source
    assert 'git check-ref-format --branch "$BASE_REF"' in source
    assert '"refs/heads/${BASE_REF}:refs/remotes/origin/${BASE_REF}"' in source
    assert 'git diff --name-only "origin/${BASE_REF}"...HEAD' in source
    assert 'git fetch origin "${{ github.base_ref }}"' not in source
    assert '"origin/${{ github.base_ref }}"...HEAD' not in source


def test_changed_file_collection_retains_merge_base_when_main_advances(tmp_path):
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT='0', BASE_REF='main')
    def git(*arguments, cwd=tmp_path):
        return subprocess.run(['git', *arguments], cwd=cwd, env=environment,
                              capture_output=True, text=True, check=True).stdout.strip()
    remote, source, runner = (tmp_path / name for name in ('remote.git', 'source', 'runner'))
    git('init', '--bare', '--initial-branch=main', str(remote))
    git('clone', remote.as_uri(), str(source))
    git('config', 'user.name', 'Fixture', cwd=source)
    git('config', 'user.email', 'fixture@example.invalid', cwd=source)
    def commit(filename):
        (source / filename).write_text(filename)
        git('add', filename, cwd=source)
        git('commit', '-m', 'test: add ' + filename, cwd=source)
    commit('baseline.txt')
    git('checkout', '-b', 'feature', cwd=source)
    commit('feature.txt')
    git('checkout', '-b', 'pr-merge', 'main', cwd=source)
    git('merge', '--no-ff', 'feature', '-m', 'test: synthetic PR merge', cwd=source)
    git('push', 'origin', 'main', 'feature', 'pr-merge', cwd=source)
    git('clone', remote.as_uri(), str(runner))
    git('checkout', 'pr-merge', cwd=runner)
    git('checkout', 'main', cwd=source)
    commit('advanced.txt')
    git('push', 'origin', 'main', cwd=source)
    steps = yaml.safe_load(WORKFLOW.read_text())['jobs']['check']['steps']
    script = next(step['run'] for step in steps if step.get('name') == 'Collect changed files')
    assert script.count('/tmp/changed_files.txt') == 2
    script = script.replace('/tmp/changed_files.txt', '"$CHANGED_FILE_FIXTURE"')
    changed = tmp_path / 'changed.txt'
    result = subprocess.run(['bash', '-euo', 'pipefail', '-c', script], cwd=runner,
        env={**environment, 'CHANGED_FILE_FIXTURE': str(changed)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert changed.read_text().splitlines() == ['feature.txt']
