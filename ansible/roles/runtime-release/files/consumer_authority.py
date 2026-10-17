"""Admit existing shared consumer helpers before directory or file convergence."""
import os
import json
import re
from pathlib import Path
import stat
import sys

DIRECTORY = Path('/usr/local/libexec/ripdpi-consumer')
NAMES = {'firewall_consumer.py', 'amneziawg_consumer.py', 'transport_runtime_transaction.py', 'runtime_build_receipt.py'}


def directory(path, *, private=False):
    for current in [*reversed(path.parents), path]:
        try:
            info = current.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('unsafe helper ancestry')
    if private and stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('unowned private directory')


def main():
    raw = sys.stdin.buffer.read(8193)
    value = json.loads(raw) if raw.strip() else {}
    if not isinstance(value, dict) or set(value) - {'private', 'directories'} or len(raw) > 8192:
        raise ValueError('guard input')
    private = value.get('private', [])
    if not isinstance(private, list) or len(private) > 2:
        raise ValueError('guard input')
    forbidden = {'/', '/etc', '/var', '/var/lib', '/var/lib/ripdpi', '/opt', '/root', '/usr', '/usr/local', '/usr/local/libexec', '/run', '/tmp', '/home'}
    public = value.get('directories', [])
    if not isinstance(public, list) or len(public) > 4:
        raise ValueError('guard input')
    directory(DIRECTORY)
    for raw_path in private + public:
        if (not isinstance(raw_path, str) or raw_path in forbidden
                or re.fullmatch(r'/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+', raw_path) is None
                or str(Path(raw_path)) != raw_path or '..' in Path(raw_path).parts):
            raise ValueError('guard path')
        directory(Path(raw_path), private=raw_path in private)
    for name in NAMES:
        try:
            info = (DIRECTORY / name).lstat()
        except FileNotFoundError:
            continue
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) not in {0o644, 0o755} or info.st_size > 1048576):
            raise ValueError('unsafe helper file')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError):
        print('consumer-helper-authority-refused', file=sys.stderr)
        sys.exit(1)
