#!/usr/bin/env python3
"""Accept one complete AWG executable, unit and configuration generation."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from transport_runtime_transaction import Transaction, Refusal, TrustedDirectory, read_private, validate_receipt, admission
from firewall_consumer import operate as firewall

STATE = Path('/var/lib/ripdpi/amneziawg/runtime')
RECORD = Path('/var/lib/ripdpi/amneziawg/instances.json')
BINARIES = {'/usr/local/bin/amneziawg-go', '/usr/bin/awg', '/usr/bin/awg-quick'}
SHARED = {'/etc/systemd/system/awg-quick@.service', '/etc/systemd/system/awg-quick.target'}
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}')


def names(value):
    if (not isinstance(value, dict) or set(value) != {'schema', 'config_dir', 'instances'}
            or value['schema'] != 1 or type(value['schema']) is not int
            or not isinstance(value['config_dir'], str)
            or not Path(value['config_dir']).is_absolute() or str(Path(value['config_dir'])) != value['config_dir']
            or '..' in Path(value['config_dir']).parts
            or re.fullmatch(r'/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+', value['config_dir']) is None
            or any(part in {'.', '..'} for part in Path(value['config_dir']).parts)
            or not isinstance(value['instances'], list)
            or len(value['instances']) > 32 or any(not isinstance(item, str) or NAME.fullmatch(item) is None for item in value['instances'])
            or len(set(value['instances'])) != len(value['instances'])):
        raise Refusal('awg-membership-invalid')
    return value['instances']


def record():
    value = read_private(RECORD, os.geteuid())
    if value is None:
        return {'schema': 1, 'config_dir': '/etc/amnezia/amneziawg', 'instances': []}
    names(value)
    return value


def run(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode:
        raise Refusal('awg-consumer-command-failed')
    return result.stdout.decode('utf-8', 'strict')


def fields(unit):
    result = subprocess.run(['systemctl', 'show', unit, '--property=LoadState,ActiveState,UnitFileState,MainPID'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
    if values.get('LoadState') == 'not-found':
        values['UnitFileState'] = ''
    # Target units have no service process and do not expose MainPID.
    if unit == 'awg-quick.target' and 'MainPID' not in values:
        values['MainPID'] = '0'
    if set(values) != {'LoadState', 'ActiveState', 'UnitFileState', 'MainPID'} or (result.returncode and values.get('LoadState') != 'not-found'):
        raise Refusal('awg-unit-state-invalid')
    return values


def unit(name):
    return 'awg-quick@' + name + '.service'


class Adapter:
    def __init__(self, candidates=(), firewall_candidate=None, revocation=None):
        self.candidates = list(candidates)
        self.firewall_candidate = firewall_candidate
        self.revocation = revocation
        self.known_names = set(names(record()))
        self.desired = None
        self.activation_done = False
        self.restored_units = None
        for item in self.candidates:
            if item['path'] == str(RECORD):
                self.desired = ({'schema': 1, 'config_dir': record()['config_dir'], 'instances': []}
                                if item.get('absent') else json.loads(base64.b64decode(item['data'], validate=True)))
                self.known_names.update(names(self.desired))

    def retained(self, receipt):
        if receipt:
            self.validate_units(receipt['units'])
            self.known_names.update(name[len('awg-quick@'):-len('.service')] for name in receipt['units'] if name != 'awg-quick.target')

    def validate(self):
        allowed = BINARIES | SHARED | {str(RECORD)}
        for value in (record(), self.desired):
            if value is not None:
                allowed.update(str(Path(value['config_dir']) / (name + '.conf')) for name in names(value))
        if not self.candidates or any(item['path'] not in allowed for item in self.candidates):
            raise Refusal('awg-candidate-path-invalid')
        for item in self.candidates:
            if item['path'] in BINARIES and ('source' not in item or item['mode'] != 0o755):
                raise Refusal('awg-candidate-runtime-invalid')
        if self.firewall_candidate is not None:
            # The firewall helper admits syntax before recording its consumer intent.
            from firewall_consumer import Firewall
            Firewall([{'data': self.firewall_candidate}]).validate()

    def validate_units(self, values):
        if not isinstance(values, dict) or len(values) > 65:
            raise Refusal('awg-unit-state-invalid')
        for name, value in values.items():
            if name != 'awg-quick.target' and (not name.startswith('awg-quick@') or not name.endswith('.service')
                    or NAME.fullmatch(name[len('awg-quick@'):-len('.service')]) is None):
                raise Refusal('awg-unit-state-invalid')
            if (not isinstance(value, dict) or set(value) != {'LoadState', 'ActiveState', 'UnitFileState', 'MainPID'}
                    or value['LoadState'] not in {'loaded', 'not-found'}
                    or value['ActiveState'] not in {'active', 'inactive', 'failed'}
                    or value['UnitFileState'] not in {'enabled', 'disabled', 'static', ''}
                    or not isinstance(value['MainPID'], str) or not value['MainPID'].isdecimal()):
                raise Refusal('awg-unit-state-invalid')
        self.known_names.update(name[len('awg-quick@'):-len('.service')] for name in values if name != 'awg-quick.target')

    def inspect(self):
        selected = set(names(record())) if self.activation_done else self.known_names
        result = {unit(name): fields(unit(name)) for name in sorted(selected)}
        result['awg-quick.target'] = fields('awg-quick.target')
        self.validate_units(result)
        return result

    def stop(self):
        for name in sorted(self.known_names):
            selected = unit(name)
            if fields(selected)['LoadState'] == 'loaded':
                subprocess.run(['systemctl', 'stop', selected], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
                after = fields(selected)
                if after['ActiveState'] not in {'inactive', 'failed'} or after['MainPID'] != '0':
                    raise Refusal('awg-stop-unconfirmed')
                group = run(['systemctl', 'show', selected, '--property=ControlGroup', '--value']).strip()
                if group:
                    path = Path(group)
                    if not path.is_absolute() or '..' in path.parts or str(path) != group or path == Path('/'):
                        raise Refusal('awg-cgroup-invalid')
                    with TrustedDirectory(Path('/sys/fs/cgroup') / group[1:], 0) as directory:
                        fd = os.open('cgroup.events', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                        with os.fdopen(fd, 'r', encoding='ascii') as source:
                            events = dict(line.split() for line in source.read(4096).splitlines())
                    if events.get('populated') != '0':
                        raise Refusal('awg-stop-unconfirmed')
                if fields(selected)['ActiveState'] not in {'inactive', 'failed'} or fields(selected)['MainPID'] != '0':
                    raise Refusal('awg-stop-unconfirmed')
                pending = self.transaction.journal() if hasattr(self, 'transaction') else None
                was_absent = pending is not None and pending['units'].get(selected, {}).get('LoadState') == 'not-found'
                if was_absent or (self.desired is not None and name not in names(self.desired)):
                    run(['systemctl', 'disable', selected])
        if self.desired is not None and not names(self.desired):
            members = run(['systemctl', 'show', 'awg-quick.target', '--property=ConsistsOf', '--value']).split()
            for selected in members:
                if selected not in {unit(name) for name in self.known_names} and fields(selected)['ActiveState'] != 'inactive':
                    raise Refusal('awg-foreign-target-member')
            if fields('awg-quick.target')['LoadState'] == 'loaded':
                run(['systemctl', 'stop', 'awg-quick.target'])
                run(['systemctl', 'disable', 'awg-quick.target'])

    def start(self):
        self.restored_units = None
        if self.firewall_candidate is not None:
            firewall('apply', {'owner': 'awg', 'data': self.firewall_candidate, 'revocation': self.revocation})
        run(['systemctl', 'daemon-reload'])
        current = set(names(record()))
        for name in sorted(self.known_names - current):
            if fields(unit(name))['LoadState'] == 'loaded':
                run(['systemctl', 'disable', unit(name)])
        for name in sorted(current):
            run(['systemctl', 'enable', unit(name)])
            run(['systemctl', 'start', unit(name)])
        self.activation_done = True

    def ensure(self):
        current = set(names(record()))
        if self.firewall_candidate is not None:
            try:
                firewall('apply', {'owner': 'awg', 'data': self.firewall_candidate, 'revocation': self.revocation})
            except BaseException:
                if self.revocation is None:
                    firewall('restore', {'owner': 'awg'})
                raise
        if any(fields(unit(name))['ActiveState'] != 'active' for name in current):
            # A committed retry has already published its firewall. It must not
            # create a second firewall intent while repairing an accepted unit.
            saved, self.firewall_candidate = self.firewall_candidate, None
            try:
                self.start()
            finally:
                self.firewall_candidate = saved
            return True
        return False

    def restore(self, values):
        self.restored_units = values
        firewall('restore', {'owner': 'awg'})
        run(['systemctl', 'daemon-reload'])
        if values is None:
            return
        self.validate_units(values)
        ordered = sorted(values, key=lambda selected: selected == 'awg-quick.target')
        for selected in ordered:
            prior = values[selected]
            if prior['LoadState'] != 'loaded':
                continue
            current = fields(selected)
            if prior['UnitFileState'] in {'enabled', 'disabled'} and current['UnitFileState'] != prior['UnitFileState']:
                run(['systemctl', 'enable' if prior['UnitFileState'] == 'enabled' else 'disable', selected])
            if selected != 'awg-quick.target' or (current['ActiveState'] == 'active') != (prior['ActiveState'] == 'active'):
                if selected == 'awg-quick.target' and prior['ActiveState'] != 'active':
                    members = run(['systemctl', 'show', selected, '--property=ConsistsOf', '--value']).split()
                    if any(member not in {unit(name) for name in self.known_names} and fields(member)['ActiveState'] != 'inactive' for member in members):
                        raise Refusal('awg-foreign-target-member')
                run(['systemctl', 'start' if prior['ActiveState'] == 'active' else 'stop', selected])
            after = fields(selected)
            if ((after['ActiveState'] == 'active') != (prior['ActiveState'] == 'active')
                    or after['UnitFileState'] != prior['UnitFileState']):
                raise Refusal('awg-restoration-unconfirmed')

    def ready(self):
        current = set(names(record()))
        for name in self.known_names - current:
            observed = fields(unit(name))
            if observed['ActiveState'] == 'active' or observed['MainPID'] != '0' or observed['UnitFileState'] == 'enabled':
                raise Refusal('awg-retirement-unconfirmed')
        for name in current:
            expected = self.restored_units is None or self.restored_units.get(unit(name), {}).get('ActiveState') == 'active'
            active = fields(unit(name))['ActiveState'] == 'active'
            if active != expected:
                raise Refusal('awg-instance-not-active')
            if expected:
                run(['/usr/bin/awg', 'show', name])


def adopt(tx, *, retiring=False):
    if tx.accepted() is not None or not RECORD.exists():
        return
    prior = record()
    paths = (set() if retiring else BINARIES) | SHARED | {str(RECORD)} | {str(Path(prior['config_dir']) / (name + '.conf')) for name in names(prior)}
    # Membership alone is not executable authority. A legacy source-build receipt
    # must bind every installed executable before it may become a rollback target.
    if not retiring:
        import runtime_build_receipt as build
        directory = build._open_directory(Path('/var/lib/ripdpi/runtime-build-receipts'), tx.uid)
        try:
            outputs = []
            for project in ('amneziawg-go', 'amneziawg-tools'):
                receipt = build._read_receipt(directory, project + '.json')
                if not isinstance(receipt, dict) or receipt.get('schema_version') != 1 or not isinstance(receipt.get('outputs'), list):
                    raise Refusal('awg-legacy-runtime-unowned')
                outputs.extend(receipt['outputs'])
            for path in BINARIES:
                claimed = [item for item in outputs if isinstance(item, dict) and item.get('path') == path]
                observed = tx._node(Path(path))
                if len(claimed) != 1 or observed is None or observed.get('sha256') != claimed[0].get('sha256'):
                    raise Refusal('awg-legacy-runtime-unowned')
        finally:
            os.close(directory)
    captured = {}
    for path in paths:
        tx.parent(Path(path).parent)
        value = tx._node(Path(path))
        if value is None:
            raise Refusal('awg-legacy-authority-incomplete')
        captured[path] = value
    adapter = Adapter()
    tx.record('accepted.json', {'schema': 1, 'nodes': captured, 'previous': None, 'units': adapter.inspect()})


def prune_retired(tx):
    """Bound retired authority after commit; resume exact cleanup after death."""
    path = tx.root / 'retirement.json'
    intent = read_private(path, tx.uid)
    if intent is None:
        receipt = tx.accepted()
        if receipt is None:
            return
        fixed_absence = SHARED | {str(RECORD)}
        retired = [raw for raw, claim in receipt['nodes'].items() if claim is None and raw not in fixed_absence]
        if not retired:
            return
        backups = tx.backups()
        remaining = {raw: claim for raw, claim in receipt['nodes'].items() if raw not in retired}
        after = {**receipt, 'nodes': remaining,
                 'previous': None if receipt['previous'] is None else {raw: claim for raw, claim in receipt['previous'].items() if raw in remaining}}
        next_backups = None if backups is None else {
            **backups, 'nodes': {raw: claim for raw, claim in backups['nodes'].items() if raw not in retired},
            'directories': {raw: claim for raw, claim in backups['directories'].items()
                            if any(str(Path(selected).parent / '.ripdpi-transport-runtime') == raw for selected in backups['nodes'] if selected not in retired)}}
        intent = {'schema': 1, 'before': receipt, 'after': after, 'backups': backups,
                  'next_backups': next_backups, 'retired': retired,
                  'last': tx._node(tx.root / 'last.json')}
        tx.record('retirement.json', intent)
    if not isinstance(intent, dict) or set(intent) != {'schema', 'before', 'after', 'backups', 'next_backups', 'retired', 'last'} or intent['schema'] != 1:
        raise Refusal('awg-retirement-invalid')
    for key in ('before', 'after'):
        validate_receipt(intent[key], root=tx.root, uid=tx.uid, node_limit=tx.node_limit)
    absent = [raw for raw, claim in intent['before']['nodes'].items() if claim is None]
    dynamic_absence = [raw for raw in absent if raw not in SHARED | {str(RECORD)}]
    # Resume the exact older all-absence cleanup journal as well as the bounded
    # form. A caller cannot choose an arbitrary subset or change retained claims.
    if (intent['retired'] not in (absent, dynamic_absence)
            or intent['after']['nodes'] != {raw: claim for raw, claim in intent['before']['nodes'].items()
                                           if raw not in intent['retired']}):
        raise Refusal('awg-retirement-invalid')
    tx.validate_backup_map(intent['backups'])
    tx.validate_backup_map(intent['next_backups'])
    if read_private(tx.root / 'accepted.json', tx.uid) not in (intent['before'], intent['after']) or read_private(tx.root / 'backups.json', tx.uid) not in (intent['backups'], intent['next_backups']):
        raise Refusal('awg-retirement-authority-changed')
    for raw in intent['retired']:
        if tx._node(Path(raw)) is not None:
            raise Refusal('awg-retired-path-reappeared')
        saved = tx.backup_path(raw)
        observed = tx._node(saved)
        wanted = (intent['backups'] or {}).get('nodes', {}).get(raw)
        if observed is not None:
            if observed != wanted:
                raise Refusal('awg-retirement-backup-changed')
            directory = tx.parent(saved.parent)
            os.unlink(saved.name, dir_fd=directory)
            os.fsync(directory)
    last = tx.root / 'last.json'
    observed = tx._node(last)
    if observed is not None:
        if observed != intent['last']:
            raise Refusal('awg-retirement-last-changed')
        os.unlink(last.name, dir_fd=tx.state_fd)
        os.fsync(tx.state_fd)
    if intent['next_backups'] is not None:
        tx.record('backups.json', intent['next_backups'])
    tx.record('accepted.json', intent['after'])
    os.unlink(path.name, dir_fd=tx.state_fd)
    os.fsync(tx.state_fd)


def firewall_decision(tx, *, success=False):
    path = tx.root / 'firewall.json'
    decision = read_private(path, tx.uid)
    if decision is None:
        return
    if not isinstance(decision, dict) or set(decision) != {'schema', 'before', 'phase'} or decision['schema'] != 1 or decision['phase'] not in {'open', 'committing'}:
        raise Refusal('awg-firewall-decision-invalid')
    if decision['before'] is not None:
        validate_receipt(decision['before'], root=tx.root, uid=tx.uid, node_limit=tx.node_limit)
    current = tx.accepted()
    committed = decision['phase'] == 'committing' or success
    if current != decision['before']:
        last = read_private(tx.root / 'last.json', tx.uid)
        if last is None or last['before_receipt'] != decision['before'] or last['after_receipt'] != current:
            raise Refusal('awg-firewall-commit-unconfirmed')
        committed = True
    if committed:
        tx.record('firewall.json', {**decision, 'phase': 'committing'})
        firewall('finish', {'owner': 'awg', 'revocation': tx.revocation})
    else:
        firewall('restore', {'owner': 'awg'})
    os.unlink(path.name, dir_fd=tx.state_fd)
    os.fsync(tx.state_fd)


def operate(action, payload):
    check = payload.get('check', False)
    if type(check) is not bool:
        raise Refusal('awg-check-invalid')
    with Transaction(STATE, uid=os.geteuid(), check=check, awg=True, revocation=payload.get('revocation')) as tx:
        if tx.state_fd is None:
            return {'changed': action == 'apply'}
        if read_private(tx.root / 'retirement.json', tx.uid) is not None:
            if check:
                raise Refusal('awg-retirement-recovery-required')
            prune_retired(tx)
        tx.revocation_state()
        adapter = Adapter(payload.get('candidates', []), payload.get('firewall'), tx.revocation)
        if action == 'recover':
            if check:
                if tx.journal() is not None or tx.preparation() is not None or tx.compensation() is not None or read_private(tx.root / 'firewall.json', tx.uid) is not None:
                    raise Refusal('awg-recovery-required')
                tx.accepted()
                return {'changed': False}
            changed = tx.recover(adapter)
            fence = tx.revocation_state()
            if fence is not None and fence['receipt'] is None:
                return {'changed': changed, 'forward_pending': True}
            firewall_decision(tx)
            adopt(tx, retiring=payload.get('retiring', False))
            prune_retired(tx)
            return {'changed': changed}
        adapter.validate()
        if not check and payload.get('firewall') is not None:
            if read_private(tx.root / 'firewall.json', tx.uid) is not None:
                fence = tx.revocation_state()
                if fence is None or fence['authority'] != tx.revocation:
                    raise Refusal('awg-firewall-recovery-required')
            else:
                tx.record('firewall.json', {'schema': 1, 'before': tx.accepted(), 'phase': 'open'})
        try:
            result = tx.apply(payload['candidates'], adapter, check=check)
        except BaseException:
            # Only a fully compensated runtime may authorize old firewall
            # restoration. An unresolved runtime journal keeps both owners.
            if not check and tx.journal() is None and tx.compensation() is None and tx.revocation is None:
                firewall_decision(tx)
            raise
        if not check:
            firewall_decision(tx, success=True)
            prune_retired(tx)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['recover', 'apply', 'admit'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refusal('root-required')
    if args.action == 'admit':
        admission(STATE, uid=os.geteuid())
        return
    raw = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise Refusal('awg-input-oversize')
    print(json.dumps(operate(args.action, json.loads(raw)), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, Refusal, subprocess.SubprocessError):
        print('awg-consumer-refused', file=sys.stderr)
        raise SystemExit(1)
