"""Durable consumer acceptance around immutable runtime acquisition.

Trusted role code supplies exact candidates on stdin. Only this publisher writes
those nodes; the existing guarded-generation controller owns process lifecycle.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

LIMIT = 32 * 1024 * 1024


def storage_path(raw):
    return Path(raw).parent / '.ripdpi-transport-runtime'


def mount_id(fd):
    """Linux mount identity is namespace-local and must never be persisted."""
    if sys.platform != 'linux':
        return os.fstat(fd).st_dev
    with open('/proc/self/fdinfo/' + str(fd), encoding='ascii') as source:
        values = [line.split(':', 1)[1].strip() for line in source if line.startswith('mnt_id:')]
    if len(values) != 1 or not values[0].isdigit():
        raise Refusal('mount-identity-invalid')
    return int(values[0])


def storage_claim(raw):
    path = storage_path(raw)
    return {'identity': identity(path.lstat()), 'parent': identity(path.parent.lstat())}


def reserved_storage(path):
    return '.ripdpi-transport-runtime' in path.parts


def staged_path(preparation, index, entry):
    return storage_path(entry['path']) / ('staged-' + preparation['directory'][1:] + '-' + str(index))


class Refusal(RuntimeError):
    """Categorical refusal; private input and child output never form diagnostics."""


def identity(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)]


def validate_claim(value, uid):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) not in ({'identity', 'target'}, {'identity', 'sha256'}):
        raise Refusal('node-claim-invalid')
    claimed = value['identity']
    if (not isinstance(claimed, list) or len(claimed) != 5
            or any(type(item) is not int for item in claimed)
            or not all(0 <= item < 2**64 for item in claimed[:2])
            or claimed[2] != uid or not 0 <= claimed[3] < 2**32 - 1
            or not 0 <= claimed[4] <= 0o7777):
        raise Refusal('node-claim-invalid')
    if 'target' in value:
        target = value['target']
        if (not isinstance(target, str) or len(target) > 4096 or any(ord(ch) < 32 for ch in target)
                or not target or '..' in Path(target).parts):
            raise Refusal('node-claim-invalid')
    elif not isinstance(value['sha256'], str) or re.fullmatch('[0-9a-f]{64}', value['sha256']) is None or claimed[4] & 0o022:
        raise Refusal('node-claim-invalid')


def validate_receipt(value, *, root, uid):
    """Typed public boundary for receipts embedded in recovery-owner records."""
    if (not isinstance(value, dict) or set(value) != {'schema', 'nodes', 'previous', 'units'}
            or type(value['schema']) is not int or value['schema'] != 1
            or not isinstance(value['units'], dict)):
        raise Refusal('receipt-invalid')
    for key in ('nodes', 'previous'):
        mapping = value[key]
        if mapping is None and key == 'previous':
            continue
        if not isinstance(mapping, dict) or len(mapping) > 64:
            raise Refusal('receipt-invalid')
        for raw, claimed in mapping.items():
            if not isinstance(raw, str) or len(raw) > 4096 or any(ord(ch) < 32 for ch in raw):
                raise Refusal('receipt-invalid')
            path = Path(raw)
            if (reserved_storage(path) or not path.is_absolute() or '..' in path.parts or path == root
                    or (root in path.parents and path != root / 'parameters.json')):
                raise Refusal('receipt-invalid')
            validate_claim(claimed, uid)


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ancestors(path, uid):
    # Descriptor traversal is retained by Transaction while nodes are replaced.
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            info = os.fstat(fd)
            if info.st_uid not in {0, uid} or info.st_mode & 0o022:
                raise Refusal('unsafe-parent')
        return fd
    except BaseException:
        os.close(fd)
        raise


def node(path, uid, *, links=1):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if info.st_uid != uid or info.st_nlink > links or info.st_nlink < 1:
        raise Refusal('unsafe-node')
    if stat.S_ISLNK(info.st_mode):
        return {'identity': identity(info), 'target': os.readlink(path)}
    if path.name in {'geoip.dat', 'geosite.dat'} or path.name.startswith(('before-', 'after-', 'rollback-', 'undo-', 'staged-')):
        maximum = 128 * 1024 * 1024
    elif path.name in {'accepted.json', 'pending.json', 'last.json', 'preparation.json', 'compensating.json', 'parameters.json', 'backups.json'} or path.name.startswith('.write-'):
        maximum = LIMIT
    else:
        maximum = 1048576
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > maximum:
        raise Refusal('unsafe-node')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if identity(os.fstat(fd)) != identity(info):
            raise Refusal('node-changed')
        digest = hashlib.sha256()
        total = 0
        while True:
            data = os.read(fd, 1048576)
            if not data:
                break
            total += len(data)
            if total > maximum:
                raise Refusal('node-oversize')
            digest.update(data)
        return {'identity': identity(info), 'sha256': digest.hexdigest()}
    finally:
        os.close(fd)


def read_private(path, uid, *, links=1):
    observed = node(path, uid, links=links)
    if observed is None:
        return None
    if 'sha256' not in observed or observed['identity'][4] != 0o600:
        raise Refusal('unsafe-record')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as source:
        if identity(os.fstat(source.fileno())) != observed['identity']:
            raise Refusal('record-changed')
        data = source.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise Refusal('record-oversize')
    if hashlib.sha256(data).hexdigest() != observed['sha256']:
        raise Refusal('record-changed')
    value = json.loads(data)
    if value is None:
        # Record absence is a missing inode, never a root-owned JSON null that
        # could otherwise be mistaken for permission to replace unknown state.
        raise Refusal('record-invalid')
    return value


def outer_record(root, uid):
    value = read_private(root / 'outer.json', uid)
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'schema', 'receipt', 'consumer_receipt'}
            or type(value['schema']) is not int or value['schema'] != 1):
        raise Refusal('outer-intent-invalid')
    for key in ('receipt', 'consumer_receipt'):
        if value[key] is not None:
            validate_receipt(value[key], root=root, uid=uid)
    return value


def admission(root, *, uid=0):
    """Unfinished selection may run only under a live publisher's retained lock.

    Boot and controller retries never recover private intent autonomously. The
    authorized role retry must restore it before an unattended generation runs.
    """
    root = Path(root)
    if not os.path.lexists(root):
        return
    fd = ancestors(root, uid)
    try:
        info = os.fstat(fd)
        if identity(info)[2:] != [uid, os.getgid(), 0o700]:
            raise Refusal('unsafe-state-directory')
        outer = outer_record(root, uid)
        unfinished = False
        if outer is not None:
            accepted = read_private(root / 'accepted.json', uid)
            if accepted is not None:
                validate_receipt(accepted, root=root, uid=uid)
            unfinished = outer['consumer_receipt'] is None or outer['consumer_receipt'] != accepted
        for name in ('preparation.json', 'pending.json', 'compensating.json'):
            value = read_private(root / name, uid)
            if value is not None:
                if not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1:
                    raise Refusal('journal-invalid')
                unfinished = True
        if unfinished:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            raise Refusal('unfinished-runtime-without-publisher')
    finally:
        os.close(fd)


class Transaction:
    """One retained lock and exact before/after inode journal per transport set."""

    def __init__(self, root, *, uid=0, check=False):
        self.root = Path(root)
        self.uid = uid
        self.check = check
        self.parents = {}
        self.resources = ExitStack()
        self.storage_locks = set()

    def __enter__(self):
        try:
            return self._enter()
        except BaseException:
            self.resources.close()
            raise

    def _enter(self):
        self.parent(self.root.parent)
        if not self.root.exists() and self.check:
            self.state_identity = None
            self.state_fd = None
            return self
        if not self.root.exists():
            self.root.mkdir(mode=0o700)
            sync(self.root.parent)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != self.uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise Refusal('unsafe-state-directory')
        fd = ancestors(self.root, self.uid)
        self.resources.callback(os.close, fd)
        if identity(os.fstat(fd)) != identity(info):
            raise Refusal('state-directory-changed')
        fcntl.flock(fd, (fcntl.LOCK_SH if self.check else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        self.state_identity = identity(info)
        self.state_fd = fd
        return self

    def __exit__(self, *args):
        self.resources.close()

    def parent(self, path):
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts:
            raise Refusal('unsafe-path')
        if self.check and not path.exists():
            nearest = path.parent
            while not nearest.exists():
                nearest = nearest.parent
            fd = ancestors(nearest, self.uid)
            self.resources.callback(os.close, fd)
            return fd
        if path not in self.parents:
            fd = ancestors(path, self.uid)
            self.resources.callback(os.close, fd)
            self.parents[path] = (fd, identity(os.fstat(fd)))
        fd, expected = self.parents[path]
        if identity(path.lstat()) != expected or identity(os.fstat(fd)) != expected:
            raise Refusal('parent-changed')
        return fd

    def record(self, name, value):
        if identity(self.root.lstat()) != self.state_identity:
            raise Refusal('state-directory-changed')
        target = self.root / name
        before = node(target, self.uid)
        if before is not None and ('sha256' not in before or before['identity'][4] != 0o600):
            raise Refusal('unsafe-record')
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        if before is not None and before['sha256'] == hashlib.sha256(encoded).hexdigest():
            return
        if len(encoded) > LIMIT:
            raise Refusal('record-oversize')
        # An interrupted uncommitted write is retained under a unique name. It
        # cannot block the next record or authorize removal of an unknown inode.
        fd, raw_temporary = tempfile.mkstemp(prefix='.write-' + name + '-', dir=self.root)
        temporary = Path(raw_temporary)
        temporary_identity = identity(os.fstat(fd))
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if node(target, self.uid) != before:
                raise Refusal('record-changed')
            self.parent(self.root)
            os.replace(temporary.name, target.name, src_dir_fd=self.state_fd, dst_dir_fd=self.state_fd)
            os.fsync(self.state_fd)
        finally:
            observed = node(temporary, self.uid)
            if observed is not None:
                if observed['identity'] != temporary_identity:
                    raise Refusal('record-temporary-changed')
                os.unlink(temporary.name, dir_fd=self.state_fd)

    def validate(self, candidates, *, pending=False):
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 64:
            raise Refusal('candidate-invalid')
        paths = set()
        for item in candidates:
            if not isinstance(item, dict) or set(item) - {'deferred'} not in ({'path', 'data', 'mode', 'gid'}, {'path', 'target'}, {'path', 'source', 'sha256', 'mode', 'gid'}, {'path', 'absent'}):
                raise Refusal('candidate-invalid')
            path = Path(item['path'])
            if reserved_storage(path) or path in paths or path == self.root or (self.root in path.parents and path != self.root / 'parameters.json'):
                raise Refusal('candidate-invalid')
            paths.add(path)
            self.parent(path.parent)
            self.storage(item['path'])
            before = node(path, self.uid, links=2 if pending else 1)
            if type(item.get('deferred', False)) is not bool:
                raise Refusal('candidate-invalid')
            if 'absent' in item:
                if item['absent'] is not True or item.get('deferred', False):
                    raise Refusal('candidate-invalid')
                continue
            if 'target' in item:
                target = Path(item['target'])
                if not target.is_absolute() or '..' in target.parts or before and 'target' not in before:
                    raise Refusal('link-authority-invalid')
            else:
                if type(item['mode']) is not int or item['mode'] not in {0o600, 0o640, 0o644, 0o755} or type(item['gid']) is not int or not 0 <= item['gid'] < 2**32-1:
                    raise Refusal('file-authority-invalid')
                if 'source' in item:
                    source = Path(item['source'])
                    self.parent(source.parent)
                    observed = node(source, self.uid)
                    if observed is None or observed.get('sha256') != item['sha256'] or item['mode'] != 0o644:
                        raise Refusal('asset-authority-invalid')
                elif len(base64.b64decode(item['data'], validate=True)) > 1048576:
                    raise Refusal('file-authority-invalid')
                if before and 'sha256' not in before or type(item.get('deferred', False)) is not bool:
                    raise Refusal('file-authority-invalid')

    def unchanged(self, candidates, *, pending=False):
        for item in candidates:
            before = node(Path(item['path']), self.uid, links=2 if pending else 1)
            if 'absent' in item:
                if before is not None:
                    return False
                continue
            if before is None:
                return False
            if 'target' in item:
                if before.get('target') != item['target']:
                    return False
            elif (before.get('sha256') != (item['sha256'] if 'source' in item else hashlib.sha256(base64.b64decode(item['data'], validate=True)).hexdigest())
                  or before['identity'][3:] != [item['gid'], item['mode']]):
                return False
        return True

    def validate_intent(self, value):
        if not isinstance(value, dict) or set(value) != {'schema', 'before_receipt', 'after_receipt', 'before_backups', 'entries', 'units'} or type(value['schema']) is not int or value['schema'] != 1 or not isinstance(value['entries'], list) or not 1 <= len(value['entries']) <= 64 or not isinstance(value['units'], dict):
            raise Refusal('journal-invalid')
        self.validate_backup_map(value['before_backups'])
        after_receipt = value['after_receipt']
        validate_receipt(after_receipt, root=self.root, uid=self.uid)
        before_receipt = value['before_receipt']
        if before_receipt is not None:
            validate_receipt(before_receipt, root=self.root, uid=self.uid)
        paths = set()
        for entry in value['entries']:
            if not isinstance(entry, dict) or set(entry) != {'path', 'before', 'after', 'deferred', 'storage'} or type(entry['deferred']) is not bool:
                raise Refusal('journal-invalid')
            if entry['storage'] is None:
                raise Refusal('journal-invalid')
            path = Path(entry['path'])
            if reserved_storage(path) or path in paths or path == self.root or (self.root in path.parents and path != self.root / 'parameters.json'):
                raise Refusal('journal-invalid')
            paths.add(path)
            self.parent(path.parent)
            self.storage(entry['path'], expected=entry['storage'])
            for key in ('before', 'after'):
                claimed = entry[key]
                validate_claim(claimed, self.uid)
        expected_nodes = dict((before_receipt or {}).get('nodes', {}))
        expected_nodes.update({entry['path']: entry['after'] for entry in value['entries']})
        if after_receipt['nodes'] != expected_nodes:
            raise Refusal('journal-invalid')
        self.validate_backup_map(self.after_backups(value))

    def backup_path(self, raw):
        return storage_path(raw) / ('rollback-' + hashlib.sha256(raw.encode()).hexdigest())

    def storage(self, raw, *, create=False, expected=None):
        """Exact private storage in the selected node's own mount/filesystem."""
        path = storage_path(raw)
        if expected is not None and (not isinstance(expected, dict) or set(expected) != {'identity', 'parent'}
                or any(not isinstance(value, list) or len(value) != 5
                       or any(type(item) is not int or not 0 <= item < 2**64 for item in value)
                       for value in expected.values())):
            raise Refusal('storage-directory-invalid')
        parent = self.parent(path.parent)
        if expected is not None and identity(os.fstat(parent)) != expected['parent']:
            raise Refusal('storage-parent-changed')
        if not os.path.lexists(path):
            if expected is not None:
                raise Refusal('storage-directory-absent')
            if not create:
                return path
            os.mkdir(path.name, 0o700, dir_fd=parent)
            os.fsync(parent)
        storage_fd = self.parent(path)
        if path not in self.storage_locks:
            fcntl.flock(storage_fd, (fcntl.LOCK_SH if self.check else fcntl.LOCK_EX) | fcntl.LOCK_NB)
            self.storage_locks.add(path)
        claimed = identity(os.fstat(storage_fd))
        if claimed[2:] != [self.uid, os.getgid(), 0o700] or (expected is not None and claimed != expected['identity']):
            raise Refusal('storage-directory-changed')
        if mount_id(parent) != mount_id(storage_fd):
            raise Refusal('storage-mount-changed')
        # A separately mounted leaf cannot be renamed even on the same device.
        live = Path(raw)
        if sys.platform != 'linux' and os.path.ismount(live):
            raise Refusal('selected-mount-invalid')
        if sys.platform == 'linux' and os.path.lexists(live):
            leaf = os.open(live.name, getattr(os, 'O_PATH', os.O_RDONLY) | os.O_NOFOLLOW, dir_fd=parent)
            try:
                if mount_id(leaf) != mount_id(parent):
                    raise Refusal('selected-mount-invalid')
            finally:
                os.close(leaf)
        return path

    def validate_backup_map(self, value):
        if value is None:
            return
        if (not isinstance(value, dict) or set(value) != {'schema', 'nodes', 'directories'}
                or type(value['schema']) is not int or value['schema'] != 1):
            raise Refusal('backup-map-invalid')
        # Reuse the exact selectable-path and inode/type boundary; this record
        # claims backup authority independently of the last complete receipt.
        validate_receipt({'schema': 1, 'nodes': value['nodes'], 'previous': None, 'units': {}},
                         root=self.root, uid=self.uid)
        if not isinstance(value['directories'], dict) or set(value['directories']) != {str(storage_path(raw)) for raw in value['nodes']}:
            raise Refusal('backup-map-invalid')
        for raw in value['nodes']:
            if value['directories'][str(storage_path(raw))] is None:
                raise Refusal('backup-map-invalid')
            self.storage(raw, expected=value['directories'][str(storage_path(raw))])

    def after_backups(self, value):
        nodes = dict((value['before_backups'] or {}).get('nodes', {}))
        nodes.update({entry['path']: entry['before'] for entry in value['entries']})
        directories = dict((value['before_backups'] or {}).get('directories', {}))
        directories.update({str(storage_path(entry['path'])): entry['storage'] for entry in value['entries']})
        return {'schema': 1, 'nodes': nodes, 'directories': directories}

    def compensated_backups(self, value):
        after = self.after_backups(value)
        nodes = dict(after['nodes'])
        nodes.update({entry['path']: None for entry in value['entries']})
        return {**after, 'nodes': nodes}

    def backups(self, paths=()):
        value = read_private(self.root / 'backups.json', self.uid)
        self.validate_backup_map(value)
        known = (value or {}).get('nodes', {})
        for raw in set(known) | set(paths):
            self.storage(raw)
            if node(self.backup_path(raw), self.uid) != known.get(raw):
                raise Refusal('foreign-rollback')
        return value

    def cleanup_backup_authority(self, value, committed):
        """Validate the entire claimed set before retiring the first old inode."""
        before = value['before_backups']
        after = self.after_backups(value)
        current = read_private(self.root / 'backups.json', self.uid)
        self.validate_backup_map(current)
        if current not in ((before, after) if committed else (before,)):
            raise Refusal('foreign-backup-map')
        old_nodes = (before or {}).get('nodes', {})
        entries = {entry['path']: (index, entry) for index, entry in enumerate(value['entries'])}
        for raw in set(old_nodes) | set(after['nodes']):
            observed = node(self.backup_path(raw), self.uid, links=2)
            if not committed or raw not in entries:
                if observed != old_nodes.get(raw):
                    raise Refusal('foreign-rollback')
                continue
            index, entry = entries[raw]
            if current == after:
                if observed != entry['before']:
                    raise Refusal('foreign-rollback')
            elif observed not in (old_nodes.get(raw), entry['before'], None):
                raise Refusal('foreign-rollback')
            if entry['before'] is not None and observed != entry['before']:
                if node(storage_path(entry['path']) / ('before-' + str(index)), self.uid, links=2) != entry['before']:
                    raise Refusal('rollback-node-absent')
        return after

    def journal(self):
        value = read_private(self.root / 'pending.json', self.uid)
        if value is None:
            return None
        self.validate_intent(value)
        # Validate every node before the first recovery mutation.
        for index, entry in enumerate(value['entries']):
            for key in ('before', 'after'):
                claimed = entry[key]
                stored = node(storage_path(entry['path']) / (key + '-' + str(index)), self.uid, links=2)
                if stored is not None and stored != claimed:
                    raise Refusal('journal-node-changed')
            live = node(Path(entry['path']), self.uid, links=2)
            if live not in (entry['before'], entry['after'], None):
                raise Refusal('foreign-publication')
            if live is None and entry['before'] is not None and entry['after'] is not None:
                raise Refusal('publication-absent')
        receipt = read_private(self.root / 'accepted.json', self.uid)
        if receipt not in (value['before_receipt'], value['after_receipt']):
            raise Refusal('foreign-receipt')
        self.cleanup_backup_authority(value, receipt == value['after_receipt'])
        return value

    def preparation(self):
        """Inspect the durable claim before any fixed staging node is allocated."""
        value = read_private(self.root / 'preparation.json', self.uid)
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) != {'schema', 'directory', 'identity', 'intent'}
                or value['schema'] != 1 or not isinstance(value['directory'], str)
                or not value['directory'].startswith('.prepare-')
                or Path(value['directory']).name != value['directory']):
            raise Refusal('preparation-invalid')
        self.validate_intent(value['intent'])
        directory = self.root / value['directory']
        if identity(directory.lstat()) != value['identity'] or value['identity'][2:] != [self.uid, os.getgid(), 0o700]:
            raise Refusal('preparation-directory-changed')
        self.parent(directory)
        for index, entry in enumerate(value['intent']['entries']):
            staged = node(staged_path(value, index, entry), self.uid, links=2)
            if staged is not None:
                if staged != entry['after']:
                    raise Refusal('preparation-node-changed')
            for key in ('before', 'after'):
                stored = node(storage_path(entry['path']) / (key + '-' + str(index)), self.uid, links=2)
                if stored is not None and stored != entry[key]:
                    raise Refusal('preparation-node-changed')
            if node(Path(entry['path']), self.uid, links=2) != entry['before']:
                raise Refusal('preparation-publication-changed')
        if os.listdir(directory):
            raise Refusal('preparation-foreign-node')
        pending = read_private(self.root / 'pending.json', self.uid)
        if pending is not None and pending != value['intent']:
            raise Refusal('preparation-intent-changed')
        if read_private(self.root / 'accepted.json', self.uid) != value['intent']['before_receipt']:
            raise Refusal('foreign-receipt')
        if self.backups(entry['path'] for entry in value['intent']['entries']) != value['intent']['before_backups']:
            raise Refusal('foreign-backup-map')
        return value

    def finish_preparation(self, value, *, retain_fixed=False):
        """Retire only the claimed staging inodes, after complete inspection."""
        if self.preparation() != value:
            raise Refusal('preparation-changed')
        directory = self.root / value['directory']
        fd = self.parent(directory)
        for index, entry in enumerate(value['intent']['entries']):
            storage_fd = self.parent(self.storage(entry['path'], expected=entry['storage']))
            if not retain_fixed:
                for key in ('before', 'after'):
                    name = key + '-' + str(index)
                    observed = node(storage_path(entry['path']) / name, self.uid, links=2)
                    if observed is not None:
                        if observed != entry[key]:
                            raise Refusal('preparation-node-changed')
                        os.unlink(name, dir_fd=storage_fd)
            staged = staged_path(value, index, entry)
            observed = node(staged, self.uid, links=2)
            if observed is not None:
                if observed != entry['after']:
                    raise Refusal('preparation-node-changed')
                os.unlink(staged.name, dir_fd=storage_fd)
            os.fsync(storage_fd)
        os.fsync(fd)
        os.unlink('preparation.json', dir_fd=self.state_fd)
        os.fsync(self.state_fd)
        if identity(directory.lstat()) != value['identity']:
            raise Refusal('preparation-directory-changed')
        os.rmdir(directory.name, dir_fd=self.state_fd)
        os.fsync(self.state_fd)

    def recover_preparation(self):
        value = self.preparation()
        if value is None:
            return False
        self.finish_preparation(value, retain_fixed=read_private(self.root / 'pending.json', self.uid) is not None)
        return True

    def replace(self, entry, index, which):
        path = Path(entry['path'])
        fd = self.parent(path.parent)
        current = node(path, self.uid, links=2)
        if current not in (entry['before'], entry['after'], None):
            raise Refusal('foreign-publication')
        desired = entry[which]
        if current == desired:
            # Pre-publication death can leave the original selected inode
            # hardlinked to its claimed backup. Consume that exact extra link
            # before the strict runtime owner inspects the restored unit/config.
            if desired is not None:
                saved = storage_path(entry['path']) / (which + '-' + str(index))
                retained = node(saved, self.uid, links=2)
                if retained not in (None, desired):
                    raise Refusal('recovery-node-changed')
                if retained is not None:
                    storage_fd = self.parent(self.storage(entry['path'], expected=entry['storage']))
                    os.unlink(saved.name, dir_fd=storage_fd)
                    os.fsync(storage_fd)
            return
        if desired is None:
            os.unlink(path.name, dir_fd=fd)
        else:
            saved = storage_path(entry['path']) / (which + '-' + str(index))
            if node(saved, self.uid, links=2) != desired:
                raise Refusal('recovery-node-absent')
            storage_fd = self.parent(self.storage(entry['path'], expected=entry['storage']))
            os.replace(saved.name, path.name, src_dir_fd=storage_fd, dst_dir_fd=fd)
            os.fsync(storage_fd)
        os.fsync(fd)
        os.fsync(self.state_fd)

    def cleanup(self, value):
        if self.journal() != value:
            raise Refusal('cleanup-intent-changed')
        committed = read_private(self.root / 'accepted.json', self.uid) == value['after_receipt']
        after_backups = self.cleanup_backup_authority(value, committed)
        # Only exact recorded inodes may be retired; never scan the state root.
        for index, entry in enumerate(value['entries']):
            storage_fd = self.parent(self.storage(entry['path'], expected=entry['storage']))
            if committed:
                saved = storage_path(entry['path']) / ('before-' + str(index))
                rollback = self.backup_path(entry['path'])
                observed = node(rollback, self.uid, links=2)
                if observed != entry['before']:
                    if observed is not None:
                        os.unlink(rollback.name, dir_fd=storage_fd)
                    if entry['before'] is not None:
                        if node(saved, self.uid, links=2) != entry['before']:
                            raise Refusal('rollback-node-absent')
                        os.replace(saved.name, rollback.name, src_dir_fd=storage_fd, dst_dir_fd=storage_fd)
            for key in ('before', 'after'):
                path = storage_path(entry['path']) / (key + '-' + str(index))
                observed = node(path, self.uid, links=2)
                if observed is not None:
                    if observed != entry[key]:
                        raise Refusal('cleanup-node-changed')
                    os.unlink(path.name, dir_fd=storage_fd)
            os.fsync(storage_fd)
        if committed:
            self.record('backups.json', after_backups)
            last = read_private(self.root / 'last.json', self.uid)
            if last is not None:
                self.validate_intent(last)
                if last != value and last['after_receipt'] != value['before_receipt']:
                    raise Refusal('foreign-last-intent')
            self.record('last.json', value)
        (self.root / 'pending.json').unlink()
        sync(self.root)

    def compensation(self):
        value = read_private(self.root / 'compensating.json', self.uid)
        if value is None:
            return None
        self.validate_compensation(value)
        return value

    def validate_compensation(self, value, *, preparing=False):
        self.validate_intent(value)
        receipt = read_private(self.root / 'accepted.json', self.uid)
        if receipt not in (value['before_receipt'], value['after_receipt']):
            raise Refusal('foreign-receipt')
        changed_paths = {entry['path'] for entry in value['entries']}
        committed_backups = self.after_backups(value)
        compensated_backups = self.compensated_backups(value)
        current_backups = read_private(self.root / 'backups.json', self.uid)
        self.validate_backup_map(current_backups)
        if current_backups not in ((committed_backups,) if preparing else (committed_backups, compensated_backups)):
            raise Refusal('foreign-backup-map')
        for raw, expected in committed_backups['nodes'].items():
            observed = node(self.backup_path(raw), self.uid, links=2)
            if raw not in changed_paths and observed != expected:
                raise Refusal('foreign-rollback')
            if raw in changed_paths and current_backups == compensated_backups and observed is not None:
                raise Refusal('foreign-rollback')
        for raw, expected in value['after_receipt']['nodes'].items():
            if raw not in changed_paths:
                self.parent(Path(raw).parent)
                if node(Path(raw), self.uid) != expected:
                    raise Refusal('accepted-authority-changed')
        for index, entry in enumerate(value['entries']):
            current = node(Path(entry['path']), self.uid, links=2)
            if current not in (entry['before'], entry['after']):
                raise Refusal('foreign-publication')
            if preparing and current != entry['after']:
                raise Refusal('compensation-authority-changed')
            before = self.backup_path(entry['path'])
            retained = node(before, self.uid, links=2)
            if retained not in (None, entry['before']):
                raise Refusal('foreign-rollback')
            if entry['before'] is not None and current != entry['before'] and retained != entry['before']:
                raise Refusal('rollback-node-absent')
            retained_after = node(storage_path(entry['path']) / ('undo-' + str(index)), self.uid, links=2)
            if retained_after not in (None, entry['after']):
                raise Refusal('foreign-compensation-node')
            if receipt != value['before_receipt'] and entry['after'] is not None and current != entry['after'] and retained_after != entry['after']:
                raise Refusal('compensation-node-absent')

    def compensate_latest(self, adapter, *, check=False, restore_only=False, checkpoint=lambda _stage: None):
        adapter.transaction = self
        """Reverse one exact committed intent, retaining interruption recovery."""
        value = self.compensation()
        if value is None:
            value = read_private(self.root / 'last.json', self.uid)
            if value is None:
                return {'status': 'compensated', 'changed': False, 'published': False}
            self.validate_compensation(value, preparing=True)
        adapter.validate_units(value['units'])
        adapter.validate_units(value['after_receipt']['units'])
        if check:
            return {'status': 'predicted', 'changed': True, 'published': False}
        if read_private(self.root / 'pending.json', self.uid) is not None or self.preparation() is not None:
            raise Refusal('compensation-pending-intent')
        self.record('compensating.json', value)
        checkpoint('compensation-intent')
        adapter.stop()
        checkpoint('compensation-stopped')
        for index, entry in enumerate(value['entries']):
            path = Path(entry['path'])
            fd = self.parent(path.parent)
            storage_fd = self.parent(self.storage(entry['path'], expected=entry['storage']))
            current = node(path, self.uid, links=2)
            if current not in (entry['before'], entry['after']):
                raise Refusal('foreign-publication')
            undo = storage_path(entry['path']) / ('undo-' + str(index))
            if current == entry['after'] and current is not None and node(undo, self.uid, links=2) is None:
                os.link(path.name, undo.name, src_dir_fd=fd, dst_dir_fd=storage_fd, follow_symlinks=False)
                os.fsync(storage_fd)
            if current != entry['before']:
                if entry['before'] is None:
                    os.unlink(path.name, dir_fd=fd)
                else:
                    before = self.backup_path(entry['path'])
                    if node(before, self.uid, links=2) != entry['before']:
                        raise Refusal('rollback-node-absent')
                    os.replace(before.name, path.name, src_dir_fd=storage_fd, dst_dir_fd=fd)
                os.fsync(fd)
                os.fsync(storage_fd)
            checkpoint('compensated-' + str(index))
        self.record('backups.json', self.compensated_backups(value))
        units = value['units'] if value['before_receipt'] is not None else None
        if restore_only:
            return {'status': 'restored-awaiting-outer-owner', 'changed': True,
                    'published': False, 'units': units}
        adapter.retained(value['before_receipt'])
        adapter.restore(units)
        if value['before_receipt'] is not None:
            adapter.ready()
        checkpoint('compensation-ready')
        receipt = read_private(self.root / 'accepted.json', self.uid)
        if receipt not in (value['before_receipt'], value['after_receipt']):
            raise Refusal('foreign-receipt')
        if value['before_receipt'] is None:
            if receipt is not None:
                os.unlink('accepted.json', dir_fd=self.state_fd)
                os.fsync(self.state_fd)
        else:
            self.record('accepted.json', value['before_receipt'])
        checkpoint('compensation-committed')
        self.validate_compensation(value)
        for index, entry in enumerate(value['entries']):
            undo = storage_path(entry['path']) / ('undo-' + str(index))
            if node(undo, self.uid, links=2) is not None:
                storage_fd = self.parent(self.storage(entry['path'], expected=entry['storage']))
                os.unlink(undo.name, dir_fd=storage_fd)
                os.fsync(storage_fd)
        last = read_private(self.root / 'last.json', self.uid)
        if last not in (None, value):
            raise Refusal('foreign-last-intent')
        if last is not None:
            os.unlink('last.json', dir_fd=self.state_fd)
        os.unlink('compensating.json', dir_fd=self.state_fd)
        os.fsync(self.state_fd)
        return {'status': 'compensated', 'changed': True, 'published': False}

    def recover(self, adapter, *, restore_only=False):
        adapter.transaction = self
        outer_record(self.root, self.uid)
        prepared = self.recover_preparation()
        if read_private(self.root / 'compensating.json', self.uid) is not None:
            result = self.compensate_latest(adapter, restore_only=restore_only)
            return result if restore_only else True
        value = self.journal()
        if value is None:
            return {'status': 'reconciled', 'changed': prepared, 'published': False, 'units': None} if restore_only else prepared
        adapter.validate_units(value['units'])
        adapter.validate_units(value['after_receipt']['units'])
        committed = read_private(self.root / 'accepted.json', self.uid) == value['after_receipt']
        if committed:
            if restore_only:
                self.cleanup(value)
                return self.compensate_latest(adapter, restore_only=True)
            adapter.ensure()
            adapter.ready()
            self.cleanup(value)
            return True
        adapter.stop()
        for index, entry in enumerate(value['entries']):
            self.replace(entry, index, 'before')
        if restore_only:
            return {'status': 'restored-awaiting-outer-owner', 'changed': True,
                    'published': False, 'units': value['units'] if value['before_receipt'] is not None else None}
        adapter.retained(value['before_receipt'])
        adapter.restore(value['units'] if value['before_receipt'] is not None else None)
        if value['before_receipt'] is not None:
            adapter.ready()
        self.cleanup(value)
        return True

    def accepted(self):
        receipt = read_private(self.root / 'accepted.json', self.uid)
        if receipt is not None:
            validate_receipt(receipt, root=self.root, uid=self.uid)
            for raw, expected in receipt['nodes'].items():
                self.parent(Path(raw).parent)
                if node(Path(raw), self.uid) != expected:
                    raise Refusal('accepted-authority-changed')
        return receipt

    def confirm_outer(self):
        outer = outer_record(self.root, self.uid)
        if outer is not None:
            receipt = self.accepted()
            if receipt is None:
                raise Refusal('outer-consumer-unconfirmed')
            if outer['consumer_receipt'] != receipt:
                self.record('outer.json', {**outer, 'consumer_receipt': receipt})

    def apply(self, candidates, adapter, *, check=False, checkpoint=lambda _stage: None):
        adapter.transaction = self
        outer_record(self.root, self.uid)
        prepared = self.preparation()
        pending = self.journal()
        compensating = self.compensation()
        interrupted = prepared is not None or pending is not None or compensating is not None
        self.validate(candidates, pending=interrupted)
        if pending is not None:
            adapter.validate_units(pending['units'])
            adapter.validate_units(pending['after_receipt']['units'])
        if check:
            # Inspection validates recovery ownership without recovering or probing.
            self.journal()
            if not interrupted:
                receipt = self.accepted()
                self.backups(str(Path(item['path'])) for item in candidates)
                if len(set((receipt or {}).get('nodes', {})) | {str(Path(item['path'])) for item in candidates}) > 64:
                    raise Refusal('receipt-node-limit')
            return {'status': 'predicted', 'changed': interrupted or not self.unchanged(candidates, pending=interrupted), 'published': False}
        recovered = self.recover(adapter)
        self.validate(candidates)
        receipt = self.accepted()
        before_backups = self.backups(str(Path(item['path'])) for item in candidates)
        if len(set((receipt or {}).get('nodes', {})) | {str(Path(item['path'])) for item in candidates}) > 64:
            raise Refusal('receipt-node-limit')
        adapter.retained(receipt)
        if (self.unchanged(candidates) and receipt is not None
                and all(item['path'] in receipt['nodes'] for item in candidates)):
            adopted = adapter.ensure()
            adapter.ready()
            self.confirm_outer()
            return {'status': 'accepted', 'changed': recovered or adopted, 'published': False}
        adapter.validate()
        units = receipt['units'] if receipt is not None else adapter.inspect()
        adapter.validate_units(units)
        entries = []
        # Unique scratch nodes cannot block a retry after pre-claim death. They
        # remain private and are never scanned/deleted without a durable claim.
        directory = Path(tempfile.mkdtemp(prefix='.prepare-', dir=self.root))
        directory.chmod(0o700)
        directory_identity = identity(directory.lstat())
        fd = self.parent(directory)
        for index, item in enumerate(candidates):
            path = Path(item['path'])
            before = node(path, self.uid)
            storage = self.storage(item['path'], create=True)
            storage_identity = storage_claim(item['path'])
            storage_fd = self.parent(storage)
            after = storage / ('staged-' + directory.name[1:] + '-' + str(index))
            if 'absent' in item:
                observed_after = None
            else:
                if 'target' in item:
                    os.symlink(item['target'], after.name, dir_fd=storage_fd)
                else:
                    output_fd = os.open(after.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, item['mode'], dir_fd=storage_fd)
                    with os.fdopen(output_fd, 'wb') as stream:
                        os.fchown(stream.fileno(), self.uid, item['gid'])
                        os.fchmod(stream.fileno(), item['mode'])
                        if 'source' in item:
                            source_fd = os.open(item['source'], os.O_RDONLY | os.O_NOFOLLOW)
                            with os.fdopen(source_fd, 'rb') as source:
                                total = 0
                                while True:
                                    chunk = source.read(1048576)
                                    if not chunk:
                                        break
                                    total += len(chunk)
                                    if total > 128 * 1024 * 1024:
                                        raise Refusal('asset-oversize')
                                    stream.write(chunk)
                        else:
                            stream.write(base64.b64decode(item['data'], validate=True))
                        stream.flush()
                        os.fsync(stream.fileno())
                observed_after = node(after, self.uid)
                if 'source' in item and observed_after['sha256'] != item['sha256']:
                    raise Refusal('asset-changed')
            os.fsync(storage_fd)
            entries.append({'path': str(path), 'before': before, 'after': observed_after,
                            'deferred': item.get('deferred', False), 'storage': storage_identity})
            checkpoint('staged-' + str(index))
        os.fsync(fd)
        os.fsync(self.state_fd)
        next_nodes = dict((receipt or {}).get('nodes', {}))
        next_nodes.update({entry['path']: entry['after'] for entry in entries})
        next_receipt = {'schema': 1, 'nodes': next_nodes,
                        'previous': None if receipt is None else receipt['nodes'], 'units': units}
        value = {'schema': 1, 'before_receipt': receipt, 'after_receipt': next_receipt,
                 'before_backups': before_backups, 'entries': entries, 'units': units}
        self.validate_intent(value)
        preparation = {'schema': 1, 'directory': directory.name,
                       'identity': directory_identity, 'intent': value}
        self.record('preparation.json', preparation)
        checkpoint('prepared')
        for index, entry in enumerate(entries):
            path = Path(entry['path'])
            parent = self.parent(path.parent)
            storage_fd = self.parent(self.storage(entry['path'], expected=entry['storage']))
            if node(path, self.uid) != entry['before']:
                raise Refusal('preparation-publication-changed')
            if entry['before'] is not None:
                os.link(path.name, 'before-' + str(index), src_dir_fd=parent,
                        dst_dir_fd=storage_fd, follow_symlinks=False)
            if entry['after'] is not None:
                # link() is create-if-absent: a foreign fixed node is never
                # overwritten, even if another root caller races the claim.
                name = 'after-' + str(index)
                staged = staged_path(preparation, index, entry)
                os.link(staged.name, name, src_dir_fd=storage_fd, dst_dir_fd=storage_fd, follow_symlinks=False)
                os.fsync(storage_fd)
                checkpoint('linked-' + str(index))
                os.unlink(staged.name, dir_fd=storage_fd)
            os.fsync(storage_fd)
            os.fsync(fd)
            checkpoint('materialized-' + str(index))
        self.record('pending.json', value)
        self.finish_preparation(preparation, retain_fixed=True)
        checkpoint('intent')
        try:
            adapter.stop()
            checkpoint('stopped')
            for index, entry in enumerate(entries):
                if entry['deferred']:
                    continue
                self.replace(entry, index, 'after')
                checkpoint('published-' + str(index))
            known = self.journal()
            if any(node(Path(entry['path']), self.uid, links=2) != entry['before' if entry['deferred'] else 'after'] for entry in known['entries']):
                raise Refusal('publication-unconfirmed')
            adapter.start()
            checkpoint('adopted')
            adapter.ready()
            checkpoint('ready')
            for index, entry in enumerate(entries):
                if entry['deferred']:
                    self.replace(entry, index, 'after')
            next_receipt['units'] = adapter.inspect()
            self.record('pending.json', value)
            self.record('accepted.json', next_receipt)
            checkpoint('committed')
        except Exception:
            self.recover(adapter)
            raise Refusal('candidate-refused') from None
        self.confirm_outer()
        self.cleanup(value)
        return {'status': 'accepted', 'changed': True, 'published': True}
