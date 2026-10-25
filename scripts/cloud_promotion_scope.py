"""Bind first deployment to two distinct cloud resources and a pinned sentinel."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shlex

from recovery_io import ROOT, document, module, read

PROVIDERS = {'upcloud': ('upcloud_server', 'hostname'),
             'scaleway': ('scaleway_instance_server', 'name'),
             'vultr': ('vultr_instance', 'label')}
ROW_FIELDS = {'provider', 'environment', 'inventory_alias', 'server_id', 'state_sha256'}
FIELDS = {'schema_version', 'source_revision', 'target', 'sentinel', 'state_directory',
          'sops_file', 'age_key_file', 'cleanup_manifest', 'sentinel_known_hosts', 'sentinel_identity'}
SENTINEL_PROBE = '''import base64,hashlib,json,pathlib,socket
key=pathlib.Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text().split()
marker=pathlib.Path("/etc/vpn-build-id").read_text().splitlines()
environments=[line.split("=",1)[1] for line in marker if line.startswith("build_env=")]
print(json.dumps({"hostname":socket.gethostname(),
"host_key_sha256":hashlib.sha256(base64.b64decode(key[1],validate=True)).hexdigest(),
"build_environment":environments[0] if len(environments)==1 else "",
"bootstrap_ready":pathlib.Path("/var/lib/cloud-init-vpn-bootstrap.done").is_file()}))
'''


def _state(row):
    try:
        if (not isinstance(row, dict) or set(row) != ROW_FIELDS or row['provider'] not in PROVIDERS
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', row['environment'])
                or row['environment'] == 'default'
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', row['inventory_alias'])
                or not re.fullmatch(r'[0-9a-f]{64}', row['state_sha256'])):
            raise ValueError
        root = ROOT / 'terraform/providers' / row['provider']
        path = root / ('terraform.tfstate' if row['environment'] == 'prod'
                       else f"terraform.tfstate.d/{row['environment']}/terraform.tfstate")
        raw = read(path, limit=16_777_216)
        if hashlib.sha256(raw).hexdigest() != row['state_sha256']:
            raise ValueError
        state = json.loads(raw)
        if type(state.get('version')) is not int or state['version'] != 4:
            raise ValueError
        server_type, name_key = PROVIDERS[row['provider']]
        instances = []
        for resource in state['resources']:
            if resource.get('mode') == 'managed' and resource['type'] in ({v[0] for v in PROVIDERS.values()} | {'hcloud_server'}):
                if resource.get('module') or resource['type'] != server_type or resource['name'] != 'vpn':
                    raise ValueError
                for instance in resource['instances']:
                    if instance.get('deposed') or instance.get('status') not in (None, 'ready'):
                        raise ValueError
                    instances.append(instance['attributes'])
        if len(instances) != 1:
            raise ValueError
        server = instances[0]
        outputs = state['outputs']
        address = outputs['server_ipv4']['value']
        if (server['id'] != row['server_id'] or server[name_key] != row['inventory_alias']
                or outputs['server_hostname']['value'] != row['inventory_alias']
                or not isinstance(server['id'], str) or not server['id']
                or str(ipaddress.IPv4Address(address)) != address or not ipaddress.ip_address(address).is_global
                or type(outputs['ssh_port']['value']) is not int or not 1 <= outputs['ssh_port']['value'] <= 65535
                or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', outputs['admin_user']['value'])):
            raise ValueError
        if row['provider'] == 'upcloud':
            addresses = [x.get('ip_address') for x in server['network_interface']
                         if x.get('type') == 'public' and x.get('ip_address_family') == 'IPv4']
        elif row['provider'] == 'scaleway':
            addresses = [x['address'] for x in server['public_ips'] if x['family'] == 'inet']
        else:
            addresses = [server['main_ip']]
        if addresses != [address]:
            raise ValueError
        return {'id': server['id'], 'provider': row['provider'], 'public_ipv4': [address],
                'ssh_port': outputs['ssh_port']['value'], 'admin_user': outputs['admin_user']['value']}

    except (AttributeError, KeyError, TypeError):
        raise ValueError('cloud-state-refused') from None


def _sentinel(value, manifest, server, environment):
    """Resolve the actual native SSH route, then prove the pinned guest identity."""
    import install_liveness_sentinel as installer
    from fleet_inspection import InspectionError, ssh_command
    sentinel = value['liveness']['sentinels'][0]
    address = server['public_ipv4'][0]
    alias = address if server['ssh_port'] == 22 else f"[{address}]:{server['ssh_port']}"
    if (sentinel.get('vantage') != 'external' or sentinel.get('ssh_transport_host') != address
            or sentinel.get('ssh_host_key_alias') != alias):
        raise ValueError
    pins = Path(manifest['sentinel_known_hosts'])
    key = Path(manifest['sentinel_identity'])
    host = {'name': manifest['sentinel']['inventory_alias'], 'alias': address, 'transport': address,
            'address': address, 'port': server['ssh_port'], 'user': server['admin_user'], 'key': str(key)}
    # Apply the same strict source boundary as ordinary fleet inspection.
    try:
        strict = ssh_command(host, pins)
    except InspectionError:
        raise ValueError('cloud-sentinel-access-refused') from None
    clean = {k: environment[k] for k in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE') if k in environment}
    resolved = installer._run(['ssh', *module('protocol-liveness').ssh_options(sentinel, 10),
                               '-G', sentinel['ssh_target']], environment=clean).decode()
    settings = {}
    for line in resolved.splitlines():
        name, text = line.split(' ', 1)
        settings.setdefault(name, []).append(text)
    if len(settings.get('identityfile', [])) == 1:
        settings['identityfile'] = [str(Path(settings['identityfile'][0]).expanduser().absolute())]
    expected = {'hostname': address, 'hostkeyalias': alias, 'user': host['user'],
                'port': str(host['port']), 'identityfile': str(key), 'userknownhostsfile': str(pins),
                'identitiesonly': 'yes', 'identityagent': 'none', 'globalknownhostsfile': '/dev/null'}
    if any(settings.get(name) != [text] for name, text in expected.items()):
        raise ValueError
    found = installer._run(['ssh-keygen', '-F', alias, '-f', str(pins)], environment=clean)
    keys = {tuple(line.split()[1:3]) for line in found.decode().splitlines() if not line.startswith('#')}
    if len(keys) != 1 or next(iter(keys))[0] != 'ssh-ed25519':
        raise ValueError
    fingerprint = hashlib.sha256(base64.b64decode(next(iter(keys))[1], validate=True)).hexdigest()
    probe = 'python3 -I -B -S -c ' + shlex.quote(SENTINEL_PROBE)
    actual = json.loads(installer._run([*strict[:-1], probe], environment=clean))
    if actual != {'hostname': host['name'], 'host_key_sha256': fingerprint,
                  'build_environment': 'prod', 'bootstrap_ready': True}:
        raise ValueError
    return actual


def scope(value, environment):
    """Re-read private state and live SSH; no provider credential is forwarded."""
    source = value.get('prepared', {}).get('source_inputs', value['inputs'])
    manifest = document(source['provisioning_manifest'])
    if (set(manifest) != FIELDS or type(manifest['schema_version']) is not int
            or manifest['schema_version'] != 1):
        raise ValueError
    for name in ('state_directory', 'sops_file', 'age_key_file', 'sentinel_known_hosts', 'sentinel_identity'):
        module('recovery_promotion')._path(manifest[name])
    if manifest['cleanup_manifest'] is not None:
        module('recovery_promotion')._path(manifest['cleanup_manifest'])
    deploy = module('deploy-controller')
    try:
        identity = deploy.source_identity(ROOT, environment, require_clean=True)
    except deploy.DeployError:
        raise ValueError('cloud-source-identity-refused') from None
    if (identity['DEPLOY_SOURCE_REVISION'] != manifest['source_revision']
            or identity['DEPLOYABLE_SOURCE_DIGEST'] != value['target_identity']['deployable_digest']
            or source['sops_file'] != manifest['sops_file'] or source['age_key_file'] != manifest['age_key_file']):
        raise ValueError
    target = _state(manifest['target'])
    sentinel = _state(manifest['sentinel'])
    address = target['public_ipv4'][0]
    if (value['host'] != manifest['target']['provider'] + ':' + manifest['target']['environment']
            or value['target_identity']['inventory_alias'] != manifest['target']['inventory_alias']
            or hashlib.sha256(address.encode()).hexdigest() != value['target_identity']['public_service_address_sha256']
            or (target['provider'], target['id']) == (sentinel['provider'], sentinel['id'])
            or target['public_ipv4'] == sentinel['public_ipv4']
            or manifest['target']['inventory_alias'] == manifest['sentinel']['inventory_alias']
            or manifest['sentinel']['environment'].startswith('ci-staging-')):
        raise ValueError
    if manifest['target']['environment'].startswith('ci-staging-'):
        if manifest['target']['provider'] != 'upcloud' or not manifest['cleanup_manifest']:
            raise ValueError
        disposable = module('disposable_promotion')
        disposable._cleanup_target({**value, 'inputs': {'cleanup_manifest': manifest['cleanup_manifest']}},
                                   {'name': manifest['target']['inventory_alias'], 'address': address})
    elif manifest['cleanup_manifest'] is not None:
        raise ValueError
    observed = _sentinel(value, manifest, sentinel, environment)
    target['sentinel_identity'] = {**observed, 'resource_id': sentinel['id'], 'provider': sentinel['provider']}
    outputs = {key: str(Path(manifest['state_directory']) / ('promotion-' + key + '.json'))
               for key in ('authority', 'liveness', 'registry', 'proof')}
    return manifest, target, outputs
