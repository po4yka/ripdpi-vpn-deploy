"""Actual Ansible share publication repairs legacy filesystem access modes."""
from __future__ import annotations

import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_actual_share_copy_repairs_modes_preserves_bytes_and_converges(tmp_path):
    bundle = tmp_path / 'bundle'
    (bundle / 'nested').mkdir(parents=True)
    expected = {'index.html': b'synthetic recipient', 'nested/config.json': b'{"synthetic":true}'}
    for name, data in expected.items():
        (bundle / name).write_bytes(data)
    public = tmp_path / 'public'
    target = public / 'share' / 'synthetic-token'
    (target / 'nested').mkdir(parents=True)
    for directory in [public, public / 'share', target, target / 'nested']:
        directory.chmod(0o755)
    for name, data in expected.items():
        (target / name).write_bytes(data)
        (target / name).chmod(0o644)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'preserved').write_bytes(b'outside publication ownership')
    (outside / 'preserved').chmod(0o644)
    (target / 'external-link').symlink_to(outside, target_is_directory=True)
    tasks = yaml.safe_load((ROOT / 'ansible/roles/subscription-host/tasks/share-bundles.yml').read_text())
    for task in tasks:
        action = task.get('ansible.builtin.file', task.get('ansible.builtin.copy'))
        field = 'path' if 'path' in action else 'dest'
        action[field] = action[field].replace('/var/www/subscription-host', str(public))
        action['owner'] = pwd.getpwuid(os.getuid()).pw_name
        action['group'] = grp.getgrgid(os.getgid()).gr_name
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
             'become': False, 'vars': {'ansible_become': False, 'ansible_python_interpreter': sys.executable,
             'vpn': {'share_bundles': [{'token': 'synthetic-token', 'client': 'synthetic', 'local_path': str(bundle)}]}},
             'tasks': tasks, 'handlers': [{'name': 'Reload nginx', 'ansible.builtin.debug': {'msg': 'synthetic handler'}}]}]
    playbook = tmp_path / 'play.json'
    playbook.write_text(json.dumps(play))
    env = {**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg'),
           'ANSIBLE_STDOUT_CALLBACK': 'default', 'ANSIBLE_NOCOLOR': '1'}
    for iteration in range(3):
        if iteration == 2:
            # Retained tokens must stay private when there are no new uploads.
            for directory in [public, public / 'share', target, target / 'nested']:
                directory.chmod(0o755)
            for name in expected:
                (target / name).chmod(0o644)
            play[0]['vars']['vpn']['share_bundles'] = []
            playbook.write_text(json.dumps(play))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(playbook)],
                                env=env, cwd=tmp_path, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        if iteration == 1:
            assert re.search(r'changed=0\s', result.stdout[result.stdout.index('PLAY RECAP'):])
        assert stat.S_IMODE((outside / 'preserved').stat().st_mode) == 0o644
        assert (target / 'external-link').is_symlink()
        for directory in [public, public / 'share', target, target / 'nested']:
            assert stat.S_IMODE(directory.stat().st_mode) == 0o750
        for name, data in expected.items():
            info = (target / name).stat()
            assert stat.S_IMODE(info.st_mode) == 0o640
            assert info.st_gid == os.getgid()
            assert (target / name).read_bytes() == data
