"""Runtime boundary rendering and encrypted restore archive safety."""

import ast
import importlib.util
import io
import json
import ipaddress
import os
import signal
import stat
import subprocess
import sys
from pathlib import Path
import tarfile
import textwrap
import time
from types import SimpleNamespace

import pytest
import yaml

from scripts.template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/observability_kuma'
SPEC = importlib.util.spec_from_file_location('kuma_backup', ROLE / 'files/observability-kuma-backup.py')
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)
PREFLIGHT_SPEC = importlib.util.spec_from_file_location('kuma_preflight', ROLE / 'files/observability-kuma-preflight.py')
preflight = importlib.util.module_from_spec(PREFLIGHT_SPEC)
PREFLIGHT_SPEC.loader.exec_module(preflight)


@pytest.mark.parametrize('check', [False, True])
@pytest.mark.parametrize('state', ['absent', 'owned', 'foreign'])
def test_container_and_image_discovery_execute_readonly_even_in_check_mode(tmp_path, state, check):
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    enabled = next(task['block'] for task in tasks if task['name'] == 'Converge the admitted independent observer')
    names = ['Inspect named container before taking lifecycle ownership',
             'Refuse unrelated container name collision', 'Inspect existing exact architecture image']
    selected = [task.copy() for task in enabled if task['name'] in names]
    trace = tmp_path / 'docker-calls'
    binary = tmp_path / 'docker'
    binary.write_text(f'''#!{sys.executable}
import json,sys
with open({str(trace)!r},'a') as stream:stream.write(sys.argv[1]+'\\n')
if {state!r}=='absent':raise SystemExit(1)
print(json.dumps([{{'Config':{{'Labels':{{'vpn-deploy.owner':{'observability-kuma' if state == 'owned' else 'foreign'!r}}}}}}}]))
''')
    binary.chmod(0o755)
    for task in selected:
        if 'ansible.builtin.command' in task:
            task['ansible.builtin.command'] = {'argv': [str(binary), *task['ansible.builtin.command']['argv'][1:]]}
    selected.append({'name': 'Require actual discovery status', 'ansible.builtin.assert': {'that': [
        f'_observability_kuma_existing.rc == {1 if state == "absent" else 0}',
        f'_observability_kuma_image.rc == {1 if state == "absent" else 0}']}})
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
             'vars': {'ansible_python_interpreter': sys.executable, 'ansible_facts': {'architecture': 'x86_64'},
                      'observability_kuma': {'image_repository': 'fixture', 'image_digests': {'x86_64': 'sha256:' + '0' * 64}}},
             'tasks': selected}]
    path = tmp_path / 'discovery.yml';path.write_text(yaml.safe_dump(play))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path), *(['--check'] if check else [])],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    assert (result.returncode == 0) is (state != 'foreign'), result.stdout + result.stderr
    assert trace.read_text().splitlines() == (['inspect'] if state == 'foreign' else ['inspect', 'image'])


@pytest.mark.parametrize('check', [False, True])
@pytest.mark.parametrize('service,timer,service_planned,timer_planned,probe_rc,accepted,actions', [
    ('loaded', 'loaded', False, False, 0, True, 2),
    ('not-found', 'not-found', True, True, 0, True, 0),
    ('not-found', 'not-found', False, True, 0, False, 0),
    ('not-found', 'not-found', True, False, 0, False, 0),
    ('loaded', 'not-found', False, True, 0, True, 1),
    ('masked', 'loaded', True, True, 0, False, 0),
    ('loaded', 'loaded', True, True, 1, False, 0),
])
def test_first_check_defers_only_exact_planned_units(tmp_path, check, service, timer, service_planned, timer_planned, probe_rc, accepted, actions):
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    enabled = next(task['block'] for task in tasks if task['name'] == 'Converge the admitted independent observer')
    names = ['Inspect observer units in check mode', 'Require planned observer service when check mode lacks it',
             'Activate pinned observer container', 'Require planned observer backup timer when check mode lacks it',
             'Enable daily quiesced encrypted backup']
    selected = [task.copy() for task in enabled if task['name'] in names]
    trace = tmp_path / 'activation-calls';binary = tmp_path / 'systemctl'
    states = {'observability-kuma.service': service, 'observability-kuma-backup.timer': timer}
    binary.write_text(f'#!{sys.executable}\nimport sys\nprint({states!r}[sys.argv[2]])\nraise SystemExit({probe_rc})\n')
    binary.chmod(0o755)
    for task in selected:
        if 'ansible.builtin.command' in task:
            task['ansible.builtin.command'] = {'argv': [str(binary), *task['ansible.builtin.command']['argv'][1:]]}
        if 'ansible.builtin.systemd_service' in task:
            # Replace only the privileged manager boundary; evaluate real admission and when conditions.
            unit = task.pop('ansible.builtin.systemd_service')['name']
            task['ansible.builtin.command'] = {'argv': [sys.executable, '-c', f'with open({str(trace)!r},"a") as f:f.write({unit!r}+"\\n")']}
            task['check_mode'] = False;task['changed_when'] = False
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
             'vars': {'ansible_python_interpreter': sys.executable,
                      '_observability_kuma_unit': {'changed': service_planned},
                      '_observability_kuma_backup_unit_templates': {'results': [{'item': 'observability-kuma-backup.timer', 'changed': timer_planned}]}},
             'tasks': selected}]
    path = tmp_path / 'activation.yml';path.write_text(yaml.safe_dump(play))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path), *(['--check'] if check else [])],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    assert (result.returncode == 0) is (accepted if check else True), result.stdout + result.stderr
    assert (len(trace.read_text().splitlines()) if trace.exists() else 0) == (actions if check else 2)


@pytest.fixture
def backup_runtime(tmp_path, monkeypatch):
    class Destination(type(tmp_path)):
        def stat(self, *args, **kwargs):
            return SimpleNamespace(st_dev=2, st_uid=0, st_mode=0o40700)

    destination = Destination(tmp_path / 'archive')
    destination.mkdir(mode=0o700)
    monkeypatch.setattr(backup, 'private_directory', lambda path: destination)
    def private_regular(path):
        path.lstat()
        return path

    monkeypatch.setattr(backup, 'private_regular', private_regular)
    monkeypatch.setattr(backup, 'DATA', SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1)))
    marker = tmp_path / 'restart-intent'
    monkeypatch.setattr(backup, 'RESTART_INTENT', marker, raising=False)
    return {'directory': str(destination), 'image': 'fixture'}, tmp_path, marker


@pytest.mark.parametrize('active', [True, False])
def test_failed_observer_stop_restores_prior_running_state(backup_runtime, monkeypatch, active):
    config, credentials, marker = backup_runtime
    monkeypatch.setattr(backup.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0 if active else 3))
    calls = []

    def command(argv):
        calls.append(argv[1])
        if argv[1] == 'stop':
            raise OSError('stop failed after interruption')

    monkeypatch.setattr(backup, 'command', command)
    with pytest.raises(OSError, match='stop failed'):
        backup.backup(config, credentials)
    assert calls == (['stop', 'start'] if active else ['stop'])
    assert not marker.exists()


def test_failed_recovery_retains_private_restart_intent(backup_runtime, monkeypatch):
    _config, _credentials, marker = backup_runtime
    backup.record_restart_intent()
    assert marker.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(backup, 'command', lambda argv: (_ for _ in ()).throw(OSError('start failed')))
    with pytest.raises(OSError, match='start failed'):
        backup.recover()
    assert marker.exists()
    started = []
    monkeypatch.setattr(backup, 'command', started.append)
    backup.recover()
    backup.recover()
    assert started == [['/usr/bin/systemctl', 'start', 'observability-kuma.service']]
    assert not marker.exists()


@pytest.mark.parametrize('failure', ['partial-write', 'file-fsync', 'publication'])
def test_restart_intent_failure_before_publication_does_not_poison_next_backup(backup_runtime, monkeypatch, failure):
    config, credentials, marker = backup_runtime
    calls = []
    monkeypatch.setattr(backup.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(backup, 'command', lambda argv: calls.append(argv[1]))
    monkeypatch.setattr(backup.subprocess, 'Popen', lambda *a, **kw: (_ for _ in ()).throw(ValueError('archive-retry')))
    with monkeypatch.context() as fault:
        if failure == 'partial-write':
            original_fdopen = os.fdopen

            class InterruptedSink:
                def __init__(self, descriptor, mode):
                    self.sink = original_fdopen(descriptor, mode)

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.sink.close()

                def write(self, data):
                    self.sink.write(data[:4])
                    self.sink.flush()
                    backup.interrupt_backup(signal.SIGTERM, None)

            fault.setattr(backup.os, 'fdopen', InterruptedSink)
        elif failure == 'file-fsync':
            original_fsync = os.fsync

            def fsync(descriptor):
                if stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise InterruptedError('intent-file-fsync')
                original_fsync(descriptor)

            fault.setattr(backup.os, 'fsync', fsync)
        else:
            fault.setattr(backup.os, 'rename', lambda *a: (_ for _ in ()).throw(InterruptedError('intent-publication')))
        with pytest.raises(InterruptedError):
            backup.backup(config, credentials)
    assert calls == []
    assert not marker.exists()
    backup.recover()
    assert calls == []
    with pytest.raises(ValueError, match='archive-retry'):
        backup.backup(config, credentials)
    assert calls == ['stop', 'start']
    assert not marker.exists()
    assert not list(marker.parent.glob('.restart-intent-*'))


def test_restart_intent_publication_preserves_retained_intent(backup_runtime):
    _config, _credentials, marker = backup_runtime
    backup.record_restart_intent()
    before = marker.stat()
    with pytest.raises(FileExistsError):
        backup.record_restart_intent()
    assert marker.read_bytes() == b'observability-kuma.service\n'
    assert marker.stat().st_ino == before.st_ino
    assert marker.stat().st_nlink == 1
    assert not list(marker.parent.glob('.restart-intent-*'))


def test_directory_fsync_failure_keeps_only_complete_recoverable_intent(backup_runtime, monkeypatch):
    _config, _credentials, marker = backup_runtime
    with monkeypatch.context() as fault:
        fault.setattr(backup, 'sync_lifecycle_directory', lambda: (_ for _ in ()).throw(OSError('intent-directory-fsync')))
        with pytest.raises(OSError, match='intent-directory-fsync'):
            backup.record_restart_intent()
    assert marker.read_bytes() == b'observability-kuma.service\n'
    assert marker.stat().st_nlink == 1
    calls = []
    monkeypatch.setattr(backup, 'command', calls.append)
    backup.recover()
    assert calls == [['/usr/bin/systemctl', 'start', 'observability-kuma.service']]
    assert not marker.exists()


@pytest.mark.parametrize('timeout', [False, True])
def test_encryption_failure_or_timeout_restores_observer(backup_runtime, monkeypatch, capsys, timeout):
    config, credentials, marker = backup_runtime
    calls = []
    killed = []
    tar = SimpleNamespace(stdout=io.BytesIO(), wait=lambda **kw: 0, poll=lambda: None, kill=lambda: killed.append(True))

    def run(argv, **kwargs):
        if argv[0] == '/usr/bin/systemctl':
            return SimpleNamespace(returncode=0)
        if timeout:
            raise subprocess.TimeoutExpired(argv, 300)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(backup.subprocess, 'run', run)
    monkeypatch.setattr(backup.subprocess, 'Popen', lambda *a, **kw: tar)
    monkeypatch.setattr(backup, 'command', lambda argv: calls.append(argv[1]))
    with pytest.raises(subprocess.TimeoutExpired if timeout else ValueError):
        backup.backup(config, credentials)
    assert calls == ['stop', 'start']
    assert killed == [True]
    assert not marker.exists()
    assert not list(Path(config['directory']).glob('*.json'))
    assert 'completed' not in capsys.readouterr().out


def test_archive_pause_fixture_preserves_actual_service_command_boundary(backup_runtime, monkeypatch):
    config, credentials, marker = backup_runtime
    calls = []

    def run(argv, **kwargs):
        calls.append(argv[1])
        if argv[1] in ['stop', 'start']:
            assert kwargs['stdout'] == subprocess.DEVNULL
            assert kwargs['stderr'] == subprocess.DEVNULL
            assert kwargs['timeout'] == 120
        return SimpleNamespace(returncode=0)

    def paused_archive(*args, **kwargs):
        assert kwargs['stdout'] == subprocess.PIPE
        assert marker.exists()
        raise InterruptedError('archive-pause interrupted')

    tree = ast.parse((ROLE / 'molecule/runtime/active-backup-fixture.py').read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute) and target.attr == 'subprocess' for target in node.targets))
    runtime = SimpleNamespace(run=run, PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL)
    monkeypatch.setattr(backup, 'subprocess', runtime)
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), '<owned-archive-fixture>', 'exec'), {'backup': backup, 'subprocess': runtime, 'SimpleNamespace': SimpleNamespace, 'paused_archive': paused_archive})
    with pytest.raises(InterruptedError, match='archive-pause interrupted'):
        backup.backup(config, credentials)
    assert calls == ['is-active', 'stop', 'start']
    assert not marker.exists()
    assert not list(Path(config['directory']).glob('*.json'))


def test_backup_unit_recovers_forced_death_without_credentials():
    unit = render('observability-kuma-backup.service.j2')
    assert 'ExecStopPost=/usr/bin/python3 /usr/local/libexec/observability-kuma-backup.py recover' in unit
    assert 'TimeoutStopSec=150' in unit


def test_recover_entrypoint_needs_no_backup_configuration_or_credentials(backup_runtime, monkeypatch):
    _config, root, marker = backup_runtime
    backup.record_restart_intent()
    calls = []
    monkeypatch.setattr(backup, 'command', calls.append)
    monkeypatch.setattr(backup, 'open', lambda *args, **kwargs: open(root / 'lock', 'a'), raising=False)
    monkeypatch.setattr(backup.sys, 'argv', ['backup-helper', 'recover'])
    monkeypatch.delenv('CREDENTIALS_DIRECTORY', raising=False)
    assert backup.main() == 0
    assert calls == [['/usr/bin/systemctl', 'start', 'observability-kuma.service']]
    assert not marker.exists()


@pytest.mark.parametrize('termination', [signal.SIGTERM, signal.SIGKILL])
@pytest.mark.parametrize('phase', ['archive', 'intent-write'])
def test_production_backup_termination_and_separate_recovery(tmp_path, termination, phase):
    runner = tmp_path / 'runner.py'
    runner.write_text(textwrap.dedent(f'''
        import importlib.util
        import os
        from pathlib import Path
        import signal
        import sys
        from types import SimpleNamespace
        spec = importlib.util.spec_from_file_location('backup', {str(ROLE / 'files/observability-kuma-backup.py')!r})
        backup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backup)
        root = Path({str(tmp_path)!r})
        class Destination(type(root)):
            def stat(self, *args, **kwargs):
                return SimpleNamespace(st_dev=2, st_uid=0, st_mode=0o40700)
        destination = Destination(root / 'archive')
        destination.mkdir(mode=0o700, exist_ok=True)
        backup.private_directory = lambda path: destination
        def regular(path):
            path.lstat()
            return path
        backup.private_regular = regular
        backup.DATA = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1))
        backup.RESTART_INTENT = root / 'restart-intent'
        backup.subprocess.run = lambda *a, **kw: SimpleNamespace(returncode=0)
        def command(argv):
            (root / 'state').write_text('inactive' if argv[1] == 'stop' else 'active')
        backup.command = command
        def paused_archive(*args, **kwargs):
            (root / 'ready').write_text('quiesced')
            signal.pause()
            raise ValueError('archive interrupted')
        backup.subprocess.Popen = paused_archive
        if len(sys.argv) > 2 and sys.argv[2] == 'intent-write':
            original_fdopen = os.fdopen
            class PausedSink:
                def __init__(self, descriptor, mode):
                    self.sink = original_fdopen(descriptor, mode)
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    self.sink.close()
                def write(self, data):
                    self.sink.write(data[:4])
                    self.sink.flush()
                    (root / 'ready').write_text('partial-intent')
                    signal.pause()
                    raise ValueError('intent write interrupted')
            backup.os.fdopen = PausedSink
        if sys.argv[1] == 'recover':
            backup.recover()
        else:
            (root / 'state').write_text('active')
            backup.backup({{'directory': str(destination), 'image': 'fixture'}}, root)
    '''))
    process = subprocess.Popen([sys.executable, str(runner), 'backup', phase], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / 'ready').exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert (tmp_path / 'state').read_text() == ('inactive' if phase == 'archive' else 'active')
        assert (tmp_path / 'restart-intent').exists() == (phase == 'archive')
        if phase == 'intent-write':
            staged = list(tmp_path.glob('.restart-intent-*'))
            assert len(staged) == 1
            assert staged[0].read_bytes() == b'obse'
            assert staged[0].stat().st_mode & 0o777 == 0o600
        process.send_signal(termination)
        process.communicate(timeout=10)
        assert process.returncode != 0
        if termination == signal.SIGTERM or phase == 'intent-write':
            assert (tmp_path / 'state').read_text() == 'active'
            assert not (tmp_path / 'restart-intent').exists()
        else:
            assert (tmp_path / 'state').read_text() == 'inactive'
            assert (tmp_path / 'restart-intent').exists()
        subprocess.run([sys.executable, str(runner), 'recover'], check=True, timeout=10)
        assert (tmp_path / 'state').read_text() == 'active'
        assert not (tmp_path / 'restart-intent').exists()
        assert not list((tmp_path / 'archive').glob('*.json'))
        if phase == 'intent-write':
            (tmp_path / 'ready').unlink()
            process = subprocess.Popen([sys.executable, str(runner), 'backup', 'archive'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 10
            while not (tmp_path / 'ready').exists():
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert (tmp_path / 'state').read_text() == 'inactive'
            process.send_signal(signal.SIGTERM)
            process.communicate(timeout=10)
            assert (tmp_path / 'state').read_text() == 'active'
            assert not (tmp_path / 'restart-intent').exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def render(name, **overrides):
    values = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())
    values['observability_kuma'].update(bind_address='100.64.0.8', allowed_sources=['100.64.0.1/32'], backup_directory='/mnt/backup/kuma')
    values.update(ansible_facts={'architecture': 'aarch64'}, item='node', _observability_kuma_tls_generation='a' * 64)
    values.update(overrides)
    return render_template(ROLE / 'templates' / name, values)


def test_container_exact_arch_pin_loopback_and_resource_bounds():
    unit = render('observability-kuma.service.j2')
    assert 'ghcr.io/po4yka/ripdpi-vpn-deploy/observability-kuma@sha256:5251f0642523e6ce5dfffa2d1f0f5f0067201e3df14cc39b092b6827ecf6da38' in unit
    for option in ['--publish 127.0.0.1:13001:3001', '--memory 536870912', '--memory-swap 536870912', '--cpus 0.25', '--pids-limit 128', '--user 1000:1000', '--cap-drop ALL', '--read-only', '--log-driver none']:
        assert option in unit
    assert 'docker.sock' not in unit and '--privileged' not in unit and '--network host' not in unit
    assert 'StandardOutput=null' in unit and 'StandardError=null' in unit


def test_private_ingress_exposes_no_admin_and_logs_no_push_url():
    config = render('observability-kuma.conf.j2')
    assert 'listen 100.64.0.8:9444 ssl;' in config
    assert 'allow 100.64.0.1/32;' in config and 'deny all;' in config
    assert 'access_log off;' in config and 'error_log /dev/null emerg;' in config
    assert 'location / { return 404; }' in config
    assert 'limit_except GET { deny all; }' in config
    assert 'if ($args != "") { return 400; }' in config
    assert 'ssl_protocols TLSv1.2 TLSv1.3;' in config
    assert 'set_real_ip_from unix:;' in config
    assert 'real_ip_recursive off;' in config


@pytest.mark.parametrize('kind,seconds', [('node', '60s'), ('pipeline', '60s'), ('delivery', '300s')])
def test_push_systemd_credentials_and_slice(kind, seconds):
    unit = render('observability-push.service.j2', item=kind)
    timer = render('observability-push.timer.j2', item=kind)
    assert 'LoadCredential=push-token:' in unit and 'Slice=observability-agent.slice' in unit
    assert 'LoadCredential=observer-ca:' in unit
    assert 'ExecStart=/usr/bin/python3 /usr/local/libexec/observability-push.py ' + kind in unit
    assert 'OnUnitActiveSec=' + seconds in timer and 'Persistent=true' in timer
    for option in ['NoNewPrivileges', 'PrivateTmp', 'ProtectHome', 'ProtectKernelTunables', 'ProtectKernelModules', 'ProtectControlGroups', 'RestrictNamespaces', 'LockPersonality', 'RestrictRealtime', 'RestrictSUIDSGID']:
        assert option + '=true' in unit


def archive(member):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as output:
        output.addfile(member, io.BytesIO(b'ok') if member.isfile() else None)
    stream.seek(0)
    return stream


@pytest.mark.parametrize('name,kind', [('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE), ('fifo', tarfile.FIFOTYPE), ('hard', tarfile.LNKTYPE)])
def test_restore_rejects_escape_and_special_members(tmp_path, name, kind):
    member = tarfile.TarInfo(name)
    member.type = kind
    member.size = 2 if kind == tarfile.REGTYPE else 0
    with pytest.raises(ValueError, match='unsafe-archive-member'):
        backup.extract_private(archive(member), tmp_path)


def test_restore_positive_regular_archive(tmp_path, monkeypatch):
    member = tarfile.TarInfo('./kuma.db')
    member.size = 2
    monkeypatch.setattr(backup.os, 'chown', lambda *a: None)
    backup.extract_private(archive(member), tmp_path)
    assert (tmp_path / 'kuma.db').read_bytes() == b'ok'
    assert (tmp_path / 'kuma.db').stat().st_mode & 0o777 == 0o600


def test_restore_keeps_parents_writable_until_archive_is_complete(tmp_path, monkeypatch):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as output:
        root = tarfile.TarInfo('.')
        root.type = tarfile.DIRTYPE
        output.addfile(root)
        member = tarfile.TarInfo('./nested/kuma.db')
        member.size = 2
        output.addfile(member, io.BytesIO(b'ok'))
    stream.seek(0)
    owned = []

    def change_owner(path, uid, gid):
        assert (tmp_path / 'nested/kuma.db').read_bytes() == b'ok'
        assert (uid, gid) == (1000, 1000)
        owned.append(Path(path))

    monkeypatch.setattr(backup.os, 'chown', change_owner)
    backup.extract_private(stream, tmp_path)
    assert owned == [tmp_path / 'nested/kuma.db', tmp_path / 'nested', tmp_path]


def test_observer_disable_and_rotation_serialize_active_backups():
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    inspect = next(task for task in tasks if task['name'] == 'Inspect observer units for safe disable on absent deployment')
    assert inspect['loop'] == ['observability-kuma-backup.timer', 'observability-kuma-backup.service', 'observability-kuma.service']
    disable = next(task for task in tasks if task['name'] == 'Stop observer without removing secret data or backup when disabled')
    assert disable['ansible.builtin.systemd_service']['enabled'] == "{{ omit if item.item == 'observability-kuma-backup.service' else false }}"
    converge = next(task['block'] for task in tasks if task['name'] == 'Converge the admitted independent observer')
    quiesce = next(task for task in converge if task['name'] == 'Quiesce timer then active backup before changing runtime or image')
    assert quiesce['ansible.builtin.systemd_service']['enabled'] == "{{ false if item.item == 'observability-kuma-backup.timer' else omit }}"
    names = [task['name'] for task in converge]
    assert names.index('Quiesce timer then active backup before changing runtime or image') < names.index('Require consistent encrypted backup before a pinned image change')
    assert names.index('Quiesce timer then active backup before changing runtime or image') < names.index('Install private backup configuration')
    assert names.index('Activate pinned observer container') < names.index('Enable daily quiesced encrypted backup')


def test_linux_regression_invokes_production_extractor_without_dac_override():
    scenario = yaml.safe_load((ROLE / 'molecule/default/verify.yml').read_text())[0]['tasks']
    task = next(task for task in scenario if task['name'].startswith('Exercise production restore extractor'))
    arguments = task['ansible.builtin.command']['argv']
    assert '--property=CapabilityBoundingSet=CAP_CHOWN CAP_DAC_READ_SEARCH' in arguments
    assert '--property=NoNewPrivileges=true' in arguments
    source = (ROLE / 'molecule/runtime/restore-capabilities.py').read_text()
    assert "runpy.run_path('/usr/local/libexec/observability-kuma-backup.py')['extract_private']" in source
    assert "('.', './nested')" in source
    assert "('CapEff', 'CapPrm', 'CapBnd')" in source
    assert 'except PermissionError:' in source


def test_disable_scenario_exercises_real_running_backup_finalizer():
    fixture = (ROLE / 'molecule/runtime/active-backup-fixture.py').read_text()
    assert "'/usr/local/libexec/observability-kuma-backup.py'" in fixture
    assert 'backup.backup(' in fixture
    assert 'backup.subprocess = SimpleNamespace(run=subprocess.run, Popen=paused_archive,' in fixture
    assert 'signal.signal' not in fixture and 'finally:' not in fixture
    verification = (ROLE / 'molecule/default/verify.yml').read_text()
    assert 'backup-finalizer-ran' in verification
    assert '- observability-kuma-backup.service' in verification


def test_restore_stays_network_isolated_and_preserves_both_datasets():
    source = (ROLE / 'files/observability-kuma-backup.py').read_text()
    assert "'--network', 'none'" in source
    assert "'--publish'" not in source
    assert 'shutil.rmtree' not in source
    assert "'stop', '--time', '30', name" in source
    assert 'extract_private' in source and 'archive_digest' in source


def test_no_new_dependencies_or_vpn_baseline_on_observer():
    tasks = (ROLE / 'tasks/main.yml').read_text()
    assert 'ansible.builtin.apt' not in tasks
    assert 'sites-enabled/default' not in tasks
    assert 'observability-kuma.conf' in tasks
    playbook = (ROOT / 'ansible/playbooks/observability-kuma.yml').read_text()
    assert 'role: baseline' not in playbook and 'role: firewall' not in playbook


@pytest.fixture
def admission(tmp_path, monkeypatch):
    config = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())['observability_kuma']
    data = tmp_path / 'data'
    data.mkdir()
    destination = tmp_path / 'backup'
    destination.mkdir(mode=0o700)
    memory = tmp_path / 'meminfo'
    memory.write_text('MemAvailable:    2097152 kB\n')
    config.update(bind_address='100.64.0.8', allowed_sources=['100.64.0.1/32'], data_dir=str(data), backup_directory=str(destination))
    original = preflight.os.stat
    def inspect(path, **kwargs):
        info = original(path, **kwargs)
        if str(path) == str(destination):
            return SimpleNamespace(st_mode=info.st_mode, st_uid=0, st_dev=info.st_dev + 1)
        return info
    monkeypatch.setattr(preflight.os, 'stat', inspect)
    monkeypatch.setattr(preflight, 'private_directory', Path)
    def run(command, **kwargs):
        return SimpleNamespace(stdout='ext4\n')
    return config, memory, run


def test_positive_observer_preflight_requires_existing_dependencies(admission):
    config, memory, run = admission
    preflight.check(config, proc=memory, usage=lambda _: SimpleNamespace(total=100 * 1024**3, free=30 * 1024**3), run=run, bind=lambda _: None)


@pytest.mark.parametrize('failure', ['memory', 'disk', 'filesystem', 'public-source', 'broad-source', 'public-bind', 'nonlocal-bind', 'self-source'])
def test_observer_admission_failure_before_mutation(admission, failure):
    config, memory, run = admission
    free = 30 * 1024**3
    if failure == 'memory':
        memory.write_text('MemAvailable: 1024 kB\n')
    elif failure == 'disk':
        free = 6 * 1024**3
    elif failure == 'filesystem':
        run = lambda *a, **k: SimpleNamespace(stdout='nfs4\n')
    elif failure == 'public-source':
        config['allowed_sources'] = ['8.8.8.8/32']
    elif failure == 'broad-source':
        config['allowed_sources'] = ['100.64.0.0/10']
    elif failure == 'public-bind':
        config['bind_address'] = '8.8.8.8'
    elif failure == 'self-source':
        config['allowed_sources'] = ['100.64.0.8/32']
    def bind(_address):
        if failure == 'nonlocal-bind':
            raise OSError('address not available')
    with pytest.raises((ValueError, OSError)):
        preflight.check(config, proc=memory, usage=lambda _: SimpleNamespace(total=100 * 1024**3, free=free), run=run, bind=bind)


def test_local_address_uses_real_socket_bind(monkeypatch):
    bindings = []
    class Socket:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def bind(self, value):
            bindings.append(value)
            raise OSError('not assigned')
    monkeypatch.setattr(preflight.socket, 'socket', lambda *a: Socket())
    with pytest.raises(ValueError, match='local-private-address'):
        preflight.local_address(ipaddress.ip_address('100.64.0.8'))
    assert bindings == [('100.64.0.8', 0)]


@pytest.mark.parametrize('unsafe', ['symlink', 'writable', 'foreign-owner', 'none'])
def test_backup_ancestry_is_private_and_root_controlled(tmp_path, monkeypatch, unsafe):
    ancestor = tmp_path / 'parent'
    ancestor.mkdir(mode=0o755)
    target = ancestor / 'backup'
    target.mkdir(mode=0o700)
    if unsafe == 'symlink':
        link = tmp_path / 'link'
        link.symlink_to(ancestor, target_is_directory=True)
        target = link / 'backup'
    if unsafe == 'writable':
        ancestor.chmod(0o777)
    original = Path.lstat
    def inspect(path):
        info = original(path)
        mode = info.st_mode
        # Ancestors outside this fixture are represented as safe root dirs;
        # actual target type and unsafe fixture ancestry remain unchanged.
        if path not in (target, ancestor, tmp_path / 'link'):
            mode = (mode & ~0o777) | 0o755
        return SimpleNamespace(st_mode=mode, st_uid=1234 if path == ancestor and unsafe == 'foreign-owner' else 0)
    monkeypatch.setattr(Path, 'lstat', inspect)
    if unsafe == 'none':
        assert preflight.private_directory(target) == target
    else:
        with pytest.raises(ValueError, match='backup-path-boundary'):
            preflight.private_directory(target)


def test_backup_restore_reuses_admission_ancestor_check():
    source = (ROLE / 'files/observability-kuma-backup.py').read_text()
    assert "private_directory(config['directory'])" in source
    assert 'private_directory(RESTORES)' in source


@pytest.mark.parametrize("selection", ["current", "previous", "foreign-current", "foreign-previous", "other-architecture"])
def test_restore_accepts_only_explicit_current_and_previous_images(backup_runtime, monkeypatch, selection):
    import hashlib

    config, credentials, _ = backup_runtime
    current = "ghcr.io/example/observer@sha256:" + "a" * 64
    previous = "louislam/uptime-kuma@sha256:" + "b" * 64
    choices = {"current": current, "previous": previous,
               "foreign-current": "ghcr.io/example/observer@sha256:" + "c" * 64,
               "foreign-previous": "louislam/uptime-kuma@sha256:" + "c" * 64,
               "other-architecture": "ghcr.io/example/observer@sha256:" + "d" * 64}
    config.update(image=current, restore_images=[current, previous])
    identity = "20261102T000000Z-" + "e" * 32
    directory = Path(config["directory"])
    archive = b"synthetic encrypted archive"
    (directory / (identity + ".tar.age")).write_bytes(archive)
    (directory / (identity + ".json")).write_text(json.dumps({"schema_version": 1, "sha256": hashlib.sha256(archive).hexdigest(), "image": choices[selection]}))
    restores = credentials / "restores"
    restores.mkdir()
    monkeypatch.setattr(backup, "RESTORES", restores)
    monkeypatch.setattr(backup.shutil, "disk_usage", lambda path: SimpleNamespace(free=9 * 1024**3))
    class DecryptionBoundary(Exception):
        pass
    def decrypt(*args, **kwargs):
        assert selection in ["current", "previous"], "Unapproved image reached decryption"
        raise DecryptionBoundary
    monkeypatch.setattr(backup.subprocess, "Popen", decrypt)
    if selection in ["current", "previous"]:
        with pytest.raises(DecryptionBoundary):
            backup.restore(config, credentials, identity)
    else:
        with pytest.raises(ValueError, match="archive-integrity"):
            backup.restore(config, credentials, identity)


@pytest.mark.parametrize("architecture", ["x86_64", "aarch64"])
@pytest.mark.parametrize("foreign", [False, True])
def test_observer_admission_rejects_foreign_previous_image(tmp_path, architecture, foreign):
    import copy

    role = ROOT / "ansible/roles/observability_kuma"
    values = yaml.safe_load((role / "defaults/main.yml").read_text())["observability_kuma"]
    values.update(host_alias="localhost", admission_approved=True, backup_directory="/srv/observer-backup")
    if foreign:
        values["previous_image_references"][architecture] = "example.invalid/observer@sha256:" + "f" * 64
    admission = copy.deepcopy(yaml.safe_load((role / "tasks/main.yml").read_text())[0])
    play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
             "vars": {"observability_kuma": values, "ansible_facts": {"architecture": architecture}},
             "tasks": [admission]}]
    path = tmp_path / "admission.yml"
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)], capture_output=True, text=True, timeout=30,
                            env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")})
    assert (result.returncode == 0) is (not foreign), result.stdout + result.stderr


def load_address_waiter():
    spec = importlib.util.spec_from_file_location("kuma_wait_address", ROLE / "files/observability-kuma-wait-address.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("address", ["127.0.0.1", "::1"])
def test_ingress_wait_accepts_assigned_native_loopback(tmp_path, address):
    values = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["observability_kuma"]
    values.update(bind_address=address, allowed_sources=[])
    path = tmp_path / "nginx.conf"
    path.write_text(render("observability-kuma.conf.j2", observability_kuma=values))
    module = load_address_waiter()
    assert module.listener_address(path) == address
    module.wait_address(module.listener_address(path))


@pytest.mark.parametrize("failure", ["delayed", "timeout", "denied"])
def test_ingress_wait_only_waits_for_unassigned_address(monkeypatch, failure):
    import errno

    module = load_address_waiter()
    attempts = []
    class Probe:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def bind(self, endpoint):
            attempts.append(endpoint)
            if failure == "denied":
                raise PermissionError(errno.EACCES, "denied")
            if failure == "timeout" or len(attempts) < 3:
                raise OSError(errno.EADDRNOTAVAIL, "not assigned")
    monkeypatch.setattr(module.socket, "socket", lambda *args: Probe())
    clock = iter([0, 61] if failure == "timeout" else [0, 1, 2])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(module.time, "sleep", lambda duration: None)
    if failure == "delayed":
        module.wait_address("192.0.2.10")
        assert attempts == [("192.0.2.10", 0)] * 3
    else:
        with pytest.raises(TimeoutError if failure == "timeout" else PermissionError):
            module.wait_address("192.0.2.10")
        assert len(attempts) == 1


def test_ingress_boot_wait_uses_exact_private_address_and_is_removed_on_disable():
    unit = render("observability-kuma-nginx-start.conf.j2")
    assert "ExecCondition=/usr/bin/python3 -Es /usr/local/libexec/observability-kuma-wait-address.py\n" in unit
    assert "ExecStartPre=" not in unit
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    disabled = next(t["block"] for t in tasks if t["name"].startswith("Remove only disabled observer ingress"))
    removal = next(t for t in disabled if t["name"] == "Remove only disabled observer startup policy")
    assert removal["loop"] == ["/etc/systemd/system/nginx.service.d/observability-kuma.conf", "/usr/local/libexec/observability-kuma-wait-address.py"]


@pytest.mark.parametrize("state", ["ready", "invalid", "denied"])
def test_ingress_start_condition_returns_success_or_unit_failure(tmp_path, monkeypatch, capsys, state):
    module = load_address_waiter()
    path = tmp_path / "nginx.conf"
    path.write_text("invalid listener" if state == "invalid" else "listen 127.0.0.1:9444 ssl;\n")
    module.CONFIG = path
    if state == "denied":
        def denied_socket(*args):
            raise PermissionError(13, "denied")
        monkeypatch.setattr(module.socket, "socket", denied_socket)
    assert module.main() == (0 if state == "ready" else 255)
    assert capsys.readouterr().err == ("" if state == "ready" else "private ingress address unavailable\n")


@pytest.mark.parametrize("previous_policy", [False, True])
def test_failed_ingress_migration_preserves_boot_policy_pair(tmp_path, previous_policy):
    import copy

    module = load_address_waiter()
    old = tmp_path / "old.conf"
    candidate = tmp_path / "candidate.conf"
    current = tmp_path / "current.conf"
    policy = tmp_path / "startup.conf"
    old.write_text(render("observability-kuma.conf.j2"))
    values = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["observability_kuma"]
    values.update(bind_address="100.64.0.9", allowed_sources=["100.64.0.1/32"])
    candidate.write_text(render_template(ROLE / "templates/observability-kuma.conf.j2", {
        "observability_kuma": values, "_observability_kuma_tls_generation": "b" * 64}))
    current.symlink_to(old)
    if previous_policy:
        policy.write_text("previous startup policy\n")
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    enabled = next(t["block"] for t in tasks if t["name"] == "Converge the admitted independent observer")
    activation = next(t for t in enabled if "rescue" in t)
    rejection = tmp_path / "nginx-rejected"
    selected = copy.deepcopy([t for t in enabled if t is activation or t["name"] == "Require private address readiness before shared nginx starts"])
    for task in selected:
        if "block" in task:
            for step in task["block"] + task["rescue"]:
                operation = step.get("ansible.builtin.file")
                if operation:
                    operation["dest" if "dest" in operation else "path"] = str(current)
                    if "src" in operation and "_observability_kuma_previous_ingress" not in operation["src"]:
                        operation["src"] = str(candidate)
                if "ansible.builtin.command" in step:
                    step["ansible.builtin.command"]["argv"] = [sys.executable, "-c", f"from pathlib import Path;Path({str(rejection)!r}).write_text('rejected');raise SystemExit(1)"]
        else:
            task["ansible.builtin.template"].update(src=str(ROLE / "templates/observability-kuma-nginx-start.conf.j2"),
                dest=str(policy), owner=str(os.getuid()), group=str(os.getgid()))
    play = [{"hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": {"_observability_kuma_previous_ingress": {"stat": {"exists": True, "islnk": True, "lnk_source": str(old)}}},
        "tasks": selected}]
    path = tmp_path / "migration.yml"
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)], capture_output=True, text=True, timeout=30,
        env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")})
    assert result.returncode != 0
    assert rejection.read_text() == "rejected"
    assert current.resolve() == old
    assert module.listener_address(current) == "100.64.0.8"
    assert policy.exists() is previous_policy
    if previous_policy:
        assert policy.read_text() == "previous startup policy\n"


@pytest.mark.parametrize("listener", ["", "listen 0.0.0.0:9444 ssl;", "listen 127.0.0.1:9444 ssl;\nlisten [::1]:9444 ssl;"])
def test_boot_address_parser_refuses_missing_wildcard_or_multiple_listeners(tmp_path, listener):
    path = tmp_path / "nginx.conf"
    path.write_text(listener)
    with pytest.raises(ValueError):
        load_address_waiter().listener_address(path)


def test_render_check_sends_only_observer_vhost_to_nginx(monkeypatch, tmp_path):
    import shutil

    spec = importlib.util.spec_from_file_location("check_templates", ROOT / "scripts/check-templates-render.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    templates = tmp_path / "ansible/roles/observability_kuma/templates"
    templates.mkdir(parents=True)
    for name in ["observability-kuma.conf.j2", "observability-kuma-nginx-start.conf.j2"]:
        shutil.copyfile(ROLE / "templates" / name, templates / name)
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(checker, "ROLES_DIR", tmp_path / "ansible/roles")
    checked = []
    monkeypatch.setattr(checker, "validate_nginx", lambda text, label: checked.append(label))
    assert checker.main() == 0
    assert checked == ["ansible/roles/observability_kuma/templates/observability-kuma.conf.j2"]
