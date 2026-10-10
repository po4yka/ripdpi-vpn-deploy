"""Private exact-path config rollback; never scan or print credential bytes."""
import argparse
import base64
import json
import hashlib
import os
from pathlib import Path
import stat
import sys

STATE = Path('/var/lib/ripdpi/transport-egress/previous.json')
ACCEPTED = STATE.with_name('accepted.json')
CONFIG = Path('/etc/ripdpi/transport-egress')
UNITS = {'ripdpi-transport-normalizer.service', 'ripdpi-transport-direct.service', 'ripdpi-transport-warp.service', 'ripdpi-transport-generation.service'}
FILES = {'normalizer.json', 'direct.json', 'warp.json', 'generation.json', 'policy.json', 'resolv.conf', 'hosts', 'nsswitch.conf'}
FRONTEND_FILES = {
    Path('/etc/xray/config.json'), Path('/etc/hysteria/config.yaml'),
    Path('/etc/hysteria/server.fullchain.pem'), Path('/etc/hysteria/server.key'),
    Path('/etc/systemd/system/xray.service'), Path('/etc/systemd/system/hysteria-server.service'),
    Path('/usr/local/libexec/vpn-xray-validate'),
    Path('/usr/local/libexec/ripdpi-validate-yaml-mapping'),
    Path('/usr/local/libexec/transport_semantics.py'),
}
WARP_FILES = {
    Path('/etc/systemd/system/warp-svc.service.d/10-ripdpi-namespace.conf'),
    Path('/etc/systemd/system/ripdpi-warp-namespace.service'),
    Path('/etc/systemd/system/ripdpi-warp-refresh.service'),
    Path('/etc/ripdpi/warp-outbound/resolv.conf'),
    Path('/usr/local/libexec/ripdpi-warp/namespace.py'),
}
HELPERS = {'transport_egress_normalizer.py', 'transport_socks.py', 'transport_destination_policy.py', 'transport_private_authority.py', 'generation.py', 'snapshot.py', 'ownership.py', 'policy-loader.py'}


def allowed(path):
    return (path.parent == CONFIG and path.name in FILES
            or path.parent == Path('/etc/systemd/system') and path.name in UNITS
            or path in FRONTEND_FILES or path in WARP_FILES
            or path in {Path('/var/lib/ripdpi/transport-egress/managed.json'), ACCEPTED}
            or path.parent == Path('/usr/local/libexec/ripdpi-transport-egress') and path.name in HELPERS)


def safe(path, missing=False):
    for parent in reversed(path.parents):
        try:
            record = parent.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise ValueError('authority-parent-absent')
        if not stat.S_ISDIR(record.st_mode) or record.st_uid != 0 or record.st_mode & 0o022:
            raise ValueError('authority-parent-invalid')
    try:
        record = path.lstat()
    except FileNotFoundError:
        return None
    limit = 33554432 if path == STATE else 1048576
    if not stat.S_ISREG(record.st_mode) or record.st_uid != 0 or record.st_nlink != 1 or record.st_mode & 0o022 or record.st_size > limit:
        raise ValueError('authority-file-invalid')
    return record


def capture(paths):
    result = {}
    for raw in paths:
        path = Path(raw)
        if not allowed(path):
            raise ValueError('authority-path-invalid')
        record = safe(path, missing=True)
        result[raw] = None if record is None else {'mode': stat.S_IMODE(record.st_mode), 'gid': record.st_gid, 'data': base64.b64encode(path.read_bytes()).decode()}
    return result


def publish(path, content, mode, gid=0):
    safe(path)
    temporary = path.with_name(path.name + '.restore-' + str(os.getpid()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchown(fd, 0, gid)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def managed_paths():
    values = {CONFIG/name for name in FILES} | {Path('/etc/systemd/system')/name for name in UNITS}
    values |= FRONTEND_FILES | WARP_FILES | {Path('/usr/local/libexec/ripdpi-transport-egress')/name for name in HELPERS}
    values.add(Path('/var/lib/ripdpi/transport-egress/managed.json'))
    return sorted(map(str, values))


def fingerprints(snapshot):
    return {path: None if value is None else {'mode': value['mode'], 'gid': value['gid'],
            'sha256': hashlib.sha256(base64.b64decode(value['data'], validate=True)).hexdigest()}
            for path, value in snapshot.items() if path != str(ACCEPTED)}


def accept():
    value = {'schema': 1, 'files': fingerprints(capture(managed_paths()))}
    publish(ACCEPTED, json.dumps(value, sort_keys=True).encode(), 0o600)


def is_accepted(snapshot):
    record = safe(ACCEPTED)
    if record is None or stat.S_IMODE(record.st_mode) != 0o600:
        return False
    receipt = json.loads(ACCEPTED.read_bytes())
    return receipt == {'schema': 1, 'files': fingerprints(snapshot)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['validate', 'capture', 'restore', 'compare', 'inspect'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('authority-requires-root')
    if args.action == 'compare':
        raw = sys.stdin.buffer.read(33554433)
        if len(raw) > 33554432:
            raise ValueError('candidate-oversize')
        candidates = json.loads(raw)
        if not isinstance(candidates, dict) or len(candidates) > 64:
            raise ValueError('candidate-invalid')
        prior = capture(list(candidates))
        for raw, value in candidates.items():
            if not isinstance(value, dict) or set(value) != {'mode', 'gid', 'data'} or value['mode'] not in {0o600, 0o640, 0o644, 0o755} or value['gid'] != 0:
                raise ValueError('candidate-invalid')
            base64.b64decode(value['data'], validate=True)
        print(json.dumps({'changed': candidates != prior}))
        return
    if args.action == 'inspect':
        record = safe(STATE)
        if record is None:
            print(json.dumps({'accepted': False, 'units': []}))
            return
        value = json.loads(STATE.read_bytes())
        if not isinstance(value, dict) or set(value) != {'schema', 'accepted', 'files'} or value['schema'] != 2 or type(value['accepted']) is not bool:
            raise ValueError('rollback-invalid')
        files = value['files']
        accepted = value['accepted']
        units = [name for name in UNITS if files.get('/etc/systemd/system/'+name) is not None]
        # Existing fixed frontend units must be quiesced even before the first
        # guarded receipt. An unaccepted route is never a boot recovery authority.
        units += [name for name in ('xray.service', 'hysteria-server.service')
                  if files.get('/etc/systemd/system/'+name) is not None]
        if accepted:
            old = json.loads(base64.b64decode(files[str(CONFIG/'generation.json')]['data'], validate=True))
            fronts = old.get('frontend_units', [])
            if not isinstance(fronts, list) or set(fronts) - {'xray.service', 'hysteria-server.service'}:
                raise ValueError('rollback-frontends-invalid')
        print(json.dumps({'accepted': accepted, 'units': units}))
        return
    if args.action in {'validate', 'capture'}:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise ValueError('authority-input-oversize')
        paths = json.loads(raw)
        if not isinstance(paths, list) or len(paths) > 64 or len(paths) != len(set(paths)):
            raise ValueError('authority-input-invalid')
        snapshot = capture(paths)
        if args.action == 'capture':
            safe(STATE)
            payload = json.dumps({'schema': 2, 'accepted': is_accepted(snapshot), 'files': snapshot}).encode()
            if len(payload) > 33554432:
                raise ValueError('rollback-oversize')
            publish(STATE, payload, 0o600)
        return
    record = safe(STATE)
    if record is None or stat.S_IMODE(record.st_mode) != 0o600:
        raise ValueError('rollback-absent')
    snapshot = json.loads(STATE.read_bytes())
    if set(snapshot) != {'schema', 'accepted', 'files'} or snapshot['schema'] != 2 or type(snapshot['accepted']) is not bool or not isinstance(snapshot['files'], dict):
        raise ValueError('rollback-invalid')
    capture(list(snapshot['files']))
    decoded = []
    for raw, value in snapshot['files'].items():
        path = Path(raw)
        if value is None:
            decoded.append((path, None))
        elif (isinstance(value, dict) and set(value) == {'mode', 'gid', 'data'}
              and value['mode'] in {0o600, 0o640, 0o644, 0o755}
              and type(value['gid']) is int and 0 <= value['gid'] < 2**32-1):
            decoded.append((path, (base64.b64decode(value['data'], validate=True), value['mode'], value['gid'])))
        else:
            raise ValueError('rollback-invalid')
    for path, value in decoded:
        if value is None:
            path.unlink(missing_ok=True)
        else:
            publish(path, *value)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError):
        print('transport-authority-refused', file=sys.stderr)
        raise SystemExit(1)
