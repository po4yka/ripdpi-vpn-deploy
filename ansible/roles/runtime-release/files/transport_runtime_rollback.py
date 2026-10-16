"""Existing operator rollback commands use complete native consumer acceptance."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from transport_runtime_accept import Adapter, STATE, read_parameters, parameter_candidate, restore_points, unit_binary, gateway_units, fields
from transport_runtime_probe import run
from transport_runtime_transaction import Transaction, Refusal, node, read_private, identity
from transport_runtime_validate import inspect_lease, recover_validation


UNIT_ROOT = Path('/etc/systemd/system')


def file_candidate(path, data, gid, mode=0o640):
    return {'path': str(path), 'data': base64.b64encode(data).decode(), 'gid': gid, 'mode': mode}


def release_versions(raw):
    if not isinstance(raw, str):
        raise Refusal('rollback-version-invalid')
    match = re.fullmatch(r'(v?[0-9]+\.[0-9]+\.[0-9]+)(-archive|-source-[0-9a-f]{40,64})?', raw)
    if match is None:
        raise Refusal('rollback-version-invalid')
    return match[1] + (match[2] or '-archive'), match[1]


def read_release_receipt(tx, path):
    observed = node(path, tx.uid)
    if observed is None or observed['identity'][3:] != [os.getgid(), 0o644] or 'sha256' not in observed:
        raise Refusal('rollback-release-unowned')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as source:
        if identity(os.fstat(source.fileno())) != observed['identity']:
            raise Refusal('rollback-release-changed')
        data = source.read(8193)
    if len(data) > 8192 or hashlib.sha256(data).hexdigest() != observed['sha256']:
        raise Refusal('rollback-release-changed')
    return json.loads(data)


def verified_release(tx, root, version, name, mode):
    directory = root / 'releases' / version
    tx.parent(directory)
    receipt = read_release_receipt(tx, directory / '.runtime-release.json')
    keys = {'schema_version', 'version', 'arch_key', 'arch_slug', 'binary_name', 'artifact_sha256', 'binary_sha256'}
    if (not isinstance(receipt, dict) or set(receipt) != keys or receipt['schema_version'] != 1
            or type(receipt['schema_version']) is not int or receipt['version'] != version or receipt['binary_name'] != name
            or any(not isinstance(receipt[key], str) or not re.fullmatch('[0-9a-f]{64}', receipt[key])
                   for key in ('artifact_sha256', 'binary_sha256'))):
        raise Refusal('rollback-release-unowned')
    candidate = directory / name
    fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != tx.uid or info.st_gid != os.getgid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != mode:
            raise Refusal('rollback-release-unowned')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != receipt['binary_sha256']:
                raise Refusal('rollback-release-changed')
    finally:
        os.close(fd)
    return directory


def runtime_candidates(tx, raw_version, unit_path, config_path, gid, *, gateway_paths, root=Path('/opt/xray')):
    # The accepted receipt claims every candidate by inode and digest, so only runtime-publisher-owned paths belong here.
    runtime_version, asset_version = release_versions(raw_version)
    release = verified_release(tx, root, runtime_version, 'xray', 0o755)
    unit = unit_path.read_text()
    binary, assets, _config = unit_binary(unit)
    selected = os.readlink(root / 'current')
    if selected == str(release):
        raise Refusal('rollback-no-change')
    rendered = unit.replace(binary, str(release / 'xray'))
    asset_root = root / 'assets/geoip'
    links = []
    if assets.startswith(str(asset_root / 'releases') + '/'):
        asset_release = verified_release(tx, asset_root, asset_version, 'geoip.dat', 0o644)
        rendered = rendered.replace(assets, str(asset_release))
        links += [{'path': str(asset_root / 'current'), 'target': str(asset_release)},
                  {'path': str(asset_root / 'previous'), 'target': os.readlink(asset_root / 'current')},
                  {'path': str(root / 'bundled-assets/geoip.dat'), 'target': str(asset_root / 'current/geoip.dat')}]
    links += [{'path': str(root / 'current'), 'target': str(release)},
              {'path': str(root / 'previous'), 'target': selected},
              {'path': '/usr/local/bin/xray', 'target': str(root / 'current/xray')}]
    gateways = []
    for path in gateway_paths:
        text = path.read_text()
        gateway_binary, _assets, _config = unit_binary(text)
        if gateway_binary != binary:
            raise Refusal('rollback-gateway-runtime-mismatch')
        gateways.append(file_candidate(path, text.replace(binary, str(release / 'xray')).encode(), 0, 0o644))
    return [file_candidate(unit_path, rendered.encode(), 0, 0o644), *gateways, *links,
            file_candidate(config_path, config_path.read_bytes(), gid)]


class RollbackAdapter(Adapter):
    def validate(self):
        super().validate()
        for unit in gateway_units():
            path = '/etc/systemd/system/' + unit
            if not any(item['path'] == path for item in self.candidates):
                continue
            text = self.candidate(path).decode()
            binary, _assets, _config = unit_binary(text)
            prefix = 'LoadCredential=config.json:'
            sources = [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
            if (len(sources) != 1 or not Path(sources[0]).is_absolute()
                    or str(Path(sources[0])) != sources[0] or '..' in Path(sources[0]).parts):
                raise Refusal('gateway-credential-invalid')
            run([binary, 'run', '-test', '-config', sources[0]], self.timeout)

    def ready(self):
        super().ready()
        # The controller still owns startup and compensation for the entire generation.
        # Prove loaded gateway executables here without changing shared readiness callers.
        for unit in gateway_units():
            current = fields(unit)
            binary, _assets, _config = unit_binary((UNIT_ROOT / unit).read_text())
            if (current['ActiveState'] != 'active' or int(current['MainPID']) <= 0
                    or not os.path.samefile('/proc/' + current['MainPID'] + '/exe', binary)):
                raise Refusal('gateway-runtime-mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['config', 'runtime'])
    parser.add_argument('--version')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refusal('root-required')
    parameters = read_parameters()
    if parameters is None:
        raise Refusal('accepted-parameters-required')
    with Transaction(STATE, check=args.check) as tx:
        if read_private(STATE / 'outer.json', tx.uid) is not None:
            raise Refusal('outer-transaction-active')
        if args.check:
            inspect_lease(tx)
        else:
            recover_validation(tx)
        owner = RollbackAdapter([], parameters['probe_url'], parameters['expected_status'], parameters['timeout'], parameters['clients'])
        owner.transaction = tx
        if not args.check:
            tx.recover(owner)
            parameters = read_parameters()
            if parameters is None:
                raise Refusal('accepted-parameters-required')
            owner = RollbackAdapter([], parameters['probe_url'], parameters['expected_status'], parameters['timeout'], parameters['clients'])
            owner.transaction = tx
        receipt = tx.accepted()
        if receipt is None:
            raise Refusal('accepted-runtime-required')
        unit_path = UNIT_ROOT / 'xray.service'
        config_path = Path('/etc/xray/config.json')
        if not receipt['nodes'].get(str(unit_path)) or not receipt['nodes'].get(str(config_path)):
            raise Refusal('accepted-xray-required')
        gid = receipt['nodes'][str(config_path)]['identity'][3]
        if args.action == 'config':
            previous = config_path.with_name('config.json.prev')
            if not receipt['nodes'].get(str(previous)):
                raise Refusal('accepted-previous-config-required')
            candidates = restore_points([file_candidate(unit_path, unit_path.read_bytes(), 0, 0o644),
                                         file_candidate(config_path, previous.read_bytes(), gid)])
        else:
            gateway_paths = [UNIT_ROOT / unit for unit in gateway_units()]
            if any(not receipt['nodes'].get(str(path)) for path in gateway_paths):
                raise Refusal('accepted-gateway-required')
            candidates = runtime_candidates(tx, args.version, unit_path, config_path, gid,
                                            gateway_paths=gateway_paths)
        candidates.append(parameter_candidate(parameters))
        owner.candidates = candidates
        result = tx.apply(candidates, owner, check=args.check)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('transport-rollback-refused', file=sys.stderr)
        raise SystemExit(1)
