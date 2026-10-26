"""Runtime boundary rendering and encrypted restore archive safety."""

import ast
import importlib.util
import io
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
    assert '@sha256:c95c90afb9b774cfe78af58dc7660b47f955fb7edce9fd92b048f734b0d65cdb' in unit
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
