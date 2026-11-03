#!/usr/bin/env python3
"""Clean only the admitted scheduled recovery workspace under its lock."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import sys

WORK = Path('/var/lib/observability-kuma-restores/scheduled')
OWNER = b'observability-kuma-recovery-v1\n'


def owned_work(root):
    root = Path(root)
    for path in (root, *root.parents):
        info = path.lstat()
        sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o022 and not sticky):
            raise ValueError('workspace-directory-authority')
    info = root.lstat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('workspace-private-directory')
    descriptor = os.open(root / '.owner', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                or stream.read(65) != OWNER):
            raise ValueError('workspace-authority')
    return root


def cleanup(root):
    root = owned_work(root)
    if set(os.listdir(root)) - {'.owner', '.lock', 'cipher.age', 'data'}:
        raise ValueError('foreign-workspace-material')
    selected = []
    for name in ('cipher.age', 'data'):
        path = root / name
        if not os.path.lexists(path):
            continue
        descendants = [path, *path.rglob('*')] if path.is_dir() and not path.is_symlink() else [path]
        for child in descendants:
            info = child.lstat()
            if (info.st_uid != os.geteuid() or info.st_mode & 0o022
                    or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                    or stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                raise ValueError('workspace-material-authority')
        selected.append(path)
    for path in selected:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return len(selected)


def main():
    root = owned_work(WORK)
    descriptor = os.open(root / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(descriptor, 'r+b') as lock:
        info = os.fstat(lock.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError('lock-authority')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return {'schema_version': 1, 'removed': cleanup(root)}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 1:
            raise ValueError('fixed-cleanup-operation-required')
        print(json.dumps(main()))
    except Exception:
        print('observer recovery cleanup refused', file=sys.stderr)
        raise SystemExit(1) from None
