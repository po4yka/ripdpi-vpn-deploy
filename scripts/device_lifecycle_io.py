"""Private fleet admission and bounded runtime IO for device operations."""
from __future__ import annotations

import base64
import fcntl
import importlib.util
import json
import os
import re
import shlex
import stat
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from authenticated_http import https_origin
from bootstrap_readiness import check_cancelled, run_command
from client_payload import HOST, ROOT, context, read_document
from device_lifecycle_publishers import probe as publisher_probe
from device_migration_io import encoded, private_bytes, sha
from device_migration_receipt import HEX, UUID, matches, unique_object
from encrypted_client_document import MAX_BYTES, private_file
from fleet_inspection import bounded_command, select_hosts, ssh_command

NAME = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
ALIAS = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
PATH = re.compile(r'/[A-Za-z0-9_./-]+\Z')


def safe_path(value):
    if not isinstance(value, str) or not PATH.fullmatch(value) or '..' in Path(value).parts:
        raise ValueError('invalid-device-input-path')
    path = Path(value)
    return str(path.parent.resolve(strict=True) / path.name)


def load_manifest(path):
    value = json.loads(private_bytes(path, 131072), object_pairs_hook=unique_object)
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'id', 'action', 'device', 'inventory',
            'known_hosts', 'journal_host', 'nodes', 'publishers', 'delivery', 'probe'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not matches(UUID, value['id']) or value['action'] not in ('issue', 'refresh', 'revoke')
            or not matches(NAME, value['device'])):
        raise ValueError('invalid-device-manifest')
    for key in ('inventory', 'known_hosts'):
        value[key] = safe_path(value[key])
    nodes = value['nodes']
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 32:
        raise ValueError('invalid-device-fleet')
    identities = set()
    for node in nodes:
        if (not isinstance(node, dict) or set(node) != {'host', 'alias', 'cohort', 'secrets_file', 'awg_instance', 'xray_cohorts'}
                or not matches(HOST, node['host']) or not matches(ALIAS, node['alias'])
                or not matches(re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}\Z'), node['cohort'])
                or node['awg_instance'] is not None and not matches(re.compile(r'[A-Za-z0-9_=+.-]{1,15}\Z'), node['awg_instance'])
                or not isinstance(node['xray_cohorts'], list) or len(node['xray_cohorts']) > 32
                or any(not matches(NAME, name) for name in node['xray_cohorts'])
                or len(set(node['xray_cohorts'])) != len(node['xray_cohorts'])):
            raise ValueError('invalid-device-node')
        node['secrets_file'] = safe_path(node['secrets_file'])
        info = os.stat(node['secrets_file'], follow_symlinks=False)
        identity = (info.st_dev, info.st_ino)
        if identity in identities:
            raise ValueError('device-node-authorities-must-be-distinct')
        identities.add(identity)
        private_bytes(node['secrets_file'])
    for field in ('host', 'alias', 'secrets_file'):
        if len({node[field] for node in nodes}) != len(nodes):
            raise ValueError('duplicate-device-node')
    hosts = {node['host'] for node in nodes}
    if value['journal_host'] not in hosts:
        raise ValueError('invalid-device-journal-host')
    publishers = value['publishers']
    if not isinstance(publishers, list) or not 0 <= len(publishers) <= 16:
        raise ValueError('invalid-device-publishers')
    for pub in publishers:
        if (not isinstance(pub, dict) or set(pub) != {'host', 'directory', 'origin'} or pub['host'] not in hosts
                or not isinstance(pub['directory'], str) or not PATH.fullmatch(pub['directory'])
                or '..' in Path(pub['directory']).parts or https_origin(pub['origin']) != pub['origin']):
            raise ValueError('invalid-device-publisher')
    if len({pub['host'] for pub in publishers}) != len(publishers):
        raise ValueError('duplicate-device-publisher')
    delivery = value['delivery']
    if value['action'] == 'revoke':
        if delivery is not None:
            raise ValueError('revocation-has-no-delivery')
    elif (not isinstance(delivery, dict) or set(delivery) != {'hosts', 'awg_host', 'format', 'expires', 'output'}
          or not isinstance(delivery['hosts'], list) or not delivery['hosts']
          or len(set(delivery['hosts'])) != len(delivery['hosts']) or not set(delivery['hosts']) <= hosts
          or delivery['awg_host'] not in ('', *delivery['hosts']) or delivery['format'] not in ('ripdpi', 'singbox', 'native')
          or not isinstance(delivery['expires'], str)):
        raise ValueError('invalid-device-delivery')
    elif value['action'] == 'issue' or delivery['format'] == 'native':
        delivery['output'] = safe_path(delivery['output'])
    elif delivery['output'] is not None:
        raise ValueError('refresh-preserves-existing-recipient-links')
    if delivery is not None:
        if delivery['format'] == 'native' and delivery['expires']:
            raise ValueError('native-delivery-does-not-enforce-expiry')
        if delivery['format'] != 'native' and not publishers:
            raise ValueError('subscription-delivery-needs-publisher')
    probe = value['probe']
    if (not isinstance(probe, dict) or set(probe) != {'url', 'status', 'body_sha256', 'timeout_seconds'}
            or not isinstance(probe['url'], str) or not probe['url'].startswith('https://')
            or type(probe['status']) is not int or not 200 <= probe['status'] <= 299
            or not matches(HEX, probe['body_sha256']) or type(probe['timeout_seconds']) is not int
            or not 1 <= probe['timeout_seconds'] <= 30):
        raise ValueError('invalid-device-probe-control')
    url = urlsplit(probe['url'])
    if not url.hostname or url.username is not None or url.password is not None or url.fragment or len(probe['url']) > 2048:
        raise ValueError('invalid-device-probe-control')
    if delivery is not None and delivery['expires']:
        spec = importlib.util.spec_from_file_location('device_expiry', ROOT / 'scripts/normalize-subscription-expiry.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        delivery['expires'] = module.normalize_expiry(delivery['expires'])
    return value


@contextmanager
def operation_lock(path):
    path = Path(path)
    if path.parent.stat().st_uid != os.getuid() or path.parent.stat().st_mode & 0o022:
        raise ValueError('unsafe-device-journal-directory')
    fd = os.open(str(path) + '.device-operation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        before = private_file(fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        named = os.stat(str(path) + '.device-operation.lock', follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError('device-operation-lock-changed')
        yield
    finally:
        os.close(fd)


@contextmanager
def operation_locks(paths):
    """Serialize overlapping fleets independently of the chosen journal host."""
    with ExitStack() as stack:
        for path in sorted(set(paths)):
            stack.enter_context(operation_lock(path))
        yield


class LocalIO:
    def __init__(self, manifest, manifest_path):
        self.manifest, self.manifest_path = manifest, str(manifest_path)
        self.nodes = {node['host']: node for node in manifest['nodes']}
        # Admit the complete vpn inventory, including nodes without this device.
        names, section = [], ''
        for line in Path(manifest['inventory']).read_text().splitlines():
            if line.strip().startswith('['):
                section = line.strip()
            elif section == '[vpn]' and shlex.split(line, comments=True):
                names.append(shlex.split(line, comments=True)[0])
        selected = select_hosts(manifest['inventory'], names, include_variables=True, include_cohorts=True)
        if {host['name'] for host in selected} != {node['alias'] for node in self.nodes.values()}:
            raise ValueError('device-manifest-must-cover-complete-inventory')
        self.hosts, self.commands = {}, {}
        for host, node in ((host, node) for host in selected for node in self.nodes.values() if host['name'] == node['alias']):
            expected = select_hosts(manifest['inventory'], [node['host']], selection_kind='provider-env', include_variables=True, include_cohorts=True)[0]
            if expected != host or host['cohorts'] != [node['cohort']]:
                raise ValueError('device-inventory-identity-mismatch')
            allowed = {'ansible_host', 'ansible_user', 'ansible_port', 'ansible_ssh_private_key_file',
                       'ansible_python_interpreter', 'provider', 'env', 'vpn_service_address',
                       'vpn_build_environment', 'allowed_ssh_cidrs', 'terraform_public_listeners_b64',
                       'terraform_nat_source_port_range', 'server_ipv6', 'honeypot_listen_addr',
                       'observability_node_id', 'observability_capabilities', 'observability_failure_domain',
                       'observability_topology_manifest_b64', 'real_vps_awg_nat_mode', 'vpn_subscription_only'}
            if set(host['variables']) - allowed:
                raise ValueError('unsupported-device-inventory-context-override')
            if host['variables'].get('vpn_subscription_only', 'false') not in ('true', 'false', 'True', 'False', '1', '0'):
                raise ValueError('invalid-device-subscription-only-override')
            self.hosts[node['host']] = host
            self.commands[node['host']] = ssh_command(host, manifest['known_hosts'])
        self.fences = {path: sha(private_bytes(path)) for path in {self.manifest_path, manifest['inventory'], manifest['known_hosts'],
                                                                *[host['key'] for host in self.hosts.values()]}}
        self.publications = {pub['host']: pub for pub in manifest['publishers']}
        required = set()
        for host, node in self.nodes.items():
            resolved = context(node['cohort'])
            subscription_only = self.hosts[host]['variables'].get('vpn_subscription_only', resolved.get('vpn_subscription_only', False))
            if subscription_only in (True, 'true', 'True', '1') or resolved.get('vpn', {}).get('enable_subscription_host', False):
                required.add(host)
        self.retained_publishers = set(self.publications) - required
        if not required <= set(self.publications):
            raise ValueError('device-manifest-must-cover-all-configured-publishers')

    def revalidate(self):
        check_cancelled()
        if any(sha(private_bytes(path)) != digest for path, digest in self.fences.items()):
            raise ValueError('device-reviewed-input-changed')

    def source_identity(self):
        spec = importlib.util.spec_from_file_location('device_source', ROOT / 'scripts/deploy-controller.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        environment = {key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR'}}
        return module.source_identity(ROOT, environment, require_clean=True)

    def admit_output(self, path):
        parent = Path(path).parent.stat()
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError('unsafe-device-output-directory')
        if os.path.lexists(path):
            raise ValueError('device-output-already-exists')

    def verify_publisher_scope(self):
        self.revalidate()
        for host in self.nodes.keys() - self.publications.keys():
            if publisher_probe(self.hosts[host], self.commands[host]):
                raise ValueError('undeclared-retained-device-publisher')
        self.revalidate()

    def read(self, path):
        return read_document(path)

    def endpoint(self, host):
        return self.hosts[host]['address']

    def publication_io(self, host):
        from device_migration_io import PublisherIO
        publication = dict(self.publications[host], source_alias=host, target_alias=host)
        return PublisherIO({'publication': publication}, self.hosts, self.commands, revalidate=self.revalidate)

    def publisher(self, host, action, token_hash=None, expected=None, document=None, *, cleanup=False):
        self.revalidate()
        result = self.publication_io(host).publisher(host, action, token_hash, expected, document, cleanup=cleanup)
        self.revalidate()
        return result

    def verify_routes(self, host):
        self.revalidate()
        publication = self.publication_io(host)
        publication.pivot_ready()
        publication.verify_routes()
        self.revalidate()

    def read_route(self, host, token, payload, *, revoked=False):
        self.revalidate()
        publication = self.publication_io(host)
        publication.pivot_ready()
        publication.read_route(host, token, b'' if revoked else payload, expected_status=410 if revoked else 200)
        self.revalidate()

    def runtime(self, host, document, *, check=False, verify_only=False, revocation=None):
        self.revalidate()
        node = self.nodes[host]
        spec = importlib.util.spec_from_file_location('device_deploy', ROOT / 'scripts/deploy-controller.py')
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        with tempfile.TemporaryDirectory(prefix='.device-runtime-', dir=Path(node['secrets_file']).parent) as temporary:
            directory = Path(temporary)
            frozen = dict(self.hosts[host])
            frozen['key'] = str(deploy.private_file(directory / 'identity', private_bytes(frozen['key'])))
            pins = deploy.private_file(directory / 'known_hosts', private_bytes(self.manifest['known_hosts']))
            transport = deploy.transport_variables(frozen, ssh_command(frozen, pins))
            # Keep every declared cohort and host variable, replace only connection authority.
            variables = dict(frozen['variables'], **transport)
            line = node['alias'] + ' ' + ' '.join(key + '=' + shlex.quote(str(value)) for key, value in variables.items())
            inventory = deploy.private_file(directory / 'inventory.ini', (f'[vpn]\n{line}\n[vpn-{node["cohort"]}]\n{node["alias"]}\n').encode())
            secret_file = deploy.private_file(directory / 'secrets.yaml', yaml.safe_dump(document).encode())
            extra_vars = ''
            if revocation is not None:
                overrides = {'vpn_device_revocation': revocation}
                if host in self.retained_publishers:
                    overrides['vpn_device_retained_publisher'] = True
                extra_vars = str(deploy.private_file(directory / 'revocation.yaml', yaml.safe_dump(overrides).encode()))
            environment = {key: value for key, value in os.environ.items() if key in {
                'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SOPS_AGE_KEY_FILE'}}
            environment.update(ANSIBLE_INVENTORY=str(inventory), VPN_SECRETS_FILE=str(secret_file), ANSIBLE_HOST_KEY_CHECKING='true',
                               ANSIBLE_SSH_ARGS=transport['ansible_ssh_args'], ANSIBLE_SSH_COMMON_ARGS='', ANSIBLE_SSH_EXTRA_ARGS='')
            provider, env = node['host'].split(':')
            goals = ['verify'] if verify_only else ['rotate-credentials-check'] if check else ['rotate-credentials', 'verify']
            for goal in goals:
                self.revalidate()
                status, _ = run_command(['make', '-C', str(ROOT), goal, 'PROVIDER=' + provider, 'ENV=' + env,
                    'SOPS_FILE=' + node['secrets_file'], 'SECRETS_FILE=' + str(secret_file),
                    'ANSIBLE_INVENTORY=' + str(inventory), 'ANSIBLE_EXTRA_VARS_FILE=' + extra_vars, 'SKIP_PRECHECK=0',
                    'ANSIBLE_LIMIT=' + node['alias'], 'COHORTS=' + node['cohort'], 'TAG_ON_SUCCESS=0'],
                    environment=environment, timeout=3600, capture=True, output_limit=1_048_576)
                if status:
                    raise ValueError('device-runtime-adoption-unconfirmed')
                self.revalidate()

    def output(self, path, expected):
        from private_client_artifact import publish
        parent = Path(path).parent.stat()
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError('unsafe-device-output-directory')
        try:
            actual = private_bytes(path)
        except FileNotFoundError:
            publish(path, expected.decode())
        else:
            if actual != expected:
                raise ValueError('device-output-conflict')
        if private_bytes(path) != expected:
            raise ValueError('device-output-unconfirmed')

    def probe(self, host, profiles, mode):
        self.revalidate()
        control = {key: value for key, value in self.manifest['probe'].items() if key != 'timeout_seconds'}
        request = {'schema_version': 1, 'mode': mode, 'profiles': profiles, 'control': control,
                   'timeout_seconds': self.manifest['probe']['timeout_seconds']}
        source = (ROOT / 'scripts/device_lifecycle_probe_worker.py').read_text()
        # The worker program and private request share stdin; neither enters argv.
        encoded_source = base64.b64encode(source.encode()).decode()
        encoded_request = base64.b64encode(encoded(request)).decode()
        program = ('import base64,io,sys\n'
                   'sys.stdin=io.TextIOWrapper(io.BytesIO(base64.b64decode(' + repr(encoded_request) + ')))\n'
                   'exec(compile(base64.b64decode(' + repr(encoded_source) + '),"<device-probe>","exec"))\n')
        raw = bounded_command(self.commands[host][:-1] + ['sudo -n /usr/bin/python3 -'], input_bytes=program.encode(),
            input_limit=MAX_BYTES, limit=65536, timeout=240,
            environment=os.environ.copy())
        self.revalidate()
        return json.loads(raw, object_pairs_hook=unique_object)
