#!/usr/bin/env python3
"""Retain the exact firewall generation until its declared consumer commits."""
from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from transport_runtime_transaction import Transaction, Refusal, node, read_private, sync, validate_receipt

STATE = Path('/var/lib/ripdpi/firewall-runtime')
CONFIG = Path('/etc/nftables.conf')
AWG_RECORD = Path('/var/lib/ripdpi/amneziawg/instances.json')
HEADER = b'#!/usr/sbin/nft -f\n# Managed by Ansible role `firewall`. Hand edits will be overwritten.\n'


def command(argv, *, data=None):
    result = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode:
        raise Refusal('firewall-consumer-command-failed')
    return result.stdout


def accepted_awg():
    with Transaction(AWG_RECORD.parent, uid=os.geteuid(), check=True) as tx:
        record = read_private(AWG_RECORD, tx.uid) if tx.state_fd is not None else None
        if record is None:
            if Path('/etc/systemd/system/awg-quick@.service').exists():
                raise Refusal('awg-unrecorded-authority')
            return []
        if (not isinstance(record, dict) or set(record) != {'schema', 'config_dir', 'instances'}
                or record['schema'] != 1 or type(record['schema']) is not int
                or not isinstance(record['instances'], list) or len(record['instances']) > 32
                or len(set(record['instances'])) != len(record['instances'])
                or any(not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}', name) is None for name in record['instances'])):
            raise Refusal('awg-owned-policy-invalid')
        directory = Path(record['config_dir'])
        if not directory.is_absolute() or str(directory) != record['config_dir'] or '..' in directory.parts:
            raise Refusal('awg-owned-policy-invalid')
        tx.parent(directory)
        instances = []
        for name in record['instances']:
            path = directory / (name + '.conf')
            observed = node(path, tx.uid)
            if observed is None or observed['identity'][4] != 0o600 or 'sha256' not in observed:
                raise Refusal('awg-owned-policy-invalid')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'r', encoding='utf-8') as source:
                text = source.read(1048577)
            if node(path, tx.uid) != observed:
                raise Refusal('awg-owned-policy-changed')
            section, port, peers = None, None, []
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                if line in {'[Interface]', '[Peer]'}:
                    section = line
                    if section == '[Peer]':
                        peers.append({})
                    continue
                if '=' not in line or section is None:
                    raise Refusal('awg-owned-policy-invalid')
                key, value = [part.strip() for part in line.split('=', 1)]
                if key == 'ListenPort':
                    if section != '[Interface]' or port is not None or not value.isdecimal() or not 1 <= int(value) <= 65535:
                        raise Refusal('awg-owned-policy-invalid')
                    port = int(value)
                elif key == 'AllowedIPs':
                    if section != '[Peer]' or peers[-1]:
                        raise Refusal('awg-owned-policy-invalid')
                    claims = {}
                    for value in value.split(','):
                        network = ipaddress.ip_network(value.strip(), strict=True)
                        family = 'ipv4' if network.version == 4 else 'ipv6'
                        if family in claims:
                            raise Refusal('awg-owned-policy-invalid')
                        claims[family] = str(network)
                    peers[-1] = {'allowed_ips': claims}
            if port is None or any(not peer for peer in peers):
                raise Refusal('awg-owned-policy-invalid')
            instances.append({'name': name, 'listen_port': port, 'peers': peers})
        return instances


class Firewall:
    def __init__(self, candidates):
        self.candidates = candidates

    def validate(self):
        command(['nft', '-c', '-f', '-'], data=base64.b64decode(self.candidates[0]['data'], validate=True))

    def validate_units(self, value):
        if value != {}:
            raise Refusal('firewall-unit-state-invalid')

    def inspect(self):
        return {}

    def retained(self, receipt):
        pass

    def stop(self):
        pass  # Never stop nftables: the distro stop action flushes the ruleset.

    def start(self):
        command(['nft', '-f', str(CONFIG)])

    def ready(self):
        command(['nft', '-c', '-f', str(CONFIG)])

    def ensure(self):
        return False

    def restore(self, units):
        self.start()


def marker(tx):
    value = read_private(STATE / 'consumer.json', tx.uid)
    if value is not None:
        if not isinstance(value, dict) or set(value) != {'schema', 'owner', 'before'} or value['schema'] != 1 or value['owner'] not in {'site', 'awg'}:
            raise Refusal('firewall-consumer-invalid')
        if value['before'] is not None:
            validate_receipt(value['before'], root=STATE, uid=tx.uid)
    return value


def restore(tx, owner):
    value = marker(tx)
    if value is None:
        return False
    if value['owner'] != owner:
        raise Refusal('firewall-consumer-owner-mismatch')
    tx.refuse_revocation_rollback()
    if owner == 'site':
        ingress = read_private(Path('/var/lib/vpn-nginx-publication/nginx.service/site.json'), tx.uid)
        if isinstance(ingress, dict) and ingress.get('phase') == 'committing':
            raise Refusal('firewall-commit-recovery-required')
    adapter = Firewall([])
    tx.recover(adapter)
    current = tx.accepted()
    if current != value['before']:
        last = read_private(STATE / 'last.json', tx.uid)
        if last is None or last['before_receipt'] != value['before'] or last['after_receipt'] != current:
            raise Refusal('firewall-consumer-restore-unconfirmed')
        tx.compensate_latest(adapter)
    (STATE / 'consumer.json').unlink()
    sync(STATE)
    return True


def operate(action, payload):
    owner = payload.get('owner', 'site')
    if owner not in {'site', 'awg'}:
        raise Refusal('firewall-consumer-owner-invalid')
    check = action == 'status' or payload.get('check', False)
    if type(check) is not bool:
        raise Refusal('firewall-check-invalid')
    with Transaction(STATE, uid=os.geteuid(), check=check or (action in {'restore', 'status'} and not STATE.exists()),
                     revocation=payload.get('revocation')) as tx:
        if tx.state_fd is None:
            return {'owner': None} if action == 'status' else {'changed': action == 'apply'}
        value = marker(tx)
        if action == 'status':
            return {'owner': None if value is None else value['owner']}
        tx.revocation_state()
        if action == 'restore':
            if check:
                if value is not None:
                    raise Refusal('firewall-consumer-recovery-required')
                return {'changed': False}
            return {'changed': restore(tx, owner)}
        if action == 'finish':
            if value is not None:
                if value['owner'] != owner or tx.journal() is not None or tx.preparation() is not None:
                    raise Refusal('firewall-consumer-unconfirmed')
                tx.accepted()
                (STATE / 'consumer.json').unlink()
                sync(STATE)
            return {'changed': False}
        raw = base64.b64decode(payload['data'], validate=True)
        if not raw.startswith(HEADER) or len(raw) > 1048576 or re.search(rb'(?m)^\s*flush\s+ruleset(?:;|\s|$)', raw):
            raise Refusal('firewall-candidate-invalid')
        if payload.get('allow_listener_change', True) is not True and CONFIG.exists():
            pattern = rb'(?m)^    # Public listener contract:.*$'
            if re.findall(pattern, CONFIG.read_bytes()) != re.findall(pattern, raw):
                raise Refusal('firewall-protected-consumer-required')
        candidates = [{'path': str(CONFIG), 'data': payload['data'], 'gid': os.getgid(), 'mode': 0o644}]
        adapter = Firewall(candidates)
        if value is not None:
            fence = tx.revocation_state()
            if fence is None or fence['authority'] != tx.revocation or value['owner'] != owner:
                raise Refusal('firewall-consumer-recovery-required')
        if not check and value is None and tx.accepted() is None:
            old = node(CONFIG, tx.uid)
            if old is not None:
                tx.parent(CONFIG.parent)
                prior = CONFIG.read_bytes()
                if prior.startswith(HEADER) and not re.search(rb'(?m)^\s*flush\s+ruleset(?:;|\s|$)', prior):
                    command(['nft', '-c', '-f', '-'], data=prior)
                    tx.record('accepted.json', {'schema': 1, 'nodes': {str(CONFIG): old}, 'previous': None, 'units': {}})
                else:
                    # Never adopt the provider-image global-flush starter as
                    # recovery authority. Only the reviewed AWG-off baseline
                    # may replace it before the first retained transaction.
                    baseline = base64.b64decode(payload['baseline'], validate=True)
                    if not baseline.startswith(HEADER) or re.search(rb'(?m)^\s*flush\s+ruleset(?:;|\s|$)', baseline):
                        raise Refusal('firewall-bootstrap-invalid')
                    command(['nft', '-c', '-f', '-'], data=baseline)
                    fd, temporary = tempfile.mkstemp(prefix='.vpn-firewall-', dir=CONFIG.parent)
                    try:
                        with os.fdopen(fd, 'wb') as stream:
                            stream.write(baseline)
                            stream.flush()
                            os.fsync(stream.fileno())
                            os.fchmod(stream.fileno(), 0o644)
                        if node(CONFIG, tx.uid) != old:
                            raise Refusal('firewall-bootstrap-changed')
                        os.replace(temporary, CONFIG)
                        sync(CONFIG.parent)
                    finally:
                        if os.path.lexists(temporary):
                            os.unlink(temporary)
                    command(['nft', '-f', str(CONFIG)])
                    tx.record('accepted.json', {'schema': 1, 'nodes': {str(CONFIG): node(CONFIG, tx.uid)}, 'previous': None, 'units': {}})
        if not check and value is None:
            tx.record('consumer.json', {'schema': 1, 'owner': owner, 'before': tx.accepted()})
        return tx.apply(candidates, adapter, check=check)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['accepted-awg', 'apply', 'restore', 'finish', 'status'])
    parser.add_argument('--owner', choices=['site', 'awg'], default='site')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refusal('root-required')
    if args.action == 'accepted-awg':
        value = accepted_awg()
    else:
        raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1) if args.action not in {'finish', 'status'} else b''
        if len(raw) > 4 * 1024 * 1024:
            raise Refusal('firewall-input-oversize')
        value = operate(args.action, {'owner': args.owner} if args.action in {'finish', 'status'} else json.loads(raw))
    print(json.dumps(value, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, Refusal, subprocess.SubprocessError):
        print('firewall-consumer-refused', file=sys.stderr)
        raise SystemExit(1)
