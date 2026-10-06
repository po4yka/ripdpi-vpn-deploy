"""Fixed RAM-only console ingress lease; no authentication or route changes."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from uuid import UUID

STATE = Path('/run/vpn-console-bootstrap')
MAX_BYTES = 262144


class Refusal(ValueError):
    """Categorical refusal; never emit input bytes or child output."""


def command(argv, *, payload=None):
    result = subprocess.run(argv, input=payload, capture_output=True, timeout=15,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
    if result.returncode or len(result.stdout) > MAX_BYTES:
        raise Refusal('console-lease-command-refused')
    return result.stdout


def safe_directory(path, mode, *, create=False):
    if create and not os.path.lexists(path):
        path.mkdir(mode=mode)
        path.chmod(mode)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != mode):
        raise Refusal('console-lease-directory-refused')


def private_read(path):
    safe_directory(path.parent, 0o700)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise Refusal('console-lease-input-refused')
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Refusal('console-lease-input-refused')
    return data


def write_new(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def normalized(document):
    """Keep expressions and ordering; discard only handles and counter values."""
    if not isinstance(document, dict) or set(document) != {'nftables'} or not isinstance(document['nftables'], list):
        raise Refusal('console-lease-policy-refused')
    if any(not isinstance(row, dict) or len(row) != 1 or not isinstance(next(iter(row.values())), dict) for row in document['nftables']):
        raise Refusal('console-lease-policy-refused')
    def clean(value):
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == 'handle':
                    continue
                if key == 'counter' and isinstance(item, dict):
                    item = {name: number for name, number in item.items() if name not in {'packets', 'bytes'}}
                result[key] = clean(item)
            return result
        return value
    entries = [clean(row) for row in document['nftables'] if 'metainfo' not in row]
    identities = {(family, name) for family in ('ip', 'ip6') for name in ('filter', 'nat')}
    inert = [row for row in entries if 'table' in row and (row['table'].get('family'), row['table'].get('name')) in identities]
    remaining = [row for row in entries if row not in inert]
    if (len(inert) == 4 and {(row['table']['family'], row['table']['name']) for row in inert} == identities
            and all(set(row['table']) == {'family', 'name'} for row in inert)
            and not any((next(iter(row.values())).get('family'), next(iter(row.values())).get('table')) in identities for row in remaining)):
        return sorted(inert, key=lambda row: (row['table']['family'], row['table']['name']))+remaining
    return entries


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(request):
    fields = {'schema_version', 'nonce', 'hostname', 'root_filesystem_uuid', 'host_key_sha256',
              'inventory_alias', 'public_address', 'ssh_port', 'public_sources',
              'source_revision', 'deployable_digest', 'expires_at'}
    if set(request) != fields or request['schema_version'] != 1 or type(request['schema_version']) is not int:
        raise Refusal('console-lease-request-refused')
    if not re.fullmatch('[0-9a-f]{32}', request['nonce']):
        raise Refusal('console-lease-request-refused')
    for name, length in [('host_key_sha256', 64), ('source_revision', 40), ('deployable_digest', 64)]:
        if not isinstance(request[name], str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}', request[name]):
            raise Refusal('console-lease-request-refused')
    if type(request['ssh_port']) is not int or not 1 <= request['ssh_port'] <= 65535:
        raise Refusal('console-lease-request-refused')
    for name in ['hostname', 'inventory_alias']:
        if not isinstance(request[name], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', request[name]):
            raise Refusal('console-lease-request-refused')
    if not isinstance(request['root_filesystem_uuid'], str) or str(UUID(request['root_filesystem_uuid'])) != request['root_filesystem_uuid']:
        raise Refusal('console-lease-request-refused')
    if type(request['expires_at']) is not int or not 0 < request['expires_at']-time.time() <= 900:
        raise Refusal('console-lease-expired')
    sources = request['public_sources']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 8 or len(set(sources)) != len(sources):
        raise Refusal('console-lease-sources-refused')
    for value in [request['public_address'], *sources]:
        address = ipaddress.ip_address(value)
        if str(address) != value or address.is_unspecified or address.is_multicast or address.is_loopback or address.is_link_local:
            raise Refusal('console-lease-sources-refused')


def identity(request):
    if command(['hostname']).decode().strip() != request['hostname']:
        raise Refusal('console-lease-identity-refused')
    if command(['findmnt', '-n', '-o', 'UUID', '-T', '/']).decode().strip() != request['root_filesystem_uuid']:
        raise Refusal('console-lease-identity-refused')
    public = Path('/etc/ssh/ssh_host_ed25519_key.pub')
    fields = managed_file(public).split()
    if len(fields) < 2 or fields[0] != b'ssh-ed25519' or hashlib.sha256(base64.b64decode(fields[1], validate=True)).hexdigest() != request['host_key_sha256']:
        raise Refusal('console-lease-identity-refused')


def managed_file(path):
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise Refusal('console-lease-policy-refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise Refusal('console-lease-policy-refused')
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Refusal('console-lease-policy-refused')
    return data


def rule(request, address):
    family = 'ip6' if ':' in address else 'ip'
    return f'insert rule inet filter input {family} saddr {address} tcp dport {request["ssh_port"]} counter accept comment "vpn-console-lease:{request["nonce"]}"\n'


def apply():
    with coordination_lock():
        _apply_locked()


def _apply_locked():
    request = json.loads(private_read(STATE/'request.json'))
    validate(request)
    identity(request)
    main = managed_file(Path('/etc/nftables.conf'))
    if not main.startswith(b'#!/usr/sbin/nft -f\n# Managed by Ansible role `firewall`.'):
        raise Refusal('console-lease-policy-refused')
    before = normalized(json.loads(command(['nft', '-j', 'list', 'ruleset'])))
    before_text = command(['nft', '-s', 'list', 'ruleset'])
    parser = ('import subprocess,sys; subprocess.run(["/usr/sbin/nft","-f","-"],input=sys.stdin.buffer.read(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); subprocess.run(["/usr/sbin/nft","-j","list","ruleset"],check=True)')
    parsed = normalized(json.loads(command(['unshare', '--net', '/usr/bin/python3', '-I', '-B', '-c', parser], payload=before_text)))
    if parsed != before:
        raise Refusal('console-lease-policy-drift')
    marker = 'vpn-console-lease:'+request['nonce']
    if any(row.get('rule', {}).get('comment') == marker for row in before):
        raise Refusal('console-lease-already-present')
    batch = ''.join(rule(request, address) for address in request['public_sources']).encode()
    command(['nft', '-c', '-f', '-'], payload=batch)
    receipt = {'schema_version': 1, 'request': request, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               'monotonic_started': time.monotonic(), 'wall_started': time.time(),
               'monotonic_deadline': time.monotonic()+request['expires_at']-time.time(),
               'before_rules': before, 'before_sha256': digest(before),
               'main_sha256': hashlib.sha256(main).hexdigest(),
               'before_text_b64': base64.b64encode(before_text).decode(), 'request_sha256': digest(request)}
    write_new(STATE/'armed.json', json.dumps(receipt, sort_keys=True).encode())
    remaining = int(min(receipt['monotonic_deadline']-time.monotonic(), request['expires_at']-time.time()))
    # The complete scheduling and nft command budget must fit before expiry.
    if remaining < 60:
        raise Refusal('console-lease-expired')
    command(['systemd-run', '--quiet', '--unit=vpn-console-expiry-'+request['nonce'],
             '--on-active='+str(remaining)+'s', '--on-calendar=@'+str(request['expires_at']), '--timer-property=AccuracySec=1s',
             '/usr/bin/python3', '-I', '-B', str(STATE/'guest.py'), 'revoke'])
    if receipt['monotonic_deadline']-time.monotonic() < 30 or request['expires_at']-time.time() < 30:
        raise Refusal('console-lease-expired')
    command(['nft', '-f', '-'], payload=batch)
    after = normalized(json.loads(command(['nft', '-j', 'list', 'ruleset'])))
    owned = [row['rule'] for row in after if row.get('rule', {}).get('comment') == marker]
    if len(owned) != len(request['public_sources']):
        raise Refusal('console-lease-apply-refused')
    receipt.update(leased_rules=owned, leased_sha256=digest(after))
    write_new(STATE/'receipt.json', json.dumps(receipt, sort_keys=True).encode())


@contextmanager
def coordination_lock():
    safe_directory(STATE, 0o700)
    fd = os.open(STATE/'coordination.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            raise Refusal('console-lease-lock-refused')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def revoke():
    # Share the RAM lock with policy replacement, preventing handle reuse races.
    with coordination_lock():
        _revoke_locked()


def _revoke_locked():
    # Armed state is enough to remove exact request rules after a lost reply.
    receipt = json.loads(private_read(STATE/'armed.json'))
    request = receipt['request']
    marker = 'vpn-console-lease:'+request['nonce']
    document = json.loads(command(['nft', '-j', 'list', 'chain', 'inet', 'filter', 'input']))
    owned = [row['rule'] for row in document['nftables'] if row.get('rule', {}).get('comment') == marker]
    deletes = []
    for entry in owned:
        expressions = entry['expr']
        matches = [item['match'] for item in expressions if 'match' in item]
        counters = [item for item in expressions if 'counter' in item]
        if (entry.get('family') != 'inet' or entry.get('table') != 'filter' or entry.get('chain') != 'input'
                or len(expressions) != 4 or len(matches) != 2 or len(counters) != 1 or expressions[-1] != {'accept': None}
                or matches[0].get('op') != '==' or matches[0].get('right') not in request['public_sources']
                or matches[0].get('left') != {'payload': {'protocol': 'ip6' if ':' in matches[0]['right'] else 'ip', 'field': 'saddr'}}
                or matches[1] != {'op': '==', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}}, 'right': request['ssh_port']}
                or type(entry.get('handle')) is not int):
            raise Refusal('console-lease-rule-drift')
        deletes.append(f'delete rule inet filter input handle {entry["handle"]}\n')
    if deletes:
        # Validate every rule before one atomic deletion; never partially retire.
        command(['nft', '-f', '-'], payload=''.join(deletes).encode())
    print('console ingress lease removed', flush=True)


def boot(request, source):
    validate(request)
    if os.geteuid() != 0 or command(['stat', '-f', '-c', '%T', '/run']).decode().strip() != 'tmpfs':
        raise Refusal('console-lease-boot-refused')
    if not os.statvfs('/').f_flag & os.ST_RDONLY:
        raise Refusal('console-lease-boot-refused')
    safe_directory(Path('/run'), 0o755)
    # Systemd/networkd share these parents; a private umask must never hide them.
    for path in [Path('/run/systemd'), Path('/run/systemd/system'), Path('/run/systemd/system/multi-user.target.wants')]:
        safe_directory(path, 0o755, create=True)
    safe_directory(STATE, 0o700, create=True)
    write_new(STATE/'coordination.lock', b'')
    write_new(STATE/'request.json', json.dumps(request, sort_keys=True).encode())
    write_new(STATE/'guest.py', source.encode())
    unit = ('[Unit]\nDescription=Bounded console SSH ingress\nRequires=nftables.service\nAfter=nftables.service\nBefore=ssh.service\n'
            '[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I -B '+str(STATE/'guest.py')+' apply\n')
    path = Path('/run/systemd/system/vpn-console-bootstrap.service')
    write_new(path, unit.encode())
    os.symlink('../'+path.name, path.parent/'multi-user.target.wants'/path.name)
    print('RAM-only console ingress prepared; return to ordinary init', flush=True)


if __name__ == '__main__':
    import sys
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {'apply', 'revoke'}:
            raise Refusal('console-lease-command-refused')
        {'apply': apply, 'revoke': revoke}[sys.argv[1]]()
    except (Refusal, OSError, ValueError, KeyError, TypeError, UnicodeError):
        print('console ingress lease refused', file=sys.stderr)
        raise SystemExit(1) from None
