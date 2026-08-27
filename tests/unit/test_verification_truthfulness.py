"""Verification must honor the deployment host class and listener contract."""

import base64
import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import jinja2
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def playbook(name):
    return yaml.safe_load((ROOT / 'ansible/playbooks' / name).read_text())[0]


def walk(tasks, inherited=()):
    for task in tasks:
        conditions = task.get('when', [])
        if isinstance(conditions, str):
            conditions = [conditions]
        conditions = (*inherited, *conditions)
        yield task, conditions
        for branch in ('block', 'rescue', 'always'):
            yield from walk(task.get(branch, []), conditions)


@pytest.mark.parametrize('name', ['verify.yml', 'smoke-test.yml'])
def test_subscription_only_skips_every_transport(name):
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    checked = 0
    for task, conditions in walk(playbook(name)['tasks']):
        if not any('vpn.enable_' in condition for condition in conditions):
            continue
        enabled = dict.fromkeys([
            'enable_xray_reality', 'enable_nginx_xhttp', 'enable_hysteria',
            'enable_snell', 'enable_amneziawg', 'enable_watchdog', 'enable_monitoring',
        ], True)
        assert not all(env.compile_expression(condition)(
            vpn=enabled, vpn_subscription_only=True,
        ) for condition in conditions), task['name']
        checked += 1
    assert checked > 0


def test_verify_checks_custom_primary_and_fallback_listener_ports():
    source = (ROOT / 'ansible/playbooks/verify.yml').read_text()
    for variable in ('hysteria_port', 'xray_fallback_port', 'nginx_xhttp_fallback_port'):
        assert '{{{{ {} | default('.format(variable) in source


@pytest.mark.parametrize('scenario', [
    'ansible/molecule/full-stack/molecule.yml',
    'ansible/molecule/full-stack-published/molecule.yml',
    'ansible/roles/xray/molecule/default/molecule.yml',
])
def test_integration_sequence_checks_second_converge(scenario):
    config = yaml.safe_load((ROOT / scenario).read_text())
    sequence = config['scenario']['test_sequence']
    assert sequence.index('converge') < sequence.index('idempotence') < sequence.index('verify')
    if scenario.startswith('ansible/molecule/full-stack'):
        variables = config['provisioner']['inventory']['group_vars']['all']
        secrets = yaml.safe_load((ROOT / 'ansible/molecule/full-stack/test-secrets.yaml').read_text())
        contract = json.loads(base64.b64decode(''.join(variables['terraform_public_listeners_b64_chunks'])))
        fallback = next(listener for listener in contract if listener['name'] == 'xray-fallback')
        assert variables['xray_fallback_port'] == fallback['port']
        assert variables['public_site_canonical_url'] == 'https://' + secrets['nginx_xhttp']['server_name']
        assert variables['public_site_canonical_url'] == secrets['hysteria']['masquerade_url']


def test_amneziawg_scenario_executes_real_role():
    scenario = ROOT / 'ansible/roles/amneziawg/molecule/default'
    play = yaml.safe_load((scenario / 'converge.yml').read_text())[0]
    assert any(task.get('ansible.builtin.include_role', {}).get('name') == 'amneziawg'
               for task, _ in walk(play.get('tasks', [])))
    sequence = yaml.safe_load((scenario / 'molecule.yml').read_text())['scenario']['test_sequence']
    assert sequence.index('prepare') < sequence.index('converge')
    prepare = yaml.safe_load((scenario / 'prepare.yml').read_text())[0]
    preseeds = [task['ansible.builtin.debconf'] for task, _ in walk(prepare['tasks'])
                if 'ansible.builtin.debconf' in task]
    assert {'name': 'resolvconf', 'question': 'resolvconf/linkify-resolvconf',
            'vtype': 'boolean', 'value': 'false'} in preseeds


@pytest.mark.parametrize('stale_socket,expected', [(False, ['2222']), (True, ['22', '2222'])])
def test_ssh_listener_query_detects_socket_left_on_old_port(tmp_path, stale_socket, expected):
    task = next(task for task in playbook('verify.yml')['tasks']
                if task['name'] == 'Collect actual SSH service and socket listener ports')
    for name, content in {
        'ss': '#!/bin/sh\necho \'LISTEN 0 128 0.0.0.0:2222 *:* users:(("sshd",pid=2,fd=1))\'\n',
        'systemctl': '#!/bin/sh\n' + (
            'test "$1" = is-active && exit 0\necho "[::]:22 (Stream)"\n'
            if stale_socket else 'exit 3\n'
        ),
    }.items():
        script = tmp_path / name
        script.write_text(content)
        script.chmod(0o755)
    result = subprocess.run(['bash', '-c', task['ansible.builtin.shell']['cmd']],
                            env={**os.environ, 'PATH': f'{tmp_path}:{os.environ["PATH"]}'},
                            capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == expected


@pytest.mark.parametrize('revision,success', [('a' * 40, True), ('b' * 40, False)])
def test_source_drift_executes_exact_revision_comparison(tmp_path, revision, success):
    task = playbook('source-drift.yml')['tasks'][-1]
    path = tmp_path / 'drift.yml'
    path.write_text(yaml.safe_dump([{
        'name': 'Exercise full source identity', 'hosts': 'localhost', 'gather_facts': False,
        'vars': {
            'expected_source_revision': 'a' * 40, 'expected_deployable_digest': 'c' * 64,
            'deployed_source_manifest': {
                'schema_version': 2, 'source_revision': revision, 'deployable_digest': 'c' * 64,
            },
        }, 'tasks': [task],
    }], sort_keys=False))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)],
                            capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) == success, result.stdout + result.stderr


@pytest.mark.parametrize('protocol', ['xray', 'hysteria', 'snell'])
def test_smoke_wait_failure_stops_transient_unit_and_removes_credentials(tmp_path, protocol):
    block = copy.deepcopy(playbook('smoke-test.yml')['tasks'][1])
    fixture = yaml.safe_load((ROOT / 'tests/fixtures/secrets-sample.yml').read_text())
    fixture['vpn'] = {
        'enable_xray_reality': protocol == 'xray',
        'enable_hysteria': protocol == 'hysteria',
        'enable_snell': protocol == 'snell',
    }
    fixture['snell'] = {'smoke_port_base': 31082, 'variants': [
        {'id': 'test', 'listen_port': 10443, 'client_version': 4},
    ]}
    fixture['snell_secrets'] = {'variants': [
        {'id': 'test', 'psk': 'fixture-only', 'users': [{'userkey': 'fixture-only'}]},
    ]}
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    for name in ('systemctl', 'systemd-run'):
        executable = fake_bin / name
        executable.write_text(
            f'#!{sys.executable}\n'
            'import pathlib, sys\n'
            f'root = pathlib.Path({str(tmp_path)!r})\n'
            'if pathlib.Path(sys.argv[0]).name == "systemd-run":\n'
            '    unit = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--unit="))\n'
            '    (root / unit).touch()\n'
            '    (root / "started").touch()\n'
            'else:\n'
            '    (root / sys.argv[-1].removesuffix(".service")).unlink(missing_ok=True)\n'
        )
        executable.chmod(0o755)
    with socket.socket() as closed_listener:
        closed_listener.bind(('127.0.0.1', 0))
        port = closed_listener.getsockname()[1]
        for task, _ in walk([block]):
            for module in ('ansible.builtin.copy', 'ansible.builtin.file'):
                if module in task:
                    task[module].pop('owner', None)
                    task[module].pop('group', None)
            if 'ansible.builtin.set_fact' in task and 'smoketest_dir' in task['ansible.builtin.set_fact']:
                task['ansible.builtin.set_fact']['smoketest_dir'] = str(tmp_path / 'credentials')
            if 'ansible.builtin.wait_for' in task:
                task['ansible.builtin.wait_for'].update(port=port, timeout=1)
            content = task.get('ansible.builtin.copy', {}).get('content', '')
            if "lookup('template'" in content:
                task['ansible.builtin.copy']['content'] = content.replace(
                    "playbook_dir ~ '/../roles/snell/templates/smoke-client.json.j2'",
                    repr(str(ROOT / 'ansible/roles/snell/templates/smoke-client.json.j2')),
                )
        path = tmp_path / 'probe.yml'
        # Make exports ANSIBLE_BECOME; this local fixture must never invoke sudo.
        path.write_text(yaml.safe_dump([{
            'name': 'Exercise production smoke failure cleanup', 'hosts': 'localhost',
            'gather_facts': False, 'become': False, 'vars': fixture, 'tasks': [block],
        }], sort_keys=False))
        result = subprocess.run([
            'ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path),
            '-e', f'ansible_python_interpreter={sys.executable}',
        ], env={**os.environ, 'PATH': f'{fake_bin}:{os.environ["PATH"]}'},
            capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert (tmp_path / 'started').exists(), result.stdout + result.stderr
    assert not (tmp_path / f'vpn-smoke-{protocol}').exists(), result.stdout + result.stderr
    assert not (tmp_path / 'credentials').exists(), result.stdout + result.stderr
