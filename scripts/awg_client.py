#!/usr/bin/env python3
"""Enroll, revoke and export a device through the sole AWG instance authority."""
from __future__ import annotations

import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import uuid

import yaml

from awg_device_binding import NAME, BindingError, allocate_address, public_key, registry_errors, resolve_binding
from encrypted_client_document import CommittedPublication, operate
from ripdpi_cohort_fingerprint import cohort_fingerprint
from transport_semantics import transport_errors, selected_context

ROOT = Path(__file__).resolve().parents[1]
PARAMS = ('wire_profile', 'jc', 'jmin', 'jmax', 's1', 's2', 'h1', 'h2', 'h3', 'h4')


def host_context(cohort=''):
    def merge(base, override):
        for name, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(name), dict):
                merge(base[name], value)
            else:
                base[name] = copy.deepcopy(value)
        return base
    if cohort and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}', cohort):
        raise BindingError('invalid-profile-cohort')
    context = yaml.safe_load((ROOT / 'ansible/roles/amneziawg/defaults/main.yml').read_text())
    for name in ('all', 'vpn', *([f'vpn-{cohort}'] if cohort else [])):
        path = ROOT / 'ansible/group_vars' / (name + '.yml')
        if path.exists():
            merge(context, yaml.safe_load(path.read_text()) or {})
        elif cohort:
            raise BindingError('missing-profile-cohort')
    # Like client emission, repository neutral origins do not describe the private deployment.
    context.pop("public_site_canonical_url", None)
    return selected_context(context, ['awg'])


def enroll(document, context, name, host, instance=None, *, all_profiles=False):
    binding = resolve_binding(document, context, name, host, instance, enrollment=True)
    addresses = {f'ipv{version}': allocate_address(binding.instance, version) for version in (4, 6)}
    registry = document.setdefault('client_registry', {})
    if not isinstance(registry, dict):
        raise BindingError('invalid-registry-binding')
    previous = registry.get(name)
    if name in registry and (all_profiles or not isinstance(previous, dict)
            or 'awg_binding' not in previous or previous['awg_binding'] is not None
            or previous.get('awg_private_key') != '' or previous.get('awg_public_key_fingerprint') != ''
            or previous.get('status') not in ('issued', 'delivered', 'active', 'stale')):
        raise BindingError('device-already-enrolled')
    private = base64.b64encode(secrets.token_bytes(32)).decode()
    public = public_key(private)
    peer = {'name': name, 'public_key': public, 'preshared_key': base64.b64encode(secrets.token_bytes(32)).decode(), 'allowed_ips': addresses}
    document['amneziawg_secrets']['instances'][binding.index]['peers'].append(peer)
    if all_profiles:
        for root, credential in (('xray', {'uuid': str(uuid.uuid4()), 'short_id': secrets.token_hex(4)}),
                                 ('hysteria', {'password': secrets.token_urlsafe(24)})):
            clients = document[root]['clients']
            if any(item['name'] == name for item in clients):
                raise BindingError('device-already-enrolled')
            clients.append({'name': name, **credential})
        for variant in document.get('snell_secrets', {}).get('variants', []):
            if any(user['name'] == name for user in variant['users']):
                raise BindingError('device-already-enrolled')
            generated = secrets.token_urlsafe(24)
            variant['users'].append({'name': name, 'userkey': generated})
        if 'naive_secrets' in document:
            spec = importlib.util.spec_from_file_location('naive_client', ROOT / 'scripts/naive-client.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            document['naive_secrets']['clients'] = module.update_clients(document['naive_secrets'].get('clients'), 'issue', name)
    registry[name] = {'status': 'issued', 'issued_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                      'formats': [], 'hosts': [host], 'cohorts': [], 'token_hash_prefix': '', 'token_expires': '',
                      'awg_public_key_fingerprint': 'sha256:' + hashlib.sha256(public.encode()).hexdigest()[:16],
                      'awg_private_key': private, 'awg_binding': binding.identity, 'awg_delivery_host': '',
                      'last_payload_identity': {}}
    if previous is not None:
        refreshed = {key: registry[name][key] for key in ('awg_binding', 'awg_private_key', 'awg_public_key_fingerprint')}
        registry[name] = {**previous, **refreshed}
    if (transport_errors(document, context, sections=["xray", "hysteria", "awg"] if all_profiles else ["awg"])
            or registry_errors(document, context=context)):
        raise BindingError('invalid-enrollment-contract')
    return document, {'client': name, 'binding': binding.identity, 'allowed_ips': addresses}


def revoke(document, context, name, host, instance=None):
    binding = resolve_binding(document, context, name, host, instance)
    entry = document.get('client_registry', {}).get(name)
    if not isinstance(entry, dict) or entry.get('awg_binding') != binding.identity:
        raise BindingError('invalid-registry-binding')
    document['amneziawg_secrets']['instances'][binding.index]['peers'].remove(binding.peer)
    entry.update(awg_binding=None, awg_private_key='', awg_public_key_fingerprint='')
    if registry_errors(document, context=context):
        raise BindingError('invalid-revocation-contract')
    return document, {'client': name, 'binding': binding.identity, 'awg_status': 'revoked'}


def export(document, context, name, host, instance, endpoint):
    binding = resolve_binding(document, context, name, host, instance)
    try:
        endpoint = str(ipaddress.ip_address(endpoint))
    except ValueError:
        raise BindingError('invalid-awg-endpoint') from None
    server, peer = binding.instance, binding.peer
    endpoint = ('[' + endpoint + ']' if ':' in endpoint else endpoint) + ':' + str(server['listen_port'])
    params = {name: server[name] for name in PARAMS}
    params.update({f"i{index}": server[f"i{index}"] for index in range(1, 6) if f"i{index}" in server})
    block = {'tag': 'p2-awg-' + name, 'address': [peer['allowed_ips'][family] for family in ('ipv4', 'ipv6')],
             'dns': server['dns_servers'], 'mtu': server['mtu'], **params,
             'private_key_placeholder': True, 'peer': {'public_key': public_key(server['server_private_key']),
             'preshared_key': peer['preshared_key'], 'endpoint': endpoint,
             'allowed_ips': ['0.0.0.0/0', '::/0'], 'persistent_keepalive': 25},
             'cohort_fingerprint': cohort_fingerprint(params)}
    return block


def config(block):
    fields = ['[Interface]', 'PrivateKey = <CLIENT_PRIVATE_KEY>', 'Address = ' + ', '.join(block['address']),
              'DNS = ' + ', '.join(block['dns']), 'MTU = ' + str(block['mtu'])]
    fields += [key.capitalize() + ' = ' + str(block[key]) for key in (*PARAMS, *(f"i{i}" for i in range(1, 6)))
               if key != "wire_profile" and key in block]
    peer = block['peer']
    fields += ['', '[Peer]', 'PublicKey = ' + peer['public_key'], 'PresharedKey = ' + peer['preshared_key'],
               'Endpoint = ' + peer['endpoint'], 'AllowedIPs = ' + ', '.join(peer['allowed_ips']), 'PersistentKeepalive = 25']
    return '\n'.join(fields) + '\n'


def committed_result(metadata):
    print(json.dumps({**metadata, 'publication': 'committed-durability-uncertain'}))
    print('awg-device-publication-committed-durability-uncertain', file=sys.stderr)
    return 3


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Put -- before a device name that begins with a dash.")
    parser.add_argument('action', choices=['enroll', 'revoke', 'bundle', 'config'])
    parser.add_argument('name')
    parser.add_argument('--host', required=True)
    parser.add_argument('--instance', default=os.environ.get('AWG_INSTANCE') or None)
    parser.add_argument('--cohort', default=os.environ.get('COHORT', ''))
    parser.add_argument('--endpoint')
    parser.add_argument('--output')
    parser.add_argument('--file')
    parser.add_argument('--all-profiles', action='store_true')
    parser.add_argument('--emit-uri', action='store_true')
    args = parser.parse_args()
    if NAME.fullmatch(args.name) is None:
        print('client name must contain 1-64 ASCII letters, digits, underscores or hyphens', file=sys.stderr)
        return 2
    committed_metadata = None
    try:
        context = host_context(args.cohort)
        if args.action in ('enroll', 'revoke'):
            if not args.file:
                raise BindingError('missing-encrypted-document')
            transform = lambda doc: (enroll(doc, context, args.name, args.host, args.instance, all_profiles=args.all_profiles)
                                     if args.action == 'enroll' else revoke(doc, context, args.name, args.host, args.instance))
            if args.emit_uri:
                if args.action != 'enroll' or not args.all_profiles or not args.output:
                    raise BindingError('private-uri-output-required')
                from private_client_artifact import new_output
                with new_output(args.output) as (write, validate):
                    def transaction(doc):
                        updated, metadata = transform(doc)
                        xray = next(item for item in updated['xray']['clients'] if item['name'] == args.name)
                        hy = next(item for item in updated['hysteria']['clients'] if item['name'] == args.name)
                        uris = [f"vless://{xray['uuid']}@<SERVER_IP>:443?type=raw&security=reality&flow=xtls-rprx-vision&sni=<SNI>&pbk=<REALITY_PUBLIC_KEY>&sid={xray['short_id']}#{args.name}",
                                f"hysteria2://{args.name}:{hy['password']}@<SERVER_IP>:443/?sni=<SERVER_HOSTNAME>#{args.name}"]
                        write('\n'.join(uris) + '\n')
                        return updated, {**metadata, 'output': args.output}
                    result = operate(args.file, transaction, before_publish=lambda _mark_external: validate())
                    committed_metadata = result
            else:
                result = operate(args.file, transform)
            print(json.dumps(result))
        else:
            payload = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
            if len(payload) > 4 * 1024 * 1024:
                raise BindingError('private-document-too-large')
            block = export(json.loads(payload), context, args.name, args.host, args.instance, args.endpoint)
            rendered = config(block) if args.action == 'config' else json.dumps(block) + '\n'
            if args.output:
                from private_client_artifact import publish
                publish(args.output, rendered)
                print(json.dumps({'client': args.name, 'output': args.output}))
            else:
                print(rendered, end='')
        return 0
    except CommittedPublication as error:
        return committed_result(error.metadata)
    except OSError:
        if committed_metadata is not None:
            return committed_result(committed_metadata)
        print('awg-device-operation-refused', file=sys.stderr)
        return 2
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError, subprocess.TimeoutExpired):
        print('awg-device-operation-refused', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
