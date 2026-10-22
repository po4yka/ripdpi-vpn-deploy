"""Pure fleet-wide device authority changes; no secrets leave the caller."""
from __future__ import annotations

import base64
import copy
import hashlib
import ipaddress
import secrets
import uuid

from awg_client import host_context
from awg_device_binding import (
    NAME,
    allocate_address,
    host_identity,
    public_key,
    registry_errors,
    resolve_binding,
)
from client_payload import context
from transport_semantics import effective_awg_instances, transport_errors

FLAGS = {'xray': ('enable_xray_reality', 'enable_nginx_xhttp'),
         'hysteria': ('enable_hysteria',), 'awg': ('enable_amneziawg',),
         'snell': ('enable_snell',), 'naive': ('enable_naive',)}
ACTIVE = {'issued', 'delivered', 'active', 'stale'}


def profile(cohort):
    result = context(cohort)
    awg = host_context(cohort)
    result.update({key: awg[key] for key in ('amneziawg', 'amneziawg_cohort') if key in awg})
    return result


def enabled(resolved):
    vpn = resolved.get('vpn', {})
    for flags in FLAGS.values():
        if any(type(vpn.get(flag, flag == 'enable_xray_reality')) is not bool for flag in flags):
            raise ValueError('invalid-device-profile')
    return {kind for kind, flags in FLAGS.items()
            if any(vpn.get(flag, flag == 'enable_xray_reality') for flag in flags)}


def collections(document):
    """Inspect actual authority even when the registry/profile points elsewhere."""
    for kind, section in (('xray', 'xray'), ('hysteria', 'hysteria'), ('naive', 'naive_secrets')):
        if section in document:
            yield kind, document[section], 'clients'
    for instance in document.get('amneziawg_secrets', {}).get('instances', []):
        yield 'awg', instance, 'peers'
    for variant in document.get('snell_secrets', {}).get('variants', []):
        yield 'snell', variant, 'users'


def discover(document, name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('invalid-device-name')
    found = {}
    for kind, block, field in collections(document):
        rows = block.get(field)
        if (not isinstance(rows, list) or len(rows) > 256 or any(not isinstance(row, dict) for row in rows)
                or len({row.get('name') for row in rows}) != len(rows)):
            raise ValueError('invalid-device-authority')
        matching = [row for row in rows if row.get('name') == name]
        if any(row.get('address_kind', 'device') != 'device' for row in matching):
            raise ValueError('routed-peer-is-not-device')
        if matching:
            found[kind] = found.get(kind, 0) + len(matching)
    registry = document.get('client_registry', {})
    if not isinstance(registry, dict):
        raise TypeError('invalid-device-registry')
    if name in registry:
        if not isinstance(registry[name], dict):
            raise ValueError('invalid-device-registry')
        found['registry'] = 1
    return found


def new_identity():
    """Call once, then persist the prepared documents before any authority write."""
    return {'uuid': str(uuid.uuid4()), 'short_id': secrets.token_hex(4),
            'hysteria_password': secrets.token_urlsafe(32), 'naive_password': secrets.token_urlsafe(32),
            'awg_private': base64.b64encode(secrets.token_bytes(32)).decode(),
            'awg_psk': base64.b64encode(secrets.token_bytes(32)).decode()}


def _registry(hosts, nodes, issued_at):
    return {'status': 'issued', 'issued_at': issued_at, 'formats': [], 'hosts': list(hosts),
            'cohorts': [nodes[host]['cohort'] for host in hosts], 'token_hash_prefix': '', 'token_expires': '',
            'awg_public_key_fingerprint': '', 'awg_private_key': '', 'awg_binding': None,
            'awg_delivery_host': '', 'last_payload_identity': {}}


def _awg(document, resolved, name, host, instance, identity, entry):
    selected = resolve_binding(document, resolved, name, host, instance, enrollment=True)
    instances = effective_awg_instances(document['amneziawg_secrets'], resolved.get('amneziawg'), resolved.get('amneziawg_cohort'))
    allocation = {**selected.instance, 'peers': [row for item in instances for row in item['peers']]}
    for item in instances:
        if item['name'] != selected.instance['name']:
            allocation['peers'].append({'allowed_ips': {
                f'ipv{version}': str(ipaddress.ip_interface(item[f'address_v{version}']).ip) + ('/32' if version == 4 else '/128')
                for version in (4, 6)}})
    address = {f'ipv{version}': allocate_address(allocation, version) for version in (4, 6)}
    public = public_key(identity['awg_private'])
    document['amneziawg_secrets']['instances'][selected.index]['peers'].append({
        'name': name, 'public_key': public, 'preshared_key': identity['awg_psk'], 'allowed_ips': address})
    entry.update(awg_binding=selected.identity, awg_private_key=identity['awg_private'],
                 awg_public_key_fingerprint='sha256:' + hashlib.sha256(public.encode()).hexdigest()[:16])


def issue(documents, nodes, name, hosts, issued_at, *, identity=None):
    """Enroll a fresh device on selected nodes, preserving every server identity."""
    if set(documents) != set(nodes) or not hosts or len(hosts) != len(set(hosts)) or not set(hosts) <= set(nodes):
        raise ValueError('invalid-device-fleet')
    if any(discover(doc, name) for doc in documents.values()):
        raise ValueError('device-already-exists-in-fleet')
    identity = identity or new_identity()
    result = copy.deepcopy(documents)
    for host in hosts:
        host_identity(host)
        node, doc = nodes[host], result[host]
        resolved = profile(node['cohort'])
        kinds = enabled(resolved)
        if not kinds:
            raise ValueError('device-profile-has-no-transports')
        if transport_errors(doc, resolved) or registry_errors(doc, context=resolved):
            raise ValueError('invalid-device-source-authority')
        entry = _registry(hosts, nodes, issued_at)
        if 'xray' in kinds:
            doc['xray']['clients'].append({'name': name, 'uuid': identity['uuid'], 'short_id': identity['short_id']})
            cohorts = doc['xray'].get('cohorts', [])
            chosen = node.get('xray_cohorts', [])
            if (len(chosen) != len(set(chosen)) or bool(cohorts) != bool(chosen)
                    or not set(chosen) <= {row['name'] for row in cohorts}):
                raise ValueError('explicit-device-xray-cohorts-required')
            for row in cohorts:
                if row['name'] in chosen:
                    row['clients'].append(name)
        if 'hysteria' in kinds:
            doc['hysteria']['clients'].append({'name': name, 'password': identity['hysteria_password']})
        if 'awg' in kinds:
            _awg(doc, resolved, name, host, node.get('awg_instance'), identity, entry)
        if 'snell' in kinds:
            selected = {row['id'] for row in resolved['snell']['variants']}
            variants = doc['snell_secrets']['variants']
            if not selected or not selected <= {row['id'] for row in variants}:
                raise ValueError('missing-device-snell-variant')
            for variant in variants:
                if variant['id'] in selected:
                    # Variant credentials must be distinct, including on the same device.
                    variant['users'].append({'name': name, 'userkey': secrets.token_urlsafe(32)})
        if 'naive' in kinds:
            doc['naive_secrets']['clients'].append({'name': name, 'username': name, 'password': identity['naive_password']})
        doc.setdefault('client_registry', {})[name] = entry
        if transport_errors(doc, resolved) or registry_errors(doc, context=resolved):
            raise ValueError('invalid-device-prepared-authority')
        _unique(doc)
    return result


def _unique(document):
    for kind, block, field in collections(document):
        fields = {'xray': ('name', 'uuid', 'short_id'), 'hysteria': ('name', 'password'),
                  'awg': ('name', 'public_key', 'preshared_key'), 'snell': ('name', 'userkey'),
                  'naive': ('name', 'username', 'password')}[kind]
        for key in fields:
            values = [row.get(key) for row in block[field]]
            if any(not isinstance(value, str) or not value for value in values) or len(values) != len(set(values)):
                raise ValueError('conflicting-device-credential')


def revoke(documents, name):
    """Remove all device credentials, including inactive variants and old nodes."""
    result = copy.deepcopy(documents)
    for doc in result.values():
        if not discover(doc, name):
            continue
        for _, block, field in collections(doc):
            block[field] = [row for row in block[field] if row['name'] != name]
        for cohort in doc.get('xray', {}).get('cohorts', []):
            cohort['clients'] = [client for client in cohort['clients'] if client != name]
        entry = doc.get('client_registry', {}).get(name)
        if entry is not None:
            entry.update(status='revoked', awg_binding=None, awg_private_key='', awg_public_key_fingerprint='',
                         awg_delivery_host='', last_payload_identity={}, token_hash_prefix='', formats=[])
            entry.pop('migration_delivery', None)
    return result
