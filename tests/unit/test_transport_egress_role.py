"""Executable private role helper contracts; native systemd proof is separate."""
from __future__ import annotations
import base64
import configparser
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/transport-egress'

@pytest.fixture(autouse=True)
def runtime_library(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'ansible/roles/runtime-release/files'))

def load(name):
    path = ROLE / 'files' / (name + '.py')
    spec = importlib.util.spec_from_file_location('egress_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generation_exact_selected_units_and_identity():
    mod = load('generation')
    normalizer = {'runtime_uid': 1001, 'backends': {'direct': {}}, 'listeners': []}
    config = {'schema_version': 1, 'normalizer_uid': 1001,
              'gateway_units': ['ripdpi-transport-direct.service'],
              'frontend_units': ['xray.service'], 'control_timeout_seconds': 30,
              'recovery_seconds': 5}
    assert mod.validate(config, normalizer) == config
    for field, value in [('frontend_units', ['ssh.service']),
                         ('gateway_units', ['ripdpi-transport-warp.service']),
                         ('normalizer_uid', 0), ('control_timeout_seconds', 61)]:
        with pytest.raises(mod.Refusal):
            mod.validate({**config, field: value}, normalizer)


@pytest.mark.parametrize('unit,option', [('xray.service', '-config'), ('hysteria-server.service', '-c')])
@pytest.mark.parametrize('selection', ['default', 'custom', 'relative', 'traversal', 'duplicate', 'writable', 'hardlink', 'foreign-owner', 'fifo'])
def test_generation_reads_configuration_from_exact_owned_unit(tmp_path, monkeypatch, unit, option, selection):
    import os
    from types import SimpleNamespace
    mod = load('generation')
    monkeypatch.setattr(mod, 'UNIT_ROOT', tmp_path)
    path = '/etc/selected/config.yaml' if selection == 'custom' else '/etc/hysteria/config.yaml'
    if selection == 'relative':
        path = 'config.yaml'
    elif selection == 'traversal':
        path = '/etc/hysteria/../config.yaml'
    text = 'ExecStart=/owned/runtime run ' + option + ' ' + path + '\n'
    if selection == 'duplicate':
        text += text
    target = tmp_path / unit
    target.write_text(text)
    target.chmod(0o666 if selection == 'writable' else 0o644)
    if selection == 'hardlink':
        os.link(target, tmp_path / 'other-unit')
    elif selection == 'fifo':
        target.unlink()
        os.mkfifo(target)
    def owned_stat(fd):
        info = os.fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=1 if selection == 'foreign-owner' else 0,
                               st_nlink=info.st_nlink, st_size=info.st_size)
    monkeypatch.setattr(mod, 'os', SimpleNamespace(open=os.open, read=os.read, close=os.close,
                        fstat=owned_stat, O_RDONLY=os.O_RDONLY, O_NOFOLLOW=os.O_NOFOLLOW,
                        O_NONBLOCK=os.O_NONBLOCK, O_CLOEXEC=os.O_CLOEXEC))
    if selection in {'default', 'custom'}:
        assert mod.frontend_config_path(unit) == Path(path)
    else:
        with pytest.raises(mod.Refusal):
            mod.frontend_config_path(unit)


@pytest.mark.parametrize('variant', [
    'canonical', 'reserialized', 'flow', 'wrong-address', 'wrong-user', 'wrong-password',
    'extra-outbound', 'wrong-type', 'wrong-name', 'extra-socks-field', 'missing-socks',
    'duplicate-root', 'duplicate-password', 'duplicate-name', 'merge-key',
    'malformed', 'scalar', 'non-string-key', 'unsafe-tag', 'invalid-map', 'invalid-map-sequence',
    'control-character', 'multiple-documents', 'too-deep',
])
def test_generation_hysteria_credentials_follow_yaml_authority(tmp_path, monkeypatch, variant):
    import os
    from types import SimpleNamespace
    mod = load('generation')
    expected = {'name': 'direct_hysteria', 'address': '127.0.0.1', 'port': 12081,
                'username': 'normalizer-direct-hysteria', 'password': 'synthetic-authority'}
    raw = '''outbounds:
  - name: guarded-direct
    type: socks5
    socks5:
      addr: "127.0.0.1:12081"
      username: "normalizer-direct-hysteria"
      password: "synthetic-authority"
'''
    document = yaml.safe_load(raw)
    outbound = document['outbounds'][0]
    if variant in {'reserialized', 'flow'}:
        raw = yaml.safe_dump(document, default_flow_style=variant == 'flow')
        assert yaml.safe_load(raw) == document
    elif variant in {'wrong-address', 'wrong-user', 'wrong-password'}:
        field = {'wrong-address': 'addr', 'wrong-user': 'username', 'wrong-password': 'password'}[variant]
        outbound['socks5'][field] = 'synthetic-mismatch'
        raw = yaml.safe_dump(document)
    elif variant == 'extra-outbound':
        document['outbounds'].append({'name': 'unguarded', 'type': 'direct'})
        raw = yaml.safe_dump(document)
    elif variant in {'wrong-type', 'wrong-name'}:
        outbound['type' if variant == 'wrong-type' else 'name'] = 'unguarded'
        raw = yaml.safe_dump(document)
    elif variant == 'extra-socks-field':
        outbound['socks5']['unexpected'] = True
        raw = yaml.safe_dump(document)
    elif variant == 'missing-socks':
        del outbound['socks5']
        raw = yaml.safe_dump(document)
    elif variant == 'duplicate-root':
        raw += raw
    elif variant == 'duplicate-password':
        raw += '      password: "synthetic-authority"\n'
    elif variant == 'duplicate-name':
        raw += '    name: guarded-direct\n'
    elif variant == 'merge-key':
        raw += '    <<: {type: direct}\n'
    elif variant == 'malformed':
        raw = 'outbounds: [\n'
    elif variant == 'scalar':
        raw = 'synthetic-authority\n'
    elif variant == 'non-string-key':
        raw += '42: synthetic-authority\n'
    elif variant == 'unsafe-tag':
        raw = '!!python/object/apply:builtins.print [synthetic-authority]\n'
    elif variant == 'invalid-map':
        raw = '!!map synthetic-authority\n'
    elif variant == 'invalid-map-sequence':
        raw = '!!map [synthetic-authority]\n'
    elif variant == 'control-character':
        raw += '\x00'
    elif variant == 'multiple-documents':
        raw += '---\n' + raw
    elif variant == 'too-deep':
        raw = '[' * 1500 + 'synthetic-authority' + ']' * 1500
    path = tmp_path / 'config.yaml'
    path.write_text(raw)
    path.chmod(0o640)
    monkeypatch.setattr(mod, 'frontend_config_path', lambda _unit: path)
    def owned_stat(fd):
        info = os.fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=0,
                               st_nlink=info.st_nlink, st_size=info.st_size)
    monkeypatch.setattr(mod, 'os', SimpleNamespace(open=os.open, read=os.read, close=os.close,
                        fstat=owned_stat, O_RDONLY=os.O_RDONLY, O_NOFOLLOW=os.O_NOFOLLOW))
    controller = object.__new__(mod.Controller)
    controller.config = {'frontend_units': ['hysteria-server.service']}
    controller.normalizer = {'listeners': [expected]}
    if variant in {'canonical', 'reserialized', 'flow'}:
        controller.frontend_credentials()
    else:
        with pytest.raises(mod.Refusal, match='^generation-frontend-(authority-invalid|credential-mismatch)$') as error:
            controller.frontend_credentials()
        assert 'synthetic' not in str(error.value)


def test_snapshot_allowlist_covers_complete_route_and_excludes_registration():
    mod = load('snapshot')
    for path in ['/etc/xray/config.json', '/etc/hysteria/config.yaml',
                 '/etc/hysteria/server.key', '/etc/hysteria/server.fullchain.pem', '/etc/systemd/system/xray.service',
                 '/etc/ripdpi/transport-egress/policy.json',
                 '/usr/local/libexec/ripdpi-transport-egress/transport_socks.py']:
        assert mod.allowed(Path(path))
    for path in ['/etc/shadow', '/var/lib/cloudflare-warp/reg.json',
                 '/etc/systemd/system/sshd.service', '/tmp/normalizer.json']:
        assert not mod.allowed(Path(path))


def test_snapshot_compares_bytes_permissions_and_group(monkeypatch, capsys):
    mod = load('snapshot')
    value = {'mode': 0o640, 'gid': 0, 'data': base64.b64encode(b'private candidate').decode()}
    monkeypatch.setattr(mod.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(mod, 'capture', lambda paths: {paths[0]: value})
    import io
    monkeypatch.setattr(sys, 'argv', ['snapshot.py', 'compare'])
    monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(json.dumps({'/etc/xray/config.json': value}).encode())))
    mod.main()
    assert json.loads(capsys.readouterr().out) == {'changed': False}


def test_generation_probe_denies_authentication_without_exposing_values():
    mod = load('generation')
    import socket
    import threading
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0)); listener.listen()
    def server():
        with listener.accept()[0] as conn:
            assert conn.recv(3) == b'\x05\x01\x02'
            conn.sendall(b'\x05\xff')
        listener.close()
    thread = threading.Thread(target=server); thread.start()
    with pytest.raises(mod.Refusal, match='readiness-auth-method'):
        mod.probe({'address': '127.0.0.1', 'port': listener.getsockname()[1],
                   'username': 'synthetic', 'password': 'synthetic', 'probe_kind': 'auth'})
    thread.join(3)
    assert not thread.is_alive()


def test_role_transaction_precedes_publication_and_readiness_is_not_is_active():
    tasks = yaml.safe_load((ROLE / 'tasks/stage.yml').read_text())[-1]['block']
    publication = next(task for task in tasks if task.get('name') == 'Validate and publish changed private candidates')['block']
    names = [task['name'] for task in publication]
    assert names.index('Validate every native gateway candidate before quiescence') < names.index('Capture and stop the previous whole-route generation') < names.index('Publish the complete validated candidate')
    activate = (ROLE / 'tasks/activate.yml').read_text()
    active_tasks = next(task['block'] for task in yaml.safe_load(activate) if task['name'] == 'Activate only a ready guarded generation after frontend staging')
    readiness = next(task for task in active_tasks if task['name'].startswith('Require current authenticated'))
    assert 'status' in readiness['ansible.builtin.command']['argv']
    assert 'is-active' not in activate
    rollback = (ROLE / 'tasks/rollback.yml').read_text()
    rollback_tasks = yaml.safe_load(rollback)[0]['block']
    restore = next(task for task in rollback_tasks if task['name'].startswith('Restore accepted files'))
    assert restore['ansible.builtin.command']['argv'][-1] == 'restore'
    assert 'Require actual accepted generation readiness after rollback' in rollback


def test_vendor_role_never_creates_registration_and_suppresses_autostart():
    role = ROOT / 'ansible/roles/warp-outbound'
    sources = '\n'.join(p.read_text() for p in (role/'tasks').glob('*.yml'))
    assert 'registration, new' not in sources and 'registration new' not in sources
    tasks = yaml.safe_load((role/'tasks/activate.yml').read_text())[0]['block']
    registration = next(task for task in tasks if task['name'].startswith('Inspect retained registration'))
    assert registration['ansible.builtin.command']['argv'][-2:] == ['registration', 'show']
    assert 'policy_rc_d: 101' in sources
    prepare = (role/'tasks/prepare.yml').read_text()
    assert prepare.index('masked: true') < prepare.index('- name: Install cloudflare-warp package')
    mode = next(task for task in tasks if task['name'].startswith('Select tunnel_only'))
    assert mode['ansible.builtin.command']['argv'][-2:] == ['mode', 'tunnel_only']
    dropin = (role/'templates/vendor-namespace.conf.j2').read_text()
    assert 'NetworkNamespacePath=/run/netns/ripdpi-warp' in dropin
    assert 'InaccessiblePaths=-/run/dbus' in dropin


def test_vendor_resolver_has_canonical_directives_and_identical_publication_bytes(monkeypatch, capsys):
    import io
    from jinja2 import Environment, FileSystemLoader
    role = ROOT / 'ansible/roles/warp-outbound'
    tasks = yaml.safe_load((role / 'tasks/prepare.yml').read_text())
    render = next(task for task in tasks if task['name'].startswith('Render one canonical'))
    candidates = next(task for task in tasks if task['name'].startswith('Build fixed namespace'))
    publish = next(task for task in tasks if task['name'].startswith('Seal namespace vendor DNS'))
    assert render['ansible.builtin.set_fact']['_warp_resolver_content'] == "{{ lookup('ansible.builtin.template', 'resolv.conf.j2') }}"
    path = '/etc/ripdpi/warp-outbound/resolv.conf'
    assert candidates['ansible.builtin.set_fact']['_warp_candidate_files'][path]['data'] == '{{ _warp_resolver_content | b64encode }}'
    assert publish['ansible.builtin.copy']['content'] == '{{ _warp_resolver_content }}'
    environment = Environment(loader=FileSystemLoader(str(role / 'templates')),
                              trim_blocks=True, keep_trailing_newline=True)
    resolver = {'nameservers': ['1.1.1.1', '8.8.8.8'], 'timeout_seconds': 1, 'attempts': 1}
    content = environment.get_template('resolv.conf.j2').render(
        transport_egress_input_config={'resolver': resolver}, warp_outbound_nameservers=resolver['nameservers'])
    assert content == 'nameserver 1.1.1.1\nnameserver 8.8.8.8\noptions timeout:1 attempts:1\n'
    snapshot = load('snapshot')
    published = {'mode': 0o644, 'gid': 0, 'data': base64.b64encode(content.encode()).decode()}
    monkeypatch.setattr(snapshot.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(snapshot, 'capture', lambda _: {path: published})
    monkeypatch.setattr(sys, 'argv', ['snapshot.py', 'compare'])
    for second, changed in [('8.8.8.8', False), ('8.8.4.4', True)]:
        candidate = environment.get_template('resolv.conf.j2').render(
            transport_egress_input_config={'resolver': resolver}, warp_outbound_nameservers=['1.1.1.1', second])
        value = {path: {**published, 'data': base64.b64encode(candidate.encode()).decode()}}
        monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(json.dumps(value).encode())))
        snapshot.main()
        assert json.loads(capsys.readouterr().out) == {'changed': changed}


def test_identity_requires_actual_dedicated_named_group(monkeypatch):
    from types import SimpleNamespace
    mod = load('identity')
    entry = SimpleNamespace(pw_name='transport-normalizer', pw_uid=1001, pw_gid=1001, pw_shell='/usr/sbin/nologin')
    monkeypatch.setattr(mod.pwd, 'getpwnam', lambda _: entry)
    monkeypatch.setattr(mod.pwd, 'getpwall', lambda: [entry])
    monkeypatch.setattr(mod.grp, 'getgrall', lambda: [])
    monkeypatch.setattr(mod.grp, 'getgrnam', lambda _: SimpleNamespace(gr_gid=1001, gr_mem=[]))
    assert mod.inspect(['transport-normalizer'])['uids'] == {'transport-normalizer': 1001}
    monkeypatch.setattr(mod.grp, 'getgrnam', lambda _: SimpleNamespace(gr_gid=1002, gr_mem=[]))
    with pytest.raises(ValueError, match='identity-group-invalid'):
        mod.inspect(['transport-normalizer'])
    monkeypatch.setattr(mod.grp, 'getgrnam', lambda _: SimpleNamespace(gr_gid=1001, gr_mem=['foreign']))
    with pytest.raises(ValueError, match='identity-group-invalid'):
        mod.inspect(['transport-normalizer'])


def test_accepted_receipt_covers_frontend_bytes_and_permissions(tmp_path, monkeypatch):
    mod = load('snapshot')
    mod.ACCEPTED = tmp_path/'accepted.json'
    data = {'mode':0o640,'gid':1001,'data':base64.b64encode(b'accepted frontend').decode()}
    files = {'/etc/xray/config.json':data}
    receipt = {'schema':1,'files':mod.fingerprints(files)}
    mod.ACCEPTED.write_text(json.dumps(receipt));mod.ACCEPTED.chmod(0o600)
    from types import SimpleNamespace
    monkeypatch.setattr(mod,'safe',lambda _:SimpleNamespace(st_mode=0o100600))
    assert mod.is_accepted(files)
    changed = {'/etc/xray/config.json':{**data,'data':base64.b64encode(b'never accepted frontend').decode()}}
    assert not mod.is_accepted(changed)
    assert not mod.is_accepted({'/etc/xray/config.json':{**data,'gid':1002}})
    assert not mod.is_accepted({'/etc/xray/config.json':{**data,'mode':0o600}})


def test_role_capture_paths_match_controller_accepted_authority():
    mod = load('snapshot')
    assert Path('/etc/hysteria/ech.key') in mod.FRONTEND_FILES
    paths = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())['transport_egress_snapshot_paths']
    assert len(paths) == len(set(paths))
    assert set(paths) == set(mod.managed_paths()) | {str(mod.ACCEPTED)}
    # An absent optional file still has an explicit fingerprint in the receipt.
    assert mod.fingerprints({path: None for path in paths}) == mod.fingerprints(
        {path: None for path in mod.managed_paths()})


@pytest.mark.parametrize('present', [False, True])
@pytest.mark.parametrize('filename,mode', [('masquerade-hosts', 0o640), ('ech.key', 0o600)])
def test_optional_frontend_authority_retains_accepted_capture_and_restores_bytes(tmp_path, monkeypatch, present, filename, mode):
    import io
    import os
    mod = load('snapshot')
    hosts = tmp_path / filename
    mod.ACCEPTED = tmp_path / 'accepted.json'
    mod.STATE = tmp_path / 'previous.json'
    if present:
        hosts.write_bytes(b'127.0.0.1 owned-origin.invalid\n')
        hosts.chmod(mode)
    # The portable actor owns these exact temporary files; this exercises real
    # serialization/publication/restore, not production root-ancestry admission.
    owned = {hosts, mod.ACCEPTED, mod.STATE}
    def safe_owned(path, missing=False):
        assert path in owned
        return path.lstat() if path.exists() else None
    monkeypatch.setattr(mod, 'safe', safe_owned)
    monkeypatch.setattr(mod, 'allowed', lambda path: path in owned)
    monkeypatch.setattr(mod, 'managed_paths', lambda: [str(hosts)])
    monkeypatch.setattr(mod.os, 'geteuid', lambda: 0)
    actual_fchown = os.fchown
    def chown_owned(fd, uid, gid):
        assert uid == 0 and gid in {0, os.getgid()}
        actual_fchown(fd, -1, os.getgid() if gid == 0 else gid)
    monkeypatch.setattr(mod.os, 'fchown', chown_owned)
    mod.accept()
    monkeypatch.setattr(sys, 'argv', ['snapshot.py', 'capture'])
    monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(
        json.dumps([str(hosts), str(mod.ACCEPTED)]).encode())))
    mod.main()
    prior = json.loads(mod.STATE.read_bytes())
    assert prior['accepted'] is True
    hosts.write_bytes(b'invalid candidate\n')
    hosts.chmod(0o600)
    monkeypatch.setattr(sys, 'argv', ['snapshot.py', 'restore'])
    mod.main()
    assert mod.is_accepted(mod.capture([str(hosts)]))
    if present:
        assert hosts.read_bytes() == b'127.0.0.1 owned-origin.invalid\n'
        assert hosts.stat().st_mode & 0o777 == mode
        assert hosts.stat().st_gid == prior['files'][str(hosts)]['gid']
    else:
        assert not hosts.exists()


def test_vendor_metadata_query_has_one_property_argument_and_private_result():
    tasks = yaml.safe_load((ROOT / 'ansible/roles/warp-outbound/tasks/vendor-ownership.yml').read_text())
    query = next(task for task in tasks if task['name'] == 'Inspect canonical vendor service ownership')
    assert query['ansible.builtin.command']['argv'] == [
        'systemctl', 'show', 'warp-svc.service',
        '--property=LoadState,FragmentPath,ActiveState,DropInPaths']
    assert query['no_log'] is True
    guard = next(task for task in tasks if task['name'].startswith('Refuse adoption'))
    assert "'LoadState=not-found' in _warp_vendor_unit.stdout_lines" in guard['ansible.builtin.assert']['that'][0]


def test_generation_restores_guard_only_after_definitive_consumer_stop(monkeypatch):
    mod = load('generation')
    normalizer = {'runtime_uid': 1001, 'backends': {'direct': {}}, 'listeners': []}
    config = {'schema_version': 1, 'normalizer_uid': 1001,
              'gateway_units': ['ripdpi-transport-direct.service'],
              'frontend_units': ['xray.service'], 'control_timeout_seconds': 30,
              'recovery_seconds': 5}
    controller = mod.Controller(config, normalizer)
    calls = []
    monkeypatch.setattr(controller, 'stop_frontends', lambda: calls.append('frontends-stopped'))
    monkeypatch.setattr(controller, 'stop_gateways', lambda: calls.append('gateways-stopped'))
    monkeypatch.setattr(controller, 'start', lambda unit: calls.append(unit))
    monkeypatch.setattr(mod, 'command', lambda argv, _: calls.append(argv[1]))
    controller.prepare()
    assert calls == ['frontends-stopped', 'gateways-stopped', 'apply', 'verify', 'ripdpi-transport-direct.service']


def test_rollback_retires_new_vendor_before_restoring_its_isolation_files():
    tasks = yaml.safe_load((ROLE / 'tasks/rollback.yml').read_text())[0]['block']
    names = [task['name'] for task in tasks]
    retire = next(task for task in tasks if task['name'].startswith('Retire owned candidate WARP'))
    assert retire['ansible.builtin.include_role'] == {'name': 'warp-outbound', 'tasks_from': 'retire'}
    assert "'ripdpi-transport-warp.service' not in" in retire['when']
    assert names.index('Quiesce owned candidate processes before restoring accepted authority') < names.index(retire['name']) < names.index('Restore accepted files including policy and frontend credentials')
    quiesce = yaml.safe_load((ROLE / 'tasks/quiesce.yml').read_text())
    assert [task['name'] for task in quiesce] == [
        'Inspect rollback unit authority before stopping candidate services',
        'Stop candidate controller before restoring any credential file',
        'Stop remaining candidate generation processes before restore']
    assert quiesce[0]['ansible.builtin.command']['argv'][-1] == 'stop-units'


@pytest.mark.parametrize('state,selected', [
    ('LoadState=not-found\nActiveState=inactive\nMainPID=0\n', False),
    ('LoadState=loaded\nActiveState=inactive\nMainPID=0\n', True),
    ('LoadState=not-found\nActiveState=active\nMainPID=123\n', True),
    ('LoadState=loaded\nActiveState=failed\nMainPID=0\n', True),
])
def test_quiescence_omits_only_confirmed_absent_claims(monkeypatch, state, selected):
    mod = load('ownership')
    unit = 'ripdpi-transport-direct.service'
    monkeypatch.setattr(mod, 'read', lambda: {'schema': 1, 'units': [unit]})
    def show(argv, **kwargs):
        assert argv == ['systemctl', 'show', unit, '--property=LoadState,ActiveState,MainPID']
        assert kwargs['check'] and kwargs['timeout'] == 10
        return subprocess.CompletedProcess(argv, 0, state)
    monkeypatch.setattr(mod.subprocess, 'run', show)
    assert mod.stop_units()['units'] == ([unit] if selected else [])


@pytest.mark.parametrize('failure', ['query', 'partial'])
def test_quiescence_refuses_unconfirmed_absence(monkeypatch, failure):
    mod = load('ownership')
    monkeypatch.setattr(mod, 'read', lambda: {'schema': 1, 'units': ['ripdpi-transport-direct.service']})
    def show(argv, **_kwargs):
        if failure == 'query':
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0, 'LoadState=not-found\n')
    monkeypatch.setattr(mod.subprocess, 'run', show)
    with pytest.raises((ValueError, subprocess.SubprocessError)):
        mod.stop_units()


def test_retirement_preserves_claim_scope_but_stops_only_confirmed_units():
    tasks = yaml.safe_load((ROLE / 'tasks/retire.yml').read_text())
    retirement = tasks[1]
    assert '_transport_egress_retire_owner.stdout' in retirement['when']
    query, controller, gateways = retirement['block'][:3]
    assert query['ansible.builtin.command']['argv'][-1] == 'stop-units'
    assert '_transport_egress_retire_stop_units.stdout' in controller['when']
    assert '_transport_egress_retire_stop_units.stdout' in gateways['loop']
    removal = next(task for task in retirement['block'] if task['name'].startswith('Remove listener authority'))
    assert 'when' not in removal


def test_actual_gateway_identity_checks_every_uid_column(tmp_path, monkeypatch):
    from types import SimpleNamespace
    mod = load('generation')
    normalizer = {'runtime_uid': 1001, 'backends': {'direct': {}}, 'listeners': []}
    config = {'schema_version': 1, 'normalizer_uid': 1001,
              'gateway_units': ['ripdpi-transport-direct.service'],
              'frontend_units': [], 'control_timeout_seconds': 30, 'recovery_seconds': 5}
    controller = mod.Controller(config, normalizer)
    monkeypatch.setattr(mod, 'private_json', lambda _: {'gateway_uid': 1002})
    monkeypatch.setattr(mod, 'command', lambda *_: 'LoadState=loaded\nActiveState=active\nMainPID=1234\nFragmentPath=/etc/systemd/system/ripdpi-transport-direct.service\n')
    monkeypatch.setattr(Path, 'lstat', lambda _: SimpleNamespace(st_mode=0o100644, st_uid=0, st_nlink=1))
    proc = tmp_path/'status'
    actual_open = mod.os.open
    monkeypatch.setattr(mod.os, 'open', lambda path, flags: actual_open(proc, flags))
    proc.write_text('Pid:\t1234\nUid:\t1002\t1002\t1002\t1002\n')
    assert controller.state('ripdpi-transport-direct.service')['MainPID'] == '1234'
    for index in range(4):
        identities = ['1002'] * 4
        identities[index] = '0'
        proc.write_text('Pid:\t1234\nUid:\t'+'\t'.join(identities)+'\n')
        with pytest.raises(mod.Refusal, match='generation-process-identity'):
            controller.state('ripdpi-transport-direct.service')
        # Identity mismatch must not inhibit exact owned-unit shutdown inspection.
        assert controller.state('ripdpi-transport-direct.service', check_identity=False)['MainPID'] == '1234'


def test_unaccepted_frontend_boot_authority_disabled_before_publication_and_after_restore():
    begin = yaml.safe_load((ROLE / 'tasks/begin.yml').read_text())[0]['block']
    disable = next(task for task in begin if task['name'].startswith('Disable unaccepted'))
    assert disable['ansible.builtin.systemd_service']['enabled'] is False
    rollback = yaml.safe_load((ROLE / 'tasks/rollback.yml').read_text())[0]['block']
    retained = next(task for task in rollback if task['name'].startswith('Keep restored unaccepted'))
    assert retained['ansible.builtin.systemd_service'] == {'name': '{{ item }}', 'state': 'stopped', 'enabled': False}


def test_partial_namespace_retirement_skips_only_actual_missing_units():
    tasks = yaml.safe_load((ROOT / 'ansible/roles/warp-outbound/tasks/disable.yml').read_text())[1]['block']
    query = next(task for task in tasks if task['name'].startswith('Inspect exact current'))
    assert query['ansible.builtin.command']['argv'][-1] == '--property=LoadState,FragmentPath'
    assert query['no_log'] is True
    stop = next(task for task in tasks if task['name'].startswith('Stop owned namespace'))
    assert stop['when'] == "'LoadState=not-found' not in item.stdout_lines"
    remove = next(task for task in tasks if task['name'].startswith('Remove only empty'))
    assert remove['ansible.builtin.command']['argv'][-1] == 'retire'


def test_identity_rejects_global_uid_primary_group_and_group_aliases(monkeypatch):
    from types import SimpleNamespace as Entry
    mod = load('identity')
    actor = Entry(pw_name='transport-normalizer', pw_uid=1001, pw_gid=1001, pw_shell='/usr/sbin/nologin')
    group = Entry(gr_name='transport-normalizer', gr_gid=1001, gr_mem=[])
    monkeypatch.setattr(mod.pwd, 'getpwnam', lambda _: actor)
    monkeypatch.setattr(mod.grp, 'getgrnam', lambda _: group)
    monkeypatch.setattr(mod.grp, 'getgrall', lambda: [group])
    foreign = Entry(pw_name='foreign', pw_uid=1001, pw_gid=2000)
    monkeypatch.setattr(mod.pwd, 'getpwall', lambda: [actor, foreign])
    with pytest.raises(ValueError, match='identity-authority-shared'):
        mod.inspect(['transport-normalizer'])
    foreign.pw_uid, foreign.pw_gid = 2000, 1001
    with pytest.raises(ValueError, match='identity-group-invalid'):
        mod.inspect(['transport-normalizer'])
    monkeypatch.setattr(mod.pwd, 'getpwall', lambda: [actor])
    monkeypatch.setattr(mod.grp, 'getgrall', lambda: [group, Entry(gr_name='foreign', gr_gid=1001)])
    with pytest.raises(ValueError, match='identity-group-invalid'):
        mod.inspect(['transport-normalizer'])


def test_identity_admits_only_empty_unshared_nonzero_orphan_group(monkeypatch):
    from types import SimpleNamespace as Entry
    mod = load('identity')
    def absent(_):
        raise KeyError
    group = Entry(gr_name='transport-normalizer', gr_gid=1001, gr_mem=[])
    monkeypatch.setattr(mod.pwd, 'getpwnam', absent)
    monkeypatch.setattr(mod.pwd, 'getpwall', lambda: [])
    monkeypatch.setattr(mod.grp, 'getgrnam', lambda _: group)
    monkeypatch.setattr(mod.grp, 'getgrall', lambda: [group])
    assert mod.inspect(['transport-normalizer']) == {
        'uids': {}, 'gids': {}, 'missing': ['transport-normalizer'], 'missing_groups': []}
    for gid, members in [(0, []), (1001, ['foreign']), (1001, ['transport-normalizer'])]:
        group.gr_gid, group.gr_mem = gid, members
        with pytest.raises(ValueError, match='identity-group-invalid'):
            mod.inspect(['transport-normalizer'])
    group.gr_gid, group.gr_mem = 1001, []
    monkeypatch.setattr(mod.pwd, 'getpwall', lambda: [Entry(pw_name='foreign', pw_uid=2000, pw_gid=1001)])
    with pytest.raises(ValueError, match='identity-group-invalid'):
        mod.inspect(['transport-normalizer'])
    monkeypatch.setattr(mod.pwd, 'getpwall', lambda: [])
    monkeypatch.setattr(mod.grp, 'getgrnam', absent)
    assert mod.inspect(['transport-normalizer'])['missing_groups'] == ['transport-normalizer']


def test_command_failure_classification_never_reproduces_arguments_or_stderr(monkeypatch):
    from types import SimpleNamespace
    mod = load('generation')
    monkeypatch.setattr(mod.subprocess, 'run', lambda *_args, **_kwargs:
        SimpleNamespace(returncode=1, stdout=b'', stderr=b'private stderr value'))
    for argv, category in [
            (['systemctl', 'start', 'ripdpi-transport-direct.service'], 'systemctl-start-direct'),
            ([mod.LOADER, 'apply', '--config', '/private-value'], 'policy-apply'),
            (['unknown-command', 'private-argument'], 'unknown')]:
        with pytest.raises(mod.Refusal) as error:
            mod.command(argv, 1)
        assert str(error.value) == 'generation-command-failed-' + category
        assert 'private' not in str(error.value)


@pytest.mark.parametrize('initial,operations', [('inactive', ['start']), ('failed', ['reset-failed', 'start'])])
def test_start_resets_only_actual_failed_state(monkeypatch, initial, operations):
    mod = load('generation')
    controller = mod.Controller({'schema_version': 1, 'normalizer_uid': 1001,
        'gateway_units': ['ripdpi-transport-direct.service'], 'frontend_units': [],
        'control_timeout_seconds': 30, 'recovery_seconds': 5},
        {'runtime_uid': 1001, 'backends': {'direct': {}}, 'listeners': []})
    states = iter([{'ActiveState': initial, 'MainPID': '0'}, {'ActiveState': 'active', 'MainPID': '1234'}])
    identity_checks = []
    def inspect(_unit, *, check_identity=True):
        identity_checks.append(check_identity)
        return next(states)
    monkeypatch.setattr(controller, 'state', inspect)
    calls = []
    monkeypatch.setattr(mod, 'command', lambda argv, _: calls.append(argv[1]))
    assert controller.start('ripdpi-transport-direct.service') == 1234
    assert calls == operations
    assert identity_checks == [False, True]


@pytest.mark.parametrize('final_identity', [True, False])
def test_start_inspects_executor_metadata_but_admits_only_final_process_identity(monkeypatch, final_identity):
    mod = load('generation')
    controller = readiness_controller(mod)
    checks = []
    def inspect(_unit, *, check_identity=True):
        checks.append(check_identity)
        if not check_identity:
            return {'ActiveState': 'activating', 'MainPID': '1234'}
        if not final_identity:
            raise mod.Refusal('generation-process-identity')
        return {'ActiveState': 'active', 'MainPID': '1234'}
    monkeypatch.setattr(controller, 'state', inspect)
    operations = []
    monkeypatch.setattr(mod, 'command', lambda argv, _: operations.append(argv))
    if final_identity:
        assert controller.start('ripdpi-transport-direct.service') == 1234
    else:
        with pytest.raises(mod.Refusal, match='generation-process-identity'):
            controller.start('ripdpi-transport-direct.service')
    assert checks == [False, True]
    assert operations == [['systemctl', 'start', 'ripdpi-transport-direct.service']]


def test_every_controller_started_foreground_runtime_has_explicit_exec_start_contract():
    for path in [ROLE / 'templates/gateway.service.j2', ROLE / 'templates/normalizer.service.j2',
                 ROOT / 'ansible/roles/xray/templates/xray.service.j2',
                 ROOT / 'ansible/roles/hysteria/templates/hysteria-server.service.j2']:
        assert 'Type=exec' in path.read_text().splitlines()
    converge = yaml.safe_load((ROLE / 'molecule/default/converge.yml').read_text())
    frontend = next(task for task in converge[0]['tasks']
                    if task.get('name') == 'Stage actual frontend service')
    assert 'Type=exec' in frontend['ansible.builtin.copy']['content'].splitlines()


def test_native_gateway_credential_preserves_json_parser_format():
    unit = (ROLE / 'templates/gateway.service.j2').read_text()
    assert 'LoadCredential=config.json:' in unit
    assert 'run -config %d/config.json' in unit
    assert 'run -config %d/config\n' not in unit


def test_generation_controller_retains_uid_drop_without_changing_recipient_capabilities():
    unit = (ROLE / 'templates/generation.service.j2').read_text()
    configuration = configparser.ConfigParser(interpolation=None, strict=False)
    configuration.read_string(unit)
    assert configuration['Install']['WantedBy'].split() == ['multi-user.target']
    assert [line for line in unit.splitlines() if line.startswith('AmbientCapabilities=')] == [
        'AmbientCapabilities=CAP_SETUID']
    for value in ['User=root', 'NoNewPrivileges=true', 'ProtectSystem=strict',
                  'RestrictNamespaces=true', 'RestrictSUIDSGID=true', 'SystemCallArchitectures=native']:
        assert value in unit.splitlines()
    for name in ['normalizer.service.j2', 'gateway.service.j2']:
        recipient = (ROLE / 'templates' / name).read_text()
        assert 'CapabilityBoundingSet=\n' in recipient
        assert 'AmbientCapabilities=CAP_SETUID' not in recipient


def test_native_identity_refusal_fixture_uses_valid_input_only_authority():
    tasks = yaml.safe_load((ROLE / 'molecule/default/verify.yml').read_text())[0]['tasks']
    builder = next(task for task in tasks if task['name'].startswith('Build non-UID input authority'))
    assert builder['ansible.builtin.command']['argv'][-1] == '--input-only'
    assert builder['delegate_to'] == 'localhost' and builder['become'] is False
    assert builder['no_log'] is True and builder['changed_when'] is False
    alias = next(task for task in tasks if task['name'].startswith('Exercise actual UID alias'))
    refusal = alias['block'][1]
    assert refusal['block'][0]['vars']['transport_egress_input_config'] == '{{ (native_identity_input.stdout | from_json).normalizer }}'
    assert refusal['rescue'][0]['ansible.builtin.assert']['that'] == "ansible_failed_task.name == 'Inspect existing transport identities without mutation'"
    sys.path.insert(0, str(ROOT / 'scripts'))
    try:
        from transport_egress_config import build
        from transport_egress_normalizer import validate_config, NormalizerError
        context = {'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': False,
                          'enable_hysteria': False, 'enable_warp_outbound': False},
                   'secrets': {'direct_gateway_password': 'synthetic gateway authority ' + 'a' * 32,
                               'direct_xray_password': 'synthetic frontend authority ' + 'b' * 32},
                   'owned_addresses': [], 'management_tcp_ports': [22], 'management_udp_ports': []}
        raw = build(context, input_only=True)['normalizer']
        assert validate_config(raw, input_only=True) is raw
        assert 'runtime_uid' not in raw and all('frontend_uid' not in row for row in raw['listeners'])
        final = build({**context, 'normalizer_uid': 1001, 'gateway_uid': 1002,
                       'frontend_uids': {'xray': 1003}})['normalizer']
        with pytest.raises(NormalizerError, match='invalid-config-shape'):
            validate_config(final, input_only=True)
    finally:
        sys.path.remove(str(ROOT / 'scripts'))


def readiness_controller(mod):
    return mod.Controller({'schema_version': 1, 'normalizer_uid': 1001,
        'gateway_units': ['ripdpi-transport-direct.service'], 'frontend_units': [],
        'control_timeout_seconds': 1, 'recovery_seconds': 1},
        {'runtime_uid': 1001, 'backends': {'direct': {'address': '127.0.0.1', 'port': 12090}},
         'listeners': [{'name': 'direct_xray', 'frontend_uid': 1003}]})


def readiness_clock(monkeypatch, mod):
    import itertools
    ticks = itertools.count()
    monkeypatch.setattr(mod.time, 'monotonic', lambda: next(ticks) * 0.6)


@pytest.mark.parametrize('state_pid,pid,uid,expected', [
    ('1234', '1234', '0', 'message-1-uid-0-process-1'),
    ('1234', '5678', '1001', 'message-0-uid-0-process-1'),
    ('0', '5678', '1001', 'message-0-uid-0-process-0'),
])
def test_readiness_journal_attribution_refuses_with_boolean_only_diagnostics(monkeypatch, state_pid, pid, uid, expected):
    mod = load('generation')
    controller = readiness_controller(mod)
    readiness_clock(monkeypatch, mod)
    monkeypatch.setattr(controller, 'state', lambda _: {'MainPID': state_pid})
    monkeypatch.setattr(mod, 'command', lambda *_: json.dumps({
        '_PID': pid, '_UID': uid, 'MESSAGE': 'normalizer-ready'}))
    monkeypatch.setattr(mod.subprocess, 'run', lambda *_args, **_kwargs: pytest.fail('probe before journal admission'))
    with pytest.raises(mod.Refusal) as error:
        controller.ready()
    assert str(error.value) == 'generation-readiness-journal-' + expected


@pytest.mark.parametrize('failure,suffix', [('returncode', ''), ('timeout', '-timeout'), ('preexec', '-child-failed')])
@pytest.mark.parametrize('probe_index,stage', [(0, 'auth-direct-xray'), (1, 'udp-control-direct')])
def test_readiness_probe_failure_categories_never_print_child_values(monkeypatch, failure, suffix, probe_index, stage, capsys):
    from types import SimpleNamespace
    mod = load('generation')
    controller = readiness_controller(mod)
    now = [0.0]
    monkeypatch.setattr(mod.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(controller, 'state', lambda _: {'MainPID': '1234'})
    monkeypatch.setattr(mod, 'command', lambda *_: json.dumps({
        '_PID': '1234', '_UID': '1001', 'MESSAGE': 'normalizer-ready'}))
    monkeypatch.setattr(mod.pwd, 'getpwuid', lambda _: SimpleNamespace(pw_uid=1003, pw_gid=1003))
    calls = []
    def child(*_args, **_kwargs):
        calls.append(True)
        if len(calls) - 1 < probe_index:
            return SimpleNamespace(returncode=0)
        now[0] = 2.0  # This exact failed child exhausts the one-second budget.
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(['private-argument'], 1, stderr=b'private child value')
        if failure == 'preexec':
            raise subprocess.SubprocessError('private child value')
        return SimpleNamespace(returncode=1, stdout=b'private child value', stderr=b'private child value')
    monkeypatch.setattr(mod.subprocess, 'run', child)
    with pytest.raises(mod.Refusal) as error:
        controller.ready()
    assert len(calls) == probe_index + 1
    assert str(error.value) == 'generation-readiness-' + stage + suffix
    assert 'private' not in str(error.value)
    assert capsys.readouterr() == ('', '')


def test_readiness_matching_journal_and_all_private_probes_remain_accepted(monkeypatch):
    from types import SimpleNamespace
    mod = load('generation')
    controller = readiness_controller(mod)
    monkeypatch.setattr(mod.time, 'monotonic', lambda: 0)
    monkeypatch.setattr(controller, 'state', lambda _: {'MainPID': '1234'})
    monkeypatch.setattr(mod, 'command', lambda *_: json.dumps({
        '_PID': '1234', '_UID': '1001', 'MESSAGE': 'normalizer-ready'}))
    monkeypatch.setattr(mod.pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_uid=uid, pw_gid=uid))
    probes = []
    def child(*_args, **kwargs):
        probes.append(json.loads(kwargs['input']))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mod.subprocess, 'run', child)
    assert controller.ready() is None
    assert [(value['name'], value['probe_kind']) for value in probes] == [
        ('direct_xray', 'auth'), ('direct', 'udp-control')]


def recovery_controller(mod):
    return mod.Controller({'schema_version': 1, 'normalizer_uid': 1001,
        'gateway_units': [mod.GATEWAYS['direct']],
        'frontend_units': ['xray.service', 'hysteria-server.service'],
        'control_timeout_seconds': 1, 'recovery_seconds': 1},
        {'runtime_uid': 1001, 'backends': {'direct': {}}, 'listeners': []})


@pytest.mark.parametrize('target', ['xray.service', 'hysteria-server.service'])
def test_requested_frontend_restart_retains_paired_processes_and_other_frontend(monkeypatch, target):
    mod = load('generation')
    controller = recovery_controller(mod)
    generation = {mod.NORMALIZER: 10, mod.GATEWAYS['direct']: 20,
                  'xray.service': 30, 'hysteria-server.service': 40}
    current = dict(generation)
    current[target] = 0  # The requested frontend may already be down.
    actions, receipts = [], []
    monkeypatch.setattr(controller, 'state', lambda unit: {'ActiveState': 'active', 'MainPID': str(current[unit])})
    monkeypatch.setattr(controller, 'frontend_credentials', lambda: actions.append('credentials'))
    monkeypatch.setattr(controller, 'ready', lambda: actions.append('authenticated-readiness'))
    def stop(unit):
        actions.append(('stop', unit))
        current[unit] = 0
    def start(unit):
        actions.append(('start', unit))
        current[unit] = 50
    monkeypatch.setattr(controller, 'stop', stop)
    monkeypatch.setattr(controller, 'start', start)
    monkeypatch.setattr(controller, 'publish_ready', lambda value: receipts.append(dict(value)))
    controller.frontend_requests.add(target)
    updated = controller.recover_frontends(generation)
    assert actions == ['credentials', 'authenticated-readiness', ('stop', target), ('start', target)]
    assert updated[target] == 50 and receipts == [updated]
    assert all(updated[unit] == pid for unit, pid in generation.items() if unit != target)
    assert controller.frontend_requests == set() and controller.deadline is None


@pytest.mark.parametrize('drift', ['normalizer', 'gateway', 'other-frontend', 'credentials'])
def test_requested_recovery_refuses_unrelated_drift_before_target_restart(monkeypatch, drift):
    mod = load('generation')
    controller = recovery_controller(mod)
    generation = {mod.NORMALIZER: 10, mod.GATEWAYS['direct']: 20,
                  'xray.service': 30, 'hysteria-server.service': 40}
    current = dict(generation)
    if drift != 'credentials':
        unit = {'normalizer': mod.NORMALIZER, 'gateway': mod.GATEWAYS['direct'],
                'other-frontend': 'hysteria-server.service'}[drift]
        current[unit] += 1
    monkeypatch.setattr(controller, 'state', lambda unit: {'ActiveState': 'active', 'MainPID': str(current[unit])})
    def credentials():
        if drift == 'credentials':
            raise mod.Refusal('generation-frontend-credential-mismatch')
    monkeypatch.setattr(controller, 'frontend_credentials', credentials)
    monkeypatch.setattr(controller, 'ready', lambda: None)
    stops = []
    monkeypatch.setattr(controller, 'stop', lambda unit: stops.append(unit))
    controller.frontend_requests.add('xray.service')
    with pytest.raises(mod.Refusal):
        controller.recover_frontends(generation)
    assert stops == [] and controller.deadline is None


@pytest.mark.parametrize('ack', ['accepted', 'unchanged', 'controller-changed', 'config-changed', 'stale-status', 'mapping-changed'])
def test_recovery_request_requires_current_controller_acknowledgement(monkeypatch, ack):
    mod = load('generation')
    controller = recovery_controller(mod)
    digest = mod.hashlib.sha256(json.dumps(controller.normalizer, sort_keys=True).encode()).hexdigest()
    before = {'schema': 1, 'controller_pid': 100, 'config_digest': digest,
              'generation': {'xray.service': 30, mod.NORMALIZER: 10, mod.GATEWAYS['direct']: 20}}
    after = json.loads(json.dumps(before))
    if ack != 'unchanged':
        after['generation']['xray.service'] = 50
    if ack == 'controller-changed':
        after['controller_pid'] += 1
    if ack == 'config-changed':
        after['config_digest'] = 'changed'
    if ack == 'mapping-changed':
        after['generation'][mod.GATEWAYS['direct']] += 1
    reads = iter([before, after])
    monkeypatch.setattr(mod, 'private_json', lambda _: next(reads, after))
    now = [0.0]
    monkeypatch.setattr(mod.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(mod.time, 'sleep', lambda duration: now.__setitem__(0, now[0]+duration))
    actions = []
    monkeypatch.setattr(controller, 'state', lambda unit: {'MainPID': '100', 'ActiveState': 'active'})
    def command(argv, timeout):
        actions.append(argv)
        assert 0 < timeout <= controller.timeout
        return 'MainPID=100\nActiveState=active\n'
    monkeypatch.setattr(mod, 'command', command)
    def status():
        if ack == 'stale-status':
            raise mod.Refusal('generation-readiness-stale')
    monkeypatch.setattr(controller, 'status', status)
    if ack == 'accepted':
        controller.recover('xray.service')
    else:
        with pytest.raises(mod.Refusal):
            controller.recover('xray.service')
    assert actions[0] == ['systemctl', 'kill', '--kill-whom=main', '--signal=SIGUSR1',
                          'ripdpi-transport-generation.service']
    assert now[0] <= 3 and controller.deadline is None


@pytest.mark.parametrize('unit', ['ssh.service', None])
def test_recovery_rejects_unknown_or_disabled_target_without_commands(monkeypatch, unit):
    mod = load('generation')
    controller = recovery_controller(mod)
    monkeypatch.setattr(mod, 'command', lambda *_: pytest.fail('refused request dispatched a command'))
    with pytest.raises(mod.Refusal, match='generation-recovery-target-invalid'):
        controller.recover(unit)
    controller.config['frontend_units'] = []
    with pytest.raises(mod.Refusal, match='generation-recovery-target-invalid'):
        controller.recover('xray.service')


def test_targeted_recovery_probe_consumes_only_the_remaining_outer_budget(monkeypatch):
    from types import SimpleNamespace
    mod = load('generation')
    controller = recovery_controller(mod)
    controller.deadline = 0.05
    now, probe_timeouts = [0.0], []
    monkeypatch.setattr(mod.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(controller, 'state', lambda _: {'MainPID': '1234'})
    monkeypatch.setattr(mod, 'command', lambda *_: json.dumps({
        '_PID': '1234', '_UID': '1001', 'MESSAGE': 'normalizer-ready'}))
    def identity(uid):
        now[0] += 0.04
        return SimpleNamespace(pw_gid=uid)
    monkeypatch.setattr(mod.pwd, 'getpwuid', identity)
    def probe(*args, **kwargs):
        probe_timeouts.append(kwargs['timeout'])
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mod.subprocess, 'run', probe)
    controller.ready()
    assert len(probe_timeouts) == 1 and 0 < probe_timeouts[0] <= 0.01 + 1e-9


def test_recovery_controller_admission_requires_all_four_root_uid_columns(tmp_path, monkeypatch):
    from types import SimpleNamespace
    mod = load('generation')
    controller = recovery_controller(mod)
    monkeypatch.setattr(mod, 'command', lambda *_: 'LoadState=loaded\nActiveState=active\nMainPID=1234\nFragmentPath=/etc/systemd/system/ripdpi-transport-generation.service\n')
    monkeypatch.setattr(Path, 'lstat', lambda _: SimpleNamespace(st_mode=0o100644, st_uid=0, st_nlink=1))
    proc = tmp_path / 'status'
    actual_open = mod.os.open
    monkeypatch.setattr(mod.os, 'open', lambda path, flags: actual_open(proc, flags))
    proc.write_text('Pid:\t1234\nUid:\t0\t0\t0\t0\n')
    assert controller.state(mod.CONTROLLER)['MainPID'] == '1234'
    for index in range(4):
        identities = ['0'] * 4
        identities[index] = '1001'
        proc.write_text('Pid:\t1234\nUid:\t'+'\t'.join(identities)+'\n')
        with pytest.raises(mod.Refusal, match='generation-process-identity'):
            controller.state(mod.CONTROLLER)


@pytest.mark.parametrize('warp', [False, True])
def test_generation_runtime_unit_query_uses_validated_topology(monkeypatch, capsys, warp):
    mod = load('generation')
    backends = {'direct': {}}
    if warp:
        backends['warp'] = {}
    normalizer = {'runtime_uid': 1001, 'backends': backends, 'listeners': []}
    units = [mod.GATEWAYS[name] for name in backends]
    config = {'schema_version': 1, 'normalizer_uid': 1001, 'gateway_units': units,
              'frontend_units': ['xray.service'], 'control_timeout_seconds': 30, 'recovery_seconds': 5}
    monkeypatch.setattr(mod.sys, 'argv', ['generation', 'runtime-units', '--config', 'generation', '--normalizer-config', 'normalizer'])
    monkeypatch.setattr(mod, 'private_json', lambda path: config if path == 'generation' else normalizer)
    mod.main()
    assert json.loads(capsys.readouterr().out) == units
    config['gateway_units'] = ['ssh.service']
    with pytest.raises(mod.Refusal, match='generation-gateways-invalid'):
        mod.main()
    assert capsys.readouterr().out == ''


def test_generation_units_have_one_publication_lane():
    stage = yaml.safe_load((ROLE / 'tasks/stage.yml').read_text())[-1]['block']
    authority = next(task['ansible.builtin.set_fact'] for task in stage if task['name'] == 'Retain immutable runtime and candidate authority')
    assert authority['_transport_egress_runtime_unit_candidates'] == [{
        'path': '/etc/systemd/system/ripdpi-transport-generation.service', 'mode': '0644',
        'content': '{{ lookup("ansible.builtin.template", "generation.service.j2") }}'}]
    files = next(task['loop'] for task in stage
                 if task['name'] == 'Render fixed private candidate files without remote publication')
    assert not any(item['path'].endswith('/ripdpi-transport-generation.service') for item in files)
    render = next(task['ansible.builtin.set_fact'] for task in stage if task['name'] == 'Render gateway credentials and units into private candidates')
    assert 'gateway.service.j2' not in render['_transport_egress_candidate_files']
    assert 'gateway.service.j2' in render['_transport_egress_runtime_unit_candidates']
    select = next(task for task in stage if task['name'] == 'Select generation units for the sole runtime publisher')
    assert select['loop'] == '{{ _transport_egress_runtime_unit_candidates }}'
    assert 'transport_runtime_candidates' in select['ansible.builtin.set_fact']
    publish = next(task for task in stage if task['name'] == 'Validate and publish changed private candidates')['block']
    live = next(task for task in publish if task['name'] == 'Publish the complete validated candidate')
    assert live['loop'] == '{{ _transport_egress_candidate_files }}'
    assert next(task for task in publish if task['name'] == 'Stage release-bound generation units for syntax validation only')['ansible.builtin.copy']['dest'].startswith('{{ _transport_egress_candidate_dir.path }}')
    names = [task['name'] for task in publish]
    assert names.index('Publish the complete validated candidate') < names.index('Verify actual published unit syntax')
    verify = next(task for task in publish if task['name'] == 'Verify actual published unit syntax')
    assert '_transport_egress_candidate_dir.path' in verify['ansible.builtin.command']['argv']


def test_direct_gateway_forwards_sealed_dns_over_encrypted_upstreams_only():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from template_render import merge_render_vars, render_template
    template = ROOT / 'ansible/roles/transport-egress/templates/gateway.json.j2'
    values = merge_render_vars()
    direct = json.loads(render_template(template, values))
    forbidden = values['_transport_egress_forbidden']['ipv4'] + values['_transport_egress_forbidden']['ipv6']
    assert [server['address'] for server in direct['dns']['servers']] == ['https+local://1.1.1.1/dns-query', 'https+local://8.8.8.8/dns-query']
    assert all(server['unexpectedIPs'] == forbidden for server in direct['dns']['servers'])
    forwarder = next(item for item in direct['inbounds'] if item['tag'] == 'dns-forwarder')
    assert forwarder['protocol'] == 'dokodemo-door' and forwarder['listen'] == '127.0.0.1'
    assert forwarder['port'] == values['transport_egress_policy_config_data']['resolver']['forwarder_port'] == 12053
    assert forwarder['settings'] == {'address': '127.0.0.1', 'port': 53, 'network': 'tcp,udp'}
    resolver = next(item for item in direct['outbounds'] if item['tag'] == 'dns-resolver')
    assert resolver == {'tag': 'dns-resolver', 'protocol': 'dns', 'settings': {'nonIPQuery': 'drop'}}
    assert direct['outbounds'][0]['protocol'] == 'freedom'
    assert direct['routing']['rules'] == [{'type': 'field', 'inboundTag': ['dns-forwarder'], 'outboundTag': 'dns-resolver'}]
    values['_transport_egress_backend_name'] = 'warp'
    values['_transport_egress_backend'] = {**values['_transport_egress_backend'], 'address': '10.250.254.2', 'port': 12091}
    warp = json.loads(render_template(template, values))
    assert [item['tag'] for item in warp['inbounds']] == ['recipient'] and 'routing' not in warp
    assert [item['protocol'] for item in warp['outbounds']] == ['freedom']
    assert [server['address'] for server in warp['dns']['servers']] == [server['address'] for server in direct['dns']['servers']]
