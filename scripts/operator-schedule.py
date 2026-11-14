#!/usr/bin/env python3
"""Schedule bounded drift verification and authenticated offsite kit backups."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import signal
import subprocess
import sys
import tempfile

from bootstrap_readiness import ReadinessError, cancellation
from operator_maintenance_io import (MaintenanceError, ROOT, command_environment, digest_file,
                                    encrypted_command, new_file, private_directory, private_lock,
                                    read_bytes, update_document, write_document)
from recovery_io import document, module, digest, Journal, unique

JOBS = ('drift', 'backup')
FIELDS = {'schema_version', 'id', 'expires_at', 'state_directory', 'maintenance_config',
          'backup_config', 'backup_profile', 'jobs'}
# Time for the drift child to finish deferred plaintext cleanup after its own deadline.
CLEANUP_GRACE_SECONDS = 300


def now():
    return datetime.now(timezone.utc).isoformat()


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise MaintenanceError('timezone-required')
    return parsed.timestamp()


def budget(plan, job):
    remaining = stamp(plan['expires_at']) - datetime.now(timezone.utc).timestamp()
    if remaining <= 0:
        raise MaintenanceError('authorization-expired-before-command')
    return min(plan['jobs'][job]['timeout_seconds'], remaining)


def cron_interval(seconds):
    if type(seconds) is not int or seconds < 60 or seconds > 86400 or seconds % 60:
        raise MaintenanceError('invalid-schedule-interval')
    if seconds < 3600 and 3600 % seconds == 0:
        return f'*/{seconds // 60} * * * *'
    if seconds % 3600 == 0 and 86400 % seconds == 0:
        return f'0 */{seconds // 3600} * * *' if seconds < 86400 else '0 3 * * *'
    raise MaintenanceError('unsupported-schedule-interval')


def prepare(config_path, output):
    config = document(config_path)
    fleet = module('fleet-maintenance')
    if (set(config) != FIELDS or type(config['schema_version']) is not int or config['schema_version'] != 1
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', config['id'])
            or set(config['jobs']) != set(JOBS)):
        raise MaintenanceError('invalid-schedule-configuration')
    fleet.deadline(config)
    state = private_directory(fleet.absolute(config['state_directory']))
    if any(state.iterdir()):
        raise MaintenanceError('empty-schedule-state-directory-required')
    for job in JOBS:
        item = config['jobs'][job]
        if set(item) != {'interval_seconds', 'timeout_seconds', 'max_age_seconds'}:
            raise MaintenanceError('invalid-job-policy')
        cron_interval(item['interval_seconds'])
        if (type(item['timeout_seconds']) is not int or not 60 <= item['timeout_seconds'] <= 14400
                or type(item['max_age_seconds']) is not int
                or item['max_age_seconds'] < item['interval_seconds'] + item['timeout_seconds']):
            raise MaintenanceError('invalid-job-deadline')
    for field in ('maintenance_config', 'backup_config', 'backup_profile'):
        fleet.absolute(config[field])
    maintenance = document(config['maintenance_config'])
    fleet.deadline(maintenance)
    if stamp(config['expires_at']) > stamp(maintenance['expires_at']):
        raise MaintenanceError('schedule-exceeds-maintenance-grant')
    kit = module('operator-kit').configuration(config['backup_config'])
    kit_root = Path(kit['kit']).resolve()
    if state.is_relative_to(kit_root) and not state.is_relative_to(kit_root / 'runtime'):
        raise MaintenanceError('schedule-runtime-must-be-excluded-from-backup')
    # Use ordinary preparation to discover inventory, site and probe dependencies.
    with tempfile.TemporaryDirectory(prefix='schedule-prepare-', dir=state) as scratch:
        scratch = Path(scratch)
        operation = scratch / 'operation'
        operation.mkdir(mode=0o700)
        candidate = {**maintenance, 'state_directory': str(operation)}
        write_document(scratch / 'config.json', candidate)
        fleet.prepare(scratch / 'config.json', scratch / 'plan.json')
        prepared = document(scratch / 'plan.json')
    inputs = dict(prepared['inputs'])
    for path in (config['maintenance_config'], config['backup_config'], config['backup_profile'], kit['identity']):
        inputs[path] = {'sha256': digest_file(path), 'private': True}
    plan = {**config, 'source': prepared['source'], 'inputs': inputs,
            'maintenance_inputs': prepared['inputs'],
            'site_trees': prepared['site_trees'], 'log_recipient': maintenance['log_recipient'],
            'path': command_environment()['PATH'], 'python': sys.executable}
    write_document(output, plan)
    return {'phase': 'prepared', 'jobs': list(JOBS), 'installed': False}


def recheck(plan):
    fleet = module('fleet-maintenance')
    fleet.recheck(plan)


def publish(path, value):
    if os.path.lexists(path):
        update_document(path, digest_file(path), value)
    else:
        write_document(path, value)


def drift(plan, directory):
    recheck(plan)
    fleet = module('fleet-maintenance')
    operation = directory / 'operation'
    operation.mkdir(mode=0o700)
    raw = read_bytes(plan['maintenance_config'])
    if hashlib.sha256(raw).hexdigest() != plan['inputs'][plan['maintenance_config']]['sha256']:
        raise MaintenanceError('frozen-maintenance-configuration-changed')
    config = {**json.loads(raw, object_pairs_hook=unique), 'state_directory': str(operation)}
    write_document(directory / 'maintenance.json', config)
    fleet.prepare(directory / 'maintenance.json', directory / 'maintenance-plan.json')
    prepared = document(directory / 'maintenance-plan.json')
    if (prepared['inputs'] != plan['maintenance_inputs'] or prepared['source'] != plan['source']
            or prepared['site_trees'] != plan['site_trees']):
        raise MaintenanceError('frozen-maintenance-inputs-changed')
    fleet.execute(prepared, 'check', None)


def cleanup_identity(plan, directory):
    directory = private_directory(directory)
    if directory.parent != Path(plan['state_directory']) or not directory.name.startswith('backup-'):
        raise MaintenanceError('foreign-schedule-runtime')
    key = directory / 'working-age.key'
    if os.path.lexists(key):
        original = directory / 'original-backup.json'
        if digest_file(original) != plan['inputs'][plan['backup_config']]['sha256']:
            raise MaintenanceError('retained-backup-config-changed')
        identity = document(original)['identity']
        if digest_file(key) != plan['inputs'][identity]['sha256']:
            raise MaintenanceError('retained-backup-identity-changed')
        key.unlink()


def cleanup_previous(plan, directory, job):
    directory = private_directory(directory)
    if directory.parent != Path(plan['state_directory']) or not directory.name.startswith(job + '-'):
        raise MaintenanceError('foreign-schedule-runtime')
    if job == 'backup':
        cleanup_identity(plan, directory)
    elif os.path.lexists(directory / 'maintenance-plan.json'):
        previous = document(directory / 'maintenance-plan.json')
        if previous['state_directory'] != str(directory / 'operation'):
            raise MaintenanceError('foreign-maintenance-runtime')
        fleet = module('fleet-maintenance')
        with ExitStack() as stack:
            fleet.locks(previous, stack)
            journal = stack.enter_context(Journal(previous))
            fleet.cleanup_retained(previous, journal)


def run(plan, config_path, job):
    state = private_directory(plan['state_directory'])
    with private_lock(state / f'{job}.lock'):
        path = state / f'{job}.json'
        previous = document(path) if os.path.lexists(path) else {}
        if previous and previous.get('plan_sha256') != digest(plan):
            raise MaintenanceError('schedule-state-plan-conflict')
        result = {'schema_version': 1, 'job': job, 'phase': 'running', 'started_at': now(),
                  'plan_sha256': digest(plan),
                  'last_success_at': previous.get('last_success_at')}
        if previous.get('run_directory'):
            result['run_directory'] = previous['run_directory']
        publish(path, result)
        directory = None
        try:
            if previous.get('run_directory'):
                cleanup_previous(plan, Path(previous['run_directory']), job)
            recheck(plan)
            directory = Path(tempfile.mkdtemp(prefix=job + '-', dir=state))
            result['run_directory'] = str(directory)
            publish(path, result)
            frozen_plan = directory / 'schedule.json'
            write_document(frozen_plan, plan)
            if job == 'drift':
                command = [sys.executable, str(ROOT / 'scripts/operator-schedule.py'), '_drift',
                           '--config', str(frozen_plan), '--output', str(directory),
                           '--plan-sha256', digest(plan)]
            else:
                def copy_input(original, name):
                    raw = read_bytes(original)
                    if hashlib.sha256(raw).hexdigest() != plan['inputs'][original]['sha256']:
                        raise MaintenanceError('frozen-input-changed')
                    destination = directory / name
                    with new_file(destination) as stream:
                        stream.write(raw)
                    return destination

                copied_config = copy_input(plan['backup_config'], 'original-backup.json')
                backup = document(copied_config)
                backup['identity'] = str(copy_input(backup['identity'], 'working-age.key'))
                write_document(directory / 'backup-config.json', backup)
                profile = copy_input(plan['backup_profile'], 'profile.sops.json')
                command = ['make', 'routine-backup', 'PROFILE=' + str(profile),
                           'CONFIG=' + str(directory / 'backup-config.json'), 'OUTPUT=' + str(directory / 'backup.json')]
            limit = budget(plan, job)
            if job == 'drift':
                # The drift child cancels itself at the limit and cleans node plaintext; its
                # stages run in separate sessions that a kill of the child would orphan.
                limit += CLEANUP_GRACE_SECONDS
            code = encrypted_command(command, directory / 'command.log.age', plan['log_recipient'],
                environment=command_environment({'PATH': plan['path']}), cwd=ROOT, timeout=limit)
            if code:
                raise MaintenanceError('scheduled-command-failed')
            if job == 'backup':
                receipt = document(directory / 'backup.json')
                if (receipt.get('phase') != 'offsite-download-decrypt-manifest-verified'
                        or receipt.get('delivery', {}).get('remote_verified') is not True
                        or type(receipt.get('files_verified')) is not int or receipt['files_verified'] < 1
                        or not re.fullmatch('[0-9a-f]{64}', receipt.get('manifest_sha256', ''))
                        or stamp(receipt['at']) < stamp(result['started_at'])):
                    raise MaintenanceError('verified-backup-receipt-required')
            else:
                receipt = document(directory / 'operation/journal.json')['observed']['maintenance']
                if receipt.get('status') != 'checked' or receipt.get('cleanup') != 'absent':
                    raise MaintenanceError('completed-drift-check-required')
            if job == 'backup':
                cleanup_identity(plan, directory)
            result.update(phase='succeeded', finished_at=now())
            result['last_success_at'] = result['finished_at']
            publish(path, result)
            return result
        except BaseException:
            result.update(phase='failed', finished_at=now())
            publish(path, result)
            raise
        finally:
            if job == 'backup' and directory is not None:
                cleanup_identity(plan, directory)


def status(plan):
    state = private_directory(plan['state_directory'])
    results = {}
    for job in JOBS:
        path = state / f'{job}.json'
        result = document(path) if os.path.lexists(path) else {'phase': 'never-run', 'last_success_at': None}
        if result['phase'] != 'never-run' and result.get('plan_sha256') != digest(plan):
            results[job] = {'phase': 'different-plan', 'overdue': True}
            continue
        if result['phase'] == 'running':
            try:
                with private_lock(state / f'{job}.lock'):
                    result = {**result, 'phase': 'interrupted'}
            except BlockingIOError:
                pass
        last = result.get('last_success_at')
        age = datetime.now(timezone.utc).timestamp() - stamp(last) if last else None
        result = {**result, 'overdue': age is None or age < 0 or age > plan['jobs'][job]['max_age_seconds']}
        results[job] = result
    return {'jobs': results, 'authorization_expired': stamp(plan['expires_at']) <= datetime.now(timezone.utc).timestamp(),
            'fresh_live_verification': False}


def render(plan, config_path, system):
    config_path = Path(config_path).absolute()
    # Cron treats percent as input redirection even inside shell quotes.
    for value in (str(config_path), str(ROOT), plan['python'], plan['path']):
        if any(char in value for char in ('\n', '\r', '%')):
            raise MaintenanceError('unsafe-scheduler-path')
    rendered = {}
    for job in JOBS:
        label = 'org.ripdpi.operator.' + plan['id'] + '.' + job
        args = [plan['python'], str(ROOT / 'scripts/operator-schedule.py'), 'run',
                '--config', str(config_path), '--job', job, '--plan-sha256', digest(plan)]
        if system == 'Darwin':
            rendered[label + '.plist'] = plistlib.dumps({
                'Label': label, 'ProgramArguments': args, 'WorkingDirectory': str(ROOT),
                'EnvironmentVariables': {'PATH': plan['path']},
                'StartInterval': plan['jobs'][job]['interval_seconds'], 'ProcessType': 'Background',
                'StandardOutPath': '/dev/null', 'StandardErrorPath': '/dev/null'}).decode()
        elif system == 'Linux':
            rendered[job] = cron_interval(plan['jobs'][job]['interval_seconds']) + ' ' + shlex.join(args) + ' >/dev/null 2>&1'
        else:
            raise MaintenanceError('unsupported-scheduler-platform')
    return rendered


def scheduler_command(argv, **kwargs):
    result = subprocess.run(argv, capture_output=True, timeout=30, env=command_environment(), **kwargs)
    if result.returncode:
        raise MaintenanceError('scheduler-command-failed')
    return result.stdout


def install(plan, config_path, *, remove=False):
    system = os.uname().sysname
    rendered = render(plan, config_path, system)
    if not remove:
        recheck(plan)
    if system == 'Darwin':
        parent = Path.home() / 'Library/LaunchAgents'
        # Never change the permissions of a pre-existing user directory.
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        domain = f'gui/{os.getuid()}'
        for filename, contents in rendered.items():
            destination = parent / filename
            label = filename.removesuffix('.plist')
            if os.path.lexists(destination):
                if read_bytes(destination).decode() != contents:
                    raise MaintenanceError('scheduler-file-conflict')
                loaded = subprocess.run(['launchctl', 'print', domain + '/' + label],
                                        capture_output=True, timeout=30, env=command_environment())
                if loaded.returncode == 0:
                    if not remove:
                        continue
                    scheduler_command(['launchctl', 'bootout', domain + '/' + label])
                if remove:
                    destination.unlink()
                    continue
            elif remove:
                continue
            else:
                # LaunchAgents is commonly 0755; publish through a private staging directory.
                with tempfile.TemporaryDirectory(prefix='.operator-', dir=parent) as scratch:
                    private_directory(scratch)
                    staged = Path(scratch) / filename
                    with staged.open('xb') as stream:
                        os.chmod(staged, 0o600)
                        stream.write(contents.encode())
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.link(staged, destination, follow_symlinks=False)
            scheduler_command(['launchctl', 'bootstrap', domain, str(destination)])
    else:
        existing = subprocess.run(['crontab', '-l'], capture_output=True, timeout=30, env=command_environment())
        if existing.returncode and b'no crontab' not in existing.stderr.lower():
            raise MaintenanceError('crontab-read-failed')
        lines = existing.stdout.decode().splitlines()
        start, end = '# ripdpi-operator:' + plan['id'] + ':BEGIN', '# ripdpi-operator:' + plan['id'] + ':END'
        if lines.count(start) != lines.count(end) or lines.count(start) > 1:
            raise MaintenanceError('malformed-schedule-block')
        if start in lines:
            first, last = lines.index(start), lines.index(end)
            if first >= last:
                raise MaintenanceError('malformed-schedule-block')
            del lines[first:last + 1]
        if not remove:
            lines.extend([start, *rendered.values(), end])
        scheduler_command(['crontab', '-'], input=('\n'.join(lines) + '\n').encode())
    return {'phase': 'removed' if remove else 'installed', 'jobs': list(JOBS)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'render', 'install', 'remove', 'run', 'status', '_drift'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--job', choices=JOBS)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    try:
        with cancellation(signals=(signal.SIGINT, signal.SIGTERM, signal.SIGALRM)):
            if args.action == 'prepare':
                if args.output is None:
                    raise MaintenanceError('output-required')
                result = prepare(args.config, args.output)
            else:
                plan = document(args.config)
                if args.plan_sha256 is not None and digest(plan) != args.plan_sha256:
                    raise MaintenanceError('schedule-plan-changed')
                if args.action not in {'status', 'remove', 'render'}:
                    if plan['python'] != sys.executable:
                        raise MaintenanceError('scheduled-python-changed')
                    os.environ['PATH'] = plan['path']
                if args.action == 'render':
                    result = render(plan, args.config, os.uname().sysname)
                elif args.action in {'install', 'remove'}:
                    result = install(plan, args.config, remove=args.action == 'remove')
                elif args.action == 'status':
                    result = status(plan)
                elif args.action == '_drift':
                    if args.output is None:
                        raise MaintenanceError('output-required')
                    signal.setitimer(signal.ITIMER_REAL, budget(plan, 'drift'))
                    drift(plan, private_directory(args.output))
                    result = {'phase': 'checked'}
                else:
                    if args.job is None:
                        raise MaintenanceError('job-required')
                    result = run(plan, args.config, args.job)
            print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, ReadinessError, subprocess.SubprocessError):
        print('operator-schedule: operation refused; inspect private job status and encrypted diagnostics', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
