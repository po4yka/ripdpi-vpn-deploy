"""Real local subprocess discovery boundaries, not live publisher acceptance."""
import inspect
import json
import os
import subprocess
import sys
import time

import pytest

import device_lifecycle_publishers as publishers


UNITS = ("vpn-bootstrap.service", "vpn-sub-mirror.timer")


def state(*, active=False):
    return "\n\n".join(
        f"Id={unit}\nLoadState={'loaded' if active else 'not-found'}\n"
        f"ActiveState={'active' if active else 'inactive'}\nSubState={'running' if active else 'dead'}\n"
        + (f"MainPID={'123' if active else '0'}\n" if unit.endswith('.service') else "")
        for unit in UNITS
    )


def run_worker(tmp_path, output=None, *, status=0, paths=None, body=None):
    command = tmp_path / 'systemctl'
    command.write_text(f'#!{sys.executable}\n' + (body if body is not None else
                       f'import sys\nsys.stdout.write({(state() if output is None else output)!r})\nsys.exit({status})\n'))
    command.chmod(0o700)
    paths = paths if paths is not None else [str(tmp_path / 'missing')]
    program = (inspect.getsource(publishers._worker) + '\nimport json,sys\ntry:\n'
               f'    print(json.dumps(_worker(paths={paths!r},units={UNITS!r},systemctl={str(command)!r})))\n'
               "except Exception:\n    print('publisher-discovery-unconfirmed',file=sys.stderr)\n    sys.exit(2)\n")
    return subprocess.run([sys.executable, '-I', '-B', '-S', '-'], input=program.encode(),
                          capture_output=True, timeout=15)


def test_actual_subprocess_requires_complete_inactive_absence(tmp_path):
    result = run_worker(tmp_path)
    assert result.returncode == 0 and result.stdout == b'false\n' and result.stderr == b''
    active = run_worker(tmp_path, state(active=True))
    assert active.returncode == 0 and active.stdout == b'true\n'


@pytest.mark.parametrize('kind', ['file', 'broken-symlink', 'directory'])
def test_exact_owned_authority_presence_is_never_assumed_retired(tmp_path, kind):
    path = tmp_path / 'retained'
    if kind == 'file':
        path.write_text('private-publisher-value')
    elif kind == 'broken-symlink':
        path.symlink_to(tmp_path / 'missing-destination')
    else:
        path.mkdir()
    result = run_worker(tmp_path, paths=[str(path)], status=3)
    assert result.returncode == 0 and result.stdout == b'true\n'
    assert b'private-publisher-value' not in result.stdout + result.stderr


@pytest.mark.parametrize('output,status', [
    ('', 0), (state() + '\nPrivate=secret', 0), (state().replace('MainPID=0', 'MainPID=x'), 0),
    (state().replace('LoadState=not-found', 'LoadState=error'), 0),
    (state().split('\n\n')[0], 0), (state(), 3), ('private-diagnostic' * 2000, 0),
    (state().replace('Id=vpn-bootstrap.service', 'Id=vpn-bootstrap.service\nId=other.service'), 0),
])
def test_malformed_missing_oversized_or_failed_commands_refuse(tmp_path, output, status):
    result = run_worker(tmp_path, output, status=status)
    assert result.returncode == 2 and not result.stdout
    assert result.stderr == b'publisher-discovery-unconfirmed\n'


def test_timeout_reaps_actual_owned_child(tmp_path):
    pidfile = tmp_path / 'pid'
    result = run_worker(tmp_path, body=f'import os,time\nopen({str(pidfile)!r},"w").write(str(os.getpid()))\ntime.sleep(30)\n')
    assert result.returncode == 2 and result.stderr == b'publisher-discovery-unconfirmed\n'
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_shipped_worker_cancellation_reaps_owned_group(tmp_path):
    pidfile = tmp_path / 'pid'
    command = tmp_path / 'systemctl'
    command.write_text(f'#!{sys.executable}\nimport os,time\nopen({str(pidfile)!r},"w").write(str(os.getpid()))\ntime.sleep(30)\n')
    command.chmod(0o700)
    invocation = f'_worker(paths={[str(tmp_path / "missing")]!r},units={UNITS!r},systemctl={str(command)!r})'
    program = publishers.worker_program().replace(b'result = _worker()', ('result = ' + invocation).encode())
    process = subprocess.Popen([sys.executable, '-I', '-B', '-S', '-'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.stdin.write(program)
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pidfile.exists()
        process.terminate()
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 2 and not output and errors == b'publisher-discovery-unconfirmed\n'
        with pytest.raises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize('wire', [
    '{"schema_version":1,"active_possible":false}',
    '{"schema_version":1,"active_possible":true}',
    '{"schema_version":1,"active_possible":false,"active_possible":true}',
    '{"schema_version":true,"active_possible":false}',
    '{"schema_version":1,"active_possible":0}',
    'private-ssh-diagnostic',
])
def test_controller_validates_actual_child_output_without_printing_it(monkeypatch, wire):
    remote = 'sudo -n /usr/bin/python3 -I -B -S -'
    def actual_child(argv, **kwargs):
        assert argv[-1] == remote and kwargs['timeout'] == 30
        assert b'/etc/nginx/sites-enabled/vpn-sub.conf' in kwargs['input_bytes']
        result = subprocess.run([sys.executable, '-I', '-S', '-c', 'import sys;sys.stdout.write(sys.argv[1])', wire],
                                capture_output=True, check=True, timeout=5)
        return result.stdout
    monkeypatch.setattr(publishers, 'bounded_command', actual_child)
    if wire in ('{"schema_version":1,"active_possible":false}', '{"schema_version":1,"active_possible":true}'):
        assert publishers.probe({'transport': 'fixture'}, ['ssh', 'fixture', remote]) is json.loads(wire)['active_possible']
    else:
        with pytest.raises(ValueError, match='^publisher-discovery-unconfirmed$'):
            publishers.probe({'transport': 'fixture'}, ['ssh', 'fixture', remote])


def test_controller_transport_error_is_not_absence(monkeypatch):
    def failed(*args, **kwargs):
        subprocess.run([sys.executable, '-I', '-S', '-c', 'raise SystemExit(3)'], check=True, capture_output=True)
    monkeypatch.setattr(publishers, 'bounded_command', failed)
    with pytest.raises(ValueError, match='^publisher-discovery-unconfirmed$'):
        publishers.probe({'transport': 'fixture'}, ['ssh', 'fixture', 'sudo -n /usr/bin/python3 -I -B -S -'])
