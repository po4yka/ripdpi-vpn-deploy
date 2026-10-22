#!/usr/bin/env python3
"""Execute or resume a reviewed UpCloud replacement with device continuity."""
from __future__ import annotations

import argparse
import json
import sys
import time

from bootstrap_readiness import cancellation
from recovery_io import ActionRequired, Journal, RecoveryError, digest, load_manifest
from recovery_runtime import Runtime


def matching_server(manifest, state, observation, expected=None):
    rows = observation['servers']
    if len(rows) != 1 or state is None:
        raise RecoveryError('recovery-provider-state-not-reconciled')
    server = rows[0]
    if (state['id'] != server['uuid'] or state['hostname'] != server['hostname']
            or state['hostname'] != manifest['hostname'] or state['zone'] != server['zone']
            or state['plan'] != server['plan'] or state['labels'] != server['labels']
            or server['state'] != 'started'
            or expected is not None and any(server[key] != expected[key]
                for key in ('uuid', 'hostname', 'created', 'zone', 'plan', 'labels', 'public_ipv4'))):
        raise RecoveryError('recovery-provider-identity-changed')
    return server


def provision(manifest, runtime, journal, approval):
    runtime.source()
    inputs = runtime.inputs()
    observed = runtime.observe()
    state = runtime.state()
    retained = journal.state['observed'].get('provision_plan')
    attempt = journal.state['observed'].get('apply_attempt')
    owned = journal.state['observed'].get('server')
    if owned is not None:
        return matching_server(manifest, state, observed, owned)
    if state is not None or observed['servers']:
        if attempt is None:
            raise RecoveryError('recovery-existing-resource-not-owned')
        if state is None:
            orphan = observed['servers'][0]
            planned = retained['review']['server']
            if (orphan['created'] < attempt['started_at'] - 5
                    or any(orphan[key] != planned[key] for key in ('hostname', 'zone', 'plan', 'labels'))):
                raise RecoveryError('recovery-orphan-identity-unproven')
            journal.approve('import', {'server': orphan, 'plan': retained, 'inputs': inputs}, approval)
            if runtime.observe() != observed or runtime.state() is not None or runtime.inputs() != inputs:
                raise RecoveryError('recovery-import-input-changed')
            runtime.import_server(orphan)
            state = runtime.state()
        matching_server(manifest, state, runtime.observe())
        # A lost apply may have left firewall/outputs unfinished. Re-plan against
        # imported/current state; only an admitted empty plan proves convergence.
        if (retained.get('state_sha256') != digest(state)
                or retained['inputs'] != inputs):
            retained = runtime.plan(state)
            journal.observe('provision_plan', retained)
    else:
        if retained is None:
            runtime.make('init')
            retained = runtime.plan(None)
            journal.observe('provision_plan', retained)
        elif retained['inputs'] != inputs:
            raise RecoveryError('recovery-provision-input-changed')
    if retained['review']['changes']:
        action = 'apply' if attempt is None else 'apply-reconcile'
        binding = {'plan': retained, 'provider': runtime.observe(), 'attempt': attempt}
        journal.approve(action, binding, approval)
        if runtime.observe() != binding['provider'] or runtime.inputs() != retained['inputs']:
            raise RecoveryError('recovery-apply-input-changed')
        if runtime.state() is None and binding['provider']['servers']:
            raise RecoveryError('recovery-provider-state-not-reconciled')
        journal.observe('apply_attempt', {'started_at': int(time.time()), 'plan_sha256': retained['plan_sha256'],
            'number': 1 if attempt is None else attempt['number'] + 1})
        runtime.apply(retained)
    server = matching_server(manifest, runtime.state(), runtime.observe())
    journal.observe('server', server)
    return server


def recover(manifest, runtime, journal, approval=None):
    runtime.migration_contract()
    server = provision(manifest, runtime, journal, approval)
    host = runtime.inventory_render()
    pins = runtime.pin_binding(server, host)
    journal.approve('authenticated-host-pin', pins, approval)
    if runtime.pin_binding(server, host) != pins:
        raise RecoveryError('recovery-pin-changed')
    contexts = runtime.management(host)
    # Reconcile the encrypted migration journal through its canonical prepare.
    # Retain its original digest: a retry never grants a fresh migration approval.
    migration_approval = journal.state['observed'].get('migration_approval')
    if migration_approval is None:
        review = runtime.migration('plan')
        journal.approve('device-migration', review, approval)
        migration_approval = review['approval']
        journal.observe('migration_approval', migration_approval)
    migration = runtime.migration('prepare', migration_approval)
    if migration['phase'] != 'published':
        runtime.converge(contexts, journal, approval)
        runtime.migration('publish')
    result = runtime.migration('ready')
    # Acceptance cannot hide a provider replacement or source change while long
    # guest and per-device gates were running.
    runtime.source()
    matching_server(manifest, runtime.state(), runtime.observe(), server)
    if runtime.pin_binding(server, host) != pins:
        raise RecoveryError('recovery-final-pin-changed')
    ready = result.get('ready') is True
    journal.observe('acceptance', {'ready': ready, 'checked_at': int(time.time())})
    return {'status': 'complete' if ready else 'awaiting-device-acceptance', 'ready': ready,
            'retirement': 'not-requested'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'resume', 'status'))
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--approve')
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        with cancellation(), Journal(manifest) as journal:
            if args.action == 'status':
                result = {'status': 'retained-state-only', 'sequence': journal.state['sequence'],
                    'interrupted_operation': (journal.state['intent'] or {}).get('name'),
                    'last_acceptance': journal.state['observed'].get('acceptance'),
                    'live_revalidated': False}
            else:
                result = recover(manifest, Runtime(manifest, args.manifest, journal), journal, args.approve)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('status') != 'awaiting-device-acceptance' else 3
    except ActionRequired as action:
        print(json.dumps({'status': 'review-required', 'action': action.action,
            'approval': action.digest, 'review': action.artifact}, sort_keys=True))
        return 3
    except RecoveryError as error:
        print(json.dumps({'status': 'refused', 'reason': str(error), 'resume': 'retain-journal'}, sort_keys=True))
        return 2
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - private diagnostic boundary
        # Private child/API exceptions can contain credentials, payloads or paths.
        print('recovery refused or interrupted; retain journal and resume after inspection', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
