#!/usr/bin/env python3
"""Review and resume an explicit private device/server migration plan."""
import argparse
import json
import signal
import sys

from bootstrap_readiness import cancellation
from device_migration import Migration
from device_migration_errors import MigrationRefused
from device_migration_io import LocalIO, load_plan, migration_lock, private_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'prepare', 'publish', 'status', 'receipt', 'attest', 'ready', 'rollback'))
    parser.add_argument('--plan', required=True)
    parser.add_argument('--approve')
    parser.add_argument('--receipt')
    parser.add_argument('--client')
    parser.add_argument('--reason')
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        with cancellation((signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)), migration_lock(plan):
            migration = Migration(plan, LocalIO(plan))
            if args.action == 'plan':
                result = migration.inspect()[-1]
            elif args.action == 'prepare':
                result = migration.prepare(args.approve)
            elif args.action == 'receipt':
                result = migration.evidence(private_bytes(args.receipt, 4096))
            elif args.action == 'attest':
                result = migration.evidence(client=args.client, reason=args.reason)
            else:
                result = getattr(migration, args.action)()
        print(json.dumps(result, sort_keys=True))
        return 0
    except MigrationRefused as error:
        print('device-migration: ' + str(error) + '; retain source until ready succeeds', file=sys.stderr)
        return 2
    except (Exception, KeyboardInterrupt):
        # Exceptions can contain private JSON, endpoint, filename or command data.
        print('device-migration: refused or interrupted; retain source and reconcile the private plan', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
