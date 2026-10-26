"""First cloud or recovery onboarding through the canonical sentinel installer."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import time
from pathlib import Path

import jsonschema
import yaml
from recovery_io import ROOT, canonical, digest, document, load_manifest, module, read

KIND = 'recovery-promotion-intent'
CLOUD_KIND = 'cloud-promotion-intent'
TARGET = {'inventory_alias', 'public_service_address_sha256', 'deployable_digest'}
INPUTS = {'recovery_manifest', 'sops_file', 'age_key_file', 'awg_key_file'}
OUTPUTS = {'authority', 'liveness', 'registry', 'proof'}
FIELDS = {'schema_version', 'kind', 'target_identity', 'host', 'cohort', 'client', 'liveness', 'inputs'}


def _manifest_input(value):
    return 'provisioning_manifest' if value['kind'] == CLOUD_KIND else 'recovery_manifest'


def _input_fields(value):
    return (INPUTS - {'recovery_manifest'}) | {_manifest_input(value)}


class PromotionError(ValueError):
    """Categorical rejection; private input and probe content never escape."""


def _path(value):
    if (not isinstance(value, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', value)
            or str(Path(value)) != value or '..' in Path(value).parts):
        raise PromotionError('recovery-promotion-path-refused')
    return Path(value)


def required_profiles(cohort):
    from client_payload import context
    vpn = context(cohort)['vpn']
    return sorted(name for name, toggle, default in (
        ('p0-reality', 'enable_xray_reality', True), ('p1-xhttp', 'enable_nginx_xhttp', True),
        ('p2-hysteria2', 'enable_hysteria', False), ('p2-amneziawg', 'enable_amneziawg', False))
        if vpn.get(toggle, default) is True)


def validate_intent(value):
    try:
        cloud = isinstance(value, dict) and value.get('kind') == CLOUD_KIND
        inputs = _input_fields(value)
        authority = _manifest_input(value)
        if (not isinstance(value, dict) or set(value) not in (FIELDS, FIELDS | {'prepared'})
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or value['kind'] not in {KIND, CLOUD_KIND}
                or not re.fullmatch(r'(upcloud|scaleway|vultr):[a-z0-9][a-z0-9-]{0,63}' if cloud
                                    else r'upcloud:[a-z0-9][a-z0-9-]{0,63}', value['host'])
                or value['host'].split(':')[1] == 'default'
                or (not cloud and (value['host'].split(':')[1] in {'prod', 'staging'}
                                   or value['host'].split(':')[1].startswith('ci-staging-')))
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value['cohort'])
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value['client'])
                or set(value['target_identity']) != TARGET or set(value['inputs']) != inputs):
            raise ValueError
        for name, path in value['inputs'].items():
            if name != 'awg_key_file' or path is not None:
                _path(path)
        required = required_profiles(value['cohort'])
        if not required or (value['inputs']['awg_key_file'] is None) != ('p2-amneziawg' not in required):
            raise ValueError
        config = value['liveness']
        schema = json.loads((ROOT / 'contract/protocol-liveness.schema.json').read_bytes())
        schema['$defs']['target']['required'].remove('applied_at')
        del schema['$defs']['target']['properties']['applied_at']
        jsonschema.Draft202012Validator(schema).validate(config)
        if (len(config['sentinels']) != 1 or len(config['policies']) != 1
                or config['sentinels'][0]['target'] != value['target_identity']
                or sorted(config['policies'][0]['required_profiles']) != required
                or config['sentinels'][0]['policy'] != config['policies'][0]['id']
                or module('protocol-liveness').semantic_errors(config)):
            raise ValueError
        if cloud and (config['sentinels'][0].get('vantage') != 'external'
                      or not config['sentinels'][0].get('ssh_transport_host')
                      or not config['sentinels'][0].get('ssh_host_key_alias')):
            raise ValueError
        if 'p2-amneziawg' in required:
            awg = config['sentinels'][0]['awg_target']
            if awg['provider'] + ':' + awg['environment'] != value['host']:
                raise ValueError
        if 'prepared' in value:
            prepared = value['prepared']
            if (set(prepared) != {'scope_sha256', 'source_inputs', 'input_sha256', 'outputs'}
                    or set(prepared['source_inputs']) != inputs
                    or set(prepared['input_sha256']) != inputs - {authority}
                    or set(prepared['outputs']) != OUTPUTS
                    or not re.fullmatch(r'[0-9a-f]{64}', prepared['scope_sha256'])):
                raise ValueError
            for name, path in prepared['source_inputs'].items():
                if name != 'awg_key_file' or path is not None:
                    _path(path)
            for name, sha in prepared['input_sha256'].items():
                if (sha is None) != (value['inputs'][name] is None):
                    raise ValueError
                if sha is not None and not re.fullmatch(r'[0-9a-f]{64}', sha):
                    raise ValueError
            if (prepared['source_inputs'][authority] != value['inputs'][authority]
                    or (prepared['source_inputs']['awg_key_file'] is None) != (value['inputs']['awg_key_file'] is None)):
                raise ValueError
            for path in prepared['outputs'].values():
                _path(path)
            paths = [*prepared['outputs'].values(),
                     prepared['outputs']['registry'] + '.pending.json',
                     prepared['outputs']['registry'] + '.lock',
                     str(Path(prepared['outputs']['authority']).with_suffix('.lock')),
                     prepared['source_inputs']['sops_file'] + '.new-client.lock',
                     *[path for path in prepared['source_inputs'].values() if path],
                     *[path for name, path in value['inputs'].items() if path and name != authority]]
            if len({str(Path(path).resolve()) for path in paths}) != len(paths):
                raise ValueError
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError, jsonschema.ValidationError):
        raise PromotionError('recovery-promotion-intent-refused') from None


def _scope(value, environment):
    """The existing recovery journal and current local state bind this new node."""
    if value['kind'] == CLOUD_KIND:
        from cloud_promotion_scope import scope
        return scope(value, environment)
    from recovery_provider import server_from_state
    manifest_path = value.get('prepared', {}).get('source_inputs', value['inputs'])['recovery_manifest']
    manifest = load_manifest(manifest_path)
    deploy = module('deploy-controller')
    try:
        identity = deploy.source_identity(ROOT, environment, require_clean=True)
    except deploy.DeployError:
        raise PromotionError('recovery-promotion-clean-source-required') from None
    if (identity['DEPLOY_SOURCE_REVISION'] != manifest['source_revision']
            or identity['DEPLOYABLE_SOURCE_DIGEST'] != value['target_identity']['deployable_digest']):
        raise PromotionError('recovery-promotion-source-mismatch')
    journal = document(Path(manifest['state_directory']) / 'journal.json')
    if journal['manifest_sha256'] != digest(manifest):
        raise PromotionError('recovery-promotion-journal-mismatch')
    server = journal['observed']['server']
    state_path = ROOT / 'terraform/providers/upcloud/terraform.tfstate.d' / manifest['environment'] / 'terraform.tfstate'
    state = server_from_state(json.loads(read(state_path, limit=16_777_216)), manifest)
    from recovery import matching_server
    matching_server(manifest, state, {'servers': [server]}, server)
    source = value.get('prepared', {}).get('source_inputs', value['inputs'])
    if (value['host'] != 'upcloud:' + manifest['environment'] or value['cohort'] != manifest['cohort']
            or Path(source['sops_file']).resolve() != Path(manifest['sops_file']).resolve()
            or Path(source['age_key_file']).resolve() != Path(manifest['age_key_file']).resolve()
            or value['target_identity']['inventory_alias'] != manifest['hostname']
            or value['target_identity']['public_service_address_sha256'] not in {
                hashlib.sha256(address.encode()).hexdigest() for address in server['public_ipv4']}):
        raise PromotionError('recovery-promotion-target-mismatch')
    outputs = {key: str(Path(manifest['state_directory']) / ('promotion-' + key + '.json')) for key in OUTPUTS}
    return manifest, server, outputs


def _original(value):
    original = copy.deepcopy(value)
    original['inputs'] = original.pop('prepared')['source_inputs']
    return original


def _binding(value, manifest, server, hashes):
    return digest({'intent': _original(value) if 'prepared' in value else value,
                   'manifest_sha256': digest(manifest), 'server': server, 'input_sha256': hashes})


def prepare_intent(intent, host, memberships, directory, deployed_secrets, environment):
    """Freeze capabilities before site writes, retaining the exact source authority."""
    from disposable_promotion import _decrypt
    deploy = module('deploy-controller')
    plaintext = directory / 'recovery-promotion-plaintext.yaml'
    try:
        value = validate_intent(intent)
        if 'prepared' in value:
            raise ValueError
        manifest, server, outputs = _scope(value, environment)
        if (memberships != ['vpn-' + value['cohort']]
                or host['name'] != value['target_identity']['inventory_alias']
                or host['address'] not in server['public_ipv4']
                or (value['kind'] == CLOUD_KIND and (host['port'] != server['ssh_port']
                                                   or host['user'] != server['admin_user']))):
            raise ValueError
        source_inputs = copy.deepcopy(value['inputs'])
        hashes = {}
        for name in _input_fields(value) - {_manifest_input(value)}:
            if value['inputs'][name] is None:
                hashes[name] = None
                continue
            raw = read(value['inputs'][name], limit=4_194_304)
            hashes[name] = hashlib.sha256(raw).hexdigest()
            suffix = '.yaml' if name == 'sops_file' else ''
            value['inputs'][name] = str(deploy.private_file(directory / ('recovery-' + name + suffix), raw))
        value['prepared'] = {'scope_sha256': '', 'source_inputs': source_inputs,
                             'input_sha256': hashes, 'outputs': outputs}
        value['prepared']['scope_sha256'] = _binding(value, manifest, server, hashes)
        _decrypt(Path(value['inputs']['sops_file']), Path(value['inputs']['age_key_file']), plaintext, environment)
        secrets = yaml.safe_load(read(plaintext, limit=4_194_304))
        if not isinstance(secrets, dict) or secrets != yaml.safe_load(deployed_secrets):
            raise ValueError
        client = secrets.get('client_registry', {}).get(value['client'], {})
        if client.get('status') not in {'issued', 'delivered', 'active'}:
            raise ValueError
        if value['inputs']['awg_key_file'] is not None:
            import hmac

            from awg_device_binding import resolve_binding
            binding = client['awg_binding']
            selected = resolve_binding(secrets, {}, value['client'], value['host'], binding['instance'])
            private = read(value['inputs']['awg_key_file'], limit=128).rstrip(b'\n')
            if (selected.identity != binding or not isinstance(client.get('awg_private_key'), str)
                    or not re.fullmatch(rb'[A-Za-z0-9+/]{43}=', private)
                    or not hmac.compare_digest(private, client['awg_private_key'].encode())):
                raise ValueError
        validate_intent(value)
        return value
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        raise PromotionError('recovery-promotion-preflight-refused') from None
    finally:
        try:
            plaintext.unlink(missing_ok=True)
        except OSError:
            raise PromotionError('recovery-promotion-cleanup-incomplete') from None


def _ensure(path, value):
    if os.path.lexists(path):
        if document(path) != value:
            raise PromotionError('recovery-promotion-output-conflict')
    else:
        import install_liveness_sentinel as installer
        installer._write(path, canonical(value))


def finalize(intent, environment, *, clock=None):
    """Run only after data-plane convergence; resume the real installer receipt."""
    import install_liveness_sentinel as installer
    from disposable_liveness_executor import _exclusive_locks
    try:
        value = validate_intent(intent)
        prepared = value['prepared']
        manifest, server, outputs = _scope(value, environment)
        if outputs != prepared['outputs']:
            raise ValueError
        paths = {key: Path(path) for key, path in outputs.items()}
        source = prepared['source_inputs']
        locks = (Path(source['sops_file'] + '.new-client.lock'), paths['authority'].with_suffix('.lock'))
        with _exclusive_locks(locks):
            if value['kind'] == CLOUD_KIND and _scope(value, environment) != (manifest, server, outputs):
                raise ValueError
            hashes = {}
            for name in _input_fields(value) - {_manifest_input(value)}:
                hashes[name] = None if source[name] is None else hashlib.sha256(read(source[name], limit=4_194_304)).hexdigest()
                if source[name] is not None and hashlib.sha256(read(value['inputs'][name], limit=4_194_304)).hexdigest() != hashes[name]:
                    raise ValueError
            if (hashes != prepared['input_sha256']
                    or _binding(value, manifest, server, hashes) != prepared['scope_sha256']):
                raise ValueError
            if paths['authority'].exists():
                authority = document(paths['authority'])
                if (set(authority) != {'schema_version', 'scope_sha256', 'applied_at'}
                        or authority['schema_version'] != 1 or authority['scope_sha256'] != prepared['scope_sha256']
                        or type(authority['applied_at']) is not int or authority['applied_at'] < 1):
                    raise ValueError
            else:
                if any(os.path.lexists(path) for path in paths.values()):
                    raise ValueError
                authority = {'schema_version': 1, 'scope_sha256': prepared['scope_sha256'],
                             'applied_at': int((clock or time.time)())}
                _ensure(paths['authority'], authority)
            config = copy.deepcopy(value['liveness'])
            sentinel = config['sentinels'][0]
            sentinel['target']['applied_at'] = authority['applied_at']
            module('protocol-liveness').validate_config(config)
            _ensure(paths['liveness'], config)
            env = {key: environment[key] for key in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE') if key in environment}
            env.update(HOSTS=value['host'], COHORTS=value['cohort'], SOPS_FILE=value['inputs']['sops_file'],
                       SOPS_AGE_KEY_FILE=value['inputs']['age_key_file'])
            with installer.registry_lock(paths['registry']):
                registry = installer._state(paths['registry'], 'sentinels')
                pending = installer._state(paths['registry'].with_name(paths['registry'].name + '.pending.json'), 'pending')
                sid = sentinel['id']
                if set(registry['sentinels']) - {sid} or set(pending['pending']) - {sid}:
                    raise ValueError
                entry = registry['sentinels'].get(sid)
                if entry is not None and pending['pending']:
                    # Registry publication precedes pending deletion. The fixed
                    # installer reconciles the same generation after this crash.
                    if pending['pending'].get(sid) != entry:
                        raise ValueError
                    entry = None
                if entry is not None:
                    if entry['client'] != value['client']:
                        raise ValueError
                    revision, runner, _engine = installer._source_identity(ROOT)
                    expected = {**sentinel['target'], 'required_profiles': required_profiles(value['cohort']),
                        'source_revision': revision, 'runner_sha256': hashlib.sha256(runner).hexdigest(),
                        'public_profile_digest': entry['provenance']['public_profile_digest']}
                    if (revision != manifest['source_revision'] or entry['target_identity'] != expected
                            or any(entry.get(key) != sentinel.get(key) for key in
                                ('ssh_target', 'ssh_transport_host', 'ssh_host_key_alias', 'policy', 'vantage'))):
                        raise ValueError
                    receipt = installer._receipt(sentinel, entry, env)
                    if receipt != {'generation_id': entry['generation_id'], 'status': 'committed',
                        'runner_sha256': expected['runner_sha256'], 'provenance': entry['provenance'], 'target_identity': expected}:
                        raise ValueError
            if entry is None:
                key = None if value['inputs']['awg_key_file'] is None else read(value['inputs']['awg_key_file'], limit=128).decode('ascii')
                with io.StringIO(key or '') as stream:
                    receipt = installer.install(paths['liveness'], sid, value['client'], paths['registry'],
                        read_awg_stdin=key is not None, stdin=stream, environment=env)
                if receipt.get('status') != 'committed':
                    raise ValueError
            proof = {'schema_version': 1, 'liveness_config': str(paths['liveness']),
                     'expected_sentinels': [sid], 'target_identity': receipt['target_identity']}
            if value['kind'] == CLOUD_KIND:
                if _scope(value, environment) != (manifest, server, outputs):
                    raise ValueError
            _ensure(paths['proof'], proof)
            return paths['proof']
    except (OSError, ValueError, TypeError, KeyError):
        raise PromotionError('recovery-promotion-finalization-refused') from None
