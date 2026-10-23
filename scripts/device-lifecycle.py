#!/usr/bin/env python3
"""Review and resume fleet device issuance, refresh or complete revocation."""
import argparse
import json
import signal
import sys

from bootstrap_readiness import cancellation
from device_lifecycle import Lifecycle
from device_lifecycle_io import LocalIO, load_manifest, operation_locks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'prepare', 'run', 'resume', 'status'))
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--approve')
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        authorities = [node['secrets_file'] for node in manifest['nodes']]
        with cancellation((signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)), operation_locks(authorities):
            operation = Lifecycle(manifest, LocalIO(manifest, args.manifest))
            if args.command == 'plan':
                result = operation.inspect()[-1]
            elif args.command == 'prepare':
                result = operation.prepare(args.approve)
            elif args.command in ('run', 'resume'):
                result = operation.run()
            else:
                result = operation.status()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - private exception boundary
        # Private subprocess errors may contain credentials or full profiles.
        print('device-lifecycle: refused or interrupted; inspect private intent and resume the same manifest', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
