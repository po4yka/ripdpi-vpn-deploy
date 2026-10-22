"""Bounded canonical executors for private, resumable replacement recovery."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

import bootstrap_readiness
import fleet_inspection
from recovery_io import (
    ROOT,
    RecoveryError,
    canonical,
    digest,
    document,
    file_digest,
    module,
    read,
)
from recovery_provider import review_plan, server_from_state


class Runtime:
    def __init__(self, manifest, manifest_path, journal):
        self.manifest, self.path, self.journal = manifest, str(manifest_path), journal
        self.root = ROOT
        self.inventory = ROOT / 'ansible/inventory/generated.ini'
        self.tfroot = ROOT / 'terraform/providers/upcloud'
        self.environment = {key: os.environ[key] for key in (
            'PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR',
            'UPCLOUD_TOKEN', 'UPCLOUD_USERNAME', 'UPCLOUD_PASSWORD',
            'UPCLOUD_API_USERNAME', 'UPCLOUD_API_PASSWORD', 'TAILSCALE_AUTH_KEY') if key in os.environ}
        self.cleanup_plaintext()
        self.environment.update({'PROVIDER': 'upcloud', 'ENV': manifest['environment'],
            'TF_IN_AUTOMATION': 'true', 'TF_INPUT': '0', 'PYTHONNOUSERSITE': '1',
            'PYTHONDONTWRITEBYTECODE': '1', 'SOPS_AGE_KEY_FILE': manifest['age_key_file'],
            'SOPS_FILE': manifest['sops_file'], 'ANSIBLE_SSH_PRIVATE_KEY_FILE': manifest['ssh_key_file'],
            'INSPECT_KNOWN_HOSTS': manifest['known_hosts_file']})

    def cleanup_plaintext(self):
        if not self.journal.state['observed'].get('plaintext_owned'):
            return
        names = ['runtime-secrets.yaml', *[name for name in os.listdir(self.journal.fd)
            if name.startswith('.vpn-' + self.manifest['environment'] + '.secrets.')]]
        if len(names) > 33:
            raise RecoveryError('recovery-plaintext-cleanup-bound')
        for name in names:
            try:
                info = os.stat(name, dir_fd=self.journal.fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise RecoveryError('recovery-plaintext-output-changed')
            os.unlink(name, dir_fd=self.journal.fd)
        os.fsync(self.journal.fd)
        self.journal.observe('plaintext_owned', False)

    def command(self, name, argv, *, extra=None, timeout=900, allowed=(0,)):
        if document(self.path) != self.manifest:
            raise RecoveryError('recovery-manifest-changed')
        self.journal.verify()
        stderr = bytearray()
        environment = self.environment | (extra or {})
        if name != 'bootstrap-tailnet':
            environment.pop('TAILSCALE_AUTH_KEY', None)
        if name not in {'observe-provider', 'init', 'plan', 'apply', 'import-server'}:
            for key in ('UPCLOUD_TOKEN', 'UPCLOUD_USERNAME', 'UPCLOUD_PASSWORD',
                        'UPCLOUD_API_USERNAME', 'UPCLOUD_API_PASSWORD'):
                environment.pop(key, None)
        with self.journal.operation(name, {'argv_sha256': digest(argv)}):
            try:
                status, output = bootstrap_readiness.run_command(argv, timeout=timeout,
                    environment=environment, cwd=self.root, capture=True,
                    stderr_output=stderr, output_limit=1_048_576)
            except (OSError, bootstrap_readiness.ReadinessError):
                self.journal.write(f'command-{self.journal.state["sequence"]}.stderr', bytes(stderr) or b'no diagnostics\n')
                raise RecoveryError('recovery-child-interrupted') from None
            self.journal.write(f'command-{self.journal.state["sequence"]}.stdout', output or b'no output\n')
            self.journal.write(f'command-{self.journal.state["sequence"]}.stderr', bytes(stderr) or b'no diagnostics\n')
            if status not in allowed:
                raise RecoveryError('recovery-child-failed-' + name)
            return status, output

    def make(self, goal, *, extra=None, allowed=(0,)):
        fields = dict(extra or {})
        if goal != 'bootstrap-tailnet':
            fields.update(PROVIDER='upcloud', ENV=self.manifest['environment'],
                SOPS_FILE=self.manifest['sops_file'],
                ANSIBLE_SSH_PRIVATE_KEY_FILE=self.manifest['ssh_key_file'],
                INSPECT_KNOWN_HOSTS=self.manifest['known_hosts_file'])
        return self.command(goal, ['make', '--no-print-directory', goal,
            *[key + '=' + value for key, value in fields.items()]], extra=extra, allowed=allowed,
            timeout=4200 if goal in {'dry-run', 'deploy'} else 900)

    def terraform(self, *args, name='terraform', allowed=(0,)):
        return self.command(name, [str(self.root / 'scripts/terraform-env.sh'), *args], allowed=allowed)

    def source(self):
        deploy = module('deploy-controller')
        try:
            identity = deploy.source_identity(self.root, self.environment, require_clean=True)
        except deploy.DeployError:
            raise RecoveryError('recovery-clean-source-required') from None
        if identity['DEPLOY_SOURCE_REVISION'] != self.manifest['source_revision']:
            raise RecoveryError('recovery-source-revision-changed')
        return identity

    def observe(self):
        _, raw = self.command('observe-provider', [sys.executable, str(self.root / 'scripts/recovery_provider.py'),
            '--manifest', self.path], timeout=45)
        value = json.loads(raw)
        if (set(value) != {'account_sha256', 'servers'} or len(value['servers']) > 1
                or value['account_sha256'] != hashlib.sha256(self.manifest['account'].encode()).hexdigest()):
            raise RecoveryError('recovery-provider-observation-invalid')
        return value

    def state(self):
        # This provider root has a local backend. A missing local state is the only
        # absent-state case; authentication/CLI failures are never treated as empty.
        path = self.tfroot / 'terraform.tfstate.d' / self.manifest['environment'] / 'terraform.tfstate'
        if not os.path.lexists(path):
            return None
        return server_from_state(json.loads(read(path, limit=16_777_216)), self.manifest)

    def inputs(self):
        return {'source': self.source(), 'tfvars_sha256': file_digest(
            self.tfroot / 'environments' / (self.manifest['environment'] + '.tfvars'), private=False)}

    def plan(self, existing):
        inputs = self.inputs()
        self.make('plan')
        saved = self.tfroot / (self.manifest['environment'] + '.tfplan')
        payload = read(saved, private=False, limit=16_777_216)
        path = self.journal.write('approved.tfplan', payload)
        _, raw = self.terraform('show', '-json', str(path), name='inspect-plan')
        parsed = json.loads(raw)
        reviewed = review_plan(parsed, self.manifest, existing=existing)
        plan_json = self.journal.write('approved-plan.json', raw)
        self.command('plan-policy', [str(self.root / 'scripts/check-tf-plan.sh'), str(plan_json)])
        if self.inputs() != inputs:
            raise RecoveryError('recovery-plan-input-changed')
        return {'plan_sha256': hashlib.sha256(payload).hexdigest(), 'review': reviewed,
                'inputs': inputs, 'state_sha256': digest(existing)}

    def apply(self, retained):
        path = self.journal.directory / 'approved.tfplan'
        payload = read(path, limit=16_777_216)
        if hashlib.sha256(payload).hexdigest() != retained['plan_sha256'] or self.inputs() != retained['inputs']:
            raise RecoveryError('recovery-approved-plan-changed')
        # As in policy-plan.sh, policy and apply consume one private per-operation
        # snapshot. Replacing the retained approval file cannot change this apply.
        with tempfile.TemporaryDirectory(prefix='apply-', dir=self.journal.directory) as owned:
            frozen = module('deploy-controller').private_file(Path(owned) / 'plan.tfplan', payload)
            _, raw = self.terraform('show', '-json', str(frozen), name='recheck-plan')
            review_plan(json.loads(raw), self.manifest, existing=self.state())
            policy = self.journal.write('apply-policy.json', raw)
            self.command('apply-policy', [str(self.root / 'scripts/check-tf-plan.sh'), str(policy)])
            if file_digest(frozen) != retained['plan_sha256'] or self.inputs() != retained['inputs']:
                raise RecoveryError('recovery-approved-plan-changed')
            self.terraform('apply', str(frozen), name='apply')

    def import_server(self, server):
        self.source()
        self.terraform('import', '-var-file=environments/' + self.manifest['environment'] + '.tfvars',
                       'upcloud_server.vpn', server['uuid'], name='import-server')

    def migration_contract(self):
        from device_migration_io import load_plan
        plan = load_plan(self.manifest['migration_plan'])
        for key in ('age_key_file', 'ssh_key_file', 'sops_file'):
            read(self.manifest[key])
        _, selector = self.command('observability-scope', [sys.executable,
            str(self.root / 'scripts/validate-secrets.py'), '--print-observability-selector',
            *[part for row in self.manifest['inventory'] for part in ('--environment', row['host'].split(':')[1])]])
        if selector.strip() != b'false':
            raise RecoveryError('recovery-observability-topology-not-supported')
        target = plan['target']
        publication = plan['publication']
        if (len(target['alias']) > 64 or target['host'] != 'upcloud:' + self.manifest['environment']
                or target['cohort'] != self.manifest['cohort']
                or Path(target['secrets_file']).resolve() != Path(self.manifest['sops_file']).resolve()
                or Path(plan['known_hosts']).resolve() != Path(self.manifest['known_hosts_file']).resolve()
                or Path(plan['inventory']).resolve() != self.inventory.resolve()
                or publication['source_alias'] != publication['target_alias']
                or publication['target_alias'] in {plan['source']['alias'], target['alias']}):
            raise RecoveryError('recovery-requires-surviving-dedicated-publisher')
        return plan

    def inventory_render(self, handoff=None):
        rows = self.manifest['inventory']
        target = 'upcloud:' + self.manifest['environment']
        self.make('inventory', extra={'HOSTS': ','.join(row['host'] for row in rows),
            'COHORTS': ','.join(row['cohort'] for row in rows),
            'TAILNET_HANDOFFS': ','.join((str(handoff) if row['host'] == target else row['handoff']) or '-' for row in rows)})
        plan = self.migration_contract()
        hosts = fleet_inspection.select_hosts(self.inventory, [plan['target']['alias']], include_variables=True)
        host = hosts[0]
        if host['key'] != self.manifest['ssh_key_file']:
            raise RecoveryError('recovery-inventory-key-mismatch')
        return host

    def pin_binding(self, server, host):
        config = document(self.manifest['bootstrap_config'])
        if (config['provider'] != 'upcloud' or config['environment'] != self.manifest['environment']
                or config['inventory_alias'] != host['name'] or host['address'] not in server['public_ipv4']
                or config['public_address'] != host['address'] or config['ssh_port'] != host['port']
                or config['source_revision'] != self.manifest['source_revision']
                or config['deployable_digest'] != self.source()['DEPLOYABLE_SOURCE_DIGEST']
                or Path(config['known_hosts']).resolve() != Path(self.manifest['known_hosts_file']).resolve()):
            raise RecoveryError('recovery-bootstrap-binding-changed')
        pin = read(self.manifest['known_hosts_file'], private=False)
        lookup = host['alias'] if host['port'] == 22 else '[' + host['alias'] + ']:' + str(host['port'])
        snapshot = self.journal.write('reviewed-known-hosts', pin)
        _, found = self.command('inspect-host-pin', ['ssh-keygen', '-F', lookup, '-f', str(snapshot)])
        matches = set()
        for line in found.decode().splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[1] == 'ssh-ed25519':
                matches.add(hashlib.sha256(base64.b64decode(fields[2], validate=True)).hexdigest())
        if matches != {config['host_key_sha256']}:
            raise RecoveryError('recovery-authenticated-host-pin-required')
        return {'server': server, 'known_hosts_sha256': hashlib.sha256(pin).hexdigest(),
            'bootstrap_config_sha256': file_digest(self.manifest['bootstrap_config']),
            'ssh_key_sha256': file_digest(self.manifest['ssh_key_file'])}

    def management(self, host):
        self.source()
        pins = self.journal.directory / 'reviewed-known-hosts'
        ssh = fleet_inspection.ssh_command(host, pins)[:-1]
        with self.journal.operation('wait-pinned-bootstrap', {'alias': host['name']}):
            bootstrap_readiness.wait_for_bootstrap(ssh, environment=self.environment, first_boot=True)
        self.make('install-ssh-recovery', extra={'ANSIBLE_LIMIT': host['name'],
            'SSH_RECOVERY_EXCLUSIVE_WINDOW': '1', 'SSH_RECOVERY_INVENTORY': str(self.inventory),
            'SSH_RECOVERY_KNOWN_HOSTS': str(pins)})
        config = document(self.manifest['bootstrap_config'])
        handoff = self.journal.directory / ('handoff-' + str(self.journal.state['sequence'] + 1) + '.json')
        config['output'] = str(handoff)
        config['known_hosts'] = str(pins)
        prepared = self.journal.write('bootstrap-input.json', canonical(config))
        self.make('bootstrap-tailnet', extra={'ANSIBLE_LIMIT': host['name'], 'TAILNET_BOOTSTRAP_CONFIG': str(prepared)})
        proof = document(handoff)
        if proof['status'] != 'configured':
            raise RecoveryError('recovery-tailnet-not-confirmed')
        self.journal.observe('handoff', str(handoff))
        self.inventory_render(handoff)
        contexts = self.journal.write('contexts.json', canonical({host['name']: proof['contexts']}))
        identity = self.source()
        ownership = {'schema_version': 1, 'mode': 'deploy', 'inventory_alias': host['name'],
            'inventory_path': str(self.inventory), 'known_hosts_path': str(pins),
            'contexts_path': str(contexts), 'source_revision': identity['DEPLOY_SOURCE_REVISION'],
            'deployable_digest': identity['DEPLOYABLE_SOURCE_DIGEST']}
        path = self.journal.write('ownership.json', canonical(ownership))
        self.make('migrate-ssh-ownership', extra={'SSH_OWNERSHIP_CONFIG': str(path)})
        return contexts

    def migration(self, action, approval=None, *, allowed=(0,)):
        argv = [sys.executable, str(self.root / 'scripts/device-migration.py'), action,
                '--plan', self.manifest['migration_plan']]
        if action == 'ready':
            argv = [sys.executable, str(self.root / 'scripts/recovery_guest.py'),
                    '--manifest', self.path, '--action', 'ready']
        if approval is not None:
            argv.extend(['--approve', approval])
        status, raw = self.command('migration-' + action, argv, allowed=allowed)
        return json.loads(raw) if status == 0 else {'ready': False}

    def verify_target(self, *, allowed=(0,)):
        return self.command('verify-target', [sys.executable,
            str(self.root / 'scripts/recovery_guest.py'), '--manifest', self.path], allowed=allowed, timeout=1500)

    def converge(self, contexts, journal, approval):
        alias = self.migration_contract()['target']['alias']
        plaintext = journal.directory / 'runtime-secrets.yaml'
        environment = {'ANSIBLE_LIMIT': alias, 'ANSIBLE_TAGS': '', 'SKIP_PRECHECK': '0',
            'ANSIBLE_EXTRA_VARS_FILE': '', 'SECRETS_FILE': str(plaintext),
            'DEPLOY_SSH_CONTEXTS_FILE': str(contexts),
            'DEPLOY_PROMOTION_CONFIG_FILE': self.manifest['promotion_configs_file'], 'TAG_ON_SUCCESS': '0'}
        if os.path.lexists(plaintext):
            raise RecoveryError('recovery-plaintext-output-occupied')
        journal.observe('plaintext_owned', True)
        try:
            ciphertext = file_digest(self.manifest['sops_file'])
            self.make('decrypt', extra=environment)
            if file_digest(self.manifest['sops_file']) != ciphertext:
                raise RecoveryError('recovery-decrypt-input-changed')
            inputs = {'source': self.source(), 'secrets_sha256': ciphertext,
                'inventory_sha256': file_digest(self.inventory, private=False),
                'pins_sha256': file_digest(self.manifest['known_hosts_file'], private=False),
                'promotion_sha256': file_digest(self.manifest['promotion_configs_file']),
                'contexts_sha256': file_digest(contexts)}
            previous = journal.state['observed'].get('deploy_attempt')
            if previous == inputs:
                # A successful re-observation reconciles a lost deploy ACK. A
                # failed gate is diagnostic, and never marked as completion.
                status, _ = self.verify_target(allowed=(0, 2))
                if status == 0:
                    return
            dry = journal.state['observed'].get('dry_run')
            if (dry is None or dry['inputs'] != inputs
                    or not 0 <= time.time() - dry['observed_at'] <= 900):
                sink = journal.directory / ('failure-' + str(journal.state['sequence'] + 1) + '.json')
                mapping = journal.write('failure-sinks.json', canonical({alias: str(sink)}))
                environment['DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE'] = str(mapping)
                _, raw = self.make('dry-run', extra=environment)
                dry = {'inputs': inputs, 'output_sha256': hashlib.sha256(raw).hexdigest(),
                       'observed_at': int(time.time()), 'sequence': journal.state['sequence']}
                journal.observe('dry_run', dry)
            journal.approve('deploy', dry, approval)
            self.source()
            if (file_digest(self.manifest['sops_file']) != inputs['secrets_sha256']
                    or file_digest(self.inventory, private=False) != inputs['inventory_sha256']
                    or file_digest(self.manifest['promotion_configs_file']) != inputs['promotion_sha256']
                    or file_digest(self.manifest['known_hosts_file'], private=False) != inputs['pins_sha256']
                    or file_digest(contexts) != inputs['contexts_sha256']):
                raise RecoveryError('recovery-deploy-input-changed')
            sink = journal.directory / ('failure-' + str(journal.state['sequence'] + 1) + '.json')
            mapping = journal.write('failure-sinks.json', canonical({alias: str(sink)}))
            environment['DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE'] = str(mapping)
            journal.observe('deploy_attempt', inputs)
            self.make('deploy', extra=environment)
            self.verify_target()
        finally:
            self.cleanup_plaintext()
