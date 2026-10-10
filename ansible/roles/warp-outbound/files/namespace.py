"""Own exactly one WARP namespace/veth pair; retain vendor registration state."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

STATE = Path('/var/lib/ripdpi/warp-outbound/managed.json')
NAMESPACE = 'ripdpi-warp'
NSFILE = Path('/run/netns') / NAMESPACE
HOST = 'rpd-warp-host'
PEER = 'rpd-warp-ns'
TUNNEL = 'CloudflareWARP'
POLICY = Path('/etc/ripdpi/transport-egress/policy.json')
LOADER = '/usr/local/libexec/ripdpi-transport-egress/policy-loader.py'


class Refusal(ValueError):
    pass


def command(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
    if result.returncode:
        raise Refusal('namespace-command-failed')
    return result.stdout.decode('utf-8', 'strict')


def private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        record = os.fstat(fd)
        if not stat.S_ISREG(record.st_mode) or record.st_uid != 0 or record.st_nlink != 1 or stat.S_IMODE(record.st_mode) != 0o600 or record.st_size > 131072:
            raise Refusal('namespace-record-invalid')
        return json.loads(os.read(fd, 131073))
    finally:
        os.close(fd)


def publish(path, value):
    if path.parent.is_symlink() or path.parent.stat().st_uid != 0 or path.parent.stat().st_mode & 0o022:
        raise Refusal('namespace-parent-invalid')
    if os.path.lexists(path):
        private(path)
    fd, temporary = tempfile.mkstemp(prefix='.namespace-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as target:
            json.dump(value, target, sort_keys=True)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def owner():
    if not os.path.lexists(STATE):
        return None
    value = private(STATE)
    if value == {'schema': 1, 'unit': 'warp-svc.service'}:
        return value
    if not isinstance(value, dict) or set(value) != {'schema', 'unit', 'namespace_inode', 'host_ifindex', 'peer_ifindex'} or value['schema'] != 2 or value['unit'] != 'warp-svc.service':
        raise Refusal('namespace-record-invalid')
    for key in ['namespace_inode', 'host_ifindex', 'peer_ifindex']:
        if value[key] is not None and (type(value[key]) is not int or value[key] <= 0):
            raise Refusal('namespace-record-invalid')
    return value


def link(name, namespace=False):
    argv = ['ip'] + (['-n', NAMESPACE] if namespace else []) + ['-j', '-d', 'link', 'show']
    found = [item for item in json.loads(command(argv)) if item.get('ifname') == name]
    if len(found) > 1:
        raise Refusal('namespace-link-ambiguous')
    return found[0] if found else None


def inspect():
    record = owner()
    if NSFILE.is_symlink():
        raise Refusal('namespace-alias-refused')
    present = NSFILE.exists()
    host = link(HOST) if Path('/sys/class/net', HOST).exists() else None
    if present:
        if record is None or record.get('schema') != 2 or record['namespace_inode'] != NSFILE.stat().st_ino:
            raise Refusal('namespace-unowned')
        peer = link(PEER, True)
        if host is None or peer is None or host.get('linkinfo', {}).get('info_kind') != 'veth' or peer.get('linkinfo', {}).get('info_kind') != 'veth':
            raise Refusal('namespace-veth-invalid')
        if record['host_ifindex'] != host['ifindex'] or record['peer_ifindex'] != peer['ifindex']:
            raise Refusal('namespace-veth-unowned')
    elif host is not None:
        raise Refusal('namespace-veth-unowned')
    return {'present': present, 'record': record}


def prepare():
    state = inspect()
    if state['present']:
        return False
    # A missing namespace may be recreated after reboot only from bounded ownership.
    record = {'schema': 2, 'unit': 'warp-svc.service', 'namespace_inode': None, 'host_ifindex': None, 'peer_ifindex': None}
    if not STATE.parent.exists():
        STATE.parent.mkdir(mode=0o700, parents=True)
    publish(STATE, record)
    created = False
    try:
        command(['ip', 'netns', 'add', NAMESPACE]); created = True
        record['namespace_inode'] = NSFILE.stat().st_ino
        publish(STATE, record)
        command(['ip', 'link', 'add', HOST, 'type', 'veth', 'peer', 'name', PEER])
        record['host_ifindex'] = link(HOST)['ifindex']
        record['peer_ifindex'] = link(PEER)['ifindex']
        publish(STATE, record)
        command(['ip', 'link', 'set', PEER, 'netns', NAMESPACE])
        command(['ip', 'address', 'add', '10.250.254.1/30', 'dev', HOST])
        command(['ip', 'link', 'set', HOST, 'up'])
        command(['ip', '-n', NAMESPACE, 'link', 'set', 'lo', 'up'])
        command(['ip', '-n', NAMESPACE, 'address', 'add', '10.250.254.2/30', 'dev', PEER])
        command(['ip', '-n', NAMESPACE, 'link', 'set', PEER, 'up'])
        command(['ip', '-n', NAMESPACE, 'route', 'add', 'default', 'via', '10.250.254.1'])
        record['peer_ifindex'] = link(PEER, True)['ifindex']
        publish(STATE, record)
        if POLICY.exists():
            policy = private(POLICY)
            if policy.get('warp', {}).get('namespace') != NAMESPACE:
                raise Refusal('namespace-policy-invalid')
            policy['warp']['tunnel_ifindex'] = None
            publish(POLICY, policy)
            command([LOADER, 'apply', '--config', str(POLICY)])
            command([LOADER, 'apply', '--config', str(POLICY), '--namespace', NAMESPACE])
            command([LOADER, 'verify', '--config', str(POLICY)])
            command([LOADER, 'verify', '--config', str(POLICY), '--namespace', NAMESPACE])
        return True
    except (OSError, Refusal, KeyError, TypeError):
        if created:
            command(['ip', 'netns', 'delete', NAMESPACE])
        if link(HOST) is not None:
            command(['ip', 'link', 'delete', HOST])
        raise


def tunnel():
    if not inspect()['present']:
        raise Refusal('namespace-absent')
    value = link(TUNNEL, True)
    if value is None or value.get('linkinfo', {}).get('info_kind') != 'tun' or value.get('linkinfo', {}).get('info_data', {}).get('type') != 'tun' or 'UP' not in value.get('flags', []):
        raise Refusal('namespace-tunnel-not-ready')
    return value['ifindex']


def guard():
    if not inspect()['present']:
        raise Refusal('namespace-absent')
    policy = private(POLICY)
    if policy.get('warp', {}).get('namespace') != NAMESPACE:
        raise Refusal('namespace-policy-invalid')
    changed = policy['warp']['tunnel_ifindex'] is not None
    policy['warp']['tunnel_ifindex'] = None
    if changed:
        publish(POLICY, policy)
    command([LOADER, 'apply', '--config', str(POLICY)])
    command([LOADER, 'apply', '--config', str(POLICY), '--namespace', NAMESPACE])
    command([LOADER, 'verify', '--config', str(POLICY)])
    command([LOADER, 'verify', '--config', str(POLICY), '--namespace', NAMESPACE])
    return changed


def refresh():
    index = tunnel()
    policy = private(POLICY)
    if policy.get('warp', {}).get('namespace') != NAMESPACE:
        raise Refusal('namespace-policy-invalid')
    if policy['warp']['tunnel_ifindex'] != index:
        policy['warp']['tunnel_ifindex'] = index
        publish(POLICY, policy)
    command([LOADER, 'apply', '--config', str(POLICY)])
    command([LOADER, 'apply', '--config', str(POLICY), '--namespace', NAMESPACE])
    command([LOADER, 'verify', '--config', str(POLICY)])
    command([LOADER, 'verify', '--config', str(POLICY), '--namespace', NAMESPACE])
    return index


def retire():
    state = inspect()
    if state['record'] is None:
        return False
    if state['present']:
        inode = NSFILE.stat().st_ino
        for process in Path('/proc').iterdir():
            if process.name.isdecimal():
                try:
                    if (process/'ns/net').stat().st_ino == inode:
                        raise Refusal('namespace-process-still-active')
                except FileNotFoundError:
                    pass
        names = {value['ifname'] for value in json.loads(command(['ip', '-n', NAMESPACE, '-j', 'link', 'show']))}
        if names - {'lo', PEER, TUNNEL}:
            raise Refusal('namespace-foreign-link')
        command(['ip', 'netns', 'delete', NAMESPACE])
        if link(HOST) is not None:
            command(['ip', 'link', 'delete', HOST])
    # Preserve bounded ownership for readmission and whole-route rollback.
    retired = {'schema': 2, 'unit': 'warp-svc.service', 'namespace_inode': None,
               'host_ifindex': None, 'peer_ifindex': None}
    if not state['present'] and state['record'] == retired:
        return False
    publish(STATE, retired)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inspect', 'prepare', 'retire', 'tunnel', 'refresh', 'guard'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refusal('namespace-requires-root')
    result = globals()[args.action]()
    print(json.dumps({'changed': result} if type(result) is bool else {'tunnel_ifindex': result} if type(result) is int else result))


if __name__ == '__main__':
    try:
        main()
    except (OSError, Refusal, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print('warp-namespace-refused', file=sys.stderr)
        raise SystemExit(1)
