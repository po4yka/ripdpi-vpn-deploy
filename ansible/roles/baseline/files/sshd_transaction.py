#!/usr/bin/env python3
"""Durable SSH-only transaction core. No provider or firewall authority.

The library's filesystem/runtime seams are for isolated tests. Installation and
controller adapters must fix the roots and commands; this module has no generic
command executor or operator-supplied path interface. Private state never leaves
its root: only receipts returned by public methods are safe to report.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
from uuid import UUID, uuid4

CONFIG_ROOT = Path('/etc/ssh')
STATE_ROOT = Path('/var/lib/vpn-sshd-transaction')
OWNED = tuple('sshd_config.d/' + name for name in (
    '10-cloud-init-hardening.conf', '20-ansible-hardening.conf', '50-cloud-init.conf'))
MAX_FILE = 256 * 1024
MAX_STATE = 4 * 1024 * 1024
TERMINAL = {'committed', 'rolled_back'}
STATES = TERMINAL | {'prepared', 'applying', 'applied', 'rolling_back', 'recovery_failed'}


class TransactionError(Exception):
    """Categorical only; never attach configuration or subprocess output."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _directory(path, *, private=False):
    for current in (path, *path.parents):
        info = current.lstat()
        sticky = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or (info.st_mode & 0o022 and not sticky)):
            raise TransactionError('directory-unsafe')
    if private:
        info = path.lstat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise TransactionError('state-directory-unsafe')


def _integrity(info):
    return tuple(getattr(info, name) for name in (
        'st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def _read(path, *, private=False, limit=MAX_FILE):
    _directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise TransactionError('file-unavailable') from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & (0o077 if private else 0o022)
                or info.st_size > limit):
            raise TransactionError('file-unsafe')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            content = stream.read(limit + 1)
        after = os.fstat(fd)
        if (len(content) > limit or _integrity(info) != _integrity(after) or _integrity(path.lstat()) != _integrity(after)):
            raise TransactionError('file-changed')
        return content, info
    finally:
        os.close(fd)


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path, content, mode=0o600, uid=None, gid=None):
    _directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix='.sshd-transaction-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            if uid is not None and gid is not None:
                os.fchown(stream.fileno(), uid, gid)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError


def _hex(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError


def _record(value):
    if (not isinstance(value, dict) or set(value) != {'exists', 'data_b64', 'sha256', 'mode', 'uid', 'gid'}
            or type(value['exists']) is not bool):
        raise ValueError
    if not value['exists']:
        if any(value[key] is not None for key in value if key != 'exists'):
            raise ValueError
        return None
    content = base64.b64decode(value['data_b64'], validate=True)
    if len(content) > MAX_FILE or _hash(content) != value['sha256']:
        raise ValueError
    if (type(value['mode']) is not int or not 0 <= value['mode'] <= 0o777 or value['mode'] & 0o022
            or type(value['uid']) is not int or value['uid'] != os.geteuid()
            or type(value['gid']) is not int or value['gid'] < 0):
        raise ValueError
    return content


def _context(value):
    if not isinstance(value, dict) or set(value) != {'user', 'host', 'addr', 'laddr', 'lport'}:
        raise ValueError
    for key in ('user', 'host'):
        if not isinstance(value[key], str) or re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', value[key]) is None:
            raise ValueError
    for key in ('addr', 'laddr'):
        if not isinstance(value[key], str) or '%' in value[key]:
            raise ValueError
        ipaddress.ip_address(value[key])
    if type(value['lport']) is not int or not 1 <= value['lport'] <= 65535:
        raise ValueError


def _plan(plan):
    try:
        if (set(plan) != {'schema_version', 'operation', 'changed', 'read_set', 'include_inventory', 'files', 'effective', 'snapshot_digest'}
                or type(plan['schema_version']) is not int or plan['schema_version'] != 1
                or plan['operation'] != 'sshd-ownership' or type(plan['changed']) is not bool
                or set(plan['files']) != set(OWNED)):
            raise ValueError
        _hex(plan['snapshot_digest'])
        if _digest({k: v for k, v in plan.items() if k != 'snapshot_digest'}) != plan['snapshot_digest']:
            raise ValueError
        for name, pair in plan['files'].items():
            if set(pair) != {'before', 'after'}:
                raise ValueError
            for value in pair.values():
                _record(value)
            # The planner only removes scalar lines; it never creates/deletes files
            # or changes metadata. Missing cloud-init 50 remains missing.
            if any(pair['before'][k] != pair['after'][k] for k in ('exists', 'mode', 'uid', 'gid')):
                raise ValueError
            if name != OWNED[2] and not pair['before']['exists']:
                raise ValueError
        reads = plan['read_set']
        if not isinstance(reads, list) or not 3 <= len(reads) <= 65:
            raise ValueError
        names = []
        for item in reads:
            if set(item) != {'relative_path', 'sha256', 'size', 'mode', 'uid', 'gid', 'dev', 'ino'}:
                raise ValueError
            name = item['relative_path']
            if name != 'sshd_config' and re.fullmatch(r'sshd_config\.d/[A-Za-z0-9_.-]+\.conf', name) is None:
                raise ValueError
            _hex(item['sha256'])
            if any(type(item[k]) is not int or item[k] < 0 for k in ('size', 'mode', 'uid', 'gid', 'dev', 'ino')):
                raise ValueError
            if item['size'] > MAX_FILE or item['mode'] > 0o777 or item['mode'] & 0o022 or item['uid'] != os.geteuid():
                raise ValueError
            if name in plan['files']:
                before = plan['files'][name]['before']
                if not before['exists'] or any(item[k] != before[k] for k in ('sha256', 'mode', 'uid', 'gid')):
                    raise ValueError
            names.append(name)
        if len(set(names)) != len(names) or 'sshd_config' not in names:
            raise ValueError
        if any(pair['before']['exists'] != (name in names) for name, pair in plan['files'].items()):
            raise ValueError
        inventory = [{'relative_directory': 'sshd_config.d', 'matched_names': sorted(Path(n).name for n in names if n != 'sshd_config')}]
        if plan['include_inventory'] != inventory:
            raise ValueError
        if not isinstance(plan['effective'], list) or not 2 <= len(plan['effective']) <= 9:
            raise ValueError
        for index, item in enumerate(plan['effective']):
            if set(item) != {'context', 'before_sha256', 'after_sha256'}:
                raise ValueError
            if index:
                _context(item['context'])
            _hex(item['before_sha256'])
            if item['before_sha256'] != item['after_sha256']:
                raise ValueError
        if (plan['effective'][0]['context'] is not None
                or len({_digest(item['context']) for item in plan['effective']}) != len(plan['effective'])):
            raise ValueError
        if len(_json(plan)) > MAX_STATE // 2:
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise TransactionError('state-invalid') from None


class Transaction:
    """Bounded operations serialize with recovery; runtime methods must be bounded.

    Production callers supply only the fixed roots above and the installed
    OpenSSH/systemd adapter. No externally supplied plan is accepted by prepare.
    """
    def __init__(self, config_root, state_root, runtime):
        self.config = Path(config_root)
        self.root = Path(state_root)
        self.runtime = runtime

    @contextmanager
    def _locked(self, *, create=False):
        try:
            if not os.path.lexists(self.root):
                if not create:
                    raise TransactionError('state-missing')
                _directory(self.root.parent)
                self.root.mkdir(mode=0o700)
                _sync(self.root.parent)
            _directory(self.root, private=True)
            _directory(self.config)
            fd = os.open(self.root / 'transaction.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        except OSError:
            raise TransactionError('lock-unavailable') from None
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077):
                raise TransactionError('lock-unsafe')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise TransactionError('busy') from None
            yield
        finally:
            os.close(fd)

    def _load(self):
        path = self.root / 'transaction.json'
        if not os.path.lexists(path):
            # A marker survives prepared-state loss, preventing a false idle.
            if os.path.lexists(self.root / 'initialized'):
                raise TransactionError('state-missing')
            if set(p.name for p in self.root.iterdir()) - {'transaction.lock'}:
                raise TransactionError('state-orphaned')
            return None
        try:
            value = json.loads(_read(path, private=True, limit=MAX_STATE)[0])
            if set(value) != {'schema_version', 'generation', 'nonce', 'created', 'deadline', 'monotonic_created', 'monotonic_deadline', 'boot_id', 'status', 'plan', 'checksum'}:
                raise ValueError
            if value['schema_version'] != 1 or value['status'] not in STATES:
                raise ValueError
            _uuid(value['generation'])
            _uuid(value['boot_id'])
            _hex(value['nonce'])
            if (type(value['created']) is not int or type(value['deadline']) is not int
                    or value['created'] < 0 or not 60 <= value['deadline'] - value['created'] <= 600):
                raise ValueError
            if (type(value['monotonic_created']) is not int or type(value['monotonic_deadline']) is not int
                    or value['monotonic_created'] < 0
                    or value['monotonic_deadline'] - value['monotonic_created'] != value['deadline'] - value['created']):
                raise ValueError
            if _digest({k: v for k, v in value.items() if k != 'checksum'}) != value['checksum']:
                raise ValueError
            _plan(value['plan'])
            return value
        except (ValueError, TypeError, KeyError, AttributeError):
            raise TransactionError('state-invalid') from None

    def _save(self, state):
        state['checksum'] = _digest({k: v for k, v in state.items() if k != 'checksum'})
        content = _json(state)
        if len(content) > MAX_STATE:
            raise TransactionError('state-too-large')
        _atomic(self.root / 'transaction.json', content)

    @staticmethod
    def _receipt(state):
        if state is None:
            return {'status': 'idle'}
        return {k: state[k] for k in ('generation', 'nonce', 'status', 'deadline')} | {'snapshot_digest': state['plan']['snapshot_digest']}

    def _identity(self, state, generation, nonce):
        if state is None or state['generation'] != generation or not isinstance(nonce, str) or not hmac.compare_digest(state['nonce'], nonce):
            raise TransactionError('identity-mismatch')

    def _expired(self, state):
        now = self.runtime.clock()
        return (state['boot_id'] != self.runtime.boot_id()
                or now < state['created'] or now >= state['deadline']
                or self.runtime.monotonic() < state['monotonic_created']
                or self.runtime.monotonic() >= state['monotonic_deadline'])

    def _live(self, state):
        if self._expired(state):
            raise TransactionError('transaction-expired')

    def _current(self, name):
        path = self.config / name
        if not os.path.lexists(path):
            return dict(exists=False, data_b64=None, sha256=None, mode=None, uid=None, gid=None)
        content, info = _read(path)
        return dict(exists=True, data_b64=base64.b64encode(content).decode(), sha256=_hash(content),
                    mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)

    def _graph(self, plan, phase):
        """Preflight ALL paths before restore; partial restore must not hide drift."""
        _plan(plan)
        directory = self.config / 'sshd_config.d'
        _directory(directory)
        names = sorted(p.name for p in directory.glob('*.conf') if not p.name.startswith('.'))
        if names != plan['include_inventory'][0]['matched_names']:
            raise TransactionError('configuration-drift')
        for item in plan['read_set']:
            name = item['relative_path']
            if name in OWNED:
                continue
            data, info = _read(self.config / name)
            current = dict(sha256=_hash(data), mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid,
                           size=info.st_size, dev=info.st_dev, ino=info.st_ino)
            if any(current[k] != item[k] for k in current):
                raise TransactionError('configuration-drift')
        for name, pair in plan['files'].items():
            allowed = list(pair.values()) if phase == 'mixed' else [pair[phase]]
            if self._current(name) not in allowed:
                raise TransactionError('configuration-drift')

    def _publish(self, name, value):
        if name not in OWNED:
            raise TransactionError('path-not-owned')
        content = _record(value)
        path = self.config / name
        if content is None:
            if os.path.lexists(path):
                path.unlink()
                _sync(path.parent)
        else:
            _atomic(path, content, value['mode'], value['uid'], value['gid'])

    def prepare(self, *, contexts, timeout=180):
        if type(timeout) is not int or not 60 <= timeout <= 600:
            raise TransactionError('timeout-invalid')
        with self._locked(create=True):
            previous = self._load()
            if previous is not None and previous['status'] not in TERMINAL:
                raise TransactionError('transaction-pending')
            plan = self.runtime.build_plan(self.config, contexts)
            _plan(plan)
            self._graph(plan, 'before')
            self.runtime.assert_snapshot(plan, self.config)
            if not plan['changed']:
                return {'status': 'unchanged'}
            if previous is not None:
                _atomic(self.root / (previous['generation'] + '.json'), _json(previous))
            now = int(self.runtime.clock())
            monotonic = int(self.runtime.monotonic())
            state = dict(schema_version=1, generation=str(uuid4()), nonce=secrets.token_hex(32),
                         created=now, deadline=now + timeout, monotonic_created=monotonic,
                         monotonic_deadline=monotonic + timeout, boot_id=self.runtime.boot_id(), status='prepared', plan=plan)
            # Write marker first: a crash before state save is an explicit orphan,
            # never permission to ignore an unknown transaction on next boot.
            _atomic(self.root / 'initialized', b'1\n')
            self._save(state)
            return self._receipt(state)

    def apply(self, generation, nonce):
        with self._locked():
            state = self._load()
            self._identity(state, generation, nonce)
            self._live(state)
            if state['status'] == 'applied':
                self._graph(state['plan'], 'after')
                return self._receipt(state)
            if state['status'] != 'prepared':
                raise TransactionError('state-not-prepared')
            if not self.runtime.recovery_ready():
                raise TransactionError('recovery-not-ready')
            self._graph(state['plan'], 'before')
            self.runtime.assert_snapshot(state['plan'], self.config)
            self._live(state)
            state['status'] = 'applying'
            self._save(state)
            try:
                for name, pair in state['plan']['files'].items():
                    self._live(state)
                    self._graph(state['plan'], 'mixed')
                    if pair['before'] != pair['after']:
                        self._publish(name, pair['after'])
                self._graph(state['plan'], 'after')
                self.runtime.assert_effective(state['plan'], self.config)
                self._live(state)
                self.runtime.reload()
                self._live(state)
                state['status'] = 'applied'
                self._save(state)
                return self._receipt(state)
            except Exception:
                self._rollback(state, boot=False)
                raise TransactionError('activation-failed-rolled-back') from None

    def _rollback(self, state, *, boot):
        try:
            self._graph(state['plan'], 'mixed')
            state['status'] = 'rolling_back'
            self._save(state)
            for name, pair in state['plan']['files'].items():
                self._graph(state['plan'], 'mixed')
                if self._current(name) != pair['before']:
                    self._publish(name, pair['before'])
            self._graph(state['plan'], 'before')
            self.runtime.assert_effective(state['plan'], self.config)
            if not boot:
                self.runtime.reload()
            state['status'] = 'rolled_back'
            self._save(state)
            return self._receipt(state)
        except Exception as error:
            state['status'] = 'recovery_failed'
            self._save(state)
            if isinstance(error, TransactionError):
                raise
            raise TransactionError('recovery-failed') from None

    def confirm(self, generation, nonce, snapshot_digest):
        with self._locked():
            state = self._load()
            self._identity(state, generation, nonce)
            if snapshot_digest != state['plan']['snapshot_digest']:
                raise TransactionError('identity-mismatch')
            if state['status'] == 'committed':
                self._graph(state['plan'], 'after')
                return self._receipt(state)
            self._live(state)
            if state['status'] != 'applied':
                raise TransactionError('state-not-applied')
            self._graph(state['plan'], 'after')
            self.runtime.assert_effective(state['plan'], self.config)
            self._live(state)
            # Recovery remains installed/enabled; a durable terminal record makes
            # timer callbacks no-ops. Never cancel recovery before this fsync.
            state['status'] = 'committed'
            self._save(state)
            return self._receipt(state)

    def rollback(self, generation, nonce):
        with self._locked():
            state = self._load()
            self._identity(state, generation, nonce)
            if state['status'] == 'rolled_back':
                return self._receipt(state)
            if state['status'] == 'committed':
                raise TransactionError('already-committed')
            return self._rollback(state, boot=False)

    def recover(self, *, boot=False):
        with self._locked():
            state = self._load()
            if state is None or state['status'] in TERMINAL:
                return self._receipt(state)
            if state['status'] in {'rolling_back', 'recovery_failed'} or self._expired(state):
                return self._rollback(state, boot=boot)
            return self._receipt(state)

    def status(self):
        with self._locked():
            return self._receipt(self._load())
