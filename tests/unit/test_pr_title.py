"""PR subjects become release-please inputs after squash merging."""

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


def test_actual_event_title_is_checked_without_shell_interpolation(tmp_path):
    event = tmp_path / 'event.json'
    for title, expected in [('ci: update policy', 0), ('$(touch unexpected)', 1)]:
        event.write_text(json.dumps({'pull_request': {'title': title}}))
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                                env={**os.environ, 'GITHUB_EVENT_NAME': 'pull_request',
                                     'GITHUB_EVENT_PATH': str(event)}, capture_output=True, timeout=10)
        assert result.returncode == expected
    assert not (tmp_path / 'unexpected').exists()


def test_title_edits_trigger_read_only_ci_and_title_result_reaches_aggregate():
    ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
    assert 'edited' in ci[True]['pull_request']['types']
    assert 'pr-title' in ci['jobs']['required']['needs']
    assert ci['permissions'] == {'contents': 'read'}
    job = ci['jobs']['pr-title']
    assert 'if' not in job and 'continue-on-error' not in job
    assert job['steps'][-1]['run'] == 'python3 scripts/check-pr-title.py'
