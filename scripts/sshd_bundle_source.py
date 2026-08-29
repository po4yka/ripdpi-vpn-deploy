"""Canonical immutable SSH recovery bundle identity."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat


ROOT = Path(__file__).resolve().parents[1]
NAMES = ('sshd_migrate.py', 'sshd_transaction.py', 'sshd_ownership.py',
         'units/vpn-sshd-boot-recover.service', 'units/vpn-sshd-recover.service',
         'units/vpn-sshd-recover.timer')


class BundleSourceError(ValueError):
    """The local reviewed source bundle is unavailable or unsafe."""


def bundle_manifest():
    source = ROOT / 'ansible/roles/baseline'
    hashes = {}
    for name in NAMES:
        path = source / ('templates' if name.startswith('units/') else 'files') / Path(name).name
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                    or info.st_mode & 0o022 or info.st_size > 256 * 1024):
                raise BundleSourceError('source-file-unsafe')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                content = stream.read(256 * 1024 + 1)
            if len(content) > 256 * 1024:
                raise BundleSourceError('source-file-too-large')
            hashes[name] = hashlib.sha256(content).hexdigest()
        finally:
            os.close(fd)
    manifest = json.dumps({'schema_version': 1, 'files': hashes},
                          sort_keys=True, separators=(',', ':')) + '\n'
    return hashlib.sha256(manifest.encode()).hexdigest(), manifest
