"""Coordinate consumer recovery with the existing guarded route snapshot owner."""
from __future__ import annotations

import argparse
import json
import os
import sys

from transport_runtime_accept import Adapter, STATE, read_parameters
from transport_runtime_transaction import Transaction, Refusal, read_private, sync, validate_receipt, outer_record, revocation_record
from transport_runtime_validate import inspect_lease, recover_validation


def marker(tx):
    value = outer_record(STATE, tx.uid)
    if value is not None and value['receipt'] is not None:
        validate_receipt(value['receipt'], root=STATE, uid=tx.uid)
        adapter().validate_units(value['receipt']['units'])
    return value


def adapter():
    value = read_parameters()
    if value is None:
        raise Refusal('acceptance-parameters-required')
    return Adapter([], value['probe_url'], value['expected_status'], value['timeout'], value['clients'], value['asset_dir'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'begin', 'restore', 'finish', 'recover'])
    parser.add_argument('--revocation-stdin', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refusal('root-required')
    raw = sys.stdin.buffer.read(4097) if args.revocation_stdin else b''
    if len(raw) > 4096:
        raise Refusal('revocation-authority-invalid')
    authority = json.loads(raw) if raw.strip() else None
    with Transaction(STATE, check=args.action == 'status', revocation=authority) as tx:
        if args.action == 'status':
            inspect_lease(tx)
        else:
            recover_validation(tx)
        intent = marker(tx)
        if args.action == 'status':
            fence = revocation_record(STATE, tx.uid) if tx.state_fd is not None else None
            result = {'open': intent is not None, 'revocation':
                      intent.get('revocation') if intent is not None else
                      fence['authority'] if fence is not None and fence['receipt'] is None else None}
        elif args.action == 'begin':
            if intent is not None:
                raise Refusal('outer-recovery-required')
            tx.arm_revocation()
            tx.record('outer.json', {'schema': 1, 'receipt': tx.accepted(), 'consumer_receipt': None,
                                    **({'revocation': authority} if authority is not None else {})})
            result = {'open': True}
        elif args.action == 'restore':
            tx.refuse_revocation_rollback()
            if intent is not None and intent.get('revocation') is not None:
                raise Refusal('revocation-rollback-forbidden')
            if intent is None:
                result = {'changed': False}
            else:
                current = read_private(STATE / 'accepted.json', 0)
                owner = adapter()
                if tx.journal() is not None or (STATE / 'preparation.json').exists() or (STATE / 'compensating.json').exists():
                    result = tx.recover(owner, restore_only=True)
                elif current != intent['receipt']:
                    last = read_private(STATE / 'last.json', 0)
                    if last is None or last['before_receipt'] != intent['receipt'] or last['after_receipt'] != current:
                        raise Refusal('outer-authority-unconfirmed')
                    result = tx.compensate_latest(owner, restore_only=True)
                else:
                    tx.accepted()
                    result = {'changed': False}
        elif args.action == 'recover':
            tx.refuse_revocation_rollback()
            if intent is not None and intent.get('revocation') is not None:
                raise Refusal('revocation-rollback-forbidden')
            if intent is None:
                raise Refusal('outer-intent-required')
            owner = adapter()
            tx.recover(owner)
            if tx.accepted() != intent['receipt']:
                raise Refusal('outer-restoration-unconfirmed')
            owner.retained(intent['receipt'])
            owner.restore(None if intent['receipt'] is None else intent['receipt']['units'])
            if intent['receipt'] is not None:
                owner.ready()
            (STATE / 'outer.json').unlink()
            sync(STATE)
            result = {'changed': True}
        else:
            tx.revocation_state()
            if intent is not None and intent.get('revocation') not in (None, authority):
                raise Refusal('revocation-resume-required')
            if intent is not None:
                if tx.journal() is not None or (STATE / 'preparation.json').exists() or (STATE / 'compensating.json').exists():
                    raise Refusal('consumer-recovery-required')
                current = tx.accepted()
                if current is not None:
                    adapter().validate_units(current['units'])
                if current != intent['receipt']:
                    last = read_private(STATE / 'last.json', 0)
                    if last is None:
                        raise Refusal('outer-authority-unconfirmed')
                    tx.validate_intent(last)
                    adapter().validate_units(last['units'])
                    if last['before_receipt'] != intent['receipt'] or last['after_receipt'] != current:
                        raise Refusal('outer-authority-unconfirmed')
                if intent['consumer_receipt'] != current or current is None:
                    raise Refusal('outer-consumer-unconfirmed')
                (STATE / 'outer.json').unlink()
                sync(STATE)
            result = {'open': False}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import re
        import traceback
        from transport_runtime_probe import ProbeRefused
        category = str(error) if isinstance(error, (Refusal, ProbeRefused)) else 'validation-refused'
        if re.fullmatch('[a-z][a-z0-9-]{0,96}', category) is None:
            category = 'validation-refused'
        print('transport-runtime-refused:' + category, file=sys.stderr)
        for frame in traceback.extract_tb(error.__traceback__)[-8:]:
            if re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', frame.name):
                print('transport-runtime-frame:' + frame.name + ':' + str(frame.lineno), file=sys.stderr)
        print('transport-outer-refused', file=sys.stderr)
        raise SystemExit(1)
