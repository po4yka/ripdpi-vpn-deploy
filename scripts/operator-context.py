#!/usr/bin/env python3
"""Run one fixed routine operation with only its encrypted credential profile."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from bootstrap_readiness import ReadinessError, run_command
from operator_maintenance_io import MaintenanceError, ROOT, command_environment, read_bytes
from recovery_io import module, unique

NAMES = {'B2_APPLICATION_KEY_ID', 'B2_APPLICATION_KEY'}


def routine_environment(profile, identity):
    cipher = read_bytes(profile, limit=1024 * 1024)
    encrypted = json.loads(cipher, object_pairs_hook=unique)
    if not isinstance(encrypted, dict) or 'sops' not in encrypted:
        raise MaintenanceError('encrypted-routine-profile-required')
    read_bytes(identity, limit=65536)
    result = subprocess.run(['sops', '--decrypt', '--input-type', 'json', '--output-type', 'json', '/dev/stdin'],
                            input=cipher, capture_output=True, timeout=30,
                            env=command_environment({'SOPS_AGE_KEY_FILE': str(identity)}), check=True)
    value = json.loads(result.stdout, object_pairs_hook=unique)
    if (not isinstance(value, dict) or set(value) != NAMES
            or any(not isinstance(item, str) or not item or len(item) > 1024
                   or any(ord(char) < 32 for char in item) for item in value.values())):
        raise MaintenanceError('routine-profile-scope-refused')
    return command_environment(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        kit = module('operator-kit')
        config = kit.configuration(args.config)
        env = routine_environment(args.profile, config['identity'])
        code, _ = run_command([sys.executable, str(ROOT / 'scripts/operator-kit.py'), 'backup',
                               '--config', args.config, '--output', args.output],
                              environment=env, cwd=ROOT, stream=True, timeout=1200)
        return code
    except (OSError, ValueError, TypeError, KeyError, ReadinessError, subprocess.SubprocessError):
        print('routine-backup: operation refused; no administrative credential context selected', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
