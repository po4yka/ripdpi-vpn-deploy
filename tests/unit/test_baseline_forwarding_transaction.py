"""Real forwarding-fragment convergence; this suite does not claim kernel evidence."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TASKS = yaml.safe_load((ROOT / 'ansible/roles/baseline/tasks/forwarding.yml').read_text())
ACCEPTED = b'net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n'


def reader():
    namespace = {'__name__': 'forwarding_reader'}
    exec(compile(TASKS[0]['ansible.builtin.command']['argv'][3], '<actual forwarding reader>', 'exec'), namespace)
    return namespace['accepted_forwarding']


@pytest.mark.parametrize('change', ['accepted', 'absent', 'split-hop', 'oversize', 'writable', 'symlink', 'parent-writable'])
def test_exact_retained_fragment_authority(tmp_path, change):
    parent = tmp_path / 'sysctl.d'
    parent.mkdir(mode=0o755)
    fragment = parent / '91-vpn-forward.conf'
    if change != 'absent':
        fragment.write_bytes(ACCEPTED)
        fragment.chmod(0o644)
    if change == 'split-hop':
        fragment.write_bytes(ACCEPTED.replace(b'forwarding = 1', b'forwarding = 0'))
    elif change == 'oversize':
        fragment.write_bytes(b'x' * 129)
    elif change == 'writable':
        fragment.chmod(0o666)
    elif change == 'symlink':
        fragment.rename(parent / 'other')
        fragment.symlink_to('other')
    elif change == 'parent-writable':
        parent.chmod(0o777)
    if change in {'oversize', 'writable', 'symlink', 'parent-writable'}:
        with pytest.raises((OSError, ValueError)):
            reader()(fragment, uid=os.getuid(), anchor=tmp_path)
    else:
        assert reader()(fragment, uid=os.getuid(), anchor=tmp_path) is (change == 'accepted')


def confined_tasks(tmp_path, defer):
    tasks = copy.deepcopy(TASKS[:4])
    command = tasks[0]['ansible.builtin.command']['argv']
    command[0] = sys.executable
    command[3] = command[3].replace(
        "accepted_forwarding('/etc/sysctl.d/91-vpn-forward.conf')",
        f"accepted_forwarding({str(tmp_path / '91-vpn-forward.conf')!r}, uid={os.getuid()}, anchor=Path({str(tmp_path)!r}))")
    for task in tasks[1:]:
        for module in ['ansible.builtin.copy', 'ansible.builtin.file']:
            if module in task:
                args = task[module]
                for key in ['dest', 'path']:
                    if key in args:
                        args[key] = str(tmp_path / Path(args[key]).name)
                args.pop('owner', None)
                args.pop('group', None)
    return {'name': 'Converge actual forwarding fragment', 'vars': {'baseline_defer_awg_forwarding': defer}, 'block': tasks}


@pytest.mark.parametrize('outcome', ['protected-failed', 'awg-retired', 'awg-omitted', 'standalone', 'subscription-retired'])
def test_forwarding_removal_waits_for_selected_awg_completion(tmp_path, outcome):
    fragment = tmp_path / '91-vpn-forward.conf'
    fragment.write_bytes(ACCEPTED)
    fragment.chmod(0o644)
    tasks = [confined_tasks(tmp_path, outcome != 'standalone')]
    if outcome == 'protected-failed':
        tasks.append({'name': 'Reject protected stage before AWG', 'ansible.builtin.fail': {'msg': 'rejected-protected'}})
    if outcome in {'protected-failed', 'awg-retired', 'subscription-retired'}:
        tasks.append(confined_tasks(tmp_path, False))
    if outcome == 'subscription-retired':
        tasks[-1]['vars']['baseline_forwarding_amneziawg_active'] = False
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
             'vars': {'ansible_python_interpreter': sys.executable, 'vpn': {'enable_amneziawg': outcome == 'subscription-retired'}}, 'tasks': tasks}]
    path = tmp_path / 'play.yml'
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path)],
        env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')}, capture_output=True, text=True, timeout=40)
    assert result.returncode == (2 if outcome == 'protected-failed' else 0), result.stdout + result.stderr
    if outcome == 'protected-failed':
        assert 'rejected-protected' in result.stdout
        assert 'sudo:' not in result.stdout
    assert fragment.exists() is (outcome in {'protected-failed', 'awg-omitted'})
    if fragment.exists():
        assert fragment.read_bytes() == ACCEPTED


def test_site_reconciles_desired_forwarding_only_after_selected_awg():
    play = yaml.safe_load((ROOT / 'ansible/playbooks/site.yml').read_text())[0]
    assert play['vars']['baseline_defer_awg_forwarding'] is True
    tasks = play['tasks']
    position = next(i for i, task in enumerate(tasks) if task['name'] == 'Reconcile amneziawg runtime')
    after = tasks[position + 1]
    assert after['ansible.builtin.import_role'] == {'name': 'baseline', 'tasks_from': 'forwarding'}
    assert after['vars']['baseline_defer_awg_forwarding'] is False
    assert after['tags'] == tasks[position]['tags']
    assert after['vars']['baseline_forwarding_amneziawg_active'] == tasks[position]['vars']['amneziawg_role_enabled']
    # The existing ordered helper remains the only kernel application boundary.
    assert TASKS[-1]['ansible.builtin.command']['cmd'] == '/usr/local/libexec/vpn-baseline-sysctl'
