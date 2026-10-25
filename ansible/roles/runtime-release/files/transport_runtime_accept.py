"""Ansible consumer adapter; the guarded generation remains the lifecycle owner."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time
from urllib.parse import urlsplit


from transport_runtime_transaction import Transaction, Refusal
from transport_runtime_probe import ProbeRefused, probe, run, xray_clients

STATE = Path('/var/lib/ripdpi/transport-runtime')
PARAMETERS = STATE / 'parameters.json'
CONTROLLER = 'ripdpi-transport-generation.service'
UNITS = ('xray.service', 'hysteria-server.service')


def validate_parameters(value):
    if (not isinstance(value, dict)
            or set(value) != {'probe_url', 'expected_status', 'timeout', 'clients', 'asset_dir'}
            or type(value['timeout']) is not int or not 1 <= value['timeout'] <= 60
            or type(value['expected_status']) is not int or not 100 <= value['expected_status'] <= 599):
        raise Refusal('input-invalid')
    if (not isinstance(value['clients'], dict) or set(value['clients']) != {'xray', 'hysteria'}
            or any(not isinstance(name, str) or not name or len(name) > 64 for name in value['clients'].values())):
        raise Refusal('probe-client-invalid')
    if not isinstance(value['probe_url'], str) or any(ord(ch) < 32 for ch in value['probe_url']):
        raise Refusal('canary-invalid')
    canary = urlsplit(value['probe_url'])
    if canary.scheme not in {'http', 'https'} or not canary.hostname or canary.username or canary.password:
        raise Refusal('canary-invalid')
    if value['asset_dir'] is not None and (not isinstance(value['asset_dir'], str)
            or not Path(value['asset_dir']).is_absolute() or '..' in Path(value['asset_dir']).parts):
        raise Refusal('asset-directory-invalid')
    return value


def read_parameters(*, uid=0):
    """Read exact published authority, including a claimed interrupted backup."""
    from transport_runtime_transaction import node, read_private, storage_path, storage_claim
    observed = node(PARAMETERS, uid, links=2)
    if observed is None:
        receipt = read_private(STATE / 'accepted.json', uid)
        if receipt is not None and receipt.get('nodes', {}).get(str(PARAMETERS)) is not None:
            raise Refusal('accepted-parameters-absent')
        return None
    if PARAMETERS.lstat().st_nlink == 2:
        claimed = False
        for name in ('pending.json', 'preparation.json', 'compensating.json'):
            intent = read_private(STATE / name, uid)
            if name == 'preparation.json' and isinstance(intent, dict):
                intent = intent.get('intent')
            if (not isinstance(intent, dict)
                    or set(intent) != {'schema', 'before_receipt', 'after_receipt', 'entries', 'units', 'before_backups'}
                    or intent['schema'] != 1 or not isinstance(intent['entries'], list)
                    or not 1 <= len(intent['entries']) <= 64):
                continue
            for index, entry in enumerate(intent['entries']):
                if not isinstance(entry, dict) or entry.get('path') != str(PARAMETERS):
                    continue
                storage = storage_path(PARAMETERS)
                if (not os.path.lexists(storage) or storage_claim(PARAMETERS) != entry.get('storage')
                        or storage.is_symlink() or storage.lstat().st_mode & 0o777 != 0o700):
                    raise Refusal('unclaimed-parameters-link')
                backups = []
                if entry.get('before') == observed:
                    backups.append('before-' + str(index))
                if entry.get('after') == observed:
                    backups.append('undo-' + str(index))
                if any(node(storage / backup, uid, links=2) == observed for backup in backups):
                    claimed = True
        if not claimed:
            raise Refusal('unclaimed-parameters-link')
    return validate_parameters(read_private(PARAMETERS, uid, links=2))


def parameter_candidate(value):
    """Probe authority uses the sole selectable reserved file inside STATE."""
    value = validate_parameters(value)
    return {'path': str(PARAMETERS), 'mode': 0o600, 'gid': 0,
            'data': base64.b64encode(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).decode()}


def fields(unit, *, quiescing=False):
    raw = run(['/usr/bin/systemctl', 'show', unit, '--property=LoadState,ActiveState,UnitFileState,MainPID'], 10).decode()
    value = dict(row.split('=', 1) for row in raw.splitlines() if '=' in row)
    active = {'active', 'inactive', 'failed'}
    if quiescing:
        active |= {'activating', 'deactivating', 'reloading', 'auto-restart'}
    if value.get('LoadState') not in {'loaded', 'not-found'} or value.get('ActiveState') not in active:
        load, current = value.get('LoadState'), value.get('ActiveState')
        if load in {'loaded', 'not-found', 'error', 'masked', 'bad-setting'} and current in {
                'active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading', 'auto-restart'}:
            raise Refusal('unit-state-' + load + '-' + current)
        raise Refusal('unit-state-unconfirmed')
    return value


def unit_binary(unit):
    lines = unit.splitlines()
    starts = [line[len('ExecStart='):] for line in lines if line.startswith('ExecStart=')]
    assets = [line[len('Environment=XRAY_LOCATION_ASSET='):] for line in lines if line.startswith('Environment=XRAY_LOCATION_ASSET=')]
    if len(starts) != 1 or not starts[0].startswith('/'):
        raise Refusal('unit-executable-invalid')
    argv = shlex.split(starts[0])
    option = '-config' if '-config' in argv else '-c'
    config = argv[argv.index(option) + 1]
    return argv[0], assets[0] if len(assets) == 1 else None, config


def gateway_units():
    """Use the generation reader's validated topology, never a parallel unit list."""
    return json.loads(run(['/usr/bin/python3', '-Es',
        '/usr/local/libexec/ripdpi-transport-egress/generation.py', 'runtime-units',
        '--config', '/etc/ripdpi/transport-egress/generation.json',
        '--normalizer-config', '/etc/ripdpi/transport-egress/normalizer.json'], 10))


def restore_points(candidates):
    result = list(candidates)
    for item in candidates:
        path = Path(item['path'])
        if path.name not in {'config.json', 'config.yaml'} or 'data' not in item:
            continue
        from transport_runtime_transaction import node
        before = node(path, 0)
        if before is not None and before.get('sha256') != __import__('hashlib').sha256(base64.b64decode(item['data'], validate=True)).hexdigest():
            result.append({'path': str(path) + '.prev', 'data': base64.b64encode(path.read_bytes()).decode(),
                           'mode': item['mode'], 'gid': item['gid']})
    return result


def omit_absent_subtrees(candidates, tx):
    """An absent parent has no selected inode to journal or storage to create."""
    selected = []
    for item in candidates:
        path = Path(item['path'])
        if item.get('absent') is True and not os.path.lexists(path.parent):
            from transport_runtime_transaction import validate_receipt
            if set(item) - {'deferred'} != {'path', 'absent'} or item.get('deferred', False) is not False:
                raise Refusal('candidate-invalid')
            validate_receipt({'schema':1, 'nodes':{item['path']:None}, 'previous':None, 'units':{}},
                             root=tx.root, uid=tx.uid)
            ancestor = path.parent
            while not os.path.lexists(ancestor):
                ancestor = ancestor.parent
            tx.parent(ancestor)
            if os.path.lexists(path):
                raise Refusal('retirement-parent-unconfirmed')
        else:
            selected.append(item)
    return selected


class Adapter:
    def __init__(self, candidates, url, expected, timeout, clients, asset_dir=None):
        self.candidates = candidates
        self.clients = clients
        self.asset_dir = asset_dir
        self.known = {}
        self.url, self.expected, self.timeout = url, expected, timeout

    def candidate(self, path):
        selected = [item for item in self.candidates if item['path'] == path]
        if not selected and path in self.known:
            return Path(path).read_bytes()
        if len(selected) != 1 or 'data' not in selected[0]:
            raise Refusal('candidate-incomplete')
        return base64.b64decode(selected[0]['data'], validate=True)

    def validate(self):
        # Xray validates exact staged assets; Hysteria uses an actual owned
        # namespace/startup fixture rather than an invented server check flag.
        for unit in UNITS:
            path = '/etc/systemd/system/' + unit
            if any(item['path'] == path and item.get('absent') for item in self.candidates):
                continue
            if not any(item['path'] == path for item in self.candidates) and not (unit == 'xray.service' and self.asset_dir):
                continue
            unit_text = self.candidate(path).decode()
            binary, assets, config_path = unit_binary(unit_text)
            if unit == 'xray.service':
                with tempfile.TemporaryDirectory(prefix='ripdpi-xray-candidate-') as tmp:
                    config = Path(tmp) / 'config.json'
                    config.write_bytes(self.candidate(config_path))
                    config.chmod(0o600)
                    xray_clients(json.loads(config.read_bytes()), 1080, self.clients['xray'], timeout=self.timeout)
                    run([binary, 'run', '-test', '-config', str(config)], self.timeout,
                        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'XRAY_LOCATION_ASSET': self.asset_dir or assets})
            else:
                from transport_runtime_validate import validate_hysteria
                import yaml
                raw = self.candidate(config_path)
                document = yaml.safe_load(raw)
                tls = document.get('tls')
                ech_key = None
                if 'ech' in document:
                    prefix = 'LoadCredential=hysteria-ech:'
                    sources = [line[len(prefix):] for line in unit_text.splitlines() if line.startswith(prefix)]
                    if (len(sources) != 1 or not Path(sources[0]).is_absolute()
                            or str(Path(sources[0])) != sources[0] or '..' in Path(sources[0]).parts):
                        raise Refusal('unit-credential-invalid')
                    ech_key = self.candidate(sources[0])
                validate_hysteria(binary, raw, self.candidate(tls['cert']) if tls else None,
                                  self.candidate(tls['key']) if tls else None,
                                  unit_text, self.timeout, self.clients['hysteria'],
                                  transaction=getattr(self, 'transaction', None),
                                  ech_key=ech_key,
                                  gateway_binary=unit_binary(self.candidate(
                                      '/etc/systemd/system/' + gateway_units()[0]).decode())[0])

    def retained(self, receipt):
        self.known = (receipt or {}).get('nodes', {})

    def validate_units(self, value):
        if not isinstance(value, dict) or set(value) != {CONTROLLER, *UNITS}:
            raise Refusal('unit-state-invalid')
        for state in value.values():
            if (not isinstance(state, dict) or set(state) != {'LoadState', 'ActiveState', 'UnitFileState', 'MainPID'}
                    or state['LoadState'] not in {'loaded', 'not-found'}
                    or state['ActiveState'] not in {'active', 'inactive', 'failed'}
                    or state['UnitFileState'] not in {'enabled', 'disabled', 'static', ''}
                    or not isinstance(state['MainPID'], str) or not state['MainPID'].isdigit()):
                raise Refusal('unit-state-invalid')

    def inspect(self):
        return {unit: fields(unit) for unit in (CONTROLLER, *UNITS)}

    def stop(self):
        for unit in (CONTROLLER, *UNITS):
            # A rejected candidate can be starting or auto-restarting. Its
            # durable intent already binds the exact owned unit; stop it first,
            # then require stable PID-zero state before restoring any inode.
            if fields(unit, quiescing=True)['LoadState'] == 'loaded':
                run(['/usr/bin/systemctl', 'stop', unit], self.timeout)
                after = fields(unit)
                if after.get('MainPID', '0') != '0' or after['ActiveState'] == 'active':
                    raise Refusal('unit-stop-unconfirmed')
        # Disable only declared retirement units while their known original
        # files still exist. Their prior enablement is already journaled.
        for unit in UNITS:
            path = '/etc/systemd/system/' + unit
            if any(item['path'] == path and item.get('absent') for item in self.candidates):
                if fields(unit)['LoadState'] == 'loaded':
                    run(['/usr/bin/systemctl', 'disable', unit], self.timeout)

    def frontends(self):
        return [unit for unit in UNITS if (Path('/etc/systemd/system') / unit).exists()]

    def start(self):
        run(['/usr/bin/systemctl', 'daemon-reload'], self.timeout)
        if not self.frontends():
            self.stop()
            for unit in (CONTROLLER, *UNITS):
                if fields(unit)['LoadState'] == 'loaded':
                    run(['/usr/bin/systemctl', 'disable', unit], self.timeout)
            return
        run(['/usr/bin/systemctl', 'daemon-reload'], self.timeout)
        run(['/usr/bin/systemctl', 'enable', CONTROLLER], self.timeout)
        run(['/usr/bin/systemctl', 'restart', CONTROLLER], self.timeout)

    def ensure(self):
        if not self.frontends():
            before = self.inspect()
            self.start()
            return any(item['ActiveState'] == 'active' or item['UnitFileState'] == 'enabled'
                       for item in before.values())
        if fields(CONTROLLER)['ActiveState'] != 'active':
            self.start()
            return True
        return False

    def restore(self, units):
        run(['/usr/bin/systemctl', 'daemon-reload'], self.timeout)
        if units is None:
            self.stop()
            for unit in (CONTROLLER, *UNITS):
                if fields(unit)['LoadState'] == 'loaded':
                    run(['/usr/bin/systemctl', 'disable', unit], self.timeout)
            return
        self.validate_units(units)
        for unit in (CONTROLLER, *UNITS):
            prior = units[unit]
            if prior['LoadState'] != 'loaded':
                continue
            if prior['UnitFileState'] in {'enabled', 'disabled'}:
                action = 'enable' if prior['UnitFileState'] == 'enabled' else 'disable'
                run(['/usr/bin/systemctl', action, unit], self.timeout)
        # The controller owns normal frontend startup. Restore an independently
        # active retained frontend only when no active controller was recorded.
        if units[CONTROLLER]['ActiveState'] == 'active':
            run(['/usr/bin/systemctl', 'start', CONTROLLER], self.timeout)
            self.generation_ready(time.monotonic() + self.timeout)
        else:
            for unit in UNITS:
                if units[unit]['LoadState'] != 'loaded':
                    continue
                action = 'start' if units[unit]['ActiveState'] == 'active' else 'stop'
                run(['/usr/bin/systemctl', action, unit], self.timeout)
        for unit in (CONTROLLER, *UNITS):
            prior, current = units[unit], fields(unit)
            if ((current['ActiveState'] == 'active') != (prior['ActiveState'] == 'active')
                    or current['UnitFileState'] != prior['UnitFileState']):
                raise Refusal('unit-restoration-unconfirmed')

    def ready(self):
        if not self.frontends():
            if any(fields(unit)['ActiveState'] == 'active' or fields(unit).get('MainPID', '0') != '0'
                   for unit in (CONTROLLER, *UNITS)):
                raise Refusal('retirement-unconfirmed')
            return
        parameters = read_parameters()
        if parameters is None:
            raise Refusal('accepted-parameters-required')
        deadline = time.monotonic() + parameters['timeout']
        self.generation_ready(deadline)
        for unit in UNITS:
            path = Path('/etc/systemd/system') / unit
            if not path.exists():
                continue
            current = fields(unit)
            if current['ActiveState'] != 'active' or int(current['MainPID']) <= 0:
                raise Refusal('frontend-not-adopted')
            binary, assets, config = unit_binary(path.read_text())
            if not os.path.samefile('/proc/' + current['MainPID'] + '/exe', binary):
                raise Refusal('frontend-runtime-mismatch')
            probe(binary, config, asset_dir=assets, url=parameters['probe_url'], expected=parameters['expected_status'],
                  client_name=parameters['clients']['xray' if unit == 'xray.service' else 'hysteria'],
                  timeout=max(.01, deadline - time.monotonic()))

    def generation_ready(self, deadline):
        while True:
            try:
                run(['/usr/bin/python3', '-Es', '/usr/local/libexec/ripdpi-transport-egress/generation.py',
                     'status', '--config', '/etc/ripdpi/transport-egress/generation.json',
                     '--normalizer-config', '/etc/ripdpi/transport-egress/normalizer.json'],
                    max(.01, deadline - time.monotonic()))
                break
            except (Refusal, RuntimeError):
                if time.monotonic() >= deadline:
                    raise Refusal('generation-readiness-refused') from None
                time.sleep(.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--refresh-assets', action='store_true')
    parser.add_argument('--retire', action='store_true')
    parser.add_argument('--compensate', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refusal('root-required')
    raw = sys.stdin.buffer.read(33554433)
    if len(raw) > 33554432:
        raise Refusal('input-oversize')
    value = json.loads(raw)
    revocation = value.pop('revocation', None) if isinstance(value, dict) else None
    if args.recover and value == {}:
        parameters = read_parameters()
        if parameters is None:
            raise Refusal('accepted-parameters-required')
        value = {**parameters, 'candidates': []}
    if args.retire or args.compensate:
        from transport_runtime_transaction import read_private
        request = value
        if args.retire and (not isinstance(request, dict) or set(request) != {'paths'} or not isinstance(request['paths'], list)):
            raise Refusal('retirement-request-invalid')
        parameters = read_parameters()
        if parameters is None:
            raise Refusal('accepted-parameters-required')
        value = {**parameters, 'candidates': []}
        if args.retire:
            allowed = {'/etc/systemd/system/xray.service', '/etc/systemd/system/hysteria-server.service',
                '/etc/xray/config.json', '/etc/xray/config.json.prev', '/etc/hysteria/config.yaml',
                '/etc/hysteria/config.yaml.prev', '/etc/hysteria/server.fullchain.pem',
                '/etc/hysteria/server.key', '/etc/hysteria/ech.key', '/etc/hysteria/masquerade-hosts'}
            if not 1 <= len(request['paths']) <= len(allowed) or any(path not in allowed for path in request['paths']):
                raise Refusal('retirement-path-invalid')
            value['candidates'] = [{'path': path, 'absent': True} for path in request['paths']]
    if args.refresh_assets:
        from transport_runtime_transaction import read_private
        request = value
        if not isinstance(request, dict) or set(request) != {'install_dir', 'candidate_dir', 'desired'} or set(request['desired']) != {'geoip.dat', 'geosite.dat'}:
            raise Refusal('asset-request-invalid')
        parameters = read_parameters()
        if parameters is None:
            raise Refusal('accepted-parameters-required')
        value = {**parameters, 'candidates': [], 'asset_dir': request['candidate_dir']}
        for name, digest in request['desired'].items():
            value['candidates'].append({'path': str(Path(request['install_dir']) / name),
                'source': str(Path(request['candidate_dir']) / name), 'sha256': digest, 'mode': 0o644, 'gid': 0})
        activated = {'schema': 1, 'desired': request['desired'], 'metadata': {'mode': 0o644, 'uid': 0, 'gid': 0}}
        value['candidates'].append({'path': str(Path(request['install_dir']) / '.geodata-activated.json'),
            'data': base64.b64encode(json.dumps(activated, sort_keys=True, separators=(',', ':')).encode()).decode(), 'mode': 0o600, 'gid': 0, 'deferred': True})
    if not isinstance(value, dict) or set(value) != {'candidates', 'probe_url', 'expected_status', 'timeout', 'clients', 'asset_dir'}:
        raise Refusal('input-invalid')
    parameters = validate_parameters({key: item for key, item in value.items() if key != 'candidates'})
    # Last declaration of the same staged binary/asset wins within one play;
    # frontend authority is included once by its canonical consumer.
    candidates = list({item['path']: item for item in value['candidates']}.values())
    if not args.recover and not args.bootstrap and revocation is None:
        candidates = restore_points(candidates)
    if not (args.recover or args.bootstrap or args.compensate):
        candidates = [item for item in candidates if item['path'] != str(PARAMETERS)]
        candidates.append(parameter_candidate(parameters))
    adapter = Adapter(candidates, value['probe_url'], value['expected_status'], value['timeout'], value['clients'], value['asset_dir'])
    with Transaction(STATE, check=args.check, revocation=revocation) as tx:
        # The outer owner retains A until its complete route has committed.
        # Timers must not replace A's one compensation authority mid-staging.
        if args.refresh_assets:
            from transport_runtime_transaction import read_private
            if read_private(STATE / 'outer.json', tx.uid) is not None:
                raise Refusal('outer-transaction-active')
        adapter.transaction = tx
        tx.revocation_state()
        from transport_runtime_validate import inspect_lease, recover_validation
        if args.check:
            inspect_lease(tx)
        else:
            recover_validation(tx)
        operation_recovered = False
        if (args.retire or args.refresh_assets) and not args.check:
            operation_recovered = tx.recover(adapter)
            current_parameters = read_parameters()
            if current_parameters is None:
                raise Refusal('accepted-parameters-required')
            parameters = validate_parameters({**current_parameters,
                'asset_dir': value['asset_dir'] if args.refresh_assets else current_parameters['asset_dir']})
            candidates = [item for item in candidates if item['path'] != str(PARAMETERS)]
            candidates.append(parameter_candidate(parameters))
            adapter = Adapter(candidates, parameters['probe_url'], parameters['expected_status'],
                              parameters['timeout'], parameters['clients'], parameters['asset_dir'])
            adapter.transaction = tx
        if not any((STATE / name).exists() for name in ('pending.json', 'preparation.json', 'compensating.json')):
            retained = tx.accepted()
            adapter.known = (retained or {}).get('nodes', {})
        candidates = omit_absent_subtrees(candidates, tx)
        adapter.candidates = candidates
        if args.bootstrap and not args.check:
            from transport_runtime_transaction import read_private
            # First-use recovery needs private inputs before any acceptance.
            # Once published authority exists, bootstrap never rewrites it.
            if (not any((STATE / name).exists() for name in ('pending.json', 'preparation.json', 'compensating.json'))
                    and read_parameters() is None
                    and read_private(STATE / 'accepted.json', 0) is None):
                tx.record('parameters.json', parameters)
        if args.compensate:
            result = tx.compensate_latest(adapter, check=args.check, restore_only=True)
        elif args.recover or args.bootstrap:
            recovered = False if args.check else tx.recover(adapter)
            pending_forward = tx.revocation_state()
            pending_forward = pending_forward is not None and pending_forward['receipt'] is None
            if not pending_forward:
                tx.accepted()
            if args.bootstrap and not args.check and not (STATE / 'accepted.json').exists() and Path('/var/lib/ripdpi/transport-egress/accepted.json').exists():
                from snapshot import capture, is_accepted, managed_paths
                from transport_runtime_transaction import node
                if is_accepted(capture(managed_paths())):
                    # A pre-existing guarded receipt is only eligible after fresh
                    # native frontend traffic and loaded executable identity proof.
                    adapter.ready()
                    paths = [Path(raw) for raw in managed_paths() if Path(raw).name in {
                        'config.json', 'config.yaml', 'server.key', 'ech.key', 'server.fullchain.pem',
                        'masquerade-hosts', 'xray.service', 'hysteria-server.service'}]
                    paths += [Path(raw) for raw in (
                        '/opt/xray/current', '/opt/xray/previous', '/usr/local/bin/xray',
                        '/opt/xray/assets/geoip/current', '/opt/xray/assets/geoip/previous',
                        '/opt/xray/bundled-assets/geoip.dat', '/opt/hysteria/current',
                        '/opt/hysteria/previous', '/usr/local/bin/hysteria')]
                    nodes = {}
                    for path in paths:
                        if os.path.lexists(path):
                            tx.parent(path.parent)
                            nodes[str(path)] = node(path, 0)
                    tx.record('accepted.json', {'schema': 1, 'nodes': nodes, 'previous': None,
                                               'units': adapter.inspect()})
            result = {'status': 'inspected' if args.check else 'reconciled', 'changed': recovered}
        else:
            result = tx.apply(candidates, adapter, check=args.check)
            result['changed'] = result['changed'] or operation_recovered
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import re
        import traceback
        category = str(error) if isinstance(error, (Refusal, ProbeRefused)) else 'validation-refused'
        if re.fullmatch('[a-z][a-z0-9-]{0,96}', category) is None:
            category = 'validation-refused'
        print('transport-runtime-refused:' + category, file=sys.stderr)
        for frame in traceback.extract_tb(error.__traceback__)[-8:]:
            if re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', frame.name):
                print('transport-runtime-frame:' + frame.name + ':' + str(frame.lineno), file=sys.stderr)
        raise SystemExit(1)
