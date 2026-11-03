#!/usr/bin/env python3
"""Admit dedicated recovery credentials on the controller before delivery."""
import ipaddress
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).parent
validate = runpy.run_path(str(ROOT / 'observability-kuma-recovery-contract.py'))['validate']
StorageAuthority = runpy.run_path(str(ROOT / 'observability-kuma-storage-contract.py'))['StorageAuthority']


def admit(values):
    scope = values['scope']
    if (type(scope['enabled']) is not bool or not scope['enabled']
            or not isinstance(scope['readers'], list) or not 1 <= len(scope['readers']) <= 4
            or any(not isinstance(value, str) for value in scope['readers'])
            or len(set(scope['readers'])) != len(scope['readers'])):
        raise ValueError('recovery-policy')
    for value in scope['readers']:
        address = ipaddress.ip_address(value)
        if str(address) != value or address not in ipaddress.ip_network('100.64.0.0/10'):
            raise ValueError('exact-tailnet-reader-required')
    config = validate(values['config'])
    key = values['identity']
    pair = values['storage']
    if (not isinstance(key, str) or not key.strip() or len(key) > 4096
            or not isinstance(pair, dict) or set(pair) != {'B2_APPLICATION_KEY_ID', 'B2_APPLICATION_KEY'}
            or any(not isinstance(value, str) or not value for value in pair.values())):
        raise ValueError('dedicated-recovery-credentials-required')
    executable = shutil.which('age-keygen')
    if executable is None:
        raise ValueError('controller-age-keygen-required')
    result = subprocess.run([executable, '-y'], input=key.encode(), capture_output=True, timeout=10,
                            check=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    if result.stdout.decode().strip() != config['recipient']:
        raise ValueError('kuma-only-recipient-mismatch')
    # Only this short-lived controller process receives the selected pair.
    # The remote host receives nothing until the provider confirms the scope.
    os.environ.update(pair)
    StorageAuthority(config)


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('admission-size-limit')
        admit(json.loads(raw))
    except Exception:
        print('observer recovery admission refused', file=sys.stderr)
        raise SystemExit(1) from None
