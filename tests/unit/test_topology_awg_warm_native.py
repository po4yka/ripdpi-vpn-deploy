"""Warm complete AWG generation publication with exact ELF processes."""
from __future__ import annotations

import base64
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import uuid

import pytest
import yaml

from awg_device_binding import resolve_binding
from test_awg_activation_native import complete_publisher, render_native_awg_config
from test_awg_device_binding import document
from test_transport_semantics_native import command, exact_awg_sources

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/amneziawg"
pytestmark = pytest.mark.native_runtime


def warm_startup_diagnostics(unit, namespace, private, *, runner=subprocess.run):
    """Expose only fixed categories and kernel metadata, never command output."""
    def query(argv):
        try:
            result = runner(argv, capture_output=True, text=True, timeout=10)
            return result.stdout[:131072] if result.returncode == 0 else ''
        except (OSError, subprocess.SubprocessError):
            return ''

    allowed = {
        'LoadState': {'loaded', 'not-found', 'error', 'masked', 'merged'},
        'ActiveState': {'active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading'},
        'SubState': {'running', 'exited', 'dead', 'failed', 'start', 'start-pre', 'start-post',
                     'stop', 'stop-sigterm', 'stop-sigkill', 'auto-restart'},
        'Result': {'success', 'exit-code', 'signal', 'core-dump', 'watchdog', 'timeout',
                   'protocol', 'resources', 'oom-kill', 'exec-condition', 'start-limit-hit'},
        'ExecMainCode': None, 'ExecMainStatus': None,
    }
    text = query(['systemctl', 'show', unit, '--property=' + ','.join(allowed)])
    properties = {key: 'unavailable' for key in allowed}
    for key, choices in allowed.items():
        values = [line.partition('=')[2] for line in text.splitlines() if line.startswith(key + '=')]
        if len(values) != 1:
            continue
        value = values[0]
        if choices is not None and value in choices:
            properties[key] = value
        elif choices is None and value.isascii() and value.isdecimal() and len(value) <= 3 and int(value) <= 255:
            properties[key] = int(value)
    values = query(['ip', 'netns', 'exec', namespace, 'sysctl', '-n',
                    'net.ipv6.conf.all.disable_ipv6', 'net.ipv6.conf.default.disable_ipv6']).split()
    ipv6 = dict.fromkeys(('all_disabled', 'default_disabled'), 'unavailable')
    if len(values) == 2 and all(value in {'0', '1'} for value in values):
        ipv6 = dict(zip(ipv6, map(int, values)))
    journal = query(['journalctl', '--unit', unit, '--no-pager', '--output=cat', '--lines=64'])
    patterns = {
        'exec_failure': ('Failed at step EXEC', 'status=203/EXEC'),
        'namespace_failure': ('Failed at step NAMESPACE', 'status=226/NAMESPACE'),
        'permission_denied': ('Permission denied', 'Operation not permitted'),
        'ipv6_disabled': ('IPv6 is disabled',),
        'address_family_unavailable': ('Address family not supported by protocol',),
        'missing_path': ('No such file or directory',),
        'config_rejected': ('Line unrecognized', 'Configuration parsing error'),
        'uapi_unavailable': ('Unable to access interface',),
    }
    parents = {}
    for label, path in {
        'usr': Path('/usr'), 'usr_local': Path('/usr/local'), 'usr_local_bin': Path('/usr/local/bin'),
        'usr_bin': Path('/usr/bin'), 'etc': Path('/etc'), 'systemd': Path('/etc/systemd'),
        'systemd_system': Path('/etc/systemd/system'), 'var': Path('/var'), 'var_lib': Path('/var/lib'),
        'ripdpi': Path('/var/lib/ripdpi'), 'private': private,
    }.items():
        try:
            info = path.lstat()
            parents[label] = {'uid': info.st_uid, 'gid': info.st_gid, 'mode': format(stat.S_IMODE(info.st_mode), '04o'),
                              'nlink': info.st_nlink, 'issym': stat.S_ISLNK(info.st_mode), 'isdir': stat.S_ISDIR(info.st_mode)}
        except OSError:
            parents[label] = dict.fromkeys(('uid', 'gid', 'mode', 'nlink', 'issym', 'isdir'), 'unavailable')
    return {'unit': properties, 'ipv6': ipv6, 'parents': parents,
            'journal_flags': {key: any(pattern in journal for pattern in choices) for key, choices in patterns.items()}}


def test_warm_binary_and_unit_adoption_then_unchanged_convergence(tmp_path):
    go, tools = exact_awg_sources()
    assert os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    assert Path('/run/systemd/system').is_dir()
    token = "warm" + uuid.uuid4().hex[:7]
    interface = "a" + uuid.uuid4().hex[:10]
    unit = Path('/etc/systemd/system') / f'awg-quick@{interface}.service'
    dropin = unit.with_name(unit.name + '.d')
    private = Path('/var/lib') / token
    assert not os.path.lexists(unit) and not os.path.lexists(dropin)
    assert not os.path.lexists(private)
    quick = tools.parent / 'wg-quick/linux.bash'
    assert quick.is_file()
    ownership = ExitStack()
    private_owned = namespace_owned = dropin_owned = False
    try:
        private.mkdir(mode=0o700)
        private_owned = True
        key = command([str(tools), 'genkey']).strip()
        source = document()
        instance = source['amneziawg_secrets']['instances'][0]
        instance.update(name=interface, server_private_key=key, mtu=1420, jc=0, s1=0, s2=0)
        source['amneziawg_secrets']['instances'] = [instance]
        source['client_registry'] = {'device0': source['client_registry']['device0']}
        source['client_registry']['device0']['awg_binding']['instance'] = interface
        effective = resolve_binding(source, {}, 'device0', 'upcloud:fixture', interface).instance
        config = private / (interface + '.conf')
        config_bytes = render_native_awg_config(effective).encode()
        publisher = ownership.enter_context(complete_publisher(private))
        publisher.acquire(go, tools, quick)
        command(['ip', 'netns', 'add', token])
        namespace_owned = True
        command(['ip', '-n', token, 'link', 'set', 'lo', 'up'])
        # Keep the actual shared unit and its hardening. Only the outer network
        # namespace and userspace implementation selection belong to the fixture.
        dropin.mkdir(mode=0o755)
        dropin_owned = True
        (dropin / 'namespace.conf').write_text(
            '[Service]\nNetworkNamespacePath=/run/netns/' + token +
            '\nEnvironment=WG_QUICK_USERSPACE_IMPLEMENTATION=/usr/local/bin/amneziawg-go\n')
        command(['systemctl', 'daemon-reload'])

        def private_configuration():
            if config.read_bytes() != config_bytes:
                pytest.fail('native warm AWG private configuration bytes changed')
            assert config.stat().st_mode & 0o777 == 0o600

        initial = publisher.role([effective])
        if initial.returncode != 0:
            evidence = warm_startup_diagnostics(unit.name, token, private)
            pytest.fail('native warm AWG initial role convergence failed: ' + json.dumps(evidence, sort_keys=True))
        if key in initial.stdout + initial.stderr:
            pytest.fail('native warm AWG initial role exposed its fixture key')
        private_configuration()
        shared_path = Path('/etc/systemd/system/awg-quick@.service')
        shared = shared_path.read_text()
        retained = {path: (path.stat().st_ino, path.stat().st_mode, path.read_bytes())
                    for path in (config, shared_path, Path('/etc/systemd/system/awg-quick.target'), publisher.record)}
        # Replay the current role's real publication task, including its actual
        # changed_when contract, with complete candidates built by the adapter.
        publication = next(task for task in yaml.safe_load((ROLE / 'tasks/configure.yml').read_text())
                           if task.get('register') == '_awg_consumer_publication')

        def request_for(acquired, shared):
            request = publisher.request(acquired, {interface: config_bytes.decode()}, shared)
            # Keep actual accepted role bytes rather than snapshot-rendered
            # target/record whitespace during the binary-only publication.
            for candidate in request['candidates']:
                path = Path(candidate['path'])
                if path in retained:
                    content = shared.encode() if path == shared_path else retained[path][2]
                    candidate['data'] = base64.b64encode(content).decode()
            return request

        def converge(request):
            play = private / 'play.yml'
            play.write_text(yaml.safe_dump([{
                'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
                'vars': {'ansible_python_interpreter': sys.executable,
                         '_awg_consumer_candidates': request['candidates'],
                         '_firewall_consumer_candidate': request['firewall']},
                'tasks': [copy.deepcopy(publication)],
            }], sort_keys=False))
            play.chmod(0o600)
            result = subprocess.run(
                ['ansible-playbook', '-i', 'localhost,', str(play)],
                capture_output=True, text=True, timeout=90, env=publisher.environment)
            assert result.returncode == 0, 'native warm AWG complete publication failed'
            if key in result.stdout + result.stderr:
                pytest.fail('native warm AWG publication exposed its fixture key')
            private_configuration()
            return result.stdout

        def daemon(expected):
            group = command(['systemctl', 'show', unit.name, '--property=ControlGroup', '--value']).strip()
            assert group.startswith('/') and '..' not in Path(group).parts
            matches = set()
            for membership in (Path('/sys/fs/cgroup') / group.lstrip('/')).rglob('cgroup.procs'):
                for raw in membership.read_text().split():
                    executable = Path('/proc', raw, 'exe')
                    try:
                        if Path(os.readlink(executable)).name.split(' ')[0] == 'amneziawg-go':
                            matches.add(int(raw))
                    except (FileNotFoundError, ProcessLookupError):
                        continue
            assert len(matches) == 1, 'exact owned AWG daemon absent'
            pid = matches.pop()
            executable = Path('/proc', str(pid), 'exe')
            content = executable.read_bytes()
            assert content.startswith(b'\x7fELF')
            assert hashlib.sha256(content).digest() == hashlib.sha256(expected).digest()
            assert os.path.samefile(executable, '/usr/local/bin/amneziawg-go')
            status = Path('/proc', str(pid), 'status').read_text()
            assert 'NoNewPrivs:\t1' in status
            assert int(next(line.split()[1] for line in status.splitlines()
                            if line.startswith('CapEff:')), 16) == 1 << 12
            return pid, status

        first, _ = daemon(go.read_bytes())
        first_binary_inode = Path('/usr/local/bin/amneziawg-go').stat().st_ino
        # ELF permits trailing data. Change actual executable bytes so this is
        # a distinct content-addressed generation, rather than an inode-only copy.
        candidate = private / 'candidate-amneziawg-go'
        candidate_bytes = go.read_bytes() + b'\0'
        candidate.write_bytes(candidate_bytes)
        candidate.chmod(0o755)
        acquired = publisher.acquire(candidate, tools, quick)
        request = request_for(acquired, shared)
        converge(request)
        second, _ = daemon(candidate_bytes)
        assert second != first
        assert Path('/usr/local/bin/amneziawg-go').stat().st_ino != first_binary_inode
        # An accepted complete generation replaces every candidate inode. Its
        # unchanged non-binary content and modes must remain exact.
        if any((path.stat().st_mode, path.read_bytes()) != before[1:]
               for path, before in retained.items()):
            pytest.fail('binary-only publication changed accepted non-binary authority')
        # A complete shared-unit change must reach the actual daemon too.
        first_unit_inode = shared_path.stat().st_ino
        shared = shared.replace('[Service]', '[Service]\nUMask=0077', 1)
        request = request_for(acquired, shared)
        converge(request)
        third, status = daemon(candidate_bytes)
        assert third != second and 'Umask:\t0077' in status
        assert shared_path.stat().st_ino != first_unit_inode
        assert shared_path.read_text() == shared
        unchanged_paths = [*retained, *map(Path, (
            '/usr/local/bin/amneziawg-go', '/usr/bin/awg', '/usr/bin/awg-quick'))]
        unchanged = {path: (path.stat().st_ino, path.stat().st_mode, path.read_bytes())
                     for path in unchanged_paths}
        output = converge(request)
        assert daemon(candidate_bytes)[0] == third and 'changed=0' in output
        if any((path.stat().st_ino, path.stat().st_mode, path.read_bytes()) != before
               for path, before in unchanged.items()):
            pytest.fail('unchanged publication replaced accepted authority')
    finally:
        try:
            if dropin_owned:
                subprocess.run(['systemctl', 'stop', unit.name], capture_output=True, timeout=15)
                subprocess.run(['systemctl', 'disable', unit.name], capture_output=True, timeout=15)
                shutil.rmtree(dropin)
                subprocess.run(['systemctl', 'reset-failed', unit.name], capture_output=True, timeout=10)
        finally:
            try:
                ownership.close()
            finally:
                if namespace_owned:
                    subprocess.run(['ip', 'netns', 'delete', token], capture_output=True, timeout=10)
                if private_owned:
                    shutil.rmtree(private)
