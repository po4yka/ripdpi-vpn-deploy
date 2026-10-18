"""Native AWG expectations must match the role's actual Ansible template lookup."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import shutil

import pytest
import yaml

from awg_device_binding import resolve_binding
from test_awg_activation_native import native_publisher_environment, render_native_awg_config
from test_awg_device_binding import document

ROOT = Path(__file__).resolve().parents[2]


def test_native_expected_configuration_equals_actual_ansible_lookup(tmp_path):
    source = document()
    instance = source['amneziawg_secrets']['instances'][0]
    instance.update(name='arfixture', mtu=1420, jc=0, s1=0, s2=0)
    source['amneziawg_secrets']['instances'] = [instance]
    source['client_registry'] = {'device0': source['client_registry']['device0']}
    source['client_registry']['device0']['awg_binding']['instance'] = instance['name']
    effective = resolve_binding(source, {}, 'device0', 'upcloud:fixture', instance['name']).instance
    template = ROOT / 'ansible/roles/amneziawg/templates/awg0.conf.j2'
    destination = tmp_path / 'actual.conf'
    play = tmp_path / 'render.yml'
    play.write_text(yaml.safe_dump([{
        'hosts': 'localhost', 'connection': 'local', 'become': False, 'gather_facts': False,
        'vars': {'_inst': effective},
        'tasks': [{'ansible.builtin.copy': {
            'content': "{{ lookup('ansible.builtin.template', " + repr(str(template)) + ') }}',
            'dest': str(destination), 'mode': '0600'}, 'no_log': True}],
    }]))
    play.chmod(0o600)
    result = subprocess.run(
        ['ansible-playbook', '-i', 'localhost,', str(play)],
        env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg'),
             'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_STDOUT_CALLBACK': 'default'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, 'synthetic local Ansible template lookup failed'
    expected = render_native_awg_config(effective).encode()
    actual = destination.read_bytes()
    if expected != actual:
        pytest.fail(f'native configuration differs from Ansible: expected={len(expected)} actual={len(actual)} bytes')


def test_native_publisher_preserves_non_global_ansible_path(tmp_path, monkeypatch):
    actual_ansible = shutil.which('ansible-playbook')
    assert actual_ansible is not None, 'the pinned Ansible toolchain is required'
    toolchain = tmp_path / 'toolchain'
    adapter = tmp_path / 'adapter'
    toolchain.mkdir()
    adapter.mkdir()
    selected = toolchain / 'ansible-playbook'
    selected.symlink_to(actual_ansible)
    inherited = str(toolchain) + os.pathsep + os.environ['PATH']
    monkeypatch.setenv('PATH', inherited)
    environment = {**os.environ, **native_publisher_environment(adapter)}
    preserved = environment['PATH'] == str(adapter) + os.pathsep + inherited
    assert preserved, 'the namespace adapter must precede the complete inherited PATH'
    selected_toolchain = shutil.which('ansible-playbook', path=environment['PATH']) == str(selected)
    assert selected_toolchain, 'the non-global Ansible executable must remain selected'
    result = subprocess.run(['ansible-playbook', '--version'], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'the native publisher must retain the actual Ansible toolchain'


def test_native_publication_plan_uses_the_actual_acquired_go_directory(tmp_path, monkeypatch):
    """Check generated Ansible input; this is not native activation evidence."""
    import test_awg_activation_native as native

    release_root = tmp_path / 'releases'
    actual_path = Path
    monkeypatch.setattr(native, 'Path', lambda value: (
        release_root if value == '/opt/amneziawg/releases' else actual_path(value)))
    publisher = native.CompletePublisher(tmp_path, {'PATH': os.environ['PATH']})
    publisher.record = tmp_path / 'absent-membership.json'
    binaries = []
    for name in ('go', 'tools', 'quick'):
        file = tmp_path / name
        file.write_bytes(('synthetic acquisition ' + name).encode())
        binaries.append(file)
    acquired = publisher.acquire(*binaries)
    monkeypatch.setattr(native.subprocess, 'run', lambda args, **kwargs: (
        subprocess.CompletedProcess(args, 0, '', '')))
    publisher.role([])
    generated = yaml.safe_load((tmp_path / 'converge.yml').read_text())[0]
    expected = str(actual_path(acquired[0]['source']).parent)
    assert generated['vars']['_awg_go_release_dir'] == expected
    assert actual_path(expected, 'amneziawg-go').read_bytes() == binaries[0].read_bytes()
