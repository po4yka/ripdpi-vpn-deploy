"""Bounded private ownership of exact egress units; no prefix discovery."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

STATE = Path('/var/lib/ripdpi/transport-egress/managed.json')
UNITS = {'ripdpi-transport-normalizer.service', 'ripdpi-transport-direct.service', 'ripdpi-transport-warp.service', 'ripdpi-transport-generation.service'}


def read():
    if not os.path.lexists(STATE):
        if any((Path('/etc/systemd/system') / name).exists() for name in UNITS):
            raise ValueError('unclaimed-egress-unit')
        return {'schema': 1, 'units': []}
    fd = os.open(STATE, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096:
            raise ValueError('invalid-egress-ownership')
        value = json.loads(os.read(fd, 4097))
    finally:
        os.close(fd)
    if set(value) != {'schema', 'units'} or value['schema'] != 1 or not isinstance(value['units'], list) or len(set(value['units'])) != len(value['units']) or set(value['units']) - UNITS:
        raise ValueError('invalid-egress-ownership')
    return value


def claim(units):
    prior = read()
    if not isinstance(units, list) or set(units) - UNITS:
        raise ValueError('invalid-egress-claim')
    value = {'schema': 1, 'units': sorted(set(prior['units']) | set(units))}
    fd, path = tempfile.mkstemp(prefix='.ownership-', dir=STATE.parent)
    try:
        with os.fdopen(fd, 'w') as target:
            json.dump(value, target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(path, STATE)
    finally:
        if os.path.exists(path):
            os.unlink(path)
    return value


def stop_units():
    """A durable claim can precede publication or outlive compensation."""
    value = read()
    selected = []
    for unit in value['units']:
        result = subprocess.run(['systemctl', 'show', unit,
            '--property=LoadState,ActiveState,MainPID'], check=True,
            capture_output=True, text=True, timeout=10)
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines())
        if set(fields) != {'LoadState', 'ActiveState', 'MainPID'}:
            raise ValueError('invalid-egress-unit-state')
        if fields != {'LoadState': 'not-found', 'ActiveState': 'inactive', 'MainPID': '0'}:
            selected.append(unit)
    return {'schema': 1, 'units': selected}


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['claim']:
            raw = sys.stdin.buffer.read(4097)
            if len(raw) > 4096:
                raise ValueError('oversized-claim')
            result = claim(json.loads(raw))
        elif sys.argv[1:] == ['stop-units']:
            result = stop_units()
        elif not sys.argv[1:]:
            result = read()
        else:
            raise ValueError('invalid-command')
        print(json.dumps(result))
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print('transport-ownership-refused', file=sys.stderr)
        raise SystemExit(1)
