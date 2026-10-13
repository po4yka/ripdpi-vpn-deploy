"""Private, bounded queue compensation for sender candidate activation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from transport_runtime_transaction import Refusal, identity, mount_id, read_private, validate_claim

COPY_LIMIT = 1024**3 - 16 * 1024**2
WORKING_LIMIT = 1024**3
TOTAL_LIMIT = 2 * 1024**3
MAX_ENTRIES = 2048
STORE = '.ripdpi-queue-activation'


def directory(path, uid):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise Refusal('queue-directory-authority')
    return fd


def child_parent(root, name):
    fd = os.dup(root)
    try:
        for part in Path(name).parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def tree(root, uid, *, skip_store=False, limit=WORKING_LIMIT):
    result = {}
    device, mounting = os.fstat(root).st_dev, mount_id(root)

    def visit(fd, prefix, depth):
        if depth > 8:
            raise Refusal('queue-depth')
        for name in sorted(os.listdir(fd)):
            if not prefix and skip_store and name == STORE:
                opened = os.open(STORE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    info = os.fstat(opened)
                    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700 or mount_id(opened) != mounting:
                        raise Refusal('queue-store-authority')
                finally:
                    os.close(opened)
                continue
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', name) or name in {'.', '..'}:
                raise Refusal('queue-entry-name')
            relative = prefix + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode)
            kind = 'directory' if stat.S_ISDIR(info.st_mode) else 'file'
            if (info.st_uid != uid or info.st_dev != device
                    or mode != (0o700 if kind == 'directory' else 0o600)
                    or (kind == 'file' and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))):
                raise Refusal('queue-entry-authority')
            opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW |
                             (os.O_DIRECTORY if kind == 'directory' else 0), dir_fd=fd)
            try:
                if identity(os.fstat(opened)) != identity(info) or mount_id(opened) != mounting:
                    raise Refusal('queue-entry-changed')
                result[relative] = {'kind': kind, 'identity': identity(info),
                                    'size': info.st_size if kind == 'file' else 0,
                                    'mtime_ns': info.st_mtime_ns, 'allocated': info.st_blocks * 512}
                if len(result) > MAX_ENTRIES:
                    raise Refusal('queue-entry-count')
                if kind == 'directory':
                    visit(opened, relative + '/', depth + 1)
            finally:
                os.close(opened)
    visit(root, '', 0)
    if skip_store:
        native_shape(result)
    block = max(4096, os.fstatvfs(root).f_bsize)
    amount = sum(max(entry['allocated'], ((entry['size'] + block - 1) // block) * block) + block
                 for entry in result.values())
    if amount > limit:
        raise Refusal('queue-copy-budget')
    return result, amount


def copy_file(source, target):
    digest = hashlib.sha256()
    total = 0
    while True:
        data = os.read(source, 65536)
        if not data:
            break
        total += len(data)
        if total > COPY_LIMIT:
            raise Refusal('queue-file-budget')
        digest.update(data)
        view = memoryview(data)
        while view:
            written = os.write(target, view)
            if written <= 0:
                raise Refusal('queue-copy-write')
            view = view[written:]
    os.fsync(target)
    return digest.hexdigest()


def remove_tree(root, entries):
    for name in sorted(entries, key=lambda value: (value.count('/'), value), reverse=True):
        parent = child_parent(root, name)
        try:
            info = os.stat(Path(name).name, dir_fd=parent, follow_symlinks=False)
            if identity(info) != entries[name]['identity']:
                raise Refusal('queue-cleanup-changed')
            if entries[name]['kind'] == 'directory':
                os.rmdir(Path(name).name, dir_fd=parent)
            else:
                os.unlink(Path(name).name, dir_fd=parent)
            os.fsync(parent)
        finally:
            os.close(parent)


class QueueSnapshot:
    def __init__(self, tx, queue, agent_uid, *, checkpoint=lambda _stage: None):
        self.tx, self.queue, self.agent_uid = tx, Path(queue), agent_uid
        self.checkpoint = checkpoint

    def root(self, expected=None):
        fd = directory(self.queue, self.agent_uid)
        if expected is not None and identity(os.fstat(fd)) != expected:
            os.close(fd)
            raise Refusal('queue-root-changed')
        return fd

    def record(self, value):
        if len(json.dumps(value).encode()) > 1048576:
            raise Refusal('queue-manifest-budget')
        self.tx.record('queue-snapshot.json', value)

    def saved(self):
        value = read_private(self.tx.root / 'queue-snapshot.json', self.tx.uid)
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) != {'schema', 'phase', 'root', 'directory',
                'directory_identity', 'tree', 'intent', 'after_nodes', 'restore', 'store_identity'}
                or type(value['schema']) is not int or value['schema'] != 1 or value['phase'] not in {'preparing', 'retained', 'restored', 'aborted', 'cleaning'}
                or re.fullmatch(r'\.queue-[a-f0-9]{32}', value['directory']) is None
                or not isinstance(value['tree'], dict) or len(value['tree']) > MAX_ENTRIES):
            raise Refusal('queue-snapshot-record')
        for claim, owner in ((value['root'], self.agent_uid), (value['directory_identity'], self.tx.uid)):
            if (not isinstance(claim, list) or len(claim) != 5 or
                    any(type(number) is not int or not 0 <= number < 2**64 for number in claim) or
                    claim[2] != owner or claim[4] != 0o700):
                raise Refusal('queue-snapshot-identity')
        if not re.fullmatch('[a-f0-9]{64}', value['intent']):
            raise Refusal('queue-snapshot-intent')
        if not isinstance(value['after_nodes'], dict) or len(value['after_nodes']) > 64:
            raise Refusal('queue-after-authority')
        for path, claim in value['after_nodes'].items():
            if not Path(path).is_absolute() or '..' in Path(path).parts:
                raise Refusal('queue-after-authority')
            validate_claim(claim, self.tx.uid)
        store = value['store_identity']
        if store is not None and (not isinstance(store, list) or len(store) != 5 or
                any(type(number) is not int or not 0 <= number < 2**64 for number in store) or
                store[2:] != [self.tx.uid, os.getgid(), 0o700]):
            raise Refusal('queue-store-record')
        restore = value['restore']
        if restore is not None:
            if (not isinstance(restore, dict) or set(restore) != {'name', 'identity', 'nodes'} or
                    re.fullmatch(r'restore-[a-f0-9]{32}', restore['name']) is None or
                    not isinstance(restore['identity'], list) or len(restore['identity']) != 5 or
                    restore['identity'][2:] != [self.tx.uid, os.getgid(), 0o700] or
                    not isinstance(restore['nodes'], dict) or set(restore['nodes']) - set(value['tree'])):
                raise Refusal('queue-restore-record')
            for name, claim in restore['nodes'].items():
                if (not isinstance(claim, list) or len(claim) != 5 or
                        any(type(number) is not int or not 0 <= number < 2**64 for number in claim) or
                        claim[4] != value['tree'][name]['identity'][4]):
                    raise Refusal('queue-restore-node-record')
        native_shape(value['tree'])
        total = 0
        for path, entry in value['tree'].items():
            if (not isinstance(path, str) or len(Path(path).parts) > 8 or
                    any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', part) or part in {'.', '..'}
                        for part in Path(path).parts) or Path(path).is_absolute() or
                    Path(path).parts[0] == STORE or not isinstance(entry, dict) or
                    set(entry) - {'sha256', 'backup_identity'} != {'kind', 'identity', 'size', 'mtime_ns', 'allocated'} or
                    entry['kind'] not in {'file', 'directory'}):
                raise Refusal('queue-snapshot-entry')
            claim = entry['identity']
            if (not isinstance(claim, list) or len(claim) != 5 or
                    any(type(number) is not int or not 0 <= number < 2**64 for number in claim) or
                    claim[2] != value['root'][2] or not 0 <= claim[3] < 2**32 - 1 or
                    claim[4] != (0o700 if entry['kind'] == 'directory' else 0o600) or
                    type(entry['size']) is not int or not 0 <= entry['size'] <= COPY_LIMIT or
                    type(entry['mtime_ns']) is not int or not 0 <= entry['mtime_ns'] < 2**64):
                raise Refusal('queue-snapshot-entry')
            if entry['kind'] == 'file' and value['phase'] in {'retained', 'restored'} and not re.fullmatch(
                    '[a-f0-9]{64}', entry.get('sha256', '')):
                raise Refusal('queue-snapshot-digest')
            if type(entry['allocated']) is not int or not 0 <= entry['allocated'] <= COPY_LIMIT:
                raise Refusal('queue-snapshot-allocation')
            backup = entry.get('backup_identity')
            if backup is not None and (not isinstance(backup, list) or len(backup) != 5 or
                    any(type(number) is not int or not 0 <= number < 2**64 for number in backup) or
                    backup[2:4] != [self.tx.uid, os.getgid()] or backup[4] != claim[4]):
                raise Refusal('queue-backup-identity')
            total += max(entry['allocated'], ((entry['size'] + 4095) // 4096) * 4096) + 4096
        if total > COPY_LIMIT:
            raise Refusal('queue-snapshot-budget')
        return value

    @staticmethod
    def signature(intent):
        return hashlib.sha256(json.dumps({'entries': intent['entries'],
            'before': intent['before_receipt']}, sort_keys=True).encode()).hexdigest()

    def capture(self, intent):
        saved = self.saved()
        if saved is not None:
            if saved['intent'] != self.signature(intent):
                raise Refusal('queue-snapshot-owner')
            return
        root = self.root()
        try:
            entries, amount = tree(root, self.agent_uid, skip_store=True, limit=COPY_LIMIT)
            native_metadata(root, entries)
            if os.fstat(root).st_dev != os.fstat(self.tx.state_fd).st_dev:
                raise Refusal('queue-snapshot-filesystem')
            empty_orphans(self.tx.state_fd, '.queue-', self.tx.uid)
            if os.path.lexists(self.queue / STORE):
                fd = directory(self.queue / STORE, self.tx.uid)
                try:
                    empty_orphans(fd, 'restore-', self.tx.uid)
                finally:
                    os.close(fd)
            # The pinned one-URL queue's working ceiling is reserved separately.
            fs = os.fstatvfs(root)
            reserve = max(5 * 1024**3, fs.f_blocks * fs.f_frsize // 5)
            from observability_queue_boundary import allocated_bytes, collector_allowance
            allocated = allocated_bytes(self.queue)
            required = reserve + TOTAL_LIMIT - allocated + collector_allowance(os.fstat(root).st_dev)
            if fs.f_bavail * fs.f_frsize <= required:
                raise Refusal('queue-snapshot-capacity')
            name = '.queue-' + uuid.uuid4().hex
            os.mkdir(name, 0o700, dir_fd=self.tx.state_fd)
            os.fsync(self.tx.state_fd)
            backup = directory(self.tx.root / name, self.tx.uid)
            try:
                saved = {'schema': 1, 'phase': 'preparing', 'root': identity(os.fstat(root)),
                         'directory': name, 'directory_identity': identity(os.fstat(backup)),
                         'tree': entries, 'intent': self.signature(intent),
                         'after_nodes': (intent['after_receipt'] or {}).get('nodes', {}),
                         'restore': None, 'store_identity': None}
                self.record(saved)
                self.checkpoint('queue-intent')
                for path, entry in entries.items():
                    parent = child_parent(backup, path)
                    source_parent = child_parent(root, path)
                    try:
                        leaf = Path(path).name
                        if entry['kind'] == 'directory':
                            os.mkdir(leaf, 0o700, dir_fd=parent)
                            entry['backup_identity'] = identity(os.stat(leaf, dir_fd=parent, follow_symlinks=False))
                            self.record(saved)
                        else:
                            src = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=source_parent)
                            dst = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                          0o600, dir_fd=parent)
                            try:
                                entry['backup_identity'] = identity(os.fstat(dst))
                                self.record(saved)
                                if identity(os.fstat(src)) != entry['identity']:
                                    raise Refusal('queue-source-changed')
                                entry['sha256'] = copy_file(src, dst)
                                if os.fstat(src).st_mtime_ns != entry['mtime_ns']:
                                    raise Refusal('queue-source-changed')
                            finally:
                                os.close(src)
                                os.close(dst)
                        os.fsync(parent)
                    finally:
                        os.close(parent)
                        os.close(source_parent)
                os.fsync(backup)
                if tree(root, self.agent_uid, skip_store=True)[0] != entries_without_hash(entries):
                    raise Refusal('queue-source-changed')
                saved['phase'] = 'retained'
                self.record(saved)
                self.checkpoint('queue-retained')
            finally:
                os.close(backup)
        finally:
            os.close(root)

    def backup(self, saved, *, complete):
        fd = directory(self.tx.root / saved['directory'], self.tx.uid)
        try:
            if identity(os.fstat(fd)) != saved['directory_identity']:
                raise Refusal('queue-backup-root')
            actual, _ = tree(fd, self.tx.uid)
            if (set(actual) - set(saved['tree']) or complete and set(actual) != set(saved['tree'])):
                raise Refusal('queue-backup-entry')
            for name, entry in actual.items():
                expected = saved['tree'][name]
                if expected.get('backup_identity') is None and not complete:
                    if entry['kind'] == expected['kind'] and entry['size'] == 0:
                        continue
                    raise Refusal('queue-unclaimed-data')
                if (entry['identity'] != expected.get('backup_identity') or
                        entry['kind'] != expected['kind'] or entry['size'] > expected['size']):
                    raise Refusal('queue-backup-shape')
                if entry['kind'] == 'file' and (complete or expected.get('sha256')):
                    parent = child_parent(fd, name)
                    src = os.open(Path(name).name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                    try:
                        digest = hashlib.sha256()
                        for chunk in iter(lambda: os.read(src, 65536), b''):
                            digest.update(chunk)
                        if entry['size'] != expected['size'] or digest.hexdigest() != expected['sha256']:
                            raise Refusal('queue-backup-bytes')
                    finally:
                        os.close(src)
                        os.close(parent)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def restore(self):
        saved = self.saved()
        if saved is None or saved['phase'] in {'restored', 'aborted', 'cleaning'}:
            return
        root = self.root(saved['root'])
        backup = self.backup(saved, complete=saved['phase'] == 'retained')
        try:
            if saved['phase'] == 'retained':
                # Validate previously staged authority before touching live bytes.
                if saved['restore'] is not None:
                    storage = directory(self.queue / STORE, self.tx.uid)
                    try:
                        if identity(os.fstat(storage)) != saved['store_identity']:
                            raise Refusal('queue-restore-store')
                        self.clear_restore(storage, saved['restore'], saved)
                        saved['restore'] = None
                        self.record(saved)
                    finally:
                        os.close(storage)
                # Empty the candidate first; backup + restore never form three copies.
                current, _ = tree(root, self.agent_uid, skip_store=True)
                remove_tree(root, current)
                if not os.path.lexists(self.queue / STORE):
                    os.mkdir(STORE, 0o700, dir_fd=root)
                    os.fsync(root)
                storage = directory(self.queue / STORE, self.tx.uid)
                try:
                    if saved['store_identity'] is None:
                        empty_orphans(storage, 'restore-', self.tx.uid)
                        saved['store_identity'] = identity(os.fstat(storage))
                        self.record(saved)
                    elif identity(os.fstat(storage)) != saved['store_identity']:
                        raise Refusal('queue-restore-store')
                    prior = saved['restore']
                    if prior is not None:
                        self.clear_restore(storage, prior, saved)
                    empty_orphans(storage, 'restore-', self.tx.uid)
                    name = 'restore-' + uuid.uuid4().hex
                    os.mkdir(name, 0o700, dir_fd=storage)
                    output = directory(self.queue / STORE / name, self.tx.uid)
                    try:
                        saved['restore'] = {'name': name, 'identity': identity(os.fstat(output)), 'nodes': {}}
                        self.record(saved)
                        for path, entry in saved['tree'].items():
                            parent = child_parent(output, path)
                            original = child_parent(backup, path)
                            try:
                                leaf = Path(path).name
                                if entry['kind'] == 'directory':
                                    os.mkdir(leaf, 0o700, dir_fd=parent)
                                    saved['restore']['nodes'][path] = identity(os.stat(leaf, dir_fd=parent, follow_symlinks=False))
                                    self.record(saved)
                                else:
                                    src = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=original)
                                    dst = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                                  0o600, dir_fd=parent)
                                    try:
                                        saved['restore']['nodes'][path] = identity(os.fstat(dst))
                                        self.record(saved)
                                        if copy_file(src, dst) != entry['sha256']:
                                            raise Refusal('queue-backup-changed')
                                        os.utime(dst, ns=(entry['mtime_ns'], entry['mtime_ns']))
                                        os.fchown(dst, entry['identity'][2], entry['identity'][3])
                                        saved['restore']['nodes'][path] = identity(os.fstat(dst))
                                        self.record(saved)
                                    finally:
                                        os.close(src)
                                        os.close(dst)
                                os.fsync(parent)
                            finally:
                                os.close(parent)
                                os.close(original)
                        for path, entry in reversed(list(saved['tree'].items())):
                            if entry['kind'] == 'directory':
                                parent = child_parent(output, path)
                                child = os.open(Path(path).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                                dir_fd=parent)
                                try:
                                    os.fchown(child, entry['identity'][2], entry['identity'][3])
                                    saved['restore']['nodes'][path] = identity(os.fstat(child))
                                    self.record(saved)
                                    os.fsync(child)
                                finally:
                                    os.close(child)
                                    os.close(parent)
                        os.fsync(output)
                        self.checkpoint('queue-restore-copied')
                        for leaf in os.listdir(output):
                            os.rename(leaf, leaf, src_dir_fd=output, dst_dir_fd=root)
                            os.fsync(root)
                            self.checkpoint('queue-restored-entry')
                    finally:
                        os.close(output)
                    saved['phase'] = 'restored'
                    self.record(saved)
                    self.clear_restore(storage, saved['restore'], saved)
                    saved['restore'] = None
                    self.record(saved)
                finally:
                    os.close(storage)
            saved['phase'] = 'restored' if saved['phase'] != 'preparing' else 'aborted'
            self.record(saved)
            self.checkpoint('queue-restored')
        finally:
            os.close(backup)
            os.close(root)

    def clear_restore(self, storage, claim, saved):
        if (set(claim) != {'name', 'identity', 'nodes'} or
                re.fullmatch(r'restore-[a-f0-9]{32}', claim['name']) is None):
            raise Refusal('queue-restore-claim')
        try:
            fd = os.open(claim['name'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=storage)
        except FileNotFoundError:
            if saved['phase'] in {'retained', 'restored', 'aborted', 'cleaning'}:
                return
            raise
        try:
            if identity(os.fstat(fd)) != claim['identity']:
                raise Refusal('queue-restore-root')
            # Staged children may already have their restored agent ownership.
            entries = staging_tree(fd, saved['tree'], self.tx.uid, self.agent_uid)
            unclaimed = {name for name in entries if name not in claim['nodes']}
            if (any(entry['identity'][:2] != claim['nodes'][name][:2]
                    for name, entry in entries.items() if name not in unclaimed) or
                    any(entries[name]['size'] != 0 for name in unclaimed)):
                raise Refusal('queue-restore-replaced')
            removable = {name: entry for name, entry in entries.items() if name not in unclaimed
                         and not any(other.startswith(name + '/') for other in unclaimed)}
            remove_tree(fd, removable)
            remaining = staging_tree(fd, saved['tree'], self.tx.uid, self.agent_uid)
            if any(entry['size'] != 0 for entry in remaining.values()):
                raise Refusal('queue-unclaimed-data')
        finally:
            os.close(fd)
        if not remaining:
            os.rmdir(claim['name'], dir_fd=storage)
        os.fsync(storage)

    def cleanup(self):
        saved = self.saved()
        if saved is None:
            return
        if saved['restore'] is not None:
            storage = directory(self.queue / STORE, self.tx.uid)
            try:
                if identity(os.fstat(storage)) != saved['store_identity']:
                    raise Refusal('queue-restore-store')
                self.clear_restore(storage, saved['restore'], saved)
            finally:
                os.close(storage)
        complete = saved['phase'] not in {'preparing', 'aborted', 'cleaning'}
        try:
            backup = self.backup(saved, complete=complete)
        except FileNotFoundError:
            if saved['phase'] != 'cleaning':
                raise
            backup = None
        saved['phase'] = 'cleaning'
        self.record(saved)
        try:
            if backup is not None:
                entries, _ = tree(backup, self.tx.uid)
                unclaimed = {name for name in entries if saved['tree'][name].get('backup_identity') is None}
                removable = {name: entry for name, entry in entries.items() if name not in unclaimed
                             and not any(other.startswith(name + '/') for other in unclaimed)}
                remove_tree(backup, removable)
                remaining, _ = tree(backup, self.tx.uid)
                if any(entry['size'] != 0 for entry in remaining.values()):
                    raise Refusal('queue-unclaimed-data')
        finally:
            if backup is not None:
                os.close(backup)
        if backup is not None and not remaining:
            os.rmdir(saved['directory'], dir_fd=self.tx.state_fd)
        os.unlink('queue-snapshot.json', dir_fd=self.tx.state_fd)
        os.fsync(self.tx.state_fd)


def entries_without_hash(entries):
    return {name: {key: value for key, value in entry.items() if key not in {'sha256', 'backup_identity'}}
            for name, entry in entries.items()}


def staging_tree(root, planned, root_uid, agent_uid):
    result = {}
    def visit(fd, prefix):
        for leaf in os.listdir(fd):
            name = prefix + leaf
            if name not in planned:
                raise Refusal('queue-restore-entry')
            info = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            kind = planned[name]['kind']
            if (info.st_dev != os.fstat(root).st_dev or
                    (info.st_uid, info.st_gid) not in {(root_uid, os.getgid()),
                                                     tuple(planned[name]['identity'][2:4])} or
                    stat.S_IMODE(info.st_mode) != (0o700 if kind == 'directory' else 0o600) or
                    (kind == 'file' and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)) or
                    (kind == 'directory' and not stat.S_ISDIR(info.st_mode))):
                raise Refusal('queue-restore-entry')
            result[name] = {'kind': kind, 'identity': identity(info),
                            'size': info.st_size if kind == 'file' else 0}
            if kind == 'directory':
                child = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    if mount_id(child) != mount_id(root):
                        raise Refusal('queue-restore-mount')
                    visit(child, name + '/')
                finally:
                    os.close(child)
    visit(root, '')
    return result


def native_shape(entries):
    url_directories = set()
    for path, entry in entries.items():
        parts = Path(path).parts
        if parts == ('.vm_app_running',):
            valid = entry['kind'] == 'file' and entry['size'] == 0
        elif parts == ('persistent-queue',):
            valid = entry['kind'] == 'directory'
        elif len(parts) in {2, 3} and parts[0] == 'persistent-queue' and re.fullmatch(r'1_[0-9A-F]{16}', parts[1]):
            url_directories.add(parts[1])
            valid = (len(parts) == 2 and entry['kind'] == 'directory' or
                     len(parts) == 3 and entry['kind'] == 'file' and
                     (parts[2] in {'flock.lock', 'metainfo.json'} or re.fullmatch('[0-9A-F]{16}', parts[2])))
            if len(parts) == 3 and parts[2] in {'flock.lock', 'metainfo.json'}:
                valid = valid and entry['size'] <= 16384
            if len(parts) == 3 and entry['kind'] == 'file':
                temporary = re.fullmatch(r'(metainfo[.]json|0000000000000000)[.]tmp[.](0|[1-9][0-9]{0,19})', parts[2])
                if temporary and int(temporary[2]) < 2**64:
                    # Pinned native atomic writes stage bounded metadata or an
                    # empty initial chunk. Preserve interrupted staging bytes.
                    valid = entry['size'] <= 16384 if temporary[1] == 'metainfo.json' else entry['size'] == 0
        else:
            valid = False
        if not valid or len(url_directories) > 1:
            raise Refusal('queue-native-layout')


def native_metadata(root, entries):
    directories = [name for name, item in entries.items()
                   if name.startswith('persistent-queue/') and name.count('/') == 1 and item['kind'] == 'directory']
    if not directories:
        return
    prefix = directories[0] + '/'
    name = prefix + 'metainfo.json'
    if name not in entries:
        raise Refusal('queue-native-metadata')
    parent = child_parent(root, name)
    fd = os.open('metainfo.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        raw = os.read(fd, 16385)
        value = json.loads(raw)
    finally:
        os.close(fd)
        os.close(parent)
    if (not isinstance(value, dict) or set(value) != {'Name', 'ReaderOffset', 'WriterOffset'} or
            value['Name'] != '1:secret-url' or
            any(type(value[key]) is not int or not 0 <= value[key] < 2**64
                for key in ('ReaderOffset', 'WriterOffset'))):
        raise Refusal('queue-native-metadata')
    reader, writer = value['ReaderOffset'], value['WriterOffset']
    chunk = 536871040
    if reader > writer or writer - reader > chunk + 33554432 + 8:
        raise Refusal('queue-native-offsets')
    expected = {prefix + f'{offset:016X}' for offset in
                range(reader // chunk * chunk, writer // chunk * chunk + 1, chunk)}
    actual = {name for name in entries if name.startswith(prefix) and
              re.fullmatch('[0-9A-F]{16}', Path(name).name)}
    if (actual != expected or any(entries[name]['size'] > 504539978 for name in actual) or
            entries[prefix + f'{reader // chunk * chunk:016X}']['size'] < reader % chunk or
            entries[prefix + f'{writer // chunk * chunk:016X}']['size'] != writer % chunk):
        raise Refusal('queue-native-chunks')
    lock = entries.get(prefix + 'flock.lock')
    if lock is None or lock['size'] != 0:
        raise Refusal('queue-native-lock')


def empty_orphans(parent, prefix, uid):
    # A death between mkdir and its inode claim can leave only an empty private
    # directory. Preserve it, bound its metadata, and allocate a fresh name.
    names = [name for name in os.listdir(parent) if name.startswith(prefix)]
    if len(names) > 64:
        raise Refusal('queue-orphan-count')
    total = 0
    for name in names:
        if re.fullmatch(re.escape(prefix) + '[a-f0-9]{32}', name) is None:
            raise Refusal('queue-orphan-name')
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
                raise Refusal('queue-unclaimed-data')
            entries, amount = tree(fd, uid, limit=8 * 1024**2)
            total += amount + max(info.st_blocks * 512, os.fstatvfs(fd).f_bsize)
            if total > 8 * 1024**2 or any(entry['size'] != 0 for entry in entries.values()):
                raise Refusal('queue-unclaimed-data')
        finally:
            os.close(fd)
