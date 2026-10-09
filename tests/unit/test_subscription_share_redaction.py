"""Production share tasks hide bearer paths under verbose Ansible callbacks."""
import json
import os
import pwd
import grp
import subprocess
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_real_verbose_ansible_share_upload_censors_bearer(tmp_path):
    token = uuid.uuid4().hex
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    (bundle / 'index.html').write_text(f'<a href="/sub/{token}">synthetic</a>')
    tasks = yaml.safe_load((ROOT / 'ansible/roles/subscription-host/tasks/share-bundles.yml').read_text())
    for task in tasks:
        action = task.get('ansible.builtin.file', task.get('ansible.builtin.copy'))
        field = 'path' if 'path' in action else 'dest'
        action[field] = action[field].replace('/var/www/subscription-host', str(tmp_path / 'public'))
        action['owner'] = pwd.getpwuid(os.getuid()).pw_name
        action['group'] = grp.getgrgid(os.getgid()).gr_name
        if 'loop' in task:
            assert task['no_log'] is True and task['diff'] is False
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
             'vars': {'ansible_become': False, 'ansible_python_interpreter': __import__('sys').executable, 'vpn': {'share_bundles': [{'token': token, 'client': 'synthetic', 'local_path': str(bundle)}]}},
             'tasks': tasks, 'handlers': [{'name': 'Reload nginx', 'ansible.builtin.debug': {'msg': 'synthetic handler'}}]}]
    playbook = tmp_path / 'play.json'
    playbook.write_text(json.dumps(play))
    env = {**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg'), 'ANSIBLE_DEBUG': 'false', 'ANSIBLE_DISPLAY_ARGS_TO_STDOUT': 'true', 'ANSIBLE_NOCOLOR': '1'}
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-vvv', '--diff', str(playbook)], env=env, cwd=tmp_path, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert token not in result.stdout + result.stderr
    assert (tmp_path / 'public/share' / token / 'index.html').read_bytes() == (bundle / 'index.html').read_bytes()
