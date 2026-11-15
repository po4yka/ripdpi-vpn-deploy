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


import hashlib

TASKS = ROOT / 'ansible/roles/subscription-host/tasks'


def run_share_tasks(tmp_path, name, variables):
    """Run one production task file through ansible-playbook against a temporary public root."""
    tasks = yaml.safe_load((TASKS / name).read_text())
    selected = []
    for task in tasks:
        action = next((task[key] for key in ('ansible.builtin.file', 'ansible.builtin.copy', 'ansible.builtin.find')
                       if key in task), None)
        if action is None or 'revoked_file' in json.dumps(action):
            continue   # the deny-list file itself belongs to another test
        field = next(key for key in ('path', 'dest', 'paths') if key in action)
        action[field] = action[field].replace('/var/www/subscription-host', str(tmp_path / 'public'))
        if 'owner' in action:
            action['owner'] = pwd.getpwuid(os.getuid()).pw_name
            action['group'] = grp.getgrgid(os.getgid()).gr_name
        if 'loop' in task:
            assert task['no_log'] is True and task['diff'] is False
        selected.append(task)
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
             'vars': {'ansible_become': False, 'ansible_python_interpreter': __import__('sys').executable, **variables},
             'tasks': selected, 'handlers': [{'name': 'Reload nginx', 'ansible.builtin.debug': {'msg': 'synthetic handler'}}]}]
    playbook = tmp_path / (name + '.json')
    playbook.write_text(json.dumps(play))
    env = {**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg'), 'ANSIBLE_DEBUG': 'false', 'ANSIBLE_DISPLAY_ARGS_TO_STDOUT': 'true', 'ANSIBLE_NOCOLOR': 'true'}
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-vvv', '--diff', str(playbook)], env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


def bundle_for(tmp_path, token):
    bundle = tmp_path / ('bundle-' + token[:6])
    bundle.mkdir()
    (bundle / 'index.html').write_text(f'<a href="/sub/{token}">synthetic</a>')
    return {'token': token, 'client': 'synthetic', 'local_path': str(bundle)}


def test_real_verbose_ansible_share_upload_censors_bearer(tmp_path):
    token = uuid.uuid4().hex
    declared = bundle_for(tmp_path, token)
    output = run_share_tasks(tmp_path, 'share-bundles.yml',
                             {'vpn': {'share_bundles': [declared]}, 'subscription': {'revoked_tokens': []}})
    assert token not in output
    assert (tmp_path / 'public/share' / token / 'index.html').read_text() == f'<a href="/sub/{token}">synthetic</a>'


def test_a_declared_but_revoked_token_gets_no_bundle(tmp_path):
    kept, revoked = uuid.uuid4().hex, uuid.uuid4().hex
    variables = {'vpn': {'share_bundles': [bundle_for(tmp_path, kept), bundle_for(tmp_path, revoked)]},
                 'subscription': {'revoked_tokens': [' ' + hashlib.sha256(revoked.encode()).hexdigest().upper() + ' ']}}
    output = run_share_tasks(tmp_path, 'share-bundles.yml', variables)
    assert sorted(entry.name for entry in (tmp_path / 'public/share').iterdir()) == [kept]
    assert kept not in output and revoked not in output


def test_revocation_alone_removes_only_the_revoked_bundle(tmp_path):
    kept, revoked = uuid.uuid4().hex, uuid.uuid4().hex
    share = tmp_path / 'public/share'
    for token in (kept, revoked):
        (share / token).mkdir(parents=True)
        (share / token / 'config.singbox.json').write_text('{}')
    # Bundles that are not revoked stay, declared in this run or not.
    output = run_share_tasks(tmp_path, 'revoked-hashes.yml',
                             {'subscription': {'revoked_tokens': [hashlib.sha256(revoked.encode()).hexdigest()]}})
    assert sorted(entry.name for entry in share.iterdir()) == [kept]
    assert kept not in output and revoked not in output
