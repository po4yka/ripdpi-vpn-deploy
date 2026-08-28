"""Installed adapter command boundaries; no production systemd calls."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles/baseline/files'


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(FILES))
    spec = importlib.util.spec_from_file_location('sshd_migrate', FILES / 'sshd_migrate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boot_recovery_has_no_reload_and_normal_adapter_uses_fixed_command(adapter, monkeypatch):
    calls = []
    monkeypatch.setattr(adapter, '_command', lambda args: calls.append(args) or '')
    adapter.Runtime().reload()
    assert calls == [['/usr/bin/systemctl', 'reload', 'ssh.service']]


def test_recovery_requires_enabled_timer_and_real_ssh_dependencies(adapter, monkeypatch):
    values = installed_properties(adapter)
    monkeypatch.setattr(adapter, '_command', lambda args: values[tuple(args[1:])])
    monkeypatch.setattr(adapter, '_validate_installation', lambda: None)
    assert adapter.Runtime().recovery_ready()
    values[('show', 'ssh.socket', '--property=Requires', '--value')] = 'other.service'
    assert not adapter.Runtime().recovery_ready()
    values[('show', 'ssh.socket', '--property=Requires', '--value')] = 'vpn-sshd-boot-recover.service'
    values[('show', 'vpn-sshd-recover.timer', '--property=Requires', '--value')] = 'other.service'
    assert not adapter.Runtime().recovery_ready()


def test_request_is_fixed_shape_and_requires_two_connection_contexts(adapter):
    with pytest.raises(adapter.TransactionError):
        adapter.validate_request('prepare', {'contexts': [], 'timeout': 180, 'config_root': '/tmp'})
    with pytest.raises(adapter.TransactionError):
        adapter.validate_request('prepare', {'contexts': [], 'timeout': 180})
    with pytest.raises(adapter.TransactionError):
        adapter.validate_request('apply', {'generation': 'x', 'nonce': 'y', 'command': 'true'})


def test_unit_design_avoids_boot_reload_deadlock_and_repeated_timer_noop(adapter):
    templates = ROOT / 'ansible/roles/baseline/templates'
    boot = (templates / 'vpn-sshd-boot-recover.service').read_text()
    worker = (templates / 'vpn-sshd-recover.service').read_text()
    timer = (templates / 'vpn-sshd-recover.timer').read_text()
    assert 'Before=ssh.service ssh.socket' in boot
    assert 'RequiredBy=ssh.service ssh.socket' in boot
    assert 'boot-recover' in boot and 'systemctl' not in boot
    assert 'RemainAfterExit=yes' not in worker
    assert 'SuccessExitStatus=75' in worker
    assert 'SuccessExitStatus=' not in boot
    assert 'OnCalendar=' in timer and 'Persistent=true' in timer
    assert 'OnUnitActiveSec=15s' in timer
    assert 'Requires=vpn-sshd-boot-recover.service' in timer
    assert 'After=vpn-sshd-boot-recover.service' in timer


def installed_properties(adapter):
    values = {
        ('is-enabled', 'vpn-sshd-recover.timer'): 'enabled',
        ('is-enabled', 'vpn-sshd-boot-recover.service'): 'enabled',
        ('is-active', 'vpn-sshd-recover.timer'): 'active',
    }
    for unit in adapter.UNIT_HASHES:
        values[('show', unit, '--property=NeedDaemonReload', '--value')] = 'no'
        values[('show', unit, '--property=FragmentPath', '--value')] = '/etc/systemd/system/' + unit
        values[('show', unit, '--property=DropInPaths', '--value')] = ''
        values[('show', unit, '--property=LoadState', '--value')] = 'loaded'
        if unit.endswith('.service'):
            values[('show', unit, '--property=ActiveState', '--value')] = 'inactive'
            values[('show', unit, '--property=Result', '--value')] = 'success'
            values[('show', unit, '--property=ExecMainStartTimestampMonotonic', '--value')] = '100'
            values[('show', unit, '--property=ExecMainExitTimestampMonotonic', '--value')] = '200'
            values[('show', unit, '--property=ExecMainStatus', '--value')] = '0'
    for unit in ('ssh.service', 'ssh.socket', 'vpn-sshd-recover.timer'):
        for prop in ('Requires', 'After'):
            values[('show', unit, '--property='+prop, '--value')] = 'vpn-sshd-boot-recover.service other.service'
    return values


@pytest.mark.parametrize('unit', ['vpn-sshd-boot-recover.service', 'vpn-sshd-recover.service'])
@pytest.mark.parametrize('property_name,value', [('ActiveState', 'failed'), ('Result', 'resources'), ('LoadState', 'error')])
def test_failed_recovery_worker_is_not_ready_even_with_active_timer(adapter, monkeypatch, unit, property_name, value):
    values = installed_properties(adapter)
    monkeypatch.setattr(adapter, '_command', lambda args: values[tuple(args[1:])])
    monkeypatch.setattr(adapter, '_validate_installation', lambda: None)
    assert adapter.Runtime().recovery_ready()
    values[('show', unit, '--property=' + property_name, '--value')] = value
    assert not adapter.Runtime().recovery_ready()


@pytest.mark.parametrize('unit', ['vpn-sshd-boot-recover.service', 'vpn-sshd-recover.service'])
def test_never_executed_worker_is_not_readiness_evidence(adapter, monkeypatch, unit):
    values = installed_properties(adapter)
    monkeypatch.setattr(adapter, '_command', lambda args: values[tuple(args[1:])])
    monkeypatch.setattr(adapter, '_validate_installation', lambda: None)
    assert adapter.Runtime().recovery_ready()
    values[('show', unit, '--property=ExecMainStartTimestampMonotonic', '--value')] = '0'
    values[('show', unit, '--property=ExecMainExitTimestampMonotonic', '--value')] = '0'
    assert not adapter.Runtime().recovery_ready()
    values[('show', unit, '--property=ExecMainStartTimestampMonotonic', '--value')] = '100'
    values[('show', unit, '--property=ExecMainExitTimestampMonotonic', '--value')] = '200'
    values[('show', unit, '--property=ExecMainStatus', '--value')] = '75'
    assert not adapter.Runtime().recovery_ready()


@pytest.mark.parametrize('action,expected', [('recover', 75), ('boot-recover', 1), ('status', 1)])
def test_only_periodic_lock_contention_is_deferred_not_failed(adapter, monkeypatch, capsys, action, expected):
    import json
    class Busy:
        def recover(self, **kwargs):
            raise adapter.TransactionError('busy')
        def status(self):
            raise adapter.TransactionError('busy')
    monkeypatch.setattr(adapter.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(adapter.transaction, 'Transaction', lambda *args: Busy())
    monkeypatch.setattr(sys, 'argv', ['sshd_migrate.py', action])
    assert adapter.main() == expected
    result = json.loads(capsys.readouterr().out)
    assert result == ({'status': 'deferred', 'reason': 'busy'} if action == 'recover'
                      else {'status': 'error', 'reason': 'ssh-transaction-failed'})


@pytest.mark.parametrize('fault', ['dropin', 'transient', 'runtime-only-boot'])
def test_unapproved_loaded_recovery_units_cannot_arm(adapter, monkeypatch, fault):
    values = installed_properties(adapter)
    monkeypatch.setattr(adapter, '_command', lambda args: values[tuple(args[1:])])
    monkeypatch.setattr(adapter, '_validate_installation', lambda: None)
    assert adapter.Runtime().recovery_ready()
    if fault == 'dropin':
        values[('show', 'vpn-sshd-recover.service', '--property=DropInPaths', '--value')] = '/run/systemd/system/vpn-sshd-recover.service.d/override.conf'
    elif fault == 'transient':
        values[('show', 'vpn-sshd-recover.timer', '--property=FragmentPath', '--value')] = '/run/systemd/transient/vpn-sshd-recover.timer'
    else:
        values[('is-enabled', 'vpn-sshd-boot-recover.service')] = 'enabled-runtime'
    assert not adapter.Runtime().recovery_ready()


def test_boot_unit_provides_privsep_directory_before_ssh_service(adapter):
    boot = (ROOT / 'ansible/roles/baseline/templates/vpn-sshd-boot-recover.service').read_text()
    assert 'RuntimeDirectory=sshd' in boot
    assert 'RuntimeDirectoryPreserve=yes' in boot


def test_installer_has_exact_host_guard_without_importing_baseline_or_site(adapter):
    import yaml
    play = yaml.safe_load((ROOT / 'ansible/playbooks/install-sshd-recovery.yml').read_text())[0]
    assert play['serial'] == 1 and play['gather_facts'] is False
    assert 'roles' not in play and 'handlers' not in play
    guard = play['pre_tasks'][0]['ansible.builtin.assert']['that']
    assert 'ansible_play_hosts_all | length == 1' in guard
    assert 'ansible_limit == inventory_hostname' in guard
    assert 'ssh_recovery_exclusive_window | default(false) | bool' in guard
    assert all(not any(key.endswith(('include_role', 'import_role', 'import_playbook')) for key in task)
               for task in play['tasks'])
    writes = str(play['tasks'])
    assert 'sshd_config.d/20-' not in writes and 'site.yml' not in writes


# Reuse the real OpenSSH fixture; only service/reboot callbacks are simulated.
from test_sshd_ownership import config, CONTEXTS


def test_real_planner_transaction_and_installed_policy_round_trip(adapter, config, monkeypatch):
    import os
    monkeypatch.setattr(adapter.ownership, 'OWNER_UID', os.geteuid())
    class LocalRuntime(adapter.Runtime):
        def __init__(self):
            self.now = 1000
            self.reloads = 0
        def recovery_ready(self):
            return True
        def clock(self):
            return self.now
        def monotonic(self):
            return self.now
        def boot_id(self):
            return '00000000-0000-4000-8000-000000000001'
        def reload(self):
            self.reloads += 1
    runtime = LocalRuntime()
    import tempfile
    with tempfile.TemporaryDirectory(prefix='.sshd-state-', dir=config.parent) as state:
        root = Path(state)
        engine = adapter.transaction.Transaction(config, root, runtime)
        before = {path: path.read_bytes() for path in (config/'sshd_config.d').iterdir()}
        receipt = engine.prepare(contexts=CONTEXTS, timeout=120)
        assert receipt['status'] == 'prepared'
        engine.apply(receipt['generation'], receipt['nonce'])
        assert b'PasswordAuthentication' not in (config/'sshd_config.d/20-ansible-hardening.conf').read_bytes()
        runtime.now += 121
        assert engine.recover()['status'] == 'rolled_back'
        assert {path: path.read_bytes() for path in before} == before
        assert runtime.reloads == 2


def test_recovery_unit_identity_matches_shipped_source(adapter):
    import hashlib
    for name, expected in adapter.UNIT_HASHES.items():
        path = ROOT / 'ansible/roles/baseline/templates' / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_units_dispatch_immutable_bundle_and_grant_only_stable_lock_write(adapter):
    for name in ('vpn-sshd-boot-recover.service', 'vpn-sshd-recover.service'):
        unit = (ROOT / 'ansible/roles/baseline/templates' / name).read_text()
        assert '/usr/local/lib/vpn-sshd/sshd_bundle.py' in unit
        assert 'ProtectSystem=strict' in unit
        writes = next(line for line in unit.splitlines() if line.startswith('ReadWritePaths='))
        assert '/usr/local/lib/vpn-sshd/bundle.lock' in writes.split()
        assert '/usr/local/lib/vpn-sshd' not in writes.split()


def test_installation_uses_one_publisher_not_sequential_live_modules(adapter):
    import yaml
    play = yaml.safe_load((ROOT / 'ansible/playbooks/install-sshd-recovery.yml').read_text())[0]
    tasks = play['tasks']
    publishes = [task for task in tasks if 'ansible.builtin.command' in task
                 and 'publish' in task['ansible.builtin.command'].get('argv', [])]
    assert len(publishes) == 1
    assert all('ansible.builtin.systemd_service' not in task for task in tasks)
    assert any('/staging/' in task.get('ansible.builtin.copy', {}).get('dest', '') for task in tasks)
    assert all(task.get('ansible.builtin.copy', {}).get('dest') != '/usr/local/lib/vpn-sshd/{{ item }}'
               for task in tasks)
    bootstrap = next(task['ansible.builtin.copy'] for task in tasks
                     if task.get('ansible.builtin.copy', {}).get('dest') == '/usr/local/lib/vpn-sshd/sshd_bundle.py')
    assert bootstrap['force'] is False
    preflight = play['pre_tasks'][1]['ansible.builtin.command']['argv'][3]
    assert 'hashlib.sha256(data).hexdigest()==dispatcher_digest' in preflight


def test_installed_generation_and_controlled_links_are_checked(adapter, tmp_path, monkeypatch):
    import test_sshd_bundle
    spec = importlib.util.spec_from_file_location('bundle', FILES / 'sshd_bundle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root, state, units = (tmp_path / name for name in ('bundle', 'state', 'units'))
    root.mkdir(mode=0o755)
    (root / 'generations').mkdir(mode=0o755)
    (root / 'staging').mkdir(mode=0o700)
    (root / 'sshd_bundle.py').write_bytes((FILES / 'sshd_bundle.py').read_bytes())
    (root / 'sshd_bundle.py').chmod(0o644)
    units.mkdir(mode=0o755)
    bundle = module.Bundle(root, state, units, test_sshd_bundle.Runtime())
    generation = test_sshd_bundle.stage(bundle)
    bundle.publish(generation)
    directory = root / 'generations' / generation
    monkeypatch.setattr(adapter, 'BUNDLE_ROOT', root)
    monkeypatch.setattr(adapter, 'UNIT_ROOT', units)
    monkeypatch.setattr(adapter, '__file__', str(directory / 'sshd_migrate.py'))
    assert adapter._validate_installation() == directory
    path = units / test_sshd_bundle.UNITS[0]
    path.unlink()
    path.symlink_to('/unapproved/boot.service')
    with pytest.raises(adapter.TransactionError, match='recovery-installation-unsafe'):
        adapter._validate_installation()
