"""Actual localhost digest capture/comparison; HTTPS remains in Molecule."""
import copy
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / 'ansible/roles/nginx-xhttp/molecule/default'
WITNESS = '/run/vpn-nginx-hosts-before.sha256'


def test_scenario_retains_all_real_https_verification_and_prepare_phase():
    settings = yaml.safe_load((SCENARIO / 'molecule.yml').read_text())
    assert settings['scenario']['test_sequence'] == ['dependency', 'syntax', 'create', 'prepare', 'converge', 'idempotence', 'verify', 'destroy']
    source = (SCENARIO / 'verify.yml').read_text()
    assert 'getent' not in source and 'managed hosts entry' not in source
    assert source.count('--resolve vpn.example.test:8443:127.0.0.1') == 12
    assert 'Public responses carry the hardened header set' in source
    assert 'Missing and forbidden paths return the normal site 404' in source
    assert 'Atom feed carries the declared media type and publication identity' in source


def _run(path):
    env = os.environ.copy()
    env['ANSIBLE_STDOUT_CALLBACK'] = 'default'
    env['ANSIBLE_NOCOLOR'] = '1'
    return subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path)], env=env, capture_output=True, text=True, timeout=45)


@pytest.mark.parametrize('mutation', [False, True])
def test_actual_prepare_digest_detects_hosts_mutation_without_disclosure(tmp_path, mutation):
    hosts = tmp_path / 'hosts'
    marker = 'private-fixture-host-record.example.invalid'
    hosts.write_text('127.0.0.1 localhost\n192.0.2.9 ' + marker + '\n')
    witness = tmp_path / 'before.sha256'
    prepare = copy.deepcopy(yaml.safe_load((SCENARIO / 'prepare.yml').read_text())[0])
    verify = yaml.safe_load((SCENARIO / 'verify.yml').read_text())[0]
    checks = copy.deepcopy(verify['tasks'][1:6])
    for task in [*prepare['tasks'], *checks]:
        for module in ('ansible.builtin.stat', 'ansible.builtin.slurp'):
            if module in task:
                field = 'path' if module.endswith('.stat') else 'src'
                old = task[module][field]
                task[module][field] = str(hosts if old == '/etc/hosts' else witness)
        if 'ansible.builtin.copy' in task:
            task['ansible.builtin.copy'].update(dest=str(witness), owner=str(os.getuid()), group=str(os.getgid()))
        if task.get('name') == 'Require the original hosts witness to retain private root ownership':
            task['ansible.builtin.assert']['that'] = [value.replace('uid == 0', f'uid == {os.getuid()}').replace('gid == 0', f'gid == {os.getgid()}') for value in task['ansible.builtin.assert']['that']]
    prepare.update(hosts='localhost', connection='local', become=False, gather_facts=False)
    script = tmp_path / 'prepare.yml'
    script.write_text(yaml.safe_dump([prepare], sort_keys=False))
    captured = _run(script)
    assert captured.returncode == 0, captured.stdout + captured.stderr
    assert witness.stat().st_mode & 0o777 == 0o600
    assert witness.read_text().strip().isalnum() and len(witness.read_text().strip()) == 64
    if mutation:
        hosts.write_text(hosts.read_text() + '198.51.100.7 changed.example.invalid\n')
    script = tmp_path / 'verify.yml'
    script.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'become': False, 'gather_facts': False, 'tasks': checks}], sort_keys=False))
    checked = _run(script)
    assert (checked.returncode != 0) is mutation, checked.stdout + checked.stderr
    assert marker not in captured.stdout + captured.stderr + checked.stdout + checked.stderr
    assert witness.read_text().strip() not in captured.stdout + captured.stderr + checked.stdout + checked.stderr
