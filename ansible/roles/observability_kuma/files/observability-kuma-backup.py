#!/usr/bin/env python3
"""Quiesced encrypted backup and offline restore; never modify the database."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid

DATA = Path('/var/lib/observability-kuma')
RESTORES = Path('/var/lib/observability-kuma-restores')
MAX_DATA = 3 * 1024**3
private_directory = runpy.run_path(str(Path(__file__).with_name('observability-kuma-preflight.py')))['private_directory']


def private_regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('private-file-required')
    return path


def command(argv):
    return subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


def archive_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def backup(config, credentials):
    destination = private_directory(config['directory'])
    if destination.is_symlink() or not destination.is_dir() or destination.stat().st_dev == DATA.stat().st_dev:
        raise ValueError('separate-storage-required')
    if destination.stat().st_uid != 0 or stat.S_IMODE(destination.stat().st_mode) != 0o700:
        raise ValueError('private-storage-required')
    identity = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex
    output = destination / (identity + '.tar.age')
    # Stop the service, not just docker pause: the app must flush SQLite/WAL.
    active = subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', 'observability-kuma.service'], check=False).returncode == 0
    command(['/usr/bin/systemctl', 'stop', 'observability-kuma.service'])
    try:
        descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'wb') as sink:
            tar = subprocess.Popen(['/usr/bin/tar', '-C', str(DATA), '-cf', '-', '.'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                age = subprocess.run(['/usr/bin/age', '-R', str(credentials / 'backup-recipient')], stdin=tar.stdout, stdout=sink, stderr=subprocess.DEVNULL, timeout=300, check=False)
                tar.stdout.close()
                tar_result = tar.wait(timeout=30)
                if age.returncode or tar_result:
                    raise ValueError('encryption-failed')
                sink.flush()
                os.fsync(sink.fileno())
            finally:
                if tar.poll() is None:
                    tar.kill()
                    tar.wait()
        # Manifest preserves the matching pre-upgrade architecture image.
        manifest = {'schema_version': 1, 'image': config['image'], 'sha256': archive_digest(output), 'created_at': time.time()}
        descriptor = os.open(destination / (identity + '.json'), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'w') as sink:
            json.dump(manifest, sink)
            sink.flush()
            os.fsync(sink.fileno())
        print('encrypted backup completed: ' + identity)
    finally:
        if active:
            command(['/usr/bin/systemctl', 'start', 'observability-kuma.service'])


def extract_private(stream, destination):
    total = 0
    count = 0
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for member in archive:
            count += 1
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()) or count > 100000:
                raise ValueError('unsafe-archive-member')
            total += member.size
            if total > MAX_DATA:
                raise ValueError('restore-size-limit')
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as sink, archive.extractfile(member) as source:
                    shutil.copyfileobj(source, sink, 1024 * 1024)
    # Keep every parent root-owned until all writes finish. The restore unit
    # intentionally lacks CAP_DAC_OVERRIDE, so changing a mode-0700 parent to
    # UID 1000 during extraction would prevent later child creation.
    for parent, _directories, files in os.walk(destination, topdown=False):
        for name in files:
            os.chown(Path(parent) / name, 1000, 1000)
        os.chown(parent, 1000, 1000)


def restore(config, credentials, identity):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}', identity):
        raise ValueError('backup-id-required')
    directory = private_directory(config['directory'])
    archive = private_regular(directory / (identity + '.tar.age'))
    manifest = json.loads(private_regular(directory / (identity + '.json')).read_text())
    if manifest['schema_version'] != 1 or archive_digest(archive) != manifest['sha256'] or not re.fullmatch(r'louislam/uptime-kuma@sha256:[a-f0-9]{64}', manifest['image']):
        raise ValueError('archive-integrity')
    private_directory(RESTORES)
    if shutil.disk_usage(RESTORES).free < MAX_DATA + 5 * 1024**3:
        raise ValueError('restore-reserve')
    target = RESTORES / uuid.uuid4().hex
    target.mkdir(mode=0o700)
    process = subprocess.Popen(['/usr/bin/age', '--decrypt', '-i', str(credentials / 'age-identity'), str(archive)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        extract_private(process.stdout, target)
        process.stdout.close()
        if process.wait(timeout=60):
            raise ValueError('decryption-failed')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    name = 'observability-kuma-restore-' + uuid.uuid4().hex
    # Network none prevents all notifications, including native Telegram, even
    # before login. No published port and no simultaneous reachable monitors.
    command(['/usr/bin/docker', 'run', '-d', '--name', name, '--label', 'vpn-deploy.owner=observability-kuma-restore', '--pull=never', '--network', 'none', '--env', 'UPTIME_KUMA_DB_TYPE=sqlite', '--user', '1000:1000', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=67108864', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '536870912', '--memory-swap', '536870912', '--cpus', '0.25', '--pids-limit', '128', '--log-driver', 'none', '--mount', 'type=bind,src=' + str(target) + ',dst=/app/data', manifest['image']])
    try:
        # Upstream healthcheck accepts startup HTTP error pages; require the
        # actual application JSON instead. Local loopback needs no network.
        for attempt in range(30):
            result = subprocess.run(['/usr/bin/docker', 'exec', name, 'node', '-e', "fetch('http://127.0.0.1:3001/api/entry-page').then(async r=>{const j=await r.json();process.exit(r.status===200&&j.type==='entryPage'?0:1)}).catch(()=>process.exit(1))"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
            if result.returncode == 0:
                break
            if attempt == 29:
                raise ValueError('restored-application-not-ready')
            time.sleep(2)
    finally:
        command(['/usr/bin/docker', 'stop', '--time', '30', name])
    print('isolated restore verified; stopped container and dataset retained: ' + name + ' ' + str(target))


def main():
    try:
        os.umask(0o077)
        config = json.loads(private_regular(Path('/etc/observability-kuma/backup.json')).read_text())
        credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
        with open('/run/observability-kuma-lifecycle/lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if sys.argv[1:] == ['backup']:
                backup(config, credentials)
            elif len(sys.argv) == 3 and sys.argv[1] == 'restore':
                restore(config, credentials, sys.argv[2])
            else:
                raise ValueError('action')
        return 0
    except Exception:
        print('observer backup/restore failed; retained data requires inspection', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
