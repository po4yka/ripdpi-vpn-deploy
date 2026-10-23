"""UpCloud recovery observations and exact Terraform plan admission."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys

from recovery_io import RecoveryError, load_manifest, module
from staging_lifecycle import GuardError

UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
ADDRESSES = {'upcloud_server.vpn', 'upcloud_firewall_rules.vpn', 'terraform_data.ssh_port'}
OUTPUTS = {'server_ipv4', 'server_ipv6', 'honeypot_ipv4', 'admin_user', 'ssh_port',
           'server_hostname', 'zone', 'public_listeners', 'nat_source_port_range'}


def server_from_state(state, manifest):
    if not state:
        return None
    try:
        resources = state['resources']
        selected = []
        for resource in resources:
            if resource.get('mode') != 'managed':
                continue
            if resource.get('module'):
                raise ValueError
            address = resource['type'] + '.' + resource['name']
            if address not in ADDRESSES:
                raise ValueError
            if address == 'upcloud_server.vpn':
                selected.extend(instance['attributes'] for instance in resource['instances'])
        if not selected:
            return None
        if len(selected) != 1 or selected[0]['hostname'] != manifest['hostname'] or not UUID.fullmatch(selected[0]['id']):
            raise ValueError
        return selected[0]
    except (KeyError, TypeError, ValueError):
        raise RecoveryError('recovery-provider-state-mismatch') from None


def review_plan(plan, manifest, *, existing=None):
    """Accept only the one replacement root, without deletion or credential output."""
    try:
        if plan.get('errored') or plan.get('complete') is False:
            raise ValueError
        changes = plan.get('resource_changes', [])
        if not isinstance(changes, list):
            raise TypeError
        server = None
        summary = []
        for item in changes:
            if item.get('mode') == 'data':
                continue
            address, change = item['address'], item['change']
            actions = change['actions']
            if address not in ADDRESSES or actions not in (['no-op'], ['create'], ['update']):
                raise ValueError
            if address == 'upcloud_server.vpn':
                if server is not None:
                    raise ValueError
                server = change['after']
                if (server['hostname'] != manifest['hostname']
                        or server['labels'].get('recovery_id') != manifest['id']
                        or server['labels'].get('managed_by') != 'terraform'
                        or server.get('storage_devices')
                        or (existing is None and actions != ['create'])
                        or (existing is not None and (actions == ['create'] or change['before'].get('id') != existing['id']))):
                    raise ValueError
            if actions != ['no-op']:
                summary.append({'address': address, 'actions': actions})
        for name, change in plan.get('output_changes', {}).items():
            if name not in OUTPUTS or change['actions'] not in (['no-op'], ['create'], ['update'], ['delete']):
                raise ValueError
            if change['actions'] != ['no-op']:
                summary.append({'output': name, 'actions': change['actions']})
        if server is None:
            # Empty plans may omit changes only after state already proved the node.
            if existing is None or changes:
                raise ValueError
            server = existing
        return {'changes': summary, 'server': {key: server[key] for key in ('hostname', 'zone', 'plan', 'labels')}}
    except (KeyError, TypeError, ValueError):
        raise RecoveryError('recovery-saved-plan-outside-scope') from None


def server_identity(server, manifest):
    """Reduced live identity never carries provider-generated credentials."""
    try:
        if (not UUID.fullmatch(server['uuid']) or server['hostname'] != manifest['hostname']
                or type(server['created']) is not int or server['created'] <= 0):
            raise ValueError
        labels = server.get('labels', {}).get('label', [])
        if not isinstance(labels, list):
            raise TypeError
        if len({row['key'] for row in labels}) != len(labels):
            raise ValueError
        labels = {row['key']: row['value'] for row in labels}
        if labels.get('recovery_id') != manifest['id'] or labels.get('managed_by') != 'terraform':
            raise ValueError
        ips = server['ip_addresses']['ip_address']
        public = [row['address'] for row in ips if row['access'] == 'public' and row['family'] == 'IPv4']
        if not public or len(set(public)) != len(public):
            raise ValueError
        for address in public:
            if str(ipaddress.IPv4Address(address)) != address:
                raise ValueError
        return {key: server[key] for key in ('uuid', 'hostname', 'created', 'zone', 'plan', 'state')} | {
            'labels': labels, 'public_ipv4': sorted(public)}
    except (KeyError, TypeError, ValueError):
        raise RecoveryError('recovery-live-resource-mismatch') from None


def observe(manifest):
    guard = module('staging-cleanup-guard')
    request = guard._upcloud_request(guard._provider_authorization())
    if guard._authenticated_account_username(request) != manifest['account']:
        raise RecoveryError('recovery-provider-account-changed')
    status, payload = request('/1.3/server')
    try:
        rows = payload['servers']['server']
        if status != 200 or not isinstance(rows, list) or len(rows) > 4096:
            raise ValueError
        found = []
        for row in rows:
            if row.get('hostname') != manifest['hostname']:
                continue
            identifier = row['uuid']
            if not UUID.fullmatch(identifier):
                raise ValueError
            status, details = request('/1.3/server/' + identifier)
            if status != 200:
                raise ValueError
            found.append(server_identity(details['server'], manifest))
        if len(found) > 1:
            raise RecoveryError('recovery-provider-resource-ambiguous')
        return {'account_sha256': hashlib.sha256(manifest['account'].encode()).hexdigest(), 'servers': found}
    except (KeyError, TypeError, ValueError):
        raise RecoveryError('recovery-provider-observation-refused') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(observe(load_manifest(args.manifest)), sort_keys=True))
        return 0
    except (RecoveryError, GuardError, OSError, ValueError, KeyError, TypeError):
        print('recovery-provider-observation-failed', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
