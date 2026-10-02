"""Runtime boundary rendering and encrypted restore archive safety."""

import importlib.util
import io
import ipaddress
from pathlib import Path
import tarfile
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
    assert "'stop', 'observability-kuma.service'" in fixture
    assert "'start', 'observability-kuma.service'" in fixture
    assert 'finally:' in fixture and 'signal.SIGTERM' in fixture
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
