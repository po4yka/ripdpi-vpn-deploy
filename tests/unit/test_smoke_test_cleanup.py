"""Run the source smoke task graph with local systemd/network executables.

These tests prove Ansible control flow and real temporary-file cleanup, not
Linux systemd or live transport behavior. Only the curl bypass regression uses
dynamic loopback sockets; no host service or external network is used.
"""
from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import socket
import subprocess
import sys
import time
from threading import Thread

from jinja2 import Environment, StrictUndefined
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
PROTOCOLS = ("xray", "hysteria", "snell")
TOGGLES = {"xray": "enable_xray_reality", "hysteria": "enable_hysteria", "snell": "enable_snell"}

EXECUTABLE = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import stat
import sys
import time

state = Path(os.environ['SMOKE_FIXTURE_STATE'])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (state / 'calls.jsonl').open('a') as log:
    log.write(json.dumps({'run': os.environ.get('SMOKE_RUN', 'only'), 'name': name, 'args': args}) + '\n')
failure = os.environ.get('SMOKE_FAILURE', '')
if name == 'systemd-run':
    config_flag = next(index for index, arg in enumerate(args) if arg in ('-config', '-c'))
    config = Path(args[config_flag + 1])
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert stat.S_IMODE(config.parent.stat().st_mode) == 0o700
    unit = next(arg.split('=', 1)[1] for arg in args if arg.startswith('--unit='))
    unit = unit.removesuffix('.service') + '.service'
    marker = state / 'units' / unit
    if os.environ.get('SMOKE_FOREIGN_COLLISION') == '1':
        marker.write_text('foreign-service')
        print('Injected start failure: unit already exists', file=sys.stderr)
        sys.exit(1)
    if failure == 'start':
        print('Injected start failure', file=sys.stderr)
        sys.exit(1)
    if marker.exists():
        print('Unit already exists', file=sys.stderr)
        sys.exit(1)
    marker.write_text('owned-service')
    sys.exit(0)
if name == 'systemctl':
    unit = args[-1]
    marker = state / 'units' / unit
    if args[0] == 'show':
        print('loaded' if marker.exists() else 'not-found')
        sys.exit(0)
    if args[0] == 'is-active':
        if marker.exists():
            sys.exit(0)
        print('Injected own-unit inactive', file=sys.stderr)
        sys.exit(3)
    assert args[0] == 'stop', args
    if os.environ.get('SMOKE_COLLECTED') == '1' and marker.exists():
        marker.unlink()
    if os.environ.get('SMOKE_STOP_FAILURE') == '1':
        print('Injected cleanup failure', file=sys.stderr)
        sys.exit(1)
    if not marker.exists():
        print(f'Failed to stop {unit}: Unit {unit} not loaded.', file=sys.stderr)
        sys.exit(5)
    marker.unlink()
    sys.exit(0)
if name == 'smoke-vacancy':
    if args[0] == os.environ.get('SMOKE_OCCUPIED_PORT'):
        print('Injected occupied port', file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
if name == 'smoke-wait':
    if os.environ.get('SMOKE_UNIT_DIES') == 'before_probe':
        for marker in (state / 'units').iterdir():
            marker.unlink()
    if os.environ.get('SMOKE_HOLD_WAIT') == '1':
        (state / 'wait-ready').touch()
        deadline = time.monotonic() + 25
        while not (state / 'release-wait').exists():
            if time.monotonic() > deadline:
                print('Fixture wait release timed out', file=sys.stderr)
                sys.exit(1)
            time.sleep(0.02)
    if failure == 'wait':
        print('Injected wait failure', file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
if name == 'curl':
    curl_count = sum(json.loads(line)['name'] == 'curl' for line in (state / 'calls.jsonl').read_text().splitlines())
    if os.environ.get('SMOKE_UNIT_DIES') == 'after_probe' and curl_count == int(os.environ['SMOKE_PROBE_COUNT']):
        for marker in (state / 'units').iterdir():
            marker.unlink()
    if failure == 'curl':
        print('500')
        print('Injected curl failure', file=sys.stderr)
        sys.exit(1)
    print('204')
    sys.exit(0)
if name == 'smoke-remove':
    print('Injected workdir cleanup failure', file=sys.stderr)
    sys.exit(1)
raise AssertionError(name)
'''


def _replace_paths(value, workdir, units):
    if isinstance(value, str):
        return value.replace('/run/vpn-smoketest', str(workdir)).replace(
            '/run/systemd/transient', str(units)
        )
    if isinstance(value, list):
        return [_replace_paths(item, workdir, units) for item in value]
    if isinstance(value, dict):
        return {key: _replace_paths(item, workdir, units) for key, item in value.items()}
    return value


def _replace_waits(tasks, remove_failure=False):
    for task in tasks:
        for section in ('block', 'rescue', 'always'):
            _replace_waits(task.get(section, []), remove_failure)
        if 'ansible.builtin.wait_for' in task:
            wait = task.pop('ansible.builtin.wait_for')
            task['ansible.builtin.command'] = (
                {'argv': ['smoke-vacancy', str(wait['port'])]} if wait.get('state') == 'stopped'
                else {'cmd': 'smoke-wait'}
            )
            task['changed_when'] = False
        # Local fixture identity replaces root ownership; modes and real file
        # operations remain unchanged. The fixture must never request sudo.
        for module in ('ansible.builtin.file', 'ansible.builtin.copy'):
            arguments = task.get(module, {})
            if arguments.get('owner') == 'root':
                arguments['owner'] = str(os.getuid())
            if arguments.get('group') == 'root':
                arguments['group'] = str(os.getgid())
        if remove_failure and task.get('ansible.builtin.file', {}).get('state') == 'absent':
            path = task.pop('ansible.builtin.file')['path']
            task['ansible.builtin.command'] = {'argv': ['smoke-remove', path]}
            task['changed_when'] = False


@pytest.fixture
def smoke_run(tmp_path):
    executable = shutil.which('ansible-playbook')
    assert executable, 'ansible-playbook is required for smoke control-flow tests'
    state = tmp_path / 'state'
    units = state / 'units'
    units.mkdir(parents=True)
    workdir = tmp_path / 'owned-smoke-workdir'
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    for name in ('systemd-run', 'systemctl', 'curl', 'smoke-wait', 'smoke-vacancy', 'smoke-remove'):
        path = binaries / name
        path.write_text(EXECUTABLE)
        path.chmod(0o700)
    config = tmp_path / 'ansible.cfg'
    config.write_text('[defaults]\nfact_caching=memory\n')
    template_dir = tmp_path / 'roles/snell/templates'
    template_dir.mkdir(parents=True)
    shutil.copyfile(
        ROOT / 'ansible/roles/snell/templates/smoke-client.json.j2',
        template_dir / 'smoke-client.json.j2',
    )
    playbook_dir = tmp_path / 'playbooks'
    playbook_dir.mkdir()

    def prepare(protocol='xray', *, subscription_only=False, disabled=False, failure='',
                stop_failure=False, collision=False, render_failure=False, remove_failure=False, collected=False,
                occupied_port=None, unit_dies='', snell_count=1):
        source = copy.deepcopy(yaml.safe_load((ROOT / 'ansible/playbooks/smoke-test.yml').read_text())[0])
        source = _replace_paths(source, workdir, units)
        _replace_waits(source['tasks'], remove_failure)
        source.update(hosts='localhost', become=False, gather_facts=False)
        source['vars']['ansible_python_interpreter'] = sys.executable
        source['vars']['vpn'] = {
            toggle: subscription_only or (not disabled and name == protocol)
            for name, toggle in TOGGLES.items()
        }
        source['vars']['vpn_subscription_only'] = subscription_only
        secrets = {} if subscription_only or disabled else {
            'xray': {'clients': [{'uuid': 'fixture-private-client', 'short_id': 'fixture-short'}],
                     'reality_public_key': 'fixture-public-key', 'server_names': ['example.invalid']},
            'hysteria': {'clients': [{'name': 'fixture', 'password': 'fixture-private-password'}]},
            'nginx_xhttp': {'server_name': 'example.invalid'},
            'snell': {'smoke_port_base': 32100, 'variants': [
                {'id': 'v4-stream', 'listen_port': 4443, 'client_version': 4, 'mode': 'stream'}]},
            'snell_secrets': {'variants': [
                {'id': 'v4-stream', 'psk': 'STUB_SMOKE_PSK_ONE', 'users': [{'userkey': 'STUB_SMOKE_USERKEY_ONE'}]}]},
        }
        if render_failure:
            if protocol in ('xray', 'hysteria'):
                secrets[protocol]['clients'] = []
            else:
                secrets['snell_secrets']['variants'] = []
        if snell_count == 2:
            secrets['snell']['variants'].append(
                {'id': 'v6-default', 'listen_port': 4444, 'client_version': 6, 'mode': 'default'})
            secrets['snell_secrets']['variants'].append(
                {'id': 'v6-default', 'psk': 'STUB_SMOKE_PSK_TWO', 'users': [{'userkey': 'STUB_SMOKE_USERKEY_TWO'}]})
        secrets_file = tmp_path / 'secrets.yml'
        secrets_file.write_text(yaml.safe_dump(secrets))
        secrets_file.chmod(0o600)
        playbook = playbook_dir / 'smoke.yml'
        playbook.write_text(yaml.safe_dump([source], sort_keys=False))
        env = {key: value for key, value in os.environ.items() if not key.startswith(('ANSIBLE_', 'SMOKE_'))}
        env.update(
            PATH=str(binaries) + os.pathsep + os.environ['PATH'],
            ANSIBLE_CONFIG=str(config), ANSIBLE_BECOME='false', ANSIBLE_DEBUG='false',
            ANSIBLE_VARS_ENABLED='', ANSIBLE_NOCOLOR='1', ANSIBLE_FORCE_COLOR='0',
            ANSIBLE_LOCAL_TEMP=str(tmp_path / 'ansible-local'),
            VPN_SECRETS_FILE=str(secrets_file), SMOKE_FIXTURE_STATE=str(state),
            SMOKE_FAILURE=failure, SMOKE_STOP_FAILURE='1' if stop_failure else '0',
            SMOKE_FOREIGN_COLLISION='1' if collision else '0',
            SMOKE_COLLECTED='1' if collected else '0',
            SMOKE_OCCUPIED_PORT='' if occupied_port is None else str(occupied_port),
            SMOKE_UNIT_DIES=unit_dies, SMOKE_PROBE_COUNT=str(snell_count if protocol == 'snell' else 1),
        )
        return [executable, '-i', 'localhost,', '-c', 'local', str(playbook)], env

    def execute(**options):
        argv, env = prepare(**options)
        return subprocess.run(argv, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=45)

    def calls():
        log = state / 'calls.jsonl'
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return execute, prepare, calls, workdir, units, state, tmp_path


@pytest.mark.parametrize('protocol', PROTOCOLS)
def test_smoke_positive_cleans_owned_resources(smoke_run, protocol):
    execute, _, calls, workdir, units, _, _ = smoke_run
    result = execute(protocol=protocol)
    assert result.returncode == 0, result.stdout + result.stderr
    operations = [call['name'] for call in calls()]
    assert operations.count('systemd-run') == 1 and operations.count('curl') == 1
    stops = [call for call in calls() if call['name'] == 'systemctl' and call['args'][0] == 'stop']
    assert len(stops) == 1
    start = next(call for call in calls() if call['name'] == 'systemd-run')
    unit = next(arg.split('=', 1)[1] for arg in start['args'] if arg.startswith('--unit='))
    assert re.fullmatch(rf'vpn-smoke-{protocol}-[a-z0-9]{{32}}', unit)
    assert stops[0]['args'][-1] == unit + '.service'
    assert '--property=RuntimeMaxSec=' + ('90' if protocol == 'snell' else '60') in start['args']
    assert not workdir.exists() and not list(units.iterdir())
    assert all(marker not in result.stdout + result.stderr for marker in ('fixture-private-', 'STUB_SMOKE_'))


@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('failure', ('start', 'wait', 'curl'))
def test_smoke_failure_preserves_uncertain_claim_or_cleans_confirmed_resources(smoke_run, protocol, failure):
    execute, _, calls, workdir, units, _, _ = smoke_run
    result = execute(protocol=protocol, failure=failure)
    assert result.returncode != 0
    assert f'Injected {failure} failure' in result.stdout + result.stderr
    assert workdir.exists() is (failure == 'start')
    assert not list(units.iterdir())
    stops = [call for call in calls() if call['name'] == 'systemctl' and call['args'][0] == 'stop']
    assert len(stops) == (0 if failure == 'start' else 1)


@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('failure', ('', 'curl'))
def test_smoke_cleanup_error_is_fatal_without_masking_probe_failure(smoke_run, protocol, failure):
    execute, _, _, workdir, units, _, _ = smoke_run
    result = execute(protocol=protocol, failure=failure, stop_failure=True)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert 'Injected cleanup failure' in output
    if failure:
        assert 'Injected curl failure' in output
    assert workdir.is_dir(), 'an unconfirmed stop must retain the exclusive private claim'
    assert len(list(units.iterdir())) == 1, 'fixture records the failed stop honestly'


@pytest.mark.parametrize('subscription_only, disabled', [(True, False), (False, True)])
def test_smoke_skips_all_transport_access_without_credentials(smoke_run, subscription_only, disabled):
    execute, _, calls, workdir, _, _, _ = smoke_run
    result = execute(subscription_only=subscription_only, disabled=disabled)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls() == []
    assert not workdir.exists()
    assert 'skipped' in result.stdout


@pytest.mark.parametrize('protocol', PROTOCOLS)
def test_smoke_start_collision_never_stops_foreign_unit(smoke_run, protocol):
    execute, _, calls, workdir, units, _, _ = smoke_run
    result = execute(protocol=protocol, collision=True)
    assert result.returncode != 0
    assert not [call for call in calls() if call['name'] == 'systemctl' and call['args'][0] == 'stop']
    assert [path.read_text() for path in units.iterdir()] == ['foreign-service']
    assert workdir.is_dir(), 'failed start is not proof that the fixed SOCKS port is free'


@pytest.mark.parametrize('protocol', PROTOCOLS)
def test_smoke_render_failure_cleans_without_starting_a_client(smoke_run, protocol):
    execute, _, calls, workdir, units, _, _ = smoke_run
    result = execute(protocol=protocol, render_failure=True)
    assert result.returncode != 0
    assert not calls(), 'credential/render failures occur before client/systemd/network executables'
    assert not workdir.exists() and not list(units.iterdir())
    assert all(marker not in result.stdout + result.stderr for marker in ('fixture-private-', 'STUB_SMOKE_'))


@pytest.mark.parametrize('failure', ('', 'curl'))
def test_smoke_workdir_cleanup_failure_is_reported_without_hiding_probe_failure(smoke_run, failure):
    execute, _, _, workdir, units, _, _ = smoke_run
    result = execute(failure=failure, remove_failure=True)
    assert result.returncode != 0
    assert 'Injected workdir cleanup failure' in result.stdout + result.stderr
    if failure:
        assert 'Injected curl failure' in result.stdout + result.stderr
    assert workdir.is_dir() and not list(units.iterdir())


@pytest.mark.parametrize('protocol', PROTOCOLS)
def test_smoke_cleanup_accepts_an_already_collected_owned_unit(smoke_run, protocol):
    execute, _, calls, workdir, units, _, _ = smoke_run
    result = execute(protocol=protocol, collected=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert any(call['name'] == 'systemctl' and call['args'][0] == 'stop' for call in calls())
    assert not workdir.exists() and not list(units.iterdir())


@pytest.mark.parametrize('failure, stop_failure, collision', [
    ('start', False, False), ('', True, False), ('curl', True, False), ('', False, True),
])
def test_smoke_unconfirmed_cleanup_keeps_claim_and_refuses_retry(smoke_run, failure, stop_failure, collision):
    execute, _, calls, workdir, units, _, _ = smoke_run
    first = execute(failure=failure, stop_failure=stop_failure, collision=collision)
    assert first.returncode != 0
    assert workdir.is_dir()
    assert workdir.stat().st_mode & 0o777 == 0o700
    private_files = {path.name: (path.read_bytes(), path.stat().st_mode & 0o777)
                     for path in workdir.iterdir()}
    assert private_files and all(mode == 0o600 for _, mode in private_files.values())
    original_units = {path.name: path.read_bytes() for path in units.iterdir()}
    original_calls = calls()
    retry = execute()
    assert retry.returncode != 0
    assert calls() == original_calls, 'retry must fail before any client/network/systemd operation'
    assert {path.name: path.read_bytes() for path in units.iterdir()} == original_units
    assert {path.name: (path.read_bytes(), path.stat().st_mode & 0o777)
            for path in workdir.iterdir()} == private_files
    assert 'manual recovery' in first.stdout + first.stderr


@pytest.mark.parametrize('protocol, port, snell_count', [
    ('xray', 31080, 1), ('hysteria', 31081, 1), ('snell', 32100, 1), ('snell', 32101, 2),
])
def test_smoke_occupied_port_refuses_before_start_without_touching_foreign_listener(smoke_run, protocol, port, snell_count):
    execute, _, calls, workdir, units, state, _ = smoke_run
    foreign_listener = state / 'foreign-listener'
    foreign_listener.write_text('preserve-listener')
    result = execute(protocol=protocol, occupied_port=port, snell_count=snell_count)
    assert result.returncode != 0
    assert 'Injected occupied port' in result.stdout + result.stderr
    assert not [call for call in calls() if call['name'] in ('systemd-run', 'curl', 'systemctl')]
    assert foreign_listener.read_text() == 'preserve-listener'
    assert not workdir.exists() and not list(units.iterdir())


@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('unit_dies', ('before_probe', 'after_probe'))
def test_smoke_own_unit_death_cannot_pass_through_a_foreign_listener(smoke_run, protocol, unit_dies):
    execute, _, calls, workdir, units, _, _ = smoke_run
    result = execute(protocol=protocol, unit_dies=unit_dies)
    assert result.returncode != 0
    assert 'Injected own-unit inactive' in result.stdout + result.stderr
    curl_calls = [call for call in calls() if call['name'] == 'curl']
    assert len(curl_calls) == (0 if unit_dies == 'before_probe' else 1)
    assert not workdir.exists() and not list(units.iterdir())


@pytest.mark.parametrize('unit_dies', ('', 'after_probe'))
def test_smoke_snell_checks_own_unit_after_all_variant_probes(smoke_run, unit_dies):
    execute, _, calls, workdir, units, _, _ = smoke_run
    result = execute(protocol='snell', snell_count=2, unit_dies=unit_dies)
    assert (result.returncode == 0) is (not unit_dies), result.stdout + result.stderr
    trace = calls()
    probes = [index for index, call in enumerate(trace) if call['name'] == 'curl']
    active_checks = [index for index, call in enumerate(trace)
                     if call['name'] == 'systemctl' and call['args'][0] == 'is-active']
    assert len(probes) == 2 and len(active_checks) == 2
    assert active_checks[0] < probes[0] < probes[1] < active_checks[1]
    assert not workdir.exists() and not list(units.iterdir())


def test_smoke_refuses_occupied_workdir_without_adopting_it(smoke_run):
    execute, _, calls, workdir, _, _, _ = smoke_run
    workdir.mkdir(mode=0o700)
    marker = workdir / 'existing-private-data'
    marker.write_text('preserve-me')
    result = execute()
    assert result.returncode != 0
    assert marker.read_text() == 'preserve-me'
    assert not [call for call in calls() if call['name'] in ('systemd-run', 'curl') or call['args'][0] == 'stop']


def test_smoke_concurrent_run_cannot_stop_or_remove_the_owner(smoke_run):
    _, prepare, calls, workdir, units, state, cwd = smoke_run
    argv, env = prepare()
    owner_env = {**env, 'SMOKE_RUN': 'owner', 'SMOKE_HOLD_WAIT': '1'}
    owner = subprocess.Popen(argv, env=owner_env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 20
        while not (state / 'wait-ready').exists() and owner.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (state / 'wait-ready').exists(), 'owner must reach its local fixture listener'
        contender = subprocess.run(argv, env={**env, 'SMOKE_RUN': 'contender'}, cwd=cwd,
                                   capture_output=True, text=True, timeout=20)
        assert contender.returncode != 0, contender.stdout + contender.stderr
        assert workdir.is_dir() and len(list(units.iterdir())) == 1
        assert not [call for call in calls() if call['run'] == 'contender' and
                    (call['name'] in ('systemd-run', 'curl') or call['args'][0] == 'stop')]
    finally:
        (state / 'release-wait').touch()
        try:
            stdout, stderr = owner.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            owner.kill()
            stdout, stderr = owner.communicate()
    assert owner.returncode == 0, stdout + stderr
    assert not workdir.exists() and not list(units.iterdir())


@pytest.mark.parametrize('protocol, snell_index', [('xray', 0), ('hysteria', 0), ('snell', 0), ('snell', 1)])
@pytest.mark.parametrize('bypass_variable', ('NO_PROXY', 'no_proxy'))
def test_smoke_real_curl_cannot_bypass_closed_proxy_via_no_proxy(tmp_path, protocol, snell_index, bypass_variable):
    curl = shutil.which('curl')
    assert curl, 'real curl is required for proxy bypass regression'
    names = {'xray': 'Probe through REALITY proxy', 'hysteria': 'Probe through Hysteria proxy',
             'snell': 'Probe through every Snell variant'}

    def find_probe(tasks):
        for task in tasks:
            if task['name'] == names[protocol]:
                return task['ansible.builtin.command']['cmd']
            for section in ('block', 'rescue', 'always'):
                command = find_probe(task.get(section, []))
                if command is not None:
                    return command
        return None

    source = yaml.safe_load((ROOT / 'ansible/playbooks/smoke-test.yml').read_text())[0]
    command = find_probe(source['tasks'])
    assert command is not None
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args):
            pass

    env = {key: value for key, value in os.environ.items() if not key.lower().endswith('_proxy')}
    env.update(HOME=str(tmp_path), CURL_HOME=str(tmp_path), **{bypass_variable: '*'})
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server, socket.socket() as closed_proxy:
        # Reserve a unique port without listening: no other process can claim it.
        closed_proxy.bind(('127.0.0.1', 0))
        proxy_port = closed_proxy.getsockname()[1]
        target = f'http://127.0.0.1:{server.server_port}/generate_204'
        thread = Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        try:
            control = subprocess.run([curl, '-sS', '-o', '/dev/null', '-w', '%{http_code}',
                                      '--max-time', '5', target], env=env, cwd=tmp_path,
                                     capture_output=True, text=True, timeout=10)
            assert control.returncode == 0 and control.stdout == '204', control.stderr
            assert requests == ['/generate_204']
            # Preserve the source curl options; relocate only its target and SOCKS
            # endpoint to dynamic local fixtures. Render the real Snell expression.
            for source_port in (31080, 31081):
                command = command.replace(f'socks5h://127.0.0.1:{source_port}',
                                          f'socks5h://127.0.0.1:{proxy_port}')
            rendered = Environment(undefined=StrictUndefined).from_string(command).render(
                smoketest_target=target, snell={'smoke_port_base': proxy_port - snell_index},
                snell_index=snell_index)
            argv = shlex.split(rendered)
            assert argv[0] == 'curl'
            result = subprocess.run([curl, *argv[1:]], env=env, cwd=tmp_path,
                                    capture_output=True, text=True, timeout=20)
            assert result.returncode != 0, 'closed SOCKS proxy must fail even with inherited NO_PROXY=*'
            assert result.stdout == '000', result.stdout + result.stderr
            assert requests == ['/generate_204'], 'smoke must not reach the HTTP target directly'
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()
