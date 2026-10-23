#!/usr/bin/env python3
"""Verify the replacement with the migration controller's frozen strict transport."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bootstrap_readiness import cancellation
from recovery_io import load_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--action', choices=('verify', 'ready'), default='verify')
    args = parser.parse_args()
    try:
        from device_migration import Migration
        from device_migration_errors import MigrationRefused
        from device_migration_io import LocalIO, load_plan, migration_lock
        manifest = load_manifest(args.manifest)
        plan = load_plan(manifest['migration_plan'])
        if (plan['target']['host'] != 'upcloud:' + manifest['environment']
                or Path(plan['target']['secrets_file']).resolve() != Path(manifest['sops_file']).resolve()
                or Path(plan['known_hosts']).resolve() != Path(manifest['known_hosts_file']).resolve()):
            raise ValueError
        with cancellation():
            io = LocalIO(plan)
            if args.action == 'verify':
                io.verify_target(io.read(plan['target']['secrets_file']))
                result = {'verified': True}
            else:
                with migration_lock(plan):
                    try:
                        result = Migration(plan, io).ready()
                    except MigrationRefused as error:
                        if str(error) != 'migration-device-path-evidence-incomplete':
                            raise
                        result = {'ready': False, 'reason': 'device-path-evidence-incomplete'}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - private diagnostic boundary
        print('replacement-verification-unavailable', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
