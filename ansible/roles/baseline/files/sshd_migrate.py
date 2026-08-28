#!/usr/bin/env python3
"""Fixed installed SSH transaction adapter; JSON input is bounded and private."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
BUNDLE_ROOT = Path('/usr/local/lib/vpn-sshd')
UNIT_ROOT = Path('/etc/systemd/system')

# The isolated interpreter does not add this directory to sys.path. Load only
# adjacent root-owned modules, never PYTHONPATH or the operator working directory.
def _module(name, directory=None):
    directory = directory or Path(__file__).absolute().parent
    if __name__ == '__main__':
        for parent in (directory, *directory.parents):
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise RuntimeError('installation-unsafe')
        info = (directory / (name + '.py')).lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1:
            raise RuntimeError('installation-unsafe')
    spec = importlib.util.spec_from_file_location(name, directory / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transaction = _module('sshd_transaction')
ownership = _module('sshd_ownership')
TransactionError = transaction.TransactionError
MAX_OUTPUT = 65536
COMMAND_TIMEOUT = 10
UNIT_HASHES = {'vpn-sshd-boot-recover.service': 'f000d66c64bdeaf2148d3053f569e587a9b9d4dda3b42502d16261d12a67946d', 'vpn-sshd-recover.service': '6f6f66d895f463b50af1bd34ac90100edad0015a764a791dcc1b0d56f1f7121b', 'vpn-sshd-recover.timer': '8f25882b7f60d9795acfb90dead7c037590693f879d58fc424be164224125c6d'}


def _command(arguments):
    """No shell, bounded stdout/stderr and process-group cleanup on timeout."""
    with subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=True, env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'LANG':'C'}) as process:
        output = bytearray()
        total = 0
        deadline = time.monotonic() + COMMAND_TIMEOUT
        selector = selectors.DefaultSelector()
        try:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransactionError('command-timeout')
                for key, _ in selector.select(remaining):
                    data = os.read(key.fileobj.fileno(), 8192)
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        total += len(data)
                        if total > MAX_OUTPUT:
                            raise TransactionError('command-output-limit')
                        if key.fileobj is process.stdout:
                            output.extend(data)
            process.wait(timeout=max(0.01, deadline-time.monotonic()))
            if process.returncode:
                raise TransactionError('command-failed')
            return output.decode('utf-8', errors='strict').strip()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise TransactionError('command-failed') from None
        finally:
            selector.close()
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    # The group already exited; wait below still reaps the leader.
                    pass
                process.wait()


def _validate_installation():
    transaction._read(BUNDLE_ROOT / 'sshd_bundle.py')
    bundle = _module('sshd_bundle', BUNDLE_ROOT)
    try:
        installed = bundle.Bundle(BUNDLE_ROOT, transaction.STATE_ROOT, UNIT_ROOT, None)
        generation = installed._current()
        directory = installed._generation(generation)
        if directory != Path(__file__).absolute().parent:
            raise TransactionError('recovery-generation-stale')
        installed._check_links()
        return directory
    except bundle.BundleError:
        raise TransactionError('recovery-installation-unsafe') from None


class Runtime:
    def build_plan(self, config, contexts):
        return ownership.build_plan(config, contexts=contexts)

    def assert_snapshot(self, plan, config):
        ownership.assert_snapshot(plan, config)

    def assert_effective(self, plan, config):
        ownership.assert_effective(plan, config)

    def clock(self):
        return int(time.time())

    def monotonic(self):
        return int(time.clock_gettime(time.CLOCK_BOOTTIME))

    def boot_id(self):
        value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        transaction._uuid(value)
        return value

    def reload(self):
        _command(['/usr/bin/systemctl', 'reload', 'ssh.service'])

    def recovery_ready(self):
        try:
            directory = _validate_installation()
            def systemctl(*arguments):
                return _command(['/usr/bin/systemctl', *arguments])
            if (systemctl('is-enabled', 'vpn-sshd-recover.timer') != 'enabled'
                    or systemctl('is-enabled', 'vpn-sshd-boot-recover.service') != 'enabled'):
                return False
            if systemctl('is-active', 'vpn-sshd-recover.timer') != 'active':
                return False
            for unit in UNIT_HASHES:
                # systemd versions expose either the unit lookup path or the
                # resolved fragment. Every allowed path is independently pinned.
                fragments = {str(UNIT_ROOT / unit), str(BUNDLE_ROOT / 'current/units' / unit)}
                if directory is not None:
                    fragments.add(str(directory / 'units' / unit))
                if (systemctl('show', unit, '--property=LoadState', '--value') != 'loaded'
                        or systemctl('show', unit, '--property=NeedDaemonReload', '--value') != 'no'
                        or systemctl('show', unit, '--property=FragmentPath', '--value') not in fragments
                        or systemctl('show', unit, '--property=DropInPaths', '--value')):
                    return False
                # A live timer is not recovery capability when its worker (or
                # the boot dependency) has already failed to execute.
                if unit.endswith('.service') and (
                        systemctl('show', unit, '--property=ActiveState', '--value') not in {'inactive', 'active'}
                        or systemctl('show', unit, '--property=Result', '--value') != 'success'):
                    return False
                if unit.endswith('.service'):
                    started = systemctl('show', unit, '--property=ExecMainStartTimestampMonotonic', '--value')
                    exited = systemctl('show', unit, '--property=ExecMainExitTimestampMonotonic', '--value')
                    if (not re.fullmatch('[1-9][0-9]{0,19}', started)
                            or not re.fullmatch('[1-9][0-9]{0,19}', exited)
                            or int(exited) < int(started)
                            or systemctl('show', unit, '--property=ExecMainStatus', '--value') != '0'):
                        return False
            for unit in ('ssh.service', 'ssh.socket', 'vpn-sshd-recover.timer'):
                for prop in ('Requires', 'After'):
                    if 'vpn-sshd-boot-recover.service' not in systemctl('show', unit, '--property='+prop, '--value').split():
                        return False
            return True
        except (TransactionError, OSError):
            return False


def validate_request(action, request):
    fields = {'prepare': {'contexts', 'timeout'}, 'apply': {'generation', 'nonce'},
              'confirm': {'generation', 'nonce', 'snapshot_digest'}, 'rollback': {'generation', 'nonce'}}
    try:
        if not isinstance(request, dict) or set(request) != fields[action]:
            raise ValueError
        if action == 'prepare':
            if not isinstance(request['contexts'], list) or not 2 <= len(request['contexts']) <= 8:
                raise ValueError
            for context in request['contexts']:
                transaction._context(context)
            if len({transaction._digest(context) for context in request['contexts']}) != len(request['contexts']):
                raise ValueError
            if type(request['timeout']) is not int or not 60 <= request['timeout'] <= 600:
                raise ValueError
        else:
            transaction._uuid(request['generation'])
            transaction._hex(request['nonce'])
            if action == 'confirm':
                transaction._hex(request['snapshot_digest'])
        return request
    except (ValueError, TypeError, KeyError):
        raise TransactionError('request-invalid') from None


def _request():
    selector = selectors.DefaultSelector()
    data = bytearray()
    deadline = time.monotonic() + 5
    try:
        os.set_blocking(sys.stdin.fileno(), False)
        selector.register(sys.stdin, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TransactionError('request-timeout')
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 16384:
                raise TransactionError('request-too-large')
        return json.loads(data)
    except (OSError, ValueError):
        raise TransactionError('request-invalid') from None
    finally:
        selector.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare','apply','confirm','rollback','status','recover','boot-recover','check-installation'))
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise TransactionError('root-required')
        if args.action == 'check-installation':
            if not Runtime().recovery_ready():
                raise TransactionError('recovery-not-ready')
            print(json.dumps({'status': 'ready'}))
            return 0
        engine = transaction.Transaction(transaction.CONFIG_ROOT, transaction.STATE_ROOT, Runtime())
        if args.action in {'status', 'recover', 'boot-recover'}:
            result = engine.status() if args.action == 'status' else engine.recover(boot=args.action == 'boot-recover')
        else:
            request = validate_request(args.action, _request())
            result = getattr(engine, args.action)(**request)
        # systemd recovery must not put an active transaction nonce in the journal.
        if args.action in {'recover', 'boot-recover'}:
            result = {'status': result['status']}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (TransactionError, ownership.OwnershipError, OSError, ValueError) as error:
        if args.action == 'recover' and isinstance(error, TransactionError) and str(error) == 'busy':
            # Periodic recovery retries on its next tick. Boot recovery must
            # instead fail and prevent listeners starting over uncertain state.
            print(json.dumps({'status': 'deferred', 'reason': 'busy'}))
            return 75
        print(json.dumps({'status':'error','reason':'ssh-transaction-failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
