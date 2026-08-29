#!/usr/bin/env python3
"""Fixed installed SSH transaction adapter; JSON input is bounded and private."""
from __future__ import annotations

import argparse
import base64
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


def _command(arguments, *, deadline=None):
    """No shell, bounded stdout/stderr and process-group cleanup on timeout."""
    now = time.monotonic()
    deadline = min(now + COMMAND_TIMEOUT, deadline) if deadline is not None else now + COMMAND_TIMEOUT
    if deadline <= now:
        raise TransactionError('command-timeout')
    with subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=True, env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'LANG':'C'}) as process:
        output = bytearray()
        total = 0
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
    def build_plan(self, config, contexts, *, intent, hardening):
        if intent == 'sshd-ownership' and hardening is None:
            return ownership.build_plan(config, contexts=contexts)
        if intent == 'sshd-baseline' and type(hardening) is bytes:
            return ownership.build_baseline_plan(config, contexts=contexts, hardening=hardening)
        raise TransactionError('intent-invalid')

    def assert_snapshot(self, plan, config):
        ownership.assert_snapshot(plan, config)

    def assert_effective(self, plan, config, *, phase):
        ownership.assert_effective(plan, config, phase=phase)

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

    @staticmethod
    def activation_clock():
        # systemd's process timestamps use CLOCK_MONOTONIC, not lease BOOTTIME.
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC) // 1000

    def _budget(self, deadline):
        if self.activation_clock() >= deadline:
            raise TransactionError('recovery-deadline')

    def _show(self, unit, fields, deadline):
        self._budget(deadline)
        raw = _command(['/usr/bin/systemctl', 'show', unit,
                        '--property=' + ','.join(fields)], deadline=deadline / 1000000)
        values = {}
        for line in raw.splitlines():
            key, separator, value = line.partition('=')
            if not separator or key not in fields or key in values:
                raise TransactionError('recovery-properties-invalid')
            values[key] = value
        if set(values) != set(fields):
            raise TransactionError('recovery-properties-invalid')
        self._budget(deadline)
        return values

    def _capability(self, deadline):
        self._budget(deadline)
        directory = _validate_installation()
        units = {}
        common = ('LoadState', 'NeedDaemonReload', 'FragmentPath', 'DropInPaths', 'ActiveState', 'SubState')
        execution = ('Result', 'MainPID', 'ExecMainPID', 'ExecMainCode', 'ExecMainStatus',
                     'ExecMainStartTimestampMonotonic', 'ExecMainExitTimestampMonotonic')
        for unit in UNIT_HASHES:
            fields = common + (execution if unit.endswith('.service') else ('Requires', 'After'))
            if unit != 'vpn-sshd-recover.service':
                fields += ('UnitFileState',)
            values = self._show(unit, fields, deadline)
            fragments = {str(UNIT_ROOT / unit), str(BUNDLE_ROOT / 'current/units' / unit),
                         str(directory / 'units' / unit)}
            if (values['LoadState'] != 'loaded' or values['NeedDaemonReload'] != 'no'
                    or values['FragmentPath'] not in fragments or values['DropInPaths']):
                raise TransactionError('recovery-capability-invalid')
            units[unit] = values
        timer = units['vpn-sshd-recover.timer']
        boot = units['vpn-sshd-boot-recover.service']
        if (timer['UnitFileState'] != 'enabled' or timer['ActiveState'] != 'active'
                or timer['SubState'] not in {'waiting', 'running'}
                or boot['UnitFileState'] != 'enabled' or self._completed(boot) is None):
            raise TransactionError('recovery-capability-invalid')
        for unit in ('ssh.service', 'ssh.socket'):
            units[unit] = self._show(unit, ('Requires', 'After'), deadline)
        for unit in ('ssh.service', 'ssh.socket', 'vpn-sshd-recover.timer'):
            if any('vpn-sshd-boot-recover.service' not in units[unit][field].split()
                   for field in ('Requires', 'After')):
                raise TransactionError('recovery-capability-invalid')
        boot_id = self.boot_id()
        self._budget(deadline)
        return {'generation': str(directory), 'boot_id': boot_id, 'units': units}

    def _completed(self, values, status='0'):
        numbers = [values[name] for name in ('ExecMainPID', 'ExecMainStartTimestampMonotonic',
                                             'ExecMainExitTimestampMonotonic')]
        if (any(re.fullmatch('[1-9][0-9]{0,19}', value) is None for value in numbers)
                or values['ActiveState'] != 'inactive' or values['SubState'] != 'dead'
                or values['Result'] != 'success' or values['ExecMainCode'] != '1'
                or values['ExecMainStatus'] != status or values['MainPID'] != '0'):
            return None
        pid, started, exited = map(int, numbers)
        return (pid, started, exited) if started <= exited <= self.activation_clock() else None

    def recovery_ready(self):
        try:
            snapshot = self._capability(self.activation_clock() + 30000000)
            return self._completed(snapshot['units']['vpn-sshd-recover.service']) is not None
        except (TransactionError, OSError):
            return False

    def activation_recovery(self):
        deadline = self.activation_clock() + 30000000
        try:
            # Do not erase a real previous failure by starting the service.
            # Only completed success or known lock contention permits one new
            # execution; neither substitutes for that call's fresh exit-0 proof.
            before = self._capability(deadline)
            previous_worker = before['units']['vpn-sshd-recover.service']
            if (self._completed(previous_worker) is None
                    and self._completed(previous_worker, '75') is None):
                raise TransactionError('recovery-previous-execution-invalid')
            started_after = self.activation_clock()
            _command(['/usr/bin/systemctl', 'start', 'vpn-sshd-recover.service'],
                     deadline=deadline / 1000000)
            current = self._capability(deadline)
            worker = current['units']['vpn-sshd-recover.service']
            identity = self._completed(worker)
            if (identity is None or identity[1] < started_after
                    or identity[2] > self.activation_clock()
                    or worker == before['units']['vpn-sshd-recover.service']
                    or current['generation'] != before['generation']
                    or current['boot_id'] != before['boot_id']
                    or current['units']['vpn-sshd-boot-recover.service'] != before['units']['vpn-sshd-boot-recover.service']):
                raise TransactionError('recovery-execution-not-fresh')
            self._budget(deadline)
            return {'snapshot': current, 'identity': identity, 'deadline': deadline,
                    'started_after': started_after, 'observed_at': self.activation_clock()}
        except (TransactionError, OSError):
            return None

    def activation_fence(self, proof, acquired):
        try:
            if (not isinstance(proof, dict)
                    or set(proof) != {'snapshot', 'identity', 'deadline', 'started_after', 'observed_at'}
                    or any(type(value) is not int for value in
                           (acquired, proof['deadline'], proof['started_after'], proof['observed_at']))):
                return False
            fresh = self._completed(proof['snapshot']['units']['vpn-sshd-recover.service'])
            if (fresh is None or fresh != proof['identity']
                    or not 0 < proof['started_after'] <= fresh[1] <= fresh[2] <= proof['observed_at'] <= acquired <= self.activation_clock()
                    or not proof['observed_at'] < proof['deadline'] <= proof['started_after'] + 30000000):
                return False
            self._budget(proof['deadline'])
            current = self._capability(proof['deadline'])
            previous = proof['snapshot']
            worker_name = 'vpn-sshd-recover.service'
            def stable(unit, values):
                # The timer changes waiting/running while its pinned worker is
                # in flight; both states remain active and were checked above.
                return {key: value for key, value in values.items()
                        if unit != 'vpn-sshd-recover.timer' or key != 'SubState'}
            if (current['generation'] != previous['generation'] or current['boot_id'] != previous['boot_id']
                    or any(stable(unit, current['units'][unit]) != stable(unit, previous['units'][unit])
                           for unit in current['units'] if unit != worker_name)):
                return False
            worker = current['units'][worker_name]
            if worker == previous['units'][worker_name] and self._completed(worker) == proof['identity']:
                return True
            # Only a different execution starting strictly after this caller
            # acquired the transaction lock can be its own periodic contention.
            busy = self._completed(worker, '75')
            if busy is not None:
                return acquired < busy[1] <= busy[2] <= self.activation_clock()
            started = worker['ExecMainStartTimestampMonotonic']
            return (worker['ActiveState'] == 'activating' and worker['SubState'] == 'start'
                    and worker['Result'] == 'success' and worker['ExecMainCode'] == '0'
                    and worker['ExecMainStatus'] == '0' and worker['ExecMainExitTimestampMonotonic'] == '0'
                    and re.fullmatch('[1-9][0-9]{0,19}', worker['ExecMainPID']) is not None
                    and worker['MainPID'] == worker['ExecMainPID']
                    and re.fullmatch('[1-9][0-9]{0,19}', started) is not None
                    and acquired < int(started) <= self.activation_clock())
        except (TransactionError, OSError, KeyError, TypeError, ValueError, IndexError):
            return False


def validate_request(action, request):
    fields = {'prepare': {'intent', 'contexts', 'timeout'}, 'apply': {'generation', 'nonce'},
              'confirm': {'generation', 'nonce', 'snapshot_digest'}, 'rollback': {'generation', 'nonce'}}
    try:
        if action == 'prepare':
            if not isinstance(request, dict) or request.get('intent') not in {'sshd-ownership', 'sshd-baseline'}:
                raise ValueError
            if request['intent'] == 'sshd-baseline':
                fields['prepare'].add('hardening_b64')
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
            if request['intent'] == 'sshd-baseline':
                encoded = request['hardening_b64']
                if not isinstance(encoded, str) or len(encoded) > 10924:
                    raise ValueError
                hardening = base64.b64decode(encoded, validate=True)
                if not 0 < len(hardening) <= 8192 or base64.b64encode(hardening).decode() != encoded:
                    raise ValueError
                return {key: value for key, value in request.items() if key != 'hardening_b64'} | {'hardening': hardening}
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
