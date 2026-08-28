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
    monkeypatch.setattr(module.Runtime, 'boot_id', lambda self: '00000000-0000-4000-8000-000000000001')
    return module


def test_boot_recovery_has_no_reload_and_normal_adapter_uses_fixed_command(adapter, monkeypatch):
    calls = []
    monkeypatch.setattr(adapter, '_command', lambda args: calls.append(args) or '')
    adapter.Runtime().reload()
    assert calls == [['/usr/bin/systemctl', 'reload', 'ssh.service']]


def test_recovery_requires_enabled_timer_and_real_ssh_dependencies(adapter, monkeypatch):
    values = installed_properties(adapter)
    monkeypatch.setattr(adapter, '_command', systemd_fixture(values))
    monkeypatch.setattr(adapter, '_validate_installation', lambda: Path('/generation') / ('a'*64))
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
        values[('show', unit, '--property=UnitFileState', '--value')] = 'enabled'
        values[('show', unit, '--property=ActiveState', '--value')] = 'active'
        values[('show', unit, '--property=SubState', '--value')] = 'waiting'
        if unit.endswith('.service'):
            values[('show', unit, '--property=SubState', '--value')] = 'dead'
            values[('show', unit, '--property=MainPID', '--value')] = '0'
            values[('show', unit, '--property=ExecMainPID', '--value')] = '100'
            values[('show', unit, '--property=ExecMainCode', '--value')] = '1'
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
    monkeypatch.setattr(adapter, '_command', systemd_fixture(values))
    monkeypatch.setattr(adapter, '_validate_installation', lambda: Path('/generation') / ('a'*64))
    assert adapter.Runtime().recovery_ready()
    values[('show', unit, '--property=' + property_name, '--value')] = value
    assert not adapter.Runtime().recovery_ready()


@pytest.mark.parametrize('unit', ['vpn-sshd-boot-recover.service', 'vpn-sshd-recover.service'])
def test_never_executed_worker_is_not_readiness_evidence(adapter, monkeypatch, unit):
    values = installed_properties(adapter)
    monkeypatch.setattr(adapter, '_command', systemd_fixture(values))
    monkeypatch.setattr(adapter, '_validate_installation', lambda: Path('/generation') / ('a'*64))
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
    monkeypatch.setattr(adapter, '_command', systemd_fixture(values))
    monkeypatch.setattr(adapter, '_validate_installation', lambda: Path('/generation') / ('a'*64))
    assert adapter.Runtime().recovery_ready()
    if fault == 'dropin':
        values[('show', 'vpn-sshd-recover.service', '--property=DropInPaths', '--value')] = '/run/systemd/system/vpn-sshd-recover.service.d/override.conf'
    elif fault == 'transient':
        values[('show', 'vpn-sshd-recover.timer', '--property=FragmentPath', '--value')] = '/run/systemd/transient/vpn-sshd-recover.timer'
    else:
        values[('show', 'vpn-sshd-boot-recover.service', '--property=UnitFileState', '--value')] = 'enabled-runtime'
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
        def activation_recovery(self):
            return object()
        def activation_fence(self, proof, acquired):
            return True
        def activation_clock(self):
            return self.now * 1000000
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


def systemd_fixture(values, calls=None):
    """The subprocess boundary exposes one coherent property set per show."""
    def command(args, **kwargs):
        if calls is not None:
            calls.append(args[1:])
        if args[1] == 'show' and args[-1] != '--value':
            unit = args[2]
            fields = args[3].removeprefix('--property=').split(',')
            return '\n'.join(name + '=' + values[('show', unit, '--property=' + name, '--value')]
                             for name in fields)
        return values[tuple(args[1:])]
    return command


def activation_fixture(adapter, monkeypatch):
    values = installed_properties(adapter)
    now = {'us': 1000000}
    calls = []
    worker = 'vpn-sshd-recover.service'
    values[('show', worker, '--property=ExecMainStatus', '--value')] = '75'
    original = systemd_fixture(values, calls)
    def command(args, **kwargs):
        if args[1:] == ['start', worker]:
            calls.append(args[1:])
            now['us'] = 1300000
            for name, value in {'ExecMainStartTimestampMonotonic':'1100000',
                                'ExecMainExitTimestampMonotonic':'1200000',
                                'ExecMainPID':'201', 'ExecMainStatus':'0', 'ExecMainCode':'1',
                                'Result':'success', 'ActiveState':'inactive', 'SubState':'dead',
                                'MainPID':'0'}.items():
                values[('show', worker, '--property='+name, '--value')] = value
            return ''
        return original(args, **kwargs)
    monkeypatch.setattr(adapter, '_command', command)
    monkeypatch.setattr(adapter, '_validate_installation', lambda: Path('/generation') / ('a'*64))
    runtime = adapter.Runtime()
    monkeypatch.setattr(runtime, 'activation_clock', lambda: now['us'], raising=False)
    monkeypatch.setattr(runtime, 'boot_id', lambda: '00000000-0000-4000-8000-000000000001')
    return runtime, values, now, calls


def test_activation_replaces_old_busy_result_with_one_fresh_completed_execution(adapter, monkeypatch):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    proof = runtime.activation_recovery()
    now['us'] = 1400000
    assert runtime.activation_fence(proof, now['us'])
    assert calls.count(['start', 'vpn-sshd-recover.service']) == 1
    assert all(call[-1] != '--value' for call in calls if call[0] == 'show')


def worker_execution(values, *, status='75', started=1500000, exited=1600000, inflight=False):
    worker = 'vpn-sshd-recover.service'
    fields = {'ExecMainPID':'202', 'ExecMainStartTimestampMonotonic':str(started),
              'ExecMainExitTimestampMonotonic':str(exited), 'ExecMainCode':'1',
              'ExecMainStatus':status, 'MainPID':'0', 'ActiveState':'inactive', 'SubState':'dead'}
    if inflight:
        fields.update(ExecMainExitTimestampMonotonic='0', ExecMainCode='0', ExecMainStatus='0',
                      MainPID='202', ActiveState='activating', SubState='start')
    for name, value in fields.items():
        values[('show', worker, '--property='+name, '--value')] = value


@pytest.mark.parametrize('inflight', [False, True])
def test_fresh_proof_survives_only_its_later_periodic_self_contention(adapter, monkeypatch, inflight):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    proof = runtime.activation_recovery()
    acquired = 1400000
    worker_execution(values, inflight=inflight)
    if inflight:
        values[('show', 'vpn-sshd-recover.timer', '--property=SubState', '--value')] = 'running'
    now['us'] = 1700000
    assert runtime.activation_fence(proof, acquired)
    assert calls.count(['start', 'vpn-sshd-recover.service']) == 1
    assert not runtime.recovery_ready()  # No fresh-call proof on this interface.


@pytest.mark.parametrize('fault', ['no-proof', 'no-success-proof', 'expired-proof', 'old-execution',
                                  'equal-lock-timestamp', 'future-execution', 'real-failure', 'inflight-before-lock',
                                  'missing-pid', 'generation', 'boot', 'boot-failed', 'boot-reexecuted',
                                  'timer-disabled', 'unit-dropin', 'daemon-reload'])
def test_activation_fence_refuses_ambiguous_or_changed_capability(adapter, monkeypatch, fault):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    proof = runtime.activation_recovery()
    acquired = 1400000
    worker_execution(values)
    now['us'] = 1700000
    worker = 'vpn-sshd-recover.service'
    def change(unit, name, value):
        values[('show', unit, '--property='+name, '--value')] = value
    if fault == 'no-proof':
        proof = None
    elif fault == 'no-success-proof':
        proof['snapshot']['units'][worker]['ExecMainStatus'] = '75'
    elif fault == 'expired-proof':
        now['us'] = proof['deadline']
    elif fault in {'old-execution', 'equal-lock-timestamp'}:
        change(worker, 'ExecMainStartTimestampMonotonic', str(acquired - (fault == 'old-execution')))
    elif fault == 'future-execution':
        worker_execution(values, started=1800000, exited=1900000)
    elif fault == 'real-failure':
        change(worker, 'ExecMainStatus', '1');change(worker, 'Result', 'exit-code')
    elif fault == 'inflight-before-lock':
        worker_execution(values, started=1300000, inflight=True)
    elif fault == 'missing-pid':
        change(worker, 'ExecMainPID', '0')
    elif fault == 'generation':
        monkeypatch.setattr(adapter, '_validate_installation', lambda: Path('/generation') / ('b'*64))
    elif fault == 'boot':
        monkeypatch.setattr(runtime, 'boot_id', lambda: '00000000-0000-4000-8000-000000000002')
    elif fault == 'boot-failed':
        change('vpn-sshd-boot-recover.service', 'Result', 'resources')
    elif fault == 'boot-reexecuted':
        change('vpn-sshd-boot-recover.service', 'ExecMainStartTimestampMonotonic', '150')
    elif fault == 'timer-disabled':
        change('vpn-sshd-recover.timer', 'UnitFileState', 'disabled')
    elif fault == 'unit-dropin':
        change(worker, 'DropInPaths', '/run/override.conf')
    elif fault == 'daemon-reload':
        change(worker, 'NeedDaemonReload', 'yes')
    assert not runtime.activation_fence(proof, acquired)
    assert calls.count(['start', 'vpn-sshd-recover.service']) == 1


def test_expired_command_deadline_never_starts_a_root_process(adapter, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('expired deadline started a process')
    monkeypatch.setattr(adapter.subprocess, 'Popen', forbidden)
    with pytest.raises(adapter.TransactionError):
        adapter._command(['/usr/bin/systemctl', 'start', 'vpn-sshd-recover.service'], deadline=0)


def test_activation_property_reads_share_one_aggregate_deadline(adapter, monkeypatch):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    original = adapter._command
    deadlines = []
    def slow(args, **kwargs):
        deadlines.append(kwargs['deadline'])
        now['us'] += 8000000
        return original(args, **kwargs)
    monkeypatch.setattr(adapter, '_command', slow)
    assert runtime.activation_recovery() is None
    assert ['start', 'vpn-sshd-recover.service'] not in calls
    assert len(deadlines) == 4 and set(deadlines) == {31.0}


@pytest.mark.parametrize('fault', ['override', 'boot-never-run', 'boot-busy', 'boot-failed', 'disabled'])
def test_activation_preflight_refuses_before_any_service_start(adapter, monkeypatch, fault):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    unit = 'vpn-sshd-boot-recover.service'
    name, value = {'override':('DropInPaths','/run/untrusted.conf'),
                   'boot-never-run':('ExecMainStartTimestampMonotonic','0'),
                   'boot-busy':('ExecMainStatus','75'), 'boot-failed':('Result','resources'),
                   'disabled':('UnitFileState','disabled')}[fault]
    values[('show', unit, '--property='+name, '--value')] = value
    assert runtime.activation_recovery() is None
    assert ['start', 'vpn-sshd-recover.service'] not in calls


@pytest.mark.parametrize('fault', ['cached', 'busy', 'failed', 'future', 'inflight', 'command-failed', 'expired'])
def test_one_start_must_produce_fresh_completed_zero_without_retry(adapter, monkeypatch, fault):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    original = adapter._command
    def start(args, **kwargs):
        result = original(args, **kwargs)
        if args[1:] == ['start', 'vpn-sshd-recover.service']:
            if fault == 'command-failed':
                raise adapter.TransactionError('command-failed')
            if fault == 'expired':
                now['us'] = 31000000
            else:
                worker_execution(values, status='75' if fault == 'busy' else '0',
                                 started=100 if fault == 'cached' else 1100000,
                                 exited=200 if fault == 'cached' else 1200000,
                                 inflight=fault == 'inflight')
                if fault == 'failed':
                    values[('show', 'vpn-sshd-recover.service', '--property=Result', '--value')] = 'exit-code'
                if fault == 'future':
                    worker_execution(values, status='0', started=1400000, exited=1500000)
        return result
    monkeypatch.setattr(adapter, '_command', start)
    assert runtime.activation_recovery() is None
    assert calls.count(['start', 'vpn-sshd-recover.service']) == 1


@pytest.mark.parametrize('inflight', [False, True])
def test_real_planner_apply_survives_periodic_race_after_second_flock(adapter, config, monkeypatch, inflight):
    import os
    import tempfile
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    monkeypatch.setattr(adapter.ownership, 'OWNER_UID', os.geteuid())
    runtime.clock = lambda: 1000
    runtime.monotonic = lambda: 1000
    reloads = []
    runtime.reload = lambda: reloads.append('reload')
    actual_fence = runtime.activation_fence
    with tempfile.TemporaryDirectory(prefix='.sshd-race-state-', dir=config.parent) as state:
        engine = adapter.transaction.Transaction(config, Path(state), runtime)
        receipt = engine.prepare(contexts=CONTEXTS, timeout=120)
        def raced_fence(proof, acquired):
            # Prove this is the real second flock, not an invented lock timestamp.
            with pytest.raises(adapter.TransactionError, match='busy'):
                engine.recover()
            worker_execution(values, started=acquired+100, exited=acquired+200, inflight=inflight)
            if inflight:
                values[('show','vpn-sshd-recover.timer','--property=SubState','--value')] = 'running'
            now['us'] = acquired + 300
            return actual_fence(proof, acquired)
        runtime.activation_fence = raced_fence
        assert engine.apply(receipt['generation'], receipt['nonce'])['status'] == 'applied'
        assert b'PasswordAuthentication' not in (config/'sshd_config.d/20-ansible-hardening.conf').read_bytes()
        assert reloads == ['reload']
        assert calls.count(['start','vpn-sshd-recover.service']) == 1


def test_activation_timestamp_uses_systemd_monotonic_clock(adapter, monkeypatch):
    clocks = []
    def read(clock):
        clocks.append(clock)
        return 123456789
    monkeypatch.setattr(adapter.time, 'clock_gettime_ns', read)
    assert adapter.Runtime().activation_clock() == 123456
    assert clocks == [adapter.time.CLOCK_MONOTONIC]


def test_recovery_command_enforces_deadline_with_a_real_child(adapter):
    import time
    started = time.monotonic()
    with pytest.raises(adapter.TransactionError, match='command-timeout'):
        adapter._command([sys.executable, '-c', 'import time; time.sleep(5)'], deadline=started + 0.1)
    assert time.monotonic() - started < 2



@pytest.mark.parametrize('fault', ['exit-one', 'failed-result', 'signaled', 'never-run',
                                  'malformed', 'inflight', 'unknown-status', 'future'])
def test_prior_periodic_failure_cannot_be_hidden_by_successful_restart(adapter, monkeypatch, fault):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    worker = 'vpn-sshd-recover.service'
    changes = {
        'exit-one': {'ExecMainStatus':'1'},
        'failed-result': {'ActiveState':'failed', 'SubState':'failed', 'Result':'exit-code', 'ExecMainStatus':'1'},
        'signaled': {'Result':'signal', 'ExecMainCode':'2', 'ExecMainStatus':'9'},
        'never-run': {'ExecMainPID':'0', 'ExecMainStartTimestampMonotonic':'0', 'ExecMainExitTimestampMonotonic':'0'},
        'malformed': {'ExecMainStartTimestampMonotonic':'unknown'},
        'inflight': {'ActiveState':'activating', 'SubState':'start', 'MainPID':'100', 'ExecMainExitTimestampMonotonic':'0'},
        'unknown-status': {'ExecMainStatus':'78'},
        'future': {'ExecMainStartTimestampMonotonic':'1100000', 'ExecMainExitTimestampMonotonic':'1200000'},
    }[fault]
    for name, value in changes.items():
        values[('show', worker, '--property='+name, '--value')] = value
    # activation_fixture deliberately resets every failed process field to a
    # successful fresh execution on start. Refusal after start would be too late.
    assert runtime.activation_recovery() is None
    assert ['start', worker] not in calls


@pytest.mark.parametrize('unit', ['vpn-sshd-boot-recover.service', 'vpn-sshd-recover.service'])
@pytest.mark.parametrize('future', ['start', 'exit'])
def test_future_execution_metrics_never_prove_readiness_or_allow_restart(adapter, monkeypatch, unit, future):
    runtime, values, now, calls = activation_fixture(adapter, monkeypatch)
    values[('show', 'vpn-sshd-recover.service', '--property=ExecMainStatus', '--value')] = '0'
    values[('show', unit, '--property=ExecMainExitTimestampMonotonic', '--value')] = '3000000'
    if future == 'start':
        values[('show', unit, '--property=ExecMainStartTimestampMonotonic', '--value')] = '2000000'
    assert not runtime.recovery_ready()
    assert runtime.activation_recovery() is None
    assert ['start', 'vpn-sshd-recover.service'] not in calls
