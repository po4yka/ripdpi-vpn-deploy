"""Private plan admission and bounded migration IO; no credential diagnostics."""
from __future__ import annotations

import base64
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import socket
import ssl
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from authenticated_http import https_origin
from bootstrap_readiness import check_cancelled, run_command
from client_payload import HOST, ROOT, read_document
from device_migration_errors import MigrationRefused
from device_migration_receipt import HEX, UUID, matches, unique_object
from encrypted_client_document import MAX_BYTES, identity, private_file
from fleet_inspection import bounded_command, select_hosts, ssh_command


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def private_bytes(path, limit=MAX_BYTES):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), 'rb') as stream:
        before = private_file(stream.fileno())
        if before.st_size > limit:
            raise MigrationRefused('migration-input-limit')
        result = stream.read(limit + 1)
        if len(result) > limit or identity(before) != identity(os.fstat(stream.fileno())):
            raise MigrationRefused('migration-input-changed')
        return result


def load_plan(path):
    plan = json.loads(private_bytes(path, 65536), object_pairs_hook=unique_object)
    if (not isinstance(plan, dict) or set(plan) != {'schema_version', 'id', 'inventory', 'known_hosts', 'source', 'target', 'publication'}
            or type(plan['schema_version']) is not int or plan['schema_version'] != 1 or not matches(UUID, plan['id'])):
        raise MigrationRefused('invalid-migration-plan')
    for key in ('inventory', 'known_hosts'):
        if not isinstance(plan[key], str) or not Path(plan[key]).is_absolute():
            raise MigrationRefused('absolute-migration-input-required')
    for which in ('source', 'target'):
        node = plan[which]
        required = {'host', 'alias', 'cohort', 'secrets_file'} | ({'awg_instances'} if which == 'target' else set())
        if (not isinstance(node, dict) or set(node) != required
                or not isinstance(node['host'], str) or not HOST.fullmatch(node['host'])
                or not isinstance(node['alias'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', node['alias'])
                or not isinstance(node['cohort'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}', node['cohort'])
                or not isinstance(node['secrets_file'], str) or not Path(node['secrets_file']).is_absolute()):
            raise MigrationRefused('invalid-migration-node')
    pub = plan['publication']
    if (not isinstance(pub, dict) or set(pub) != {'source_alias', 'target_alias', 'directory', 'origin'}
            or any(not isinstance(pub[k], str) for k in pub)
            or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', pub[k]) for k in ('source_alias', 'target_alias'))
            or not re.fullmatch(r'/[A-Za-z0-9_][A-Za-z0-9_./-]*', pub['directory']) or '..' in pub['directory']):
        raise MigrationRefused('invalid-migration-publisher')
    if https_origin(pub['origin']) != pub['origin']:
        raise MigrationRefused('invalid-migration-origin')
    for value in (plan['inventory'], plan['known_hosts'], plan['source']['secrets_file'], plan['target']['secrets_file']):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', value) or '..' in Path(value).parts:
            raise MigrationRefused('unsafe-migration-command-path')
    for key in ('inventory', 'known_hosts'):
        candidate = Path(plan[key])
        plan[key] = str(candidate.parent.resolve(strict=True) / candidate.name)
    identities = []
    for key in ('source', 'target'):
        candidate = Path(plan[key]['secrets_file'])
        plan[key]['secrets_file'] = str(candidate.parent.resolve(strict=True) / candidate.name)
        descriptor = os.open(plan[key]['secrets_file'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            info = private_file(descriptor)
            identities.append((info.st_dev, info.st_ino))
        finally:
            os.close(descriptor)
    if identities[0] == identities[1]:
        raise MigrationRefused('distinct-migration-authorities-required')
    if plan['source']['host'] == plan['target']['host'] or plan['source']['secrets_file'] == plan['target']['secrets_file']:
        raise MigrationRefused('distinct-migration-authorities-required')
    if pub['target_alias'] == plan['source']['alias']:
        raise MigrationRefused('publisher-cannot-retire-with-source')
    return plan


@contextmanager
def migration_lock(plan):
    path = Path(plan['source']['secrets_file'])
    directory = path.parent.stat()
    if directory.st_uid != os.getuid() or directory.st_mode & 0o022:
        raise MigrationRefused('unsafe-migration-directory')
    fd = os.open(str(path) + '.migration.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        before = private_file(fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        named = os.stat(str(path) + '.migration.lock', follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
            raise MigrationRefused('migration-lock-changed')
        yield
    finally:
        os.close(fd)


class PublisherIO:
    """One admitted subscription namespace shared by migration and device lifecycle."""
    def __init__(self, publication, hosts, commands, *, revalidate):
        self.plan = {'publication': publication}
        self.hosts, self.commands = hosts, commands
        self.revalidate = revalidate

    def publisher(self, alias, action, token_hash=None, expected=None, document=None, *, cleanup=False):
        if not cleanup:
            check_cancelled()
        self.revalidate()
        arguments = ['sudo', '-n', '-u', 'vpn-bootstrap', '/usr/local/bin/vpn-bootstrap.py', '--migration-' + action]
        if token_hash is not None:
            if not matches(HEX, token_hash):
                raise MigrationRefused('invalid-migration-grant')
            arguments.append(token_hash)
        arguments.append(self.plan['publication']['directory'])
        request = b'' if action != 'publish' else encoded({'schema_version': 1, 'expected_document_sha256': expected,
                    'document_b64': base64.b64encode(document).decode() if document is not None else None})
        result = bounded_command(self.commands[alias][:-1] + [shlex.join(arguments)], timeout=60,
                                 limit=MAX_BYTES, input_limit=MAX_BYTES, input_bytes=request,
                                 environment=os.environ.copy())
        if action == 'ready':
            if result.strip() != b'migration-publisher-v1':
                raise MigrationRefused('migration-publisher-unavailable')
            return None
        return json.loads(result, object_pairs_hook=unique_object)

    def origin(self, alias):
        origin = urlsplit(self.plan['publication']['origin'])
        host = self.hosts[alias]['address']
        with socket.create_connection((host, origin.port or 443), timeout=10) as connection:
            with ssl.create_default_context().wrap_socket(connection, server_hostname=origin.hostname):
                pass

    def pivot_ready(self):
        origin = urlsplit(self.plan['publication']['origin'])
        target = self.hosts[self.plan['publication']['target_alias']]['address']
        addresses = {item[4][0] for item in socket.getaddrinfo(origin.hostname, origin.port or 443, type=socket.SOCK_STREAM)}
        if addresses != {target}:
            raise MigrationRefused('migration-publication-origin-pivot-unconfirmed')

    def read_route(self, alias, token, expected, *, expected_status=200):
        request = {'origin': self.plan['publication']['origin'], 'address': self.hosts[alias]['address'],
                   'token': token, 'expected_b64': base64.b64encode(expected).decode(), 'expected_status': expected_status}
        status, _ = run_command([sys.executable, str(ROOT / 'scripts/device_migration_route.py')],
                                input_data=encoded(request), capture=True, timeout=15, output_limit=4096,
                                environment=os.environ.copy())
        if status:
            raise MigrationRefused('migration-publication-route-mismatch')

    def verify_routes(self):
        """Prove the reviewed TLS origin serves this exact private namespace."""
        for alias in dict.fromkeys((self.plan['publication']['source_alias'], self.plan['publication']['target_alias'])):
            check_cancelled()
            token = secrets.token_urlsafe(32)
            token_hash = sha(token.encode())
            payload = encoded({'migration_route_nonce': secrets.token_hex(32)})
            expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
            document = encoded({'schema_version': 1, 'client': 'migration-route-check', 'expires': expires,
                                'payload_b64': base64.b64encode(payload).decode()})
            try:
                result = self.publisher(alias, 'publish', token_hash, None, document)
                if result.get('document_sha256') != sha(document) or result.get('token_hash') != token_hash:
                    raise MigrationRefused('migration-route-publication-uncertain')
                self.read_route(alias, token, payload)
            finally:
                # Even an uncertain create is reconciled through exact owned CAS.
                # A process crash leaves only an unusable-after-five-minutes probe.
                result = self.publisher(alias, 'publish', token_hash, sha(document), None, cleanup=True)
                if result.get('document_sha256') is not None or result.get('token_hash') != token_hash:
                    raise MigrationRefused('migration-route-cleanup-uncertain')


class LocalIO(PublisherIO):
    def __init__(self, plan):
        self.plan = plan
        aliases = list(dict.fromkeys([plan['source']['alias'], plan['target']['alias'],
                                     plan['publication']['source_alias'], plan['publication']['target_alias']]))
        self.hosts = {h['name']: h for h in select_hosts(plan['inventory'], aliases, include_variables=True, include_cohorts=True)}
        for key in ('source', 'target'):
            node = plan[key]
            selected = select_hosts(plan['inventory'], [node['host']], include_variables=True, selection_kind='provider-env', include_cohorts=True)[0]
            if selected != self.hosts[node['alias']] or selected['cohorts'] != [node['cohort']]:
                raise MigrationRefused('migration-inventory-identity-mismatch')
        if self.hosts[plan['source']['alias']]['address'] == self.hosts[plan['target']['alias']]['address']:
            raise MigrationRefused('distinct-migration-endpoints-required')
        # ssh_command admits the complete private key and known-hosts paths.
        self.commands = {alias: ssh_command(host, plan['known_hosts']) for alias, host in self.hosts.items()}
        with open(plan['known_hosts'], 'rb') as stream:
            pins = stream.read(65537)
        if len(pins) > 65536:
            raise MigrationRefused('migration-host-pins-limit')
        self.admission = {'hosts': self.hosts, 'pins_sha256': sha(pins)}

    def read(self, path):
        return read_document(path)

    def endpoint(self, host):
        selected = select_hosts(self.plan['inventory'], [host], selection_kind='provider-env')[0]
        return selected['address']

    def revalidate(self):
        if LocalIO(self.plan).admission != self.admission:
            raise MigrationRefused('migration-inventory-or-pins-changed')

    def verify_target(self, document):
        check_cancelled()
        self.revalidate()
        node = self.plan['target']
        provider, environment = node['host'].split(':')
        spec = importlib.util.spec_from_file_location('migration_deploy_controller', ROOT / 'scripts/deploy-controller.py')
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        env = {k: v for k, v in os.environ.items() if not (k.startswith(('MAKE', 'ANSIBLE_', 'VPN_', 'SOPS_', 'MIGRATION_')) or k in {'GNUMAKEFLAGS', 'MFLAGS', 'ENV', 'PROVIDER', 'HOSTS', 'COHORTS', 'EXTRA_VARS'})}
        env.update(PROVIDER=provider, ENV=environment, SOPS_FILE=node['secrets_file'])
        # Freeze the same admitted inventory, pins and operator key used by RPC.
        # Host-scoped transport variables outrank ambient group/config defaults.
        with tempfile.TemporaryDirectory(prefix='.migration-verify-', dir=Path(node['secrets_file']).parent) as temporary:
            directory = Path(temporary)
            inventory, inventory_fence = deploy.read_fenced_input(self.plan['inventory'])
            pins, pins_fence = deploy.read_fenced_input(self.plan['known_hosts'])
            host = dict(self.hosts[node['alias']])
            key, key_fence = deploy.read_fenced_input(host['key'], private=True)
            if sha(pins) != self.admission['pins_sha256']:
                raise MigrationRefused('migration-inventory-or-pins-changed')
            frozen_pins = deploy.private_file(directory / 'known_hosts', pins)
            host['key'] = str(deploy.private_file(directory / 'identity', key))
            transport = deploy.transport_variables(host, ssh_command(host, frozen_pins))
            lines, section, replaced = [], '', False
            for line in inventory.decode().splitlines():
                if line.strip().startswith('['):
                    section = line.strip()
                words = shlex.split(line, comments=True)
                if section == '[vpn]' and words and words[0] == node['alias']:
                    words = [word for word in words if word.split('=', 1)[0] not in transport]
                    line = shlex.join(words) + ' ' + ' '.join(
                        key + '=' + shlex.quote(str(value)) for key, value in transport.items())
                    replaced = True
                lines.append(line)
            if not replaced:
                raise MigrationRefused('migration-verification-target-missing')
            frozen_inventory = deploy.private_file(directory / 'inventory.ini', ('\n'.join(lines) + '\n').encode())
            path = deploy.private_file(directory / 'secrets.yaml', yaml.safe_dump(document).encode())
            env.update(ANSIBLE_INVENTORY=str(frozen_inventory), VPN_SECRETS_FILE=str(path),
                       ANSIBLE_HOST_KEY_CHECKING='true', ANSIBLE_SSH_ARGS=transport['ansible_ssh_args'],
                       ANSIBLE_SSH_COMMON_ARGS='', ANSIBLE_SSH_EXTRA_ARGS='')
            fences = (inventory_fence, pins_fence, key_fence)
            def verify_fences():
                try:
                    for fence in fences:
                        deploy.verify_input_fence(fence)
                except deploy.DeployError:
                    raise MigrationRefused('migration-verification-input-changed') from None
            for goal in ('verify', 'smoke-test'):
                verify_fences()
                self.revalidate()
                status, _ = run_command(['make', '-C', str(ROOT), goal, 'PROVIDER=' + provider, 'ENV=' + environment,
                                 'SOPS_FILE=' + node['secrets_file'], 'SECRETS_FILE=' + str(path),
                                 'ANSIBLE_INVENTORY=' + str(frozen_inventory), 'ANSIBLE_EXTRA_VARS_FILE=', 'SKIP_PRECHECK=0',
                                 'ANSIBLE_LIMIT=' + node['alias'], 'COHORTS=' + node['cohort'], 'TAG_ON_SUCCESS=0'],
                                environment=env, timeout=600, capture=True, output_limit=1_048_576)
                if status:
                    raise MigrationRefused('migration-target-verification-failed')
                verify_fences()
                self.revalidate()
