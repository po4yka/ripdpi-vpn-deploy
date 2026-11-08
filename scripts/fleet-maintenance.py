#!/usr/bin/env python3
"""Run exact existing-node maintenance independently of the operator terminal."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import tempfile

from bootstrap_readiness import ReadinessError, cancellation
import fleet_inspection
from fleet_rotation_liveness import UniqueLoader
from fleet_rotation_liveness import healthy_survivors, RotationError
from public_site_inputs import read_site
import yaml
from operator_maintenance_io import (MaintenanceError, ROOT, command_environment, digest_file,
                                    encrypted_command, private_directory,
                                    new_file, read_bytes, require_success, write_document)
from recovery_io import Journal, RecoveryError, digest, unique, module, document

FIELDS = {'schema_version', 'id', 'expires_at', 'state_directory', 'runtime_parent',
          'log_recipient', 'age_identity', 'nodes', 'liveness_config', 'liveness_inputs'}
NODE_FIELDS = {'host', 'environment', 'provider', 'sops_file', 'extra_vars', 'known_hosts',
               'ssh_contexts', 'inputs'}
OPTIONAL = {'promotion_config', 'tailnet_handoff', 'failure_receipts'}
PATH_ENV = {'sops_file': 'SOPS_FILE', 'extra_vars': 'ANSIBLE_EXTRA_VARS_FILE',
            'known_hosts': 'INSPECT_KNOWN_HOSTS', 'ssh_contexts': 'DEPLOY_SSH_CONTEXTS_FILE',
            'promotion_config': 'DEPLOY_PROMOTION_CONFIG_FILE',
            'tailnet_handoff': 'DEPLOY_CI_TAILNET_HANDOFF',
            'failure_receipts': 'DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE'}
STAGES = ('dry-run', 'deploy', 'verify', 'security-verify', 'smoke-test')
ATTEMPT_INPUTS = {'approved-inputs.json', 'approved.sops.yaml', 'approved-age.key'}
SAFE = re.compile(r'[A-Za-z0-9_./:+-]+\Z')
LOCK_BUSY = re.compile(rb'node-lock-busy: (?:alias=[a-z0-9-]{1,64} held-as=target|resource=inventory held-as=shared-inventory)')


def literal(value):
    if not isinstance(value, str) or not SAFE.fullmatch(value):
        raise MaintenanceError('nonliteral-input')
    return value


def absolute(value):
    literal(value)
    if not Path(value).is_absolute() or '..' in Path(value).parts:
        raise MaintenanceError('absolute-path-required')
    return value


def deadline(plan):
    try:
        if not isinstance(plan['expires_at'], str):
            raise ValueError
        expiry = datetime.fromisoformat(plan['expires_at'].replace('Z', '+00:00'))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise MaintenanceError('authorization-expired-or-invalid') from None


def source():
    if os.path.lexists(ROOT / '.fleet.mk'):
        raise MaintenanceError('dedicated-controller-without-fleet-file-required')
    if require_success(['git', 'status', '--porcelain', '--untracked-files=normal']).strip():
        raise MaintenanceError('clean-source-required')
    revision, generation = require_success(['bash', 'scripts/deploy-source-identity.sh']).decode().split()
    return {'revision': revision, 'deployable_digest': generation}


def site_manifest(path):
    entries, _ = read_site(path)
    return {name: None if data is None else hashlib.sha256(data).hexdigest()
            for name, data in sorted(entries.items())}


def known_dependencies(node, inputs, trees):
    values = yaml.load(read_bytes(node['extra_vars']), Loader=UniqueLoader)
    if not isinstance(values, dict):
        raise MaintenanceError('invalid-extra-vars')
    site = values.get('nginx_xhttp_public_site_dir')
    if site:
        trees[absolute(site)] = site_manifest(site)
    exposure = values.get('network_exposure_gate')
    if exposure is not None and not isinstance(exposure, dict):
        raise MaintenanceError('invalid-network-exposure-input')
    if exposure and exposure.get('mode') != 'disabled':
        for field in ('artifact', 'trusted_key'):
            inputs[absolute(exposure[field])] = True


def prepare(config_path, plan_path):
    if not os.path.lexists(ROOT / 'ansible/inventory/generated.ini'):
        raise MaintenanceError('generated-inventory-missing: run make inventory PROVIDER=<provider> ENV=<env>')
    value = document(config_path)
    try:
        if (set(value) != FIELDS or value['schema_version'] != 1
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value['id'])
                or not re.fullmatch(r'age1[0-9a-z]{58}', value['log_recipient'])
                or not 1 <= len(value['nodes']) <= 10):
            raise ValueError
        deadline(value)
        for field in ('state_directory', 'runtime_parent'):
            private_directory(absolute(value[field]))
        inputs = {str(ROOT / 'ansible/inventory/generated.ini'): False,
                  absolute(value['age_identity']): True,
                  absolute(value['liveness_config']): True}
        if not isinstance(value['liveness_inputs'], list):
            raise ValueError
        for path in value['liveness_inputs']:
            inputs[absolute(path)] = True
        if require_success(['age-keygen', '-y', value['age_identity']]).decode().strip() != value['log_recipient']:
            raise MaintenanceError('log-recipient-identity-mismatch')
        names, trees = [], {}
        for node in value['nodes']:
            if (not NODE_FIELDS <= set(node) or set(node) - NODE_FIELDS - OPTIONAL
                    or node['provider'] not in {'upcloud', 'scaleway', 'vultr', 'hetzner'}
                    or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', node['host'])
                    or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', node['environment'])
                    or not isinstance(node['inputs'], list)):
                raise ValueError
            names.append(node['host'])
            for field in PATH_ENV.keys() & node.keys():
                inputs[absolute(node[field])] = True
            for path in node['inputs']:
                inputs[absolute(path)] = True
            known_dependencies(node, inputs, trees)
        if len(set(names)) != len(names):
            raise ValueError
        selected = fleet_inspection.select_hosts(ROOT / 'ansible/inventory/generated.ini', names,
                                                  include_variables=True)
        for node, host in zip(value['nodes'], selected):
            if (host['variables'].get('env') != node['environment']
                    or host['variables'].get('provider') != node['provider']):
                raise ValueError
            inputs[str(host['key'])] = True
        frozen = {path: {'sha256': digest_file(path, private=private), 'private': private}
                  for path, private in sorted(inputs.items())}
        plan = {**value, 'source': source(), 'inputs': frozen, 'site_trees': trees,
                'manual_dependency_review_required': True,
                'resources': sorted({host['address'] for host in selected}
                                    | {str(ROOT / 'ansible/inventory/generated.ini')})}
        write_document(plan_path, plan)
        with Journal(plan) as journal:
            journal.observe('maintenance', {'status': 'prepared', 'accepted_nodes': [], 'cleanup': 'absent'})
        return {'phase': 'prepared', 'plan_sha256': digest(plan), 'nodes': names}
    except (KeyError, TypeError, ValueError, yaml.YAMLError, fleet_inspection.InspectionError):
        raise MaintenanceError('invalid-maintenance-configuration') from None


def recheck(plan):
    deadline(plan)
    if source() != plan['source']:
        raise MaintenanceError('source-changed')
    for path, expected in plan['inputs'].items():
        if digest_file(path, private=expected['private']) != expected['sha256']:
            raise MaintenanceError('frozen-input-changed')
    for path, expected in plan['site_trees'].items():
        if site_manifest(path) != expected:
            raise MaintenanceError('frozen-site-tree-changed')


@contextmanager
def resource_lock(path):
    with open(path, 'r+b', opener=lambda name, flags:
              os.open(name, flags | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)) as stream:
        fd = stream.fileno()
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise MaintenanceError('unsafe-resource-lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        named = path.lstat()
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
            raise MaintenanceError('resource-lock-changed')
        yield


def locks(plan, stack):
    common = require_success(['git', 'rev-parse', '--git-common-dir']).decode().strip()
    parent = (ROOT / common).resolve() / 'maintenance-locks'
    parent.mkdir(mode=0o700, exist_ok=True)
    private_directory(parent)
    for name in plan['resources']:
        path = parent / (hashlib.sha256(name.encode()).hexdigest() + '.lock')
        try:
            stack.enter_context(resource_lock(path))
        except BlockingIOError:
            raise MaintenanceError('node-lock-busy: ' + lock_holder(plan, name)) from None


def lock_holder(plan, resource):
    """Name the contended resource; every run holds node addresses as targets."""
    inventory = ROOT / 'ansible/inventory/generated.ini'
    if resource == str(inventory):
        return 'resource=inventory held-as=shared-inventory'
    try:
        hosts = fleet_inspection.select_hosts(inventory, [node['host'] for node in plan['nodes']])
    except (OSError, ValueError, fleet_inspection.InspectionError):
        hosts = []
    aliases = [host['name'] for host in hosts if host['address'] == resource]
    return f"alias={aliases[0] if aliases else 'unresolved'} held-as=target"


def node_environment(plan, node, secret):
    values = {variable: literal(node[field]) for field, variable in PATH_ENV.items() if field in node}
    values.update(ENV=node['environment'], PROVIDER=node['provider'], ANSIBLE_LIMIT=node['host'],
                  SECRETS_FILE=str(secret), SOPS_FILE=str(secret.parent / 'approved.sops.yaml'),
                  SOPS_AGE_KEY_FILE=str(secret.parent / 'approved-age.key'),
                  AGE_KEY=str(secret.parent / 'approved-age.key'),
                  DEPLOY_APPROVED_INPUTS_FILE=str(secret.parent / 'approved-inputs.json'),
                  ANSIBLE_TAGS='', SKIP_PRECHECK='0', TAG_ON_SUCCESS='0')
    return command_environment(values)


def prepare_attempt(plan, node, runtime):
    for original, name in ((node['sops_file'], 'approved.sops.yaml'),
                           (plan['age_identity'], 'approved-age.key')):
        data = read_bytes(original)
        if hashlib.sha256(data).hexdigest() != plan['inputs'][original]['sha256']:
            raise MaintenanceError('frozen-input-changed')
        with new_file(runtime / name) as stream:
            stream.write(data)
    write_document(runtime / 'approved-inputs.json',
                   {'files': plan['inputs'], 'trees': plan['site_trees']})


def stage(plan, journal, node, goal, environment):
    if goal != 'clean':
        recheck(plan)
    sequence = journal.state['sequence'] + 1
    log = journal.directory / f'{sequence:06d}-{node["host"]}-{goal}.log.age'
    with journal.operation(goal, {'host': node['host'], 'source': plan['source']}):
        code = encrypted_command(['make', '--no-print-directory', goal], log, plan['log_recipient'],
                                 environment=environment, cwd=ROOT, defer_cancellation=goal == 'clean')
        if code:
            raise MaintenanceError('canonical-stage-failed')
    return log.name


def cleanup_retained(plan, journal):
    retained = journal.state['observed'].get('runtime')
    if retained is None:
        return
    path = Path(retained['path'])
    if path.parent != Path(plan['runtime_parent']) or not path.name.startswith('maintenance-'):
        raise MaintenanceError('invalid-retained-runtime')
    private_directory(plan['runtime_parent'])
    if not os.path.lexists(path):
        journal.observe('runtime', None)
        return
    private_directory(path)
    info = path.lstat()
    if [info.st_dev, info.st_ino] != retained['identity']:
        raise MaintenanceError('retained-runtime-changed')
    secret = path / 'credentials.yaml'
    environment = retained.get('environment', '')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', environment):
        raise MaintenanceError('invalid-retained-environment')
    selected = []
    for name in os.listdir(path):
        if (name != secret.name and name not in ATTEMPT_INPUTS
                and not re.fullmatch(r'\.vpn-' + re.escape(environment) + r'\.secrets\.[A-Za-z0-9]{6,}', name)):
            raise MaintenanceError('foreign-runtime-material')
        target = path / name
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            item = os.fstat(fd)
            if (not stat.S_ISREG(item.st_mode) or item.st_uid != os.geteuid()
                    or item.st_nlink != 1 or stat.S_IMODE(item.st_mode) != 0o600):
                raise MaintenanceError('unsafe-owned-plaintext')
        finally:
            os.close(fd)
        selected.append(target)
    for target in selected:
        target.unlink()
    path.rmdir()
    journal.observe('runtime', None)


def require_deployed_source(plan, node):
    """Fresh read-only proof that the live node manifest reports the plan source."""
    hosts = fleet_inspection.select_hosts(ROOT / 'ansible/inventory/generated.ini', [node['host']])
    module('validate-ansible-extra-vars').validate(Path(node['extra_vars']))
    values = yaml.load(read_bytes(node['extra_vars']), Loader=UniqueLoader)
    hosts[0]['transport'] = values.get('ansible_host', hosts[0]['transport'])
    hosts[0]['port'] = values.get('ansible_port', hosts[0]['port'])
    command = fleet_inspection.ssh_command(hosts[0], Path(node['known_hosts']))
    raw = fleet_inspection.bounded_command(command, timeout=30,
                input_bytes=Path(fleet_inspection.__file__).read_bytes(),
                environment=command_environment())
    now = datetime.now(timezone.utc)
    report = fleet_inspection.validate_report(fleet_inspection.decode_json(raw), now)
    manifest = report['manifest']
    if (now - fleet_inspection.parse_time(report['observed_at']) > timedelta(seconds=30)
            or manifest.get('status') != 'observed'
            or manifest.get('source_revision') != plan['source']['revision']
            or manifest.get('deployable_digest') != plan['source']['deployable_digest']):
        raise MaintenanceError('deployed-source-acceptance-failed')


def converged_on_resume(plan, journal, node, action):
    """A resumed node skips dry-run and deploy only after a fresh live source proof."""
    if action != 'resume' or journal.state['observed'].get('converged') != {
            'host': node['host'], 'source': plan['source']}:
        return False
    recheck(plan)
    try:
        require_deployed_source(plan, node)
    except MaintenanceError as error:
        if str(error) != 'deployed-source-acceptance-failed':
            raise
        return False
    except (ReadinessError, fleet_inspection.InspectionError):
        # The node could not be observed: converge again through the complete sequence.
        # Local input errors propagate, because a second deploy cannot repair them.
        return False
    return True


def protocol_gate(plan, journal, node):
    recheck(plan)
    with journal.operation('protocol-gate', {'host': node['host'], 'source': plan['source']}):
        require_deployed_source(plan, node)
        selected = [{'current': node['provider'] + ':' + node['environment'],
                     'inventory_alias': node['host']}]
        if healthy_survivors(plan['liveness_config'], selected) != {node['host']}:
            raise MaintenanceError('authenticated-protocol-acceptance-failed')
    journal.observe('protocol_acceptance', {'host': node['host'],
                                          'at': datetime.now(timezone.utc).isoformat(),
                                          'source': plan['source']})


def cleanup_node(plan, journal, node, environment, secret, runtime, state, logs):
    complete = False
    try:
        logs.append(stage(plan, journal, node, 'clean', environment))
        if os.path.lexists(secret):
            raise MaintenanceError('plaintext-cleanup-failed')
        cleanup_retained(plan, journal)
        state['cleanup'] = 'absent'
        complete = True
    finally:
        if not complete:
            state['cleanup'] = 'failed'
            try:
                cleanup_retained(plan, journal)
                state['cleanup'] = 'absent-after-canonical-clean-failure'
            except (OSError, RecoveryError):
                # Retain foreign or changed material and report failed cleanup.
                pass
            state['status'] = 'failed'
            journal.observe('maintenance', state)
            raise MaintenanceError('plaintext-cleanup-failed') from None


def execute(plan, action, approval, *, ready_fd=None):
    with ExitStack() as stack:
        locks(plan, stack)
        journal = stack.enter_context(Journal(plan))
        state = journal.state['observed']['maintenance']
        if state['status'] == 'complete':
            raise MaintenanceError('operation-already-complete')
        if action != 'preview':
            expected = state.get('review_sha256')
            if (not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected)
                    or approval != expected or not state.get('preview_logs')
                    or digest({'plan': plan, 'logs': {name: digest_file(journal.directory / name)
                                                     for name in state['preview_logs']}}) != expected):
                raise MaintenanceError('reviewed-preview-required')
            if action == 'start' and state['status'] != 'previewed':
                raise MaintenanceError('use-resume-for-interrupted-operation')
        cleanup_retained(plan, journal)
        recheck(plan)
        if ready_fd is not None:
            os.write(ready_fd, b'ready');os.close(ready_fd)
        state = {**state, 'status': 'running', 'action': action}
        journal.observe('maintenance', state)
        for node in plan['nodes']:
            if action != 'preview' and node['host'] in state['accepted_nodes']:
                continue
            runtime = Path(tempfile.mkdtemp(prefix='maintenance-', dir=private_directory(plan['runtime_parent'])))
            info = runtime.lstat()
            journal.observe('runtime', {'path': str(runtime), 'identity': [info.st_dev, info.st_ino],
                                        'environment': node['environment']})
            secret = runtime / 'credentials.yaml'
            environment = node_environment(plan, node, secret)
            logs = []
            try:
                prepare_attempt(plan, node, runtime)
                logs.append(stage(plan, journal, node, 'decrypt', environment))
                goals = ('dry-run',) if action == 'preview' else STAGES
                if converged_on_resume(plan, journal, node, action):
                    goals = STAGES[STAGES.index('deploy') + 1:]
                    journal.observe('resumed_at_acceptance', {'host': node['host'], 'source': plan['source']})
                elif action != 'preview':
                    # A new deploy can stop after the node manifest is written; never trust an older record.
                    journal.observe('converged', None)
                for goal in goals:
                    logs.append(stage(plan, journal, node, goal, environment))
                    if goal == 'deploy':
                        journal.observe('converged', {'host': node['host'], 'source': plan['source']})
                if action != 'preview':
                    protocol_gate(plan, journal, node)
            finally:
                primary = sys.exception()
                failed_intent = journal.state['intent']
                if primary is not None:
                    journal.state['observed']['failed_stage'] = failed_intent
                cleanup_node(plan, journal, node, environment, secret, runtime, state, logs)
                if primary is not None:
                    state['status'] = 'failed'
                    journal.state['intent'] = failed_intent
                    journal.observe('maintenance', state)
            if action != 'preview':
                state['accepted_nodes'].append(node['host'])
            state.setdefault('logs', []).extend(logs)
            journal.observe('maintenance', state)
        state['status'] = 'previewed' if action == 'preview' else 'complete'
        if action == 'preview':
            state['preview_logs'] = list(state['logs'])
            state['review_sha256'] = digest({'plan': plan, 'logs': {
                name: digest_file(journal.directory / name) for name in state['preview_logs']}})
        journal.observe('maintenance', state)
        return state


def read_status(plan):
    directory = private_directory(plan['state_directory'])
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open('journal.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            # A writer can replace this complete immutable inode after open.
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink not in (0, 1) or stat.S_IMODE(info.st_mode) != 0o600):
                raise MaintenanceError('unsafe-status-journal')
            raw = stream.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise MaintenanceError('status-journal-limit')
            state = json.loads(raw, object_pairs_hook=unique)
    finally:
        os.close(parent)
    if state['manifest_sha256'] != digest(plan):
        raise MaintenanceError('journal-plan-mismatch')
    return state


def status(plan):
    private_directory(plan['state_directory'])
    fd = os.open(Path(plan['state_directory']) / 'recovery.lock', os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            active = False
        except BlockingIOError:
            active = True
        state = read_status(plan)
    finally:
        os.close(fd)
    result = dict(state['observed']['maintenance'])
    result['worker_active'] = active
    result['fresh_live_verification'] = False
    if result['status'] == 'running' and not active:
        result['status'] = 'interrupted'
    return result


def launch(plan_path, action, approval):
    read_fd, write_fd = os.pipe()
    try:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_worker',
                                  '--plan', str(plan_path), '--worker-action', action,
                                  '--approval', approval or '', '--ready-fd', str(write_fd)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True, pass_fds=(write_fd,), env=command_environment())
        os.close(write_fd);write_fd = None
        ready, _, _ = select.select([read_fd], [], [], 15)
        reply = os.read(read_fd, 128) if ready else b''
        if LOCK_BUSY.fullmatch(reply):
            raise MaintenanceError(reply.decode('ascii'))
        if reply != b'ready':
            raise MaintenanceError('worker-start-refused')
        return {'phase': 'started', 'pid': child.pid, 'action': action}
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'preview', 'start', 'resume', 'status', '_worker'))
    parser.add_argument('--config', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--approval')
    parser.add_argument('--worker-action', choices=('preview', 'start', 'resume'))
    parser.add_argument('--ready-fd', type=int)
    args = parser.parse_args()
    try:
        with cancellation():
            if args.action == 'prepare':
                if args.config is None:
                    raise MaintenanceError('configuration-required')
                result = prepare(args.config, args.plan)
            elif args.action == 'status':
                result = status(document(args.plan))
            elif args.action == '_worker':
                result = execute(document(args.plan), args.worker_action, args.approval, ready_fd=args.ready_fd)
            else:
                result = launch(args.plan, args.action, args.approval)
            print(json.dumps(result, sort_keys=True))
        return 0
    except MaintenanceError as error:
        if args.action == '_worker' and args.ready_fd is not None and str(error).startswith('node-lock-busy: '):
            os.write(args.ready_fd, str(error).encode('ascii'))
        print(f'maintenance: operation refused ({error}); inspect private journal and encrypted diagnostics',
              file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, ReadinessError, RecoveryError, RotationError,
            yaml.YAMLError, fleet_inspection.InspectionError):
        print('maintenance: operation refused; inspect private journal and encrypted diagnostics', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
