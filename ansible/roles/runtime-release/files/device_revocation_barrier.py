"""Retain a no-restart fence around role-owned Snell/Naive credential writes."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from transport_runtime_transaction import (
    Refusal,
    Transaction,
    admission,
    validate_receipt,
)

ROOT = Path('/var/lib/ripdpi/device-revocation')
UNIT_DIRECTORY = Path('/etc/systemd/system')
UNITS = {'snell.service', 'caddy-naive.service'}


def run(argv):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=45, check=False)
    if result.returncode:
        raise Refusal('revocation-service-command-failed')
    return result.stdout.decode()


def fields(unit):
    value = dict(line.split('=', 1) for line in run(['systemctl', 'show', unit,
                 '--property=LoadState,ActiveState,MainPID']).splitlines() if '=' in line)
    if (set(value) != {'LoadState', 'ActiveState', 'MainPID'} or not value['MainPID'].isdigit()
            or value['LoadState'] not in {'loaded', 'not-found'}):
        raise Refusal('revocation-service-state-invalid')
    return value


def stop(unit):
    state = fields(unit)
    if state['LoadState'] == 'loaded':
        run(['systemctl', 'stop', unit])
    state = fields(unit)
    if state['ActiveState'] not in {'inactive', 'failed'} or state['MainPID'] != '0':
        raise Refusal('revocation-service-stop-unconfirmed')


def plan(value, unit, root, uid):
    if (not isinstance(value, dict) or not 1 <= len(value) <= 5
            or str(UNIT_DIRECTORY / unit) not in value
            or any(digest is not None and (not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None)
                   for digest in value.values())):
        raise Refusal('revocation-service-plan-invalid')
    validate_receipt({'schema': 1, 'nodes': dict.fromkeys(value), 'previous': None, 'units': {}}, root=root, uid=uid)
    return [{'path': raw, 'absent': True} if digest is None else {'path': raw, 'sha256': digest}
            for raw, digest in sorted(value.items())]


def verify(tx, wanted):
    nodes = {}
    for raw, digest in wanted.items():
        parent = Path(raw).parent
        if digest is None:
            while not os.path.lexists(parent):
                parent = parent.parent
        tx.parent(parent)
        observed = tx._node(Path(raw))
        if (digest is None and observed is not None or digest is not None
                and (observed is None or observed.get('sha256') != digest)):
            raise Refusal('revocation-service-publication-unconfirmed')
        nodes[raw] = observed
    return nodes


def activate(unit, wanted, activation):
    if wanted[str(UNIT_DIRECTORY / unit)] is None:
        stop(unit)
        return
    config_name = 'config.json' if unit == 'snell.service' else 'caddy.json'
    configs = [raw for raw, digest in wanted.items() if Path(raw).name == config_name and digest is not None]
    if len(configs) != 1:
        raise Refusal('revocation-service-plan-incomplete')
    config = configs[0]
    binary = '/usr/local/bin/sing-box-snell' if unit == 'snell.service' else '/usr/local/bin/caddy-naive'
    if unit == 'snell.service':
        if activation is not None:
            raise Refusal('revocation-service-activation-invalid')
        run([binary, 'check', '-c', config])
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', unit])
        run(['systemctl', 'restart', unit])
    else:
        if (not isinstance(activation, dict) or set(activation) != {'server_name', 'port'}
                or not isinstance(activation['server_name'], str)
                or re.fullmatch('[A-Za-z0-9.-]{1,253}', activation['server_name']) is None
                or type(activation['port']) is not int or not 1 <= activation['port'] <= 65535):
            raise Refusal('revocation-service-activation-invalid')
        directory = Path(config).parent
        if any(str(directory / name) not in wanted for name in ('server.fullchain.pem', 'server.key')):
            raise Refusal('revocation-service-plan-incomplete')
        run(['systemctl', 'enable', unit])
        run(['/usr/bin/python3', '/usr/local/libexec/vpn-naive-activate.py', '--binary', binary,
             '--unit-file', str(UNIT_DIRECTORY / unit), '--config', config,
             '--certificate', str(directory / 'server.fullchain.pem'), '--key', str(directory / 'server.key'),
             '--unit', unit, '--state', '/var/lib/ripdpi/naive-activation',
             '--server-name', activation['server_name'], '--port', str(activation['port'])])
    state = fields(unit)
    if state['ActiveState'] != 'active' or int(state['MainPID']) <= 0:
        raise Refusal('revocation-service-start-unconfirmed')
    if not os.path.samefile('/proc/' + state['MainPID'] + '/exe', binary):
        raise Refusal('revocation-service-runtime-changed')


def operate(action, unit, payload):
    if unit not in UNITS:
        raise Refusal('revocation-service-invalid')
    root = ROOT / unit
    if action == 'admit':
        admission(root, uid=os.geteuid())
        return {'changed': False}
    if (not isinstance(payload, dict) or set(payload) - {'authority', 'plan', 'check', 'activation'}
            or type(payload.get('check', False)) is not bool):
        raise Refusal('revocation-service-request-invalid')
    check = payload.get('check', False)
    with Transaction(root, uid=os.geteuid(), check=check, revocation=payload.get('authority')) as tx:
        fence = tx.revocation_state()
        if action == 'guard' or tx.revocation is None:
            return {'changed': False}
        if action == 'abort':
            if fence is not None:
                stop(unit)
            return {'changed': fence is not None}
        wanted = payload.get('plan')
        candidates = plan(wanted, unit, root, tx.uid)
        fence = tx.arm_revocation(candidates)
        if check:
            return {'changed': fence['receipt'] is None}
        if action == 'begin':
            if fence['receipt'] is None:
                # The role installs its boot admission before this durable fence.
                run(['systemctl', 'daemon-reload'])
                stop(unit)
            return {'changed': fence['receipt'] is None}
        if action != 'activate':
            raise Refusal('revocation-service-action-invalid')
        try:
            nodes = verify(tx, wanted)
            current = fields(unit)
            if (fence['receipt'] is not None and fence['receipt']['nodes'] == nodes
                    and fence['receipt']['units'].get(unit) == current
                    and (wanted[str(UNIT_DIRECTORY / unit)] is None or
                         (current['ActiveState'] == 'active' and int(current['MainPID']) > 0
                          and os.path.samefile('/proc/' + current['MainPID'] + '/exe',
                              '/usr/local/bin/sing-box-snell' if unit == 'snell.service' else '/usr/local/bin/caddy-naive')))):
                return {'changed': False}
            # Lost acknowledgements recheck actual loaded runtime and exact bytes.
            activate(unit, wanted, payload.get('activation'))
            if verify(tx, wanted) != nodes:
                raise Refusal('revocation-service-authority-changed')
            tx.record('revocation.json', {**fence, 'receipt':
                      {'schema': 1, 'nodes': nodes, 'previous': None, 'units': {unit: fields(unit)}}})
        except BaseException:
            stop(unit)
            raise
        return {'changed': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['guard', 'begin', 'activate', 'abort', 'admit'])
    parser.add_argument('unit', choices=sorted(UNITS))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refusal('root-required')
    raw = b'{}' if args.action == 'admit' else sys.stdin.buffer.read(16385)
    if len(raw) > 16384:
        raise Refusal('revocation-service-request-oversize')
    print(json.dumps(operate(args.action, args.unit, json.loads(raw))))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print('device-revocation-service-refused', file=sys.stderr)
        raise SystemExit(1)
