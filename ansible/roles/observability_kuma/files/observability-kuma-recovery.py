#!/usr/bin/env python3
"""Verify a downloaded encrypted observer backup without touching live data."""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from urllib import error, parse, request

BACKUP = runpy.run_path(str(Path(__file__).with_name('observability-kuma-backup.py')))
validate = runpy.run_path(str(Path(__file__).with_name('observability-kuma-recovery-contract.py')))['validate']
WORKSPACE = runpy.run_path(str(Path(__file__).with_name('observability-kuma-recovery-workspace.py')))
WORK = WORKSPACE['WORK']
HEALTH = Path('/var/lib/observability-kuma-recovery-health/status.json')
CONFIG = Path('/etc/observability-kuma/recovery.json')
OWNER = WORKSPACE['OWNER']
STORAGE = runpy.run_path(str(Path(__file__).with_name('observability-kuma-storage-contract.py')))
StorageAuthority, CAPABILITIES = STORAGE['StorageAuthority'], STORAGE['CAPABILITIES']
MAX_CIPHER = BACKUP['MAX_DATA'] + 256 * 1024**2
ID = re.compile(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}\Z')
CHILD_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate-field')
        value[key] = item
    return value


def private_json(path):
    path = BACKUP['private_regular'](path)
    info = path.lstat()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) or opened.st_size > 16384:
            raise ValueError('metadata-authority-or-limit')
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError('metadata-limit')
    return json.loads(raw, object_pairs_hook=unique)


def owned_work():
    return WORKSPACE['owned_work'](WORK)


def cleanup():
    return WORKSPACE['cleanup'](WORK)


def publish(status, *, verified_at=0, backup_at=0, valid_until=0):
    if BACKUP['private_regular'](HEALTH.parent / '.owner').read_bytes() != OWNER:
        raise ValueError('health-directory-authority')
    for parent in (HEALTH.parent, *HEALTH.parent.parents):
        info = parent.lstat()
        sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o022 and not sticky):
            raise ValueError('health-directory-authority')
    if os.path.lexists(HEALTH):
        info = HEALTH.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ValueError('health-file-authority')
    value = {'schema_version': 1, 'status': status, 'verified_at': verified_at,
             'backup_at': backup_at, 'valid_until': valid_until}
    fd, name = tempfile.mkstemp(prefix='.recovery-', dir=HEALTH.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o640)
            json.dump(value, stream, sort_keys=True)
            stream.flush();os.fsync(stream.fileno())
        os.replace(name, HEALTH)
        directory = os.open(HEALTH.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


class Storage(StorageAuthority):
    def deliver(self, archive, identity, manifest):
        name = 'kuma/' + identity + '.tar.age'
        upload = self.call('b2_get_upload_url', {'bucketId': self.config['bucket_id']})
        url = parse.urlsplit(upload['uploadUrl'])
        if (url.scheme != 'https' or url.username or url.password or url.fragment or url.port not in (None, 443)
                or not url.hostname or not re.fullmatch(r'pod-[0-9-]+\.(?:backblaze\.com|backblazeb2\.com)', url.hostname)
                or not re.fullmatch(r'/b2api/v[1-4]/b2_upload_file(?:/[A-Za-z0-9_/-]+)?', url.path)):
            raise ValueError('upload-origin')
        # SHA-1 is the provider's wire checksum; recovery uses SHA-256 and age.
        wire = hashlib.sha1(usedforsecurity=False)
        with archive.open('rb') as stream:
            for data in iter(lambda: stream.read(1024 * 1024), b''):
                wire.update(data)
        with archive.open('rb') as stream:
            outbound = request.Request(upload['uploadUrl'], data=stream, method='POST', headers={
                'Authorization': upload['authorizationToken'], 'Content-Type': 'application/octet-stream',
                'Content-Length': str(archive.stat().st_size), 'X-Bz-File-Name': parse.quote(name, safe='/'),
                'X-Bz-Content-Sha1': wire.hexdigest(), 'X-Bz-Info-recovery-manifest':
                    parse.quote(json.dumps(manifest, sort_keys=True, separators=(',', ':')), safe='')})
            with self.opener.open(outbound, timeout=30) as response:
                raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('upload-response-limit')
        uploaded = json.loads(raw, object_pairs_hook=unique)
        info = self.call('b2_get_file_info', {'fileId': uploaded['fileId']})
        if (info['fileName'] != name or info['bucketId'] != self.config['bucket_id']
                or info['fileId'] != uploaded['fileId'] or info['contentLength'] != archive.stat().st_size
                or info['serverSideEncryption'] != {'algorithm': 'AES256', 'mode': 'SSE-B2'}):
            raise ValueError('uploaded-object-identity')
        destination = WORK / 'cipher.age'
        outbound = request.Request(self.download + '/b2api/v4/b2_download_file_by_id?' + parse.urlencode({'fileId': info['fileId']}),
                                   headers={'Authorization': self.auth['authorizationToken']})
        with self.opener.open(outbound, timeout=30) as response:
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > info['contentLength'] or total > MAX_CIPHER:
                        raise ValueError('download-size-limit')
                    stream.write(chunk)
                stream.flush();os.fsync(stream.fileno())
        if total != info['contentLength'] or BACKUP['archive_digest'](destination) != manifest['sha256']:
            raise ValueError('downloaded-ciphertext-mismatch')
        anonymous = self.download + '/file/' + parse.quote(self.config['bucket_name']) + '/' + parse.quote(name, safe='/')
        try:
            with self.opener.open(anonymous, timeout=15) as response:
                response.read(1)
        except error.HTTPError as refused:
            if refused.code not in (401, 403):
                raise ValueError('anonymous-check-unavailable') from None
        else:
            raise ValueError('anonymous-download-allowed')
        return destination


def selected_backup(config, now):
    candidates = []
    for path in Path(config['directory']).glob('*.json'):
        if not ID.fullmatch(path.stem):
            continue
        candidates.append(path)
        if len(candidates) > 10000:
            raise ValueError('backup-count-limit')
    if not candidates:
        raise ValueError('completed-backup-required')
    path = max(candidates, key=lambda item: item.stem)
    identity, manifest = path.stem, private_json(path)
    stamp = manifest.get('created_at')
    if not isinstance(stamp, (float, int)) or isinstance(stamp, bool) or not math.isfinite(stamp):
        raise ValueError('backup-timestamp')
    if (not 0 <= now - stamp <= config['max_backup_age_seconds'] or manifest.get('schema_version') != 1
            or manifest.get('image') not in config['restore_images']
            or manifest.get('recipient') != config['recipient']
            or not isinstance(manifest.get('contents_sha256'), str)
            or not re.fullmatch('[a-f0-9]{64}', manifest['contents_sha256'])
            or not re.fullmatch('[a-f0-9]{64}', manifest.get('sha256', ''))
            or type(manifest.get('plaintext_bytes')) is not int
            or not 0 < manifest['plaintext_bytes'] <= BACKUP['MAX_DATA']
            or type(manifest.get('entries')) is not int or not 0 < manifest['entries'] <= 100000):
        raise ValueError('fresh-complete-backup-required')
    archive = BACKUP['private_regular'](Path(config['directory']) / (identity + '.tar.age'))
    if not 0 < archive.stat().st_size <= MAX_CIPHER or BACKUP['archive_digest'](archive) != manifest['sha256']:
        raise ValueError('local-ciphertext-mismatch')
    return archive, identity, manifest


def verify(config, credentials, storage):
    archive, identity, manifest = selected_backup(config, time.time())
    required = archive.stat().st_size + manifest['plaintext_bytes'] + 5 * 1024**3 + 2 * 1024**2
    if shutil.disk_usage(WORK).free < required:
        raise ValueError('recovery-storage-reserve')
    cipher = storage.deliver(archive, identity, manifest)
    target = WORK / 'data'
    target.mkdir(mode=0o700)
    process = subprocess.Popen(['/usr/bin/age', '--decrypt', '-i', str(credentials / 'age-identity'), str(cipher)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=CHILD_ENV)
    try:
        BACKUP['extract_private'](process.stdout, target, container_owner=False)
        process.stdout.close()
        if process.wait(timeout=60):
            raise ValueError('decryption-failed')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    if BACKUP['tree_manifest'](target) != {key: manifest[key] for key in ('contents_sha256', 'entries', 'plaintext_bytes')}:
        raise ValueError('restored-manifest-mismatch')
    database = target / 'kuma.db'
    if database.is_symlink() or not database.is_file():
        raise ValueError('restored-database-required')
    # A writable isolated copy lets SQLite include and validate any WAL pages.
    connection = sqlite3.connect('file:' + parse.quote(str(database), safe='/') + '?mode=rw', uri=True, timeout=5)
    try:
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA cache_size=-8192')
        if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('sqlite-integrity')
        for table in ('user', 'monitor', 'heartbeat'):
            if connection.execute('SELECT count(*) FROM sqlite_schema WHERE type=? AND name=?', ('table', table)).fetchone() != (1,):
                raise ValueError('application-schema')
        connection.execute('SELECT count(*) FROM monitor').fetchone()
    finally:
        connection.close()
    if BACKUP['archive_digest'](archive) != manifest['sha256']:
        raise ValueError('backup-changed-during-verification')
    return manifest['created_at']


def main():
    try:
        descriptor = os.open(owned_work() / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        with os.fdopen(descriptor, 'r+b') as lock:
            info = os.fstat(lock.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError('lock-authority')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print('observer recovery already active; existing health is unchanged', file=sys.stderr)
                return 1
            if sys.argv[1:] == ['finalize']:
                if os.environ.get('SERVICE_RESULT') != 'success':
                    publish('failed')
                cleanup()
                return 0
            if sys.argv[1:] != ['verify']:
                raise ValueError('action')
            config = validate(private_json(CONFIG))
            credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
            result = subprocess.run(['/usr/bin/age-keygen', '-y', str(credentials / 'age-identity')],
                                    capture_output=True, timeout=10, check=True, env=CHILD_ENV)
            if result.stdout.decode().strip() != config['recipient']:
                raise ValueError('recovery-identity-mismatch')
            pair = private_json(credentials / 'storage')
            if set(pair) != {'B2_APPLICATION_KEY_ID', 'B2_APPLICATION_KEY'} or any(not isinstance(v, str) or not v for v in pair.values()):
                raise ValueError('storage-profile')
            try:
                cleanup()
                os.environ.update(pair)
                storage = Storage(config)
                backup_at = verify(config, credentials, storage)
            finally:
                for name in pair:
                    os.environ.pop(name, None)
                cleanup()
            now = int(time.time())
            valid_until = int(min(now + 93600, backup_at + config['max_backup_age_seconds']))
            if valid_until <= now:
                raise ValueError('backup-aged-during-verification')
            publish('ok', verified_at=now, backup_at=backup_at, valid_until=valid_until)
            return 0
    except Exception:
        publish('failed')
        print('observer recovery verification failed; no successful restore claim', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
