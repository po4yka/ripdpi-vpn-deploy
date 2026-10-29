#!/usr/bin/env python3
"""Retain the exact firewall generation until its declared consumer commits."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
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


def policy(value):
    """Compare all definitions and ordered chain rules, without kernel counters."""
    def stable(value):
        if isinstance(value, list):
            return [stable(item) for item in value]
        if isinstance(value, dict):
            result = {key: stable(item) for key, item in value.items() if key != 'handle'}
            if 'counter' in result and isinstance(result['counter'], dict):
                result['counter'] = {key: item for key, item in result['counter'].items() if key not in {'packets', 'bytes'}}
            if set(result) == {'set'} and isinstance(result['set'], list):
                result['set'].sort(key=lambda item: json.dumps(item, sort_keys=True))
            if 'val' in result and type(result.get('expires')) is int:
                # Elapsed lifetime changes between reads; the native patch
                # never recreates the set or resets an element's timeout.
                del result['expires']
            return result
        return value
    definitions, rules = [], {}
    for row in value['nftables']:
        if 'metainfo' in row:
            continue
        row = stable(row)
        kind, item = next(iter(row.items()))
        if kind == 'rule':
            key = json.dumps([item['family'], item['table'], item['chain']])
            rules.setdefault(key, []).append(row)
        else:
            if kind in {'set', 'map'} and isinstance(item.get('elem'), list):
                item['elem'].sort(key=lambda member: json.dumps(member, sort_keys=True))
            definitions.append(row)
    return {'definitions': sorted(definitions, key=lambda item: json.dumps(item, sort_keys=True)), 'rules': rules}


def live_policy():
    raw = command(['nft', '-j', 'list', 'ruleset'])
    if len(raw) > 1048576:
        raise Refusal('firewall-policy-oversize')
    return json.loads(raw)


def rotation_plan(value):
    bound = {key: item for key, item in value.items() if key not in {'phase', 'checksum'}}
    return hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()


def seal_rotation(value):
    bound = {key: item for key, item in value.items() if key != 'checksum'}
    return {**bound, 'checksum': hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()}


def rotation(tx):
    value = read_private(STATE / 'ssh-rotation.json', tx.uid)
    if value is not None:
        if (not isinstance(value, dict) or set(value) != {'schema', 'phase', 'before', 'after', 'rule_before', 'rule_after', 'policy_before', 'policy_after', 'accepted_before', 'checksum'}
                or type(value['schema']) is not int or value['schema'] != 1 or value['phase'] not in {'prepared', 'committing'}
                or value != seal_rotation(value)):
            raise Refusal('firewall-ssh-rotation-invalid')
        validate_receipt(value['accepted_before'], root=STATE, uid=tx.uid)
    return value


class SSHRotation(Firewall):
    """Use the same single-rule operation for activation and compensation."""
    def __init__(self, value):
        super().__init__([{'data': value['after']}])
        self.value = value
        self.side = 'after'

    def current(self):
        raw = live_policy()
        observed = policy(raw)
        if observed not in (self.value['policy_before'], self.value['policy_after']):
            raise Refusal('firewall-ssh-foreign-policy')
        return raw, observed

    def validate(self):
        self.current()
        super().validate()

    def select(self, side):
        raw, observed = self.current()
        desired = self.value['policy_' + side]
        if observed == desired:
            return
        prior = self.value['rule_after' if side == 'before' else 'rule_before']
        candidates = [row['rule'] for row in raw['nftables'] if 'rule' in row
                      and {key: item for key, item in row['rule'].items() if key != 'handle'} == prior]
        if len(candidates) != 1 or type(candidates[0].get('handle')) is not int:
            raise Refusal('firewall-ssh-rule-identity')
        replacement = {**self.value['rule_' + side], 'handle': candidates[0]['handle']}
        command(['nft', '-j', '-f', '-'], data=json.dumps({'nftables': [{'replace': {'rule': replacement}}]}).encode())
        if policy(live_policy()) != desired:
            raise Refusal('firewall-ssh-replacement-unconfirmed')

    def start(self):
        self.side = 'after'
        self.select('after')

    def ready(self):
        if CONFIG.read_bytes() != base64.b64decode(self.value[self.side], validate=True) or policy(live_policy()) != self.value['policy_' + self.side]:
            raise Refusal('firewall-ssh-candidate-unconfirmed')

    def restore(self, units):
        self.side = 'before'
        self.select('before')


def rotate_ssh(tx, payload, check):
    value = rotation(tx)
    if value is None:
        if marker(tx) is not None or any(os.path.lexists(STATE / name) for name in
                ('pending.json', 'preparation.json', 'compensating.json', 'outer.json', 'revocation.json')):
            raise Refusal('firewall-ssh-recovery-required')
        accepted = tx.accepted()
        if accepted is None or set(accepted['nodes']) != {str(CONFIG)}:
            raise Refusal('firewall-ssh-accepted-authority-required')
        metadata = accepted['nodes'][str(CONFIG)]
        if 'sha256' not in metadata or metadata['identity'][3:] != [os.getgid(), 0o644]:
            raise Refusal('firewall-ssh-config-metadata')
        old, new = payload['old_source'], payload['new_source']
        for address in (old, new):
            if not isinstance(address, str) or str(ipaddress.IPv4Address(address)) != address or not ipaddress.IPv4Address(address).is_global:
                raise Refusal('firewall-ssh-source-invalid')
        port = payload['port']
        if old == new or type(port) is not int or not 1 <= port <= 65535:
            raise Refusal('firewall-ssh-source-invalid')
        before = CONFIG.read_bytes()
        if not before.startswith(HEADER) or before.count(old.encode()) != 1 or new.encode() in before:
            raise Refusal('firewall-ssh-source-count')
        lines = [line for line in before.splitlines() if old.encode() in line]
        matched = re.fullmatch(rb'\s*tcp dport ' + str(port).encode() + rb' ip saddr (\{[^}]+\}|[0-9./]+) accept\s*', lines[0]) if len(lines) == 1 else None
        if matched is None:
            raise Refusal('firewall-ssh-durable-rule-invalid')
        durable_sources = []
        for item in matched[1].decode().strip('{} ').split(','):
            address = ipaddress.IPv4Interface(item.strip())
            if address.network.prefixlen != 32:
                raise Refusal('firewall-ssh-durable-rule-invalid')
            durable_sources.append(str(address.ip))
        raw = live_policy()
        selected = [row['rule'] for row in raw['nftables'] if 'rule' in row and old in json.dumps(row['rule'])]
        if len(selected) != 1:
            raise Refusal('firewall-ssh-rule-count')
        prior = {key: item for key, item in selected[0].items() if key != 'handle'}
        expr = prior.get('expr', [])
        port_match = {'match': {'op': '==', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}}, 'right': port}}
        source = [item['match'] for item in expr if item.get('match', {}).get('left') == {'payload': {'protocol': 'ip', 'field': 'saddr'}}]
        if ((prior.get('family'), prior.get('table'), prior.get('chain')) != ('inet', 'filter', 'input')
                or len(expr) != 3 or port_match not in expr or expr[-1] != {'accept': None}
                or len(source) != 1 or source[0].get('op') != '=='):
            raise Refusal('firewall-ssh-rule-invalid')
        right = source[0]['right']
        if not (right == old or isinstance(right, dict) and set(right) == {'set'} and isinstance(right['set'], list)
                and right['set'].count(old) == 1 and all(isinstance(item, str) for item in right['set'])):
            raise Refusal('firewall-ssh-source-invalid')
        if sorted(durable_sources) != sorted([right] if isinstance(right, str) else right['set']):
            raise Refusal('firewall-ssh-durable-runtime-mismatch')
        after = copy.deepcopy(prior)
        for item in after['expr']:
            match = item.get('match', {})
            if match.get('left') == {'payload': {'protocol': 'ip', 'field': 'saddr'}}:
                match['right'] = new if right == old else {'set': [new if item == old else item for item in right['set']]}
        expected = copy.deepcopy(raw)
        for row in expected['nftables']:
            if row.get('rule') == selected[0]:
                row['rule'] = after
        value = {'schema': 1, 'phase': 'prepared', 'before': base64.b64encode(before).decode(),
                 'after': base64.b64encode(before.replace(old.encode(), new.encode())).decode(),
                 'rule_before': prior, 'rule_after': after, 'policy_before': policy(raw),
                 'policy_after': policy(expected), 'accepted_before': accepted}
        value = seal_rotation(value)
        if len(json.dumps(value).encode()) > 1048576:
            raise Refusal('firewall-ssh-intent-oversize')
        SSHRotation(value).validate()
        if check:
            return {'changed': True, 'plan': rotation_plan(value)}
        if payload.get('plan') != rotation_plan(value):
            raise Refusal('firewall-ssh-reviewed-plan-changed')
        tx.record('ssh-rotation.json', value)
    elif payload.get('plan') != rotation_plan(value) or value['phase'] != 'prepared':
        raise Refusal('firewall-ssh-recovery-required')
    current = marker(tx)
    if current is None:
        if tx.accepted() != value['accepted_before']:
            raise Refusal('firewall-ssh-owner-changed')
        if not check:
            tx.record('consumer.json', {'schema': 1, 'owner': 'site', 'before': value['accepted_before']})
    elif current != {'schema': 1, 'owner': 'site', 'before': value['accepted_before']}:
        raise Refusal('firewall-ssh-owner-changed')
    candidates = [{'path': str(CONFIG), 'data': value['after'], 'gid': os.getgid(), 'mode': 0o644}]
    return tx.apply(candidates, SSHRotation(value), check=check)


def marker(tx):
    value = read_private(STATE / 'consumer.json', tx.uid)
    if value is not None:
        if not isinstance(value, dict) or set(value) != {'schema', 'owner', 'before'} or value['schema'] != 1 or value['owner'] not in {'site', 'awg'}:
            raise Refusal('firewall-consumer-invalid')
        if value['before'] is not None:
            validate_receipt(value['before'], root=STATE, uid=tx.uid)
    return value


def restore(tx, owner):
    ssh = rotation(tx)
    if ssh is not None and ssh['phase'] == 'committing':
        raise Refusal('firewall-commit-recovery-required')
    value = marker(tx)
    if value is None:
        if ssh is not None:
            if (any(os.path.lexists(STATE / name) for name in ('pending.json', 'preparation.json', 'compensating.json', 'outer.json', 'revocation.json'))
                    or tx.accepted() != ssh['accepted_before'] or policy(live_policy()) != ssh['policy_before']):
                raise Refusal('firewall-ssh-owner-changed')
            (STATE / 'ssh-rotation.json').unlink()
            sync(STATE)
        return False
    if value['owner'] != owner:
        raise Refusal('firewall-consumer-owner-mismatch')
    tx.refuse_revocation_rollback()
    if owner == 'site':
        ingress = read_private(Path('/var/lib/vpn-nginx-publication/nginx.service/site.json'), tx.uid)
        if isinstance(ingress, dict) and ingress.get('phase') == 'committing':
            raise Refusal('firewall-commit-recovery-required')
    adapter = SSHRotation(ssh) if ssh is not None else Firewall([])
    if ssh is not None:
        if value['before'] != ssh['accepted_before'] or CONFIG.read_bytes() not in (base64.b64decode(ssh['before']), base64.b64decode(ssh['after'])):
            raise Refusal('firewall-ssh-owner-changed')
        adapter.current()
    tx.recover(adapter)
    current = tx.accepted()
    if current != value['before']:
        last = read_private(STATE / 'last.json', tx.uid)
        if last is None or last['before_receipt'] != value['before'] or last['after_receipt'] != current:
            raise Refusal('firewall-consumer-restore-unconfirmed')
        tx.compensate_latest(adapter)
    (STATE / 'consumer.json').unlink()
    if ssh is not None:
        (STATE / 'ssh-rotation.json').unlink()
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
        ssh = rotation(tx)
        if action == 'status':
            return {'owner': None if value is None else value['owner']}
        tx.revocation_state()
        if ssh is not None and action not in {'rotate-ssh', 'restore', 'finish'}:
            raise Refusal('firewall-ssh-recovery-required')
        if action == 'rotate-ssh':
            if owner != 'site':
                raise Refusal('firewall-ssh-owner-invalid')
            return rotate_ssh(tx, payload, check)
        if action == 'restore':
            if check:
                if value is not None:
                    raise Refusal('firewall-consumer-recovery-required')
                return {'changed': False}
            return {'changed': restore(tx, owner)}
        if action == 'finish':
            if ssh is not None:
                if owner != 'site' or any(os.path.lexists(STATE / name) for name in ('pending.json', 'preparation.json', 'compensating.json', 'outer.json', 'revocation.json')):
                    raise Refusal('firewall-ssh-recovery-required')
                accepted = tx.accepted()
                last = read_private(STATE / 'last.json', tx.uid)
                if (last is None or last['before_receipt'] != ssh['accepted_before'] or last['after_receipt'] != accepted
                        or value is not None and value != {'schema': 1, 'owner': 'site', 'before': ssh['accepted_before']}):
                    raise Refusal('firewall-ssh-owner-changed')
                SSHRotation(ssh).ready()
                tx.record('ssh-rotation.json', seal_rotation({**ssh, 'phase': 'committing'}))
            if value is not None:
                if value['owner'] != owner or tx.journal() is not None or tx.preparation() is not None:
                    raise Refusal('firewall-consumer-unconfirmed')
                tx.accepted()
                (STATE / 'consumer.json').unlink()
                sync(STATE)
            if ssh is not None:
                (STATE / 'ssh-rotation.json').unlink()
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
    parser.add_argument('action', choices=['accepted-awg', 'apply', 'rotate-ssh', 'restore', 'finish', 'status'])
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
