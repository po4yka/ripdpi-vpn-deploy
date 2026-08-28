"""Controller argument/env boundaries without remote or Ansible execution."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'scripts/install-sshd-recovery.py'


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('install_sshd_recovery', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('target', ['', 'vpn*', 'vpn:a', 'vpn,a', 'all', "x'; touch owned", '$(touch owned)', '$(shell touch owned)'])
def test_invalid_target_refuses_before_inventory_or_subprocess(controller, monkeypatch, target):
    monkeypatch.setattr(controller.inspection, 'select_hosts', lambda *_: pytest.fail('inventory reached'))
    with pytest.raises(controller.InstallError):
        controller.build_invocation({'SSH_RECOVERY_TARGET': target, 'SSH_RECOVERY_WINDOW':'1'})


@pytest.mark.parametrize('value', ['true','True','1','yes','on','arbitrary'])
def test_debug_cannot_leak_no_log_results(controller, value):
    with pytest.raises(controller.InstallError, match='debug'):
        controller.build_invocation({'SSH_RECOVERY_TARGET':'vpn-fixture','SSH_RECOVERY_WINDOW':'1','ANSIBLE_DEBUG':value})


def test_exact_argv_and_debug_false_override_config(controller, monkeypatch):
    host = dict(name='vpn-fixture', transport='192.0.2.1', address='192.0.2.1',alias='192.0.2.1',
                port=2222,user='deploy',key='/keys/private key')
    monkeypatch.setattr(controller.inspection, 'select_hosts', lambda *_:[host])
    monkeypatch.setattr(controller.inspection, 'ssh_command', lambda *_:['ssh','-F','/dev/null','-o','StrictHostKeyChecking=yes',host['transport'],'sudo fixed'])
    argv, env, inventory = controller.build_invocation({'SSH_RECOVERY_TARGET':'vpn-fixture','SSH_RECOVERY_WINDOW':'1',
                                            'PATH':os.environ['PATH'],'ANSIBLE_DEBUG':'false'})
    assert argv[argv.index('--limit')+1] == 'vpn-fixture'
    assert '--diff' not in argv and '--tags' not in argv
    assert env['ANSIBLE_DEBUG'] == 'false'
    assert env['ANSIBLE_SSH_ARGS'] == '-F /dev/null -o StrictHostKeyChecking=yes'
    assert env['ANSIBLE_SSH_COMMON_ARGS'] == env['ANSIBLE_SSH_EXTRA_ARGS'] == ''
    assert env['ANSIBLE_HOST_KEY_CHECKING'] == 'true'
    assert inventory == '[vpn]\nvpn-fixture\n'


def test_make_limit_data_never_runs_shell_or_make_expansions(tmp_path):
    marker = tmp_path/'unexpected-execution'
    for value in [f'$(shell touch {marker})', f'$(touch {marker})', f"bad'; touch {marker}; '"]:
        command = ['make','-n','install-ssh-recovery', 'ANSIBLE_LIMIT='+value, 'SSH_RECOVERY_EXCLUSIVE_WINDOW=1']
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=20)
        assert not marker.exists()
        assert 'install-sshd-recovery.py' in result.stdout
        assert value not in result.stdout


@pytest.mark.parametrize('field', ['SSH_RECOVERY_EXCLUSIVE_WINDOW', 'SSH_RECOVERY_INVENTORY', 'SSH_RECOVERY_KNOWN_HOSTS', 'ANSIBLE_DEBUG'])
def test_make_other_owned_fields_are_literal_data(tmp_path, field):
    marker = tmp_path/'unexpected-expansion'
    value = '$(shell touch '+str(marker)+')'
    result = subprocess.run(['make','-n','install-ssh-recovery','ANSIBLE_LIMIT=vpn-fixture',field+'='+value],
                            cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert not marker.exists()
    assert value not in result.stdout
    assert 'install-sshd-recovery.py' in result.stdout


def test_make_multiple_goals_refuse_before_expanding_caller_fields(tmp_path):
    marker = tmp_path/'unexpected-multi-expansion'
    result = subprocess.run(['make','-n','install-ssh-recovery','help',
                             'ANSIBLE_LIMIT=$(shell touch '+str(marker)+')'],cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert result.returncode != 0
    assert 'requires exactly one goal' in result.stderr
    assert not marker.exists()


def test_make_does_not_call_git_before_controller_privacy_guard(tmp_path):
    marker = tmp_path / 'git-before-controller'
    spy = tmp_path / 'git'
    spy.write_text('#!/bin/sh\nprintf called >> "$SSH_GIT_SPY"\nexit 1\n')
    spy.chmod(0o755)
    environment = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
                   'SSH_GIT_SPY': str(marker), 'GIT_DIR': str(tmp_path / 'foreign-git')}
    result = subprocess.run(['make', 'install-ssh-recovery', 'ANSIBLE_LIMIT=vpn-fixture',
                             'SSH_RECOVERY_EXCLUSIVE_WINDOW=1', 'ANSIBLE_DEBUG=true'],
                            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert 'ssh-recovery-install-failed' in result.stdout
    assert not marker.exists()



def test_manifest_covers_exact_bundle_source_and_binds_generation(controller):
    import hashlib
    import json
    generation, manifest = controller.bundle_manifest()
    assert generation == hashlib.sha256(manifest.encode()).hexdigest()
    document = json.loads(manifest)
    assert document['schema_version'] == 1 and len(document['files']) == 6
    assert manifest == json.dumps(document, sort_keys=True, separators=(',',':'))+'\n'
    for name, expected in document['files'].items():
        path = ROOT/'ansible/roles/baseline'/('templates' if name.startswith('units/') else 'files')/Path(name).name
        assert expected == hashlib.sha256(path.read_bytes()).hexdigest()


def test_inherited_environment_cannot_skip_install_or_override_git_and_plugins(controller, monkeypatch):
    host = dict(name='vpn-fixture',transport='192.0.2.1',address='192.0.2.1',alias='192.0.2.1',port=2222,user='deploy',key='/keys/key')
    monkeypatch.setattr(controller.inspection,'select_hosts',lambda *_:[host])
    monkeypatch.setattr(controller.inspection,'ssh_command',lambda *_:['ssh','-F','/dev/null',host['transport'],'sudo fixed'])
    result = controller.build_invocation({'SSH_RECOVERY_TARGET':'vpn-fixture','SSH_RECOVERY_WINDOW':'1','PATH':os.environ['PATH'],
        'ANSIBLE_RUN_TAGS':'nonexistent','ANSIBLE_SKIP_TAGS':'all','ANSIBLE_SSH_EXECUTABLE':'/tmp/fake-ssh',
        'ANSIBLE_CALLBACK_PLUGINS':'/tmp/plugins','GIT_DIR':'/tmp/other-repo','PROVIDER_TOKEN':'private'})
    env = result[1]
    for name in ('ANSIBLE_RUN_TAGS','ANSIBLE_SKIP_TAGS','ANSIBLE_SSH_EXECUTABLE','ANSIBLE_CALLBACK_PLUGINS','GIT_DIR','PROVIDER_TOKEN'):
        assert name not in env


def test_strict_arguments_are_also_valid_for_sftp_and_scp(controller, monkeypatch):
    import shlex
    host = dict(name='vpn-fixture',transport='192.0.2.1',address='192.0.2.1',alias='192.0.2.1',port=2222,user='deploy',key='/keys/private key')
    monkeypatch.setattr(controller.inspection,'select_hosts',lambda *_:[host])
    monkeypatch.setattr(controller.inspection,'_local_file',lambda path,**kwargs:str(path))
    result = controller.build_invocation({'SSH_RECOVERY_TARGET':'vpn-fixture','SSH_RECOVERY_WINDOW':'1','PATH':os.environ['PATH']})
    options = shlex.split(result[1]['ANSIBLE_SSH_ARGS'])
    assert '-l' not in options and '-p' not in options
    assert 'User=deploy' in options and 'Port=2222' in options and 'IdentityFile="/keys/private key"' in options
    result = subprocess.run(['ssh', '-G', *options, host['transport']], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert 'identityfile /keys/private key\n' in result.stdout


def test_real_ansible_cannot_load_external_host_vars(controller, monkeypatch, tmp_path):
    original = tmp_path / 'inventory.ini'
    original.write_text('[vpn]\nvpn-fixture\n')
    (tmp_path / 'host_vars').mkdir()
    (tmp_path / 'host_vars/vpn-fixture.yml').write_text('ansible_ssh_args: unsafe-override\nexternal_marker: leaked\n')
    command = [sys.executable, '-m', 'ansible.cli.inventory']
    baseline = subprocess.run(command + ['-i', str(original), '--host', 'vpn-fixture'],
                              capture_output=True, text=True, timeout=15)
    assert baseline.returncode == 0, baseline.stderr
    assert json.loads(baseline.stdout)['ansible_ssh_args'] == 'unsafe-override'
    host = dict(name='vpn-fixture', transport='192.0.2.1', address='192.0.2.1', alias='192.0.2.1',
                port=2222, user='deploy', key='/keys/private key')
    monkeypatch.setattr(controller.inspection, 'select_hosts', lambda *_: [host])
    monkeypatch.setattr(controller.inspection, '_local_file', lambda path, **kwargs: str(path))
    monkeypatch.setattr(controller, '_clean_source', lambda _: None)
    monkeypatch.setenv('SSH_RECOVERY_TARGET', 'vpn-fixture')
    monkeypatch.setenv('SSH_RECOVERY_WINDOW', '1')
    monkeypatch.setenv('SSH_RECOVERY_INVENTORY', str(original))
    observed = []

    def inspect_private_inventory(argv, *, environment, **kwargs):
        path = Path(argv[argv.index('-i') + 1])
        observed.append(path)
        assert path != original and path.parent != original.parent
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.read_text() == '[vpn]\nvpn-fixture\n'
        # Also expose the hostile directory as a playbook vars source: the
        # fixed vars policy must block both inventory and playbook discovery.
        result = subprocess.run(command + ['-i', str(path), '--playbook-dir', str(tmp_path),
                                '--host', 'vpn-fixture', '--extra-vars', argv[-1]],
                                env=environment, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        variables = json.loads(result.stdout)
        assert 'external_marker' not in variables and 'ansible_ssh_args' not in variables
        assert variables['ansible_host'] == host['transport']
        assert variables['ansible_connection'] == 'ssh'
        return b''

    monkeypatch.setattr(controller.inspection, 'bounded_command', inspect_private_inventory)
    assert controller.main() == 0
    assert len(observed) == 1 and not observed[0].parent.exists()


def test_private_inventory_is_removed_on_uncertain_install(controller, monkeypatch):
    argv = ['ansible-playbook', '-i', '<private-inventory>']
    monkeypatch.setattr(controller, 'build_invocation', lambda _: (argv, {}, '[vpn]\nvpn-fixture\n'))
    monkeypatch.setattr(controller, '_clean_source', lambda _: None)
    observed = []

    def fail_install(command, **kwargs):
        observed.append(Path(command[2]))
        raise controller.inspection.InspectionError('uncertain')

    monkeypatch.setattr(controller.inspection, 'bounded_command', fail_install)
    assert controller.main() == 1
    assert len(observed) == 1 and not observed[0].parent.exists()
