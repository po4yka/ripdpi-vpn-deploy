#!/usr/bin/env python3
"""Fixed root-only publication and dispatch of immutable SSH recovery packages."""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import fcntl
import hashlib
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
import tempfile
import time

ROOT = Path('/usr/local/lib/vpn-sshd')
STATE = Path('/var/lib/vpn-sshd-transaction')
SYSTEMD = Path('/etc/systemd/system')
MODULES = ('sshd_migrate.py', 'sshd_transaction.py', 'sshd_ownership.py')
UNITS = ('vpn-sshd-boot-recover.service', 'vpn-sshd-recover.service', 'vpn-sshd-recover.timer')
FILES = set(MODULES) | {'units/' + name for name in UNITS}
ACTIONS = ('prepare', 'apply', 'confirm', 'rollback', 'status', 'recover', 'boot-recover')
TERMINAL = {'idle', 'committed', 'rolled_back'}
LIMIT = 1024 * 1024
sys.dont_write_bytecode = True


class BundleError(Exception):
    """Categorical diagnostics, never source or private transaction contents."""


def _identifier(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise BundleError('generation-invalid')
    return value


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError):
        raise BundleError('json-invalid') from None


def _directory(path, private=False):
    for parent in (path, *path.parents):
        info = parent.lstat()
        sticky = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or (info.st_mode & 0o022 and not sticky)):
            raise BundleError('directory-unsafe')
    if private and stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise BundleError('directory-not-private')


def _integrity(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
                                               'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def _read(path, private=False):
    _directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise BundleError('file-unsafe') from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != (0o600 if private else 0o644) or info.st_size > LIMIT):
            raise BundleError('file-unsafe')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            content = stream.read(LIMIT + 1)
        if (len(content) > LIMIT or _integrity(info) != _integrity(os.fstat(fd))
                or _integrity(info) != _integrity(path.lstat())):
            raise BundleError('file-changed')
        return content
    finally:
        os.close(fd)


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path, content):
    fd, temporary = tempfile.mkstemp(prefix='.bundle-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o600)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _lock(path, exclusive, create=True):
    _directory(path.parent)
    fd = os.open(path, (os.O_CREAT if create else 0) | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise BundleError('lock-unsafe')
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BundleError('busy') from None
        if _integrity(info) != _integrity(path.lstat()):
            raise BundleError('lock-changed')
        yield fd
    finally:
        os.close(fd)


class Bundle:
    """Filesystem seams are test-only. The CLI fixes all three roots."""
    def __init__(self, root, state, units, runtime):
        self.root, self.state, self.units = Path(root), Path(state), Path(units)
        self.runtime = runtime

    def _current(self):
        path = self.root / 'current'
        if not os.path.lexists(path):
            return None
        info = path.lstat()
        target = os.readlink(path) if stat.S_ISLNK(info.st_mode) else ''
        if info.st_uid != os.geteuid() or re.fullmatch('generations/[0-9a-f]{64}', target) is None:
            raise BundleError('current-unsafe')
        return target.split('/')[1]

    def _generation(self, generation, staged=False):
        _identifier(generation)
        if staged:
            _directory(self.root / 'staging', private=True)
        directory = self.root / ('staging' if staged else 'generations') / generation
        _directory(directory)
        _directory(directory / 'units')
        if ({p.name for p in directory.iterdir()} != set(MODULES) | {'units', 'manifest.json'}
                or {p.name for p in (directory / 'units').iterdir()} != set(UNITS)):
            raise BundleError('generation-layout-invalid')
        raw = _read(directory / 'manifest.json')
        manifest = _json(raw)
        if (not isinstance(manifest, dict) or set(manifest) != {'schema_version', 'files'}
                or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1
                or not isinstance(manifest['files'], dict) or set(manifest['files']) != FILES
                or hashlib.sha256(raw).hexdigest() != generation):
            raise BundleError('manifest-invalid')
        trees = {}
        for name, digest in manifest['files'].items():
            _identifier(digest)
            content = _read(directory / name)
            if hashlib.sha256(content).hexdigest() != digest:
                raise BundleError('generation-drift')
            if name in MODULES:
                try:
                    trees[name] = ast.parse(content)
                except (SyntaxError, ValueError):
                    raise BundleError('module-invalid') from None
        try:
            pins = [ast.literal_eval(node.value) for node in trees['sshd_migrate.py'].body
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'UNIT_HASHES' for t in node.targets)]
        except (ValueError, TypeError):
            raise BundleError('unit-contract-invalid') from None
        if pins != [{name: manifest['files']['units/' + name] for name in UNITS}]:
            raise BundleError('unit-contract-invalid')
        return directory

    def _pending(self):
        path = self.root / 'install.json'
        if not os.path.lexists(path):
            return None
        try:
            value = _json(_read(path, private=True))
            if (not isinstance(value, dict) or set(value) != {'schema_version', 'generation', 'previous'}
                    or type(value['schema_version']) is not int or value['schema_version'] != 1):
                raise ValueError
            _identifier(value['generation'])
            if value['previous'] is not None:
                _identifier(value['previous'])
            if self._current() not in {value['generation'], value['previous']}:
                raise ValueError
            self._generation(value['generation'])
            if value['previous'] is not None:
                self._generation(value['previous'])
            return value
        except (BundleError, ValueError, TypeError):
            raise BundleError('journal-invalid') from None

    def _journal(self, value):
        _atomic(self.root / 'install.json', json.dumps(value, sort_keys=True).encode())

    def _switch(self, generation):
        temporary = self.root / '.current-next'
        if os.path.lexists(temporary):
            if not temporary.is_symlink() or os.readlink(temporary) != 'generations/' + generation:
                raise BundleError('switch-orphaned')
            temporary.unlink()
        temporary.symlink_to('generations/' + generation)
        os.replace(temporary, self.root / 'current')
        _sync(self.root)

    def _check_links(self, missing=False):
        _directory(self.units)
        for name in UNITS:
            path = self.units / name
            if not os.path.lexists(path) and missing:
                continue
            info = path.lstat()
            if (not stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid()
                    or os.readlink(path) != str(self.root / 'current/units' / name)):
                raise BundleError('unit-link-unsafe')

    def _links(self):
        self._check_links(missing=True)
        for name in UNITS:
            path = self.units / name
            if not os.path.lexists(path):
                path.symlink_to(self.root / 'current/units' / name)
                _sync(self.units)

    def _terminal(self, directory):
        try:
            result = self.runtime.status(directory)
        except Exception:
            raise BundleError('state-unreadable') from None
        if not isinstance(result, dict) or result.get('status') not in TERMINAL:
            raise BundleError('transaction-pending')

    def publish(self, generation):
        _identifier(generation)
        _directory(self.root)
        with _lock(self.root / 'publisher.lock', True):
            with _lock(self.root / 'bundle.lock', True):
                # Bootstrap is a stable trust root. Make it durable before enabling
                # any unit that would rely on it at the next boot.
                ast.parse(_read(self.root / 'sshd_bundle.py'))
                _sync_file(self.root / 'sshd_bundle.py')
                _sync(self.root)
                current, journal = self._current(), self._pending()
                if journal and journal['generation'] != generation:
                    raise BundleError('installation-incomplete')
                directory = self.root / 'generations' / generation
                staged = not os.path.lexists(directory)
                candidate = self._generation(generation, staged=staged)
                previous_id = journal['previous'] if journal else current
                previous = self._generation(previous_id) if previous_id else None
                self._check_links(missing=True)
                if not os.path.lexists(self.state):
                    if current or journal or any(os.path.lexists(self.units / name) for name in UNITS):
                        raise BundleError('state-missing')
                    _directory(self.state.parent)
                    self.state.mkdir(mode=0o700)
                    _sync(self.state.parent)
                _directory(self.state, private=True)
                with _lock(self.state / 'transaction.lock', True):
                    if previous:
                        self._terminal(previous)
                    self._terminal(candidate)
                    if current == generation and journal is None:
                        self._check_links()
                        if self.runtime.ready(directory):
                            return {'status': 'unchanged', 'generation': generation}
                    if staged:
                        for name in FILES | {'manifest.json'}:
                            _sync_file(candidate / name)
                        _sync(candidate / 'units')
                        _sync(candidate)
                        os.rename(candidate, directory)
                        _sync(self.root / 'staging')
                        _sync(self.root / 'generations')
                    if journal is None:
                        journal = {'schema_version': 1, 'generation': generation, 'previous': current}
                        self._journal(journal)
                    self._switch(generation)
                    self._links()
            # Recovery services need the shared bundle lease and transaction
            # lock. The journal blocks new SSH mutations while these locks are
            # released; publisher.lock still excludes another installation.
            try:
                self.runtime.activate(directory)
            except Exception:
                raise BundleError('activation-failed') from None
            with _lock(self.root / 'bundle.lock', True):
                _directory(self.state, private=True)
                with _lock(self.state / 'transaction.lock', True):
                    if self._current() != generation or self._pending() != journal:
                        raise BundleError('installation-changed')
                    candidate = self._generation(generation)
                    if journal['previous'] is not None:
                        self._terminal(self._generation(journal['previous']))
                    self._terminal(candidate)
                    self._check_links()
                    try:
                        (self.root / 'install.json').unlink()
                        _sync(self.root)
                    except OSError:
                        # An uncertain deletion must not allow a new migration.
                        self._journal(journal)
                        raise BundleError('installation-incomplete') from None
                    return {'status': 'installed', 'generation': generation}

    @contextmanager
    def selected(self, action):
        if action not in ACTIONS:
            raise BundleError('action-invalid')
        _directory(self.root)
        with _lock(self.root / 'bundle.lock', False, create=False) as fd:
            journal = self._pending()
            if journal and action not in {'status', 'recover', 'boot-recover'}:
                raise BundleError('installation-incomplete')
            current = self._current()
            if current is None:
                raise BundleError('installation-incomplete')
            directory = self._generation(current)
            if not os.path.lexists(self.state):
                raise BundleError('state-missing')
            _directory(self.state, private=True)
            if journal:
                with _lock(self.state / 'transaction.lock', True):
                    self._terminal(directory)
            else:
                self._check_links()
            # The same process execs Python below, retaining its shared lease.
            os.set_inheritable(fd, True)
            yield directory


class Runtime:
    def status(self, directory):
        # Publisher already holds transaction.lock. Read using the candidate's
        # actual schema implementation without recursively taking that lock.
        spec = importlib.util.spec_from_file_location('bundle_transaction', directory / 'sshd_transaction.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        engine = module.Transaction(module.CONFIG_ROOT, STATE, None)
        return engine._receipt(engine._load())

    def activate(self, directory):
        # The durable journal excludes new mutations and both schemas have
        # already proved idle/terminal state. Stop our timer before its worker
        # so an overdue tick cannot race the boot recovery execution.
        # Starting the timer then starts its required boot oneshot first and
        # retains both workers' execution state through loaded dependencies.
        commands = [
            ['/usr/bin/systemctl', 'daemon-reload'],
            ['/usr/bin/systemctl', 'stop', 'vpn-sshd-recover.timer'],
            ['/usr/bin/systemctl', 'stop', 'vpn-sshd-recover.service'],
            ['/usr/bin/systemctl', 'enable', 'vpn-sshd-boot-recover.service'],
            ['/usr/bin/systemctl', 'enable', '--now', 'vpn-sshd-recover.timer'],
            ['/usr/bin/systemctl', 'start', 'vpn-sshd-recover.service'],
            ['/usr/bin/python3', '-I', '-B', str(directory / 'sshd_migrate.py'), 'check-installation'],
        ]
        for arguments in commands:
            self.command(arguments)

    def ready(self, directory):
        try:
            self.command(['/usr/bin/python3', '-I', '-B', str(directory / 'sshd_migrate.py'), 'check-installation'])
            return True
        except (BundleError, OSError, subprocess.TimeoutExpired):
            return False

    def command(self, arguments):
        with subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              start_new_session=True,
                              env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'}) as process:
            selector = selectors.DefaultSelector()
            deadline, total = time.monotonic() + 30, 0
            try:
                os.set_blocking(process.stdout.fileno(), False)
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise BundleError('activation-timeout')
                    data = os.read(process.stdout.fileno(), 8192)
                    total += len(data)
                    if total > 65536:
                        raise BundleError('activation-output-limit')
                    if not data:
                        selector.unregister(process.stdout)
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
                if process.returncode:
                    raise BundleError('activation-failed')
            finally:
                selector.close()
                # Do not poll/reap the leader before terminating a timed-out
                # group: descendants may retain pipes after their leader exits.
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        # The group already exited; wait below still reaps the leader.
                        pass
                    process.wait()


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
                raise BundleError('request-timeout')
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 4096:
                raise BundleError('request-too-large')
        request = _json(data)
        if not isinstance(request, dict) or set(request) != {'generation'}:
            raise BundleError('request-invalid')
        return _identifier(request['generation'])
    finally:
        selector.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=(*ACTIONS, 'publish'))
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise BundleError('root-required')
        bundle = Bundle(ROOT, STATE, SYSTEMD, Runtime())
        if args.action == 'publish':
            print(json.dumps(bundle.publish(_request()), sort_keys=True))
            return 0
        with bundle.selected(args.action) as directory:
            environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'}
            if os.environ.get('TMPDIR') == '/run/vpn-sshd-validation':
                environment['TMPDIR'] = os.environ['TMPDIR']
            os.execve('/usr/bin/python3', ['/usr/bin/python3', '-I', '-B', str(directory / 'sshd_migrate.py'), args.action], environment)
            raise BundleError('exec-returned')
    except (BundleError, OSError, ValueError, TypeError) as error:
        if args.action == 'recover' and isinstance(error, BundleError) and str(error) == 'busy':
            print(json.dumps({'status': 'deferred', 'reason': 'busy'}))
            return 75
        print(json.dumps({'status': 'error', 'reason': 'ssh-bundle-failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
