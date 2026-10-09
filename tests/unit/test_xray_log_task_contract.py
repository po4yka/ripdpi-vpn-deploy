"""Execute the production log task's argv/stdin and retain causal helper errors."""
from __future__ import annotations

import grp
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/xray'


@pytest.mark.parametrize('check', [False, True])
def test_actual_ansible_log_task_passes_only_valid_flags_and_keeps_helper_error(tmp_path, check):
    task = next(task for task in yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
                if task['name'] == 'Provision xray log directory and files without following links')
    captured = tmp_path / 'failed-result.json'
    # '/' is deliberately refused before mutation by the real helper. This
    # exercises argument parsing and the command error path without requiring
    # root or weakening its ancestor-ownership checks on the local test host.
    variables = {'role_path': str(ROLE), 'xray_log_path': '/',
                 'xray_runtime_user': pwd.getpwuid(os.getuid()).pw_name,
                 'xray_runtime_group': grp.getgrgid(os.getgid()).gr_name,
                 'ansible_python_interpreter': sys.executable, 'ansible_become': False}
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
             'become': False, 'vars': variables, 'tasks': [
                 {'name': 'Observe the real task failure', 'block': [task],
                  'rescue': [{'name': 'Capture the original command result',
                              'ansible.builtin.copy': {'dest': str(captured),
                                                      'content': '{{ ansible_failed_result | to_json }}'},
                              'check_mode': False}]}]}]
    playbook = tmp_path / 'play.json'
    playbook.write_text(json.dumps(play))
    env = {**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg'),
           'ANSIBLE_DEBUG': 'false', 'ANSIBLE_NOCOLOR': '1'}
    command = ['ansible-playbook', '-i', 'localhost,', str(playbook)]
    if check:
        command.append('--check')
    result = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    original = json.loads(captured.read_text())
    expected = ['python3', '-', '--directory', '/', '--user', variables['xray_runtime_user'],
                '--group', variables['xray_runtime_group']]
    assert original['cmd'] == expected + (['--check'] if check else [])
    assert original['rc'] == 1
    assert original['stderr'] == 'Xray log provisioning refused unsafe or unavailable state'
    assert original['msg'] == 'The command exited with a non-zero return code.'
    assert original['changed'] is False
    assert 'from_json' not in result.stdout + result.stderr
    assert 'unrecognized arguments' not in result.stdout + result.stderr
    assert not original['stdout']
