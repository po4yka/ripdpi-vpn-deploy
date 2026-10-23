"""Prepare selected device authority on a replacement without changing either input."""
from __future__ import annotations

import copy
import importlib.util
import ipaddress
import re
from pathlib import Path

from awg_client import host_context
from awg_device_binding import (
    NAME,
    allocate_address,
    host_identity,
    registry_errors,
    resolve_binding,
)
from client_payload import ROOT, context, validate_options
from transport_semantics import effective_awg_instances, transport_errors

BASELINE = {'enable_xray_reality': True, 'enable_nginx_xhttp': True,
            'enable_hysteria': False, 'enable_amneziawg': False,
            'enable_snell': False, 'enable_naive': False}
ACTIVE = {'issued', 'delivered', 'active', 'stale'}


def _node(value):
    if (not isinstance(value, dict) or not isinstance(value.get('cohort'), str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}', value['cohort'])
            or not isinstance(value.get('secrets_file'), str)
            or not Path(value['secrets_file']).is_absolute()):
        raise ValueError('invalid-migration-node')
    host_identity(value.get('host'))
    mappings = value.get('awg_instances', {})
    if (not isinstance(mappings, dict)
            or any(not isinstance(k, str) or not isinstance(v, str)
                   or not re.fullmatch(r'[A-Za-z0-9_=+.-]{1,15}', k)
                   or not re.fullmatch(r'[A-Za-z0-9_=+.-]{1,15}', v)
                   for k, v in mappings.items())):
        raise ValueError('invalid-migration-instance-map')


def _clients(block, key='clients', unique=('name',)):
    values = block.get(key) if isinstance(block, dict) else None
    if (not isinstance(values, list) or any(not isinstance(v, dict) for v in values)
            or len(values) > 256):
        raise ValueError('invalid-migration-client-collection')
    for field in unique:
        seen = set()
        for value in values:
            item = value.get(field)
            if not isinstance(item, str) or not item or item in seen:
                raise ValueError('conflicting-migration-client-identity')
            if field == 'name' and not NAME.fullmatch(item):
                raise ValueError('invalid-migration-device-name')
            if field == 'uuid' and not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', item):
                raise ValueError('invalid-migration-xray-identity')
            seen.add(item)
    return values


def _copy_client(source, target, name, *, key='clients', unique=('name',)):
    original, destination = _clients(source, key, unique), _clients(target, key, unique)
    selected = [item for item in original if item['name'] == name]
    existing = [item for item in destination if item['name'] == name]
    if len(selected) != 1:
        raise ValueError('missing-migration-client')
    if existing:
        if existing[0] != selected[0]:
            raise ValueError('conflicting-migration-client')
    else:
        destination.append(copy.deepcopy(selected[0]))
    _clients(target, key, unique)


def _xray_membership(source, target, name):
    before, after = source.get('cohorts', []), target.get('cohorts', [])
    if not isinstance(before, list) or not isinstance(after, list) or bool(before) != bool(after):
        raise ValueError('unsupported-migration-xray-cohort-map')
    if not before:
        return
    selected = {cohort['name'] for cohort in before if name in cohort['clients']}
    available = {cohort['name'] for cohort in after}
    existing = {cohort['name'] for cohort in after if name in cohort['clients']}
    if not selected or not selected <= available or existing and existing != selected:
        raise ValueError('unsupported-migration-xray-cohort-map')
    for cohort in after:
        if cohort['name'] in selected and name not in cohort['clients']:
            cohort['clients'].append(name)


def _snell(source, target, name, source_context, target_context):
    source_ids = {variant['id'] for variant in source_context['snell']['variants']}
    target_ids = {variant['id'] for variant in target_context['snell']['variants']}
    if source_ids != target_ids:
        raise ValueError('unsupported-migration-snell-variant-map')
    before = _clients(source.get('snell_secrets'), 'variants', ('id', 'psk'))
    after = _clients(target.get('snell_secrets'), 'variants', ('id', 'psk'))
    for variant_id in sorted(target_ids):
        original = [v for v in before if v['id'] == variant_id]
        destination = [v for v in after if v['id'] == variant_id]
        if len(original) != 1 or len(destination) != 1:
            raise ValueError('missing-migration-snell-variant')
        _copy_client(original[0], destination[0], name, key='users', unique=('name', 'userkey'))
    keys = [item['userkey'] for variant in after for item in _clients(variant, 'users', ('name', 'userkey'))]
    if len(keys) != len(set(keys)):
        raise ValueError('conflicting-migration-snell-userkey')


def _registry_entry(entry, source_node, target_node):
    result = copy.deepcopy(entry)
    hosts = result.get('hosts')
    if (not isinstance(hosts, list) or hosts.count(source_node['host']) != 1
            or target_node['host'] in hosts or any(not isinstance(host, str) for host in hosts)):
        raise ValueError('invalid-migration-device-hosts')
    index = hosts.index(source_node['host'])
    hosts[index] = target_node['host']
    cohorts = result.get('cohorts')
    if not isinstance(cohorts, list) or cohorts and len(cohorts) != len(hosts):
        raise ValueError('invalid-migration-device-cohorts')
    if cohorts:
        if cohorts[index] != source_node['cohort']:
            raise ValueError('conflicting-migration-source-cohort')
        cohorts[index] = target_node['cohort']
    if 'delivery_sources' in result:
        sources = result['delivery_sources']
        if (not isinstance(sources, list) or len(sources) != len(hosts)
                or sources[index] != source_node['secrets_file']):
            raise ValueError('conflicting-migration-device-sources')
        sources[index] = target_node['secrets_file']
    if result.get('awg_delivery_host') == source_node['host']:
        result['awg_delivery_host'] = target_node['host']
    if 'delivery_options' in result:
        options = result['delivery_options']
        validate_options(options)
        if (options['hosts'] != entry['hosts'] or options['cohorts'] != entry['cohorts']
                or options['awg_host'] != entry['awg_delivery_host']):
            raise ValueError('conflicting-migration-delivery-options')
        options.update(hosts=list(hosts), cohorts=list(cohorts), awg_host=result['awg_delivery_host'])
        validate_options(options)
    result.pop('migration_delivery', None)
    result.update(status='issued', formats=[], token_hash_prefix='', last_payload_identity={})
    return result


def _awg(source, target, name, source_node, target_node, source_context, target_context, entry):
    original = resolve_binding(source, source_context, name, source_node['host'])
    instance = target_node.get('awg_instances', {}).get(original.instance['name'], original.instance['name'])
    registry = target['client_registry']
    peers = [peer for item in target['amneziawg_secrets']['instances'] for peer in item['peers']
             if peer['name'] == name]
    if peers:
        existing = resolve_binding(target, target_context, name, target_node['host'], instance)
        if (any(existing.peer[key] != original.peer[key] for key in ('public_key', 'preshared_key'))
                or registry[name]['awg_private_key'] != source['client_registry'][name]['awg_private_key']
                or registry[name]['awg_public_key_fingerprint'] != source['client_registry'][name]['awg_public_key_fingerprint']):
            raise ValueError('conflicting-migration-awg-device')
        return
    if name in registry and registry[name].get('awg_binding') is not None:
        raise ValueError('conflicting-migration-awg-registry')
    selected = resolve_binding(target, target_context, name, target_node['host'], instance, enrollment=True)
    instances = effective_awg_instances(target['amneziawg_secrets'], target_context.get('amneziawg'),
                                        target_context.get('amneziawg_cohort'))
    # Allocation sees every address claim on this node, including servers of
    # other instances with overlapping pools. These reservations are never peers.
    allocation = {**selected.instance, 'peers': [peer for item in instances for peer in item['peers']]}
    for item in instances:
        if item['name'] != selected.instance['name']:
            allocation['peers'].append({'allowed_ips': {
                f'ipv{version}': str(ipaddress.ip_interface(item[f'address_v{version}']).ip) + ('/32' if version == 4 else '/128')
                for version in (4, 6)}})
    addresses = {f'ipv{version}': allocate_address(allocation, version) for version in (4, 6)}
    peer = copy.deepcopy(original.peer)
    peer['allowed_ips'] = addresses
    target['amneziawg_secrets']['instances'][selected.index]['peers'].append(peer)
    entry['awg_binding'] = selected.identity
    # An existing non-AWG registry retains delivery metadata, but acquires the
    # selected physical device's recovery authority together with its new peer.
    if name in registry:
        registry[name].update({key: entry[key] for key in ('awg_binding', 'awg_private_key', 'awg_public_key_fingerprint')})


def prepare_credentials(source: dict, target: dict, clients: list[str], source_node: dict, target_node: dict) -> dict:
    """Return an isolated target copy; never perform SOPS, provider or SSH IO."""
    try:
        return _prepare_credentials(source, target, clients, source_node, target_node)
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError('invalid-migration-credential-contract') from None


def _prepare_credentials(source, target, clients, source_node, target_node):
    _node(source_node)
    _node(target_node)
    if source_node['host'] == target_node['host'] or source_node['secrets_file'] == target_node['secrets_file']:
        raise ValueError('migration-requires-distinct-authorities')
    if (not isinstance(source, dict) or not isinstance(target, dict)
            or not isinstance(clients, list) or not clients or len(clients) > 256
            or any(not isinstance(name, str) or not NAME.fullmatch(name) for name in clients)
            or len(clients) != len(set(clients))):
        raise ValueError('invalid-migration-device-selection')
    source_context, target_context = context(source_node['cohort']), context(target_node['cohort'])
    source_awg, target_awg = host_context(source_node['cohort']), host_context(target_node['cohort'])
    for full, awg in ((source_context, source_awg), (target_context, target_awg)):
        for key in ('amneziawg', 'amneziawg_cohort'):
            if key in awg:
                full[key] = awg[key]
    enabled = {}
    for flag, default in BASELINE.items():
        before, after = source_context.get('vpn', {}).get(flag, default), target_context.get('vpn', {}).get(flag, default)
        if type(before) is not bool or type(after) is not bool or before != after:
            raise ValueError('unsupported-migration-transport-profile')
        enabled[flag] = after
    for document, selected_context in ((source, source_context), (target, target_context)):
        if (transport_errors(document, selected_context)
                or registry_errors(document, context=selected_context)):
            raise ValueError('invalid-migration-transport-authority')
    result = copy.deepcopy(target)
    registry = result.setdefault('client_registry', {})
    if not isinstance(registry, dict):
        raise TypeError('invalid-migration-registry')
    for name in clients:
        original = source.get('client_registry', {}).get(name)
        if not isinstance(original, dict) or original.get('status') not in ACTIVE:
            raise ValueError('missing-active-migration-device')
        existing = registry.get(name)
        if existing is not None and (not isinstance(existing, dict) or existing.get('status') not in ACTIVE):
            raise ValueError('conflicting-migration-registry')
        entry = _registry_entry(original, source_node, target_node)
        if enabled['enable_xray_reality'] or enabled['enable_nginx_xhttp']:
            _copy_client(source.get('xray'), result.get('xray'), name, unique=('name', 'uuid', 'short_id'))
            _xray_membership(source['xray'], result['xray'], name)
        if enabled['enable_hysteria']:
            _copy_client(source.get('hysteria'), result.get('hysteria'), name, unique=('name', 'password'))
        if enabled['enable_snell']:
            _snell(source, result, name, source_context, target_context)
        if enabled['enable_naive']:
            spec = importlib.util.spec_from_file_location('migration_naive', ROOT / 'scripts/naive-client.py')
            naive = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(naive)
            naive.validate_clients(source['naive_secrets']['clients'])
            _copy_client(source['naive_secrets'], result['naive_secrets'], name, unique=('name', 'username', 'password'))
            naive.validate_clients(result['naive_secrets']['clients'])
        if enabled['enable_amneziawg']:
            _awg(source, result, name, source_node, target_node, source_awg, target_awg, entry)
        elif existing is None:
            entry.update(awg_binding=None, awg_private_key='', awg_public_key_fingerprint='', awg_delivery_host='')
            if 'delivery_options' in entry:
                entry['delivery_options']['awg_host'] = ''
        if existing is None:
            registry[name] = entry
    if transport_errors(result, target_context) or registry_errors(result, context=target_context):
        raise ValueError('invalid-prepared-migration-authority')
    return result
