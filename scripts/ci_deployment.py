"""Typed disposable CI profiles and confirmed controller-source binding."""
from __future__ import annotations

import base64
import hashlib
import re
from uuid import UUID

CI_PROFILES = {
    'ci-p0': ['p0-reality'],
    'ci-p0p1': ['p0-reality', 'p1-xhttp'],
    'ci-p0p1p2': ['p0-reality', 'p1-xhttp', 'p2-hysteria2'],
    'ci-p0p4': ['p0-reality'],
    'ci-p0p5': ['p0-reality'],
}


def confirmed_sources(document, host, metadata, memberships, identity, pin, contexts):
    """Validate the frozen handoff against source, inventory, pins and contexts."""
    import tailnet_management as tailnet
    from sshd_contexts import bind_contexts

    if (metadata.get('provider') != 'upcloud'
            or not re.fullmatch(r'ci-staging-[a-z0-9][a-z0-9-]{0,51}', metadata.get('env', ''))
            or len(memberships) != 1 or memberships[0] not in {'vpn-' + p for p in CI_PROFILES}):
        raise ValueError('ci-target-invalid')
    if (not isinstance(document, dict)
            or set(document) != {'schema_version', 'status', 'binding', 'confirmation', 'contexts'}
            or type(document['schema_version']) is not int or document['schema_version'] != 1
            or document['status'] != 'configured'):
        raise ValueError('ci-handoff-invalid')
    binding = tailnet.validate_binding(document['binding'])
    if (binding['inventory_alias'] != host['name'] or binding['public_address'] != host['address']
            or binding['ssh_port'] != host['port']
            or binding['source_revision'] != identity['DEPLOY_SOURCE_REVISION']
            or binding['deployable_digest'] != identity['DEPLOYABLE_SOURCE_DIGEST']):
        raise ValueError('ci-handoff-binding-invalid')
    cap = document['confirmation']
    if (not isinstance(cap, dict)
            or set(cap) != {'status', 'changed', 'nonce', 'generation', 'binding_sha256', 'lease', 'node'}
            or cap['status'] != 'configured' or cap['changed'] is not False
            or cap['generation'] != tailnet.RECOVERY_GENERATION
            or not isinstance(cap['nonce'], str) or not re.fullmatch(r'[0-9a-f]{32}', cap['nonce'])
            or cap['binding_sha256'] != hashlib.sha256(tailnet._canonical_bytes(binding)).hexdigest()):
        raise ValueError('ci-confirmation-invalid')
    lease = cap['lease']
    if (not isinstance(lease, dict) or set(lease) != {'boot_id', 'started_ms', 'deadline_ms'}
            or str(UUID(lease['boot_id'])) != lease['boot_id']
            or type(lease['started_ms']) is not int or lease['started_ms'] < 0
            or type(lease['deadline_ms']) is not int
            or lease['deadline_ms'] - lease['started_ms'] != 300000):
        raise ValueError('ci-confirmation-invalid')
    if (not 1 <= len(binding['approved_sources']) <= 8
            or not isinstance(document['contexts'], list) or len(document['contexts']) != 2
            or any(not isinstance(c, dict) or c.get('host') != c.get('addr') for c in document['contexts'])):
        raise ValueError('ci-contexts-invalid')
    tailnet._validate_confirmed_node(cap['node'], cap['nonce'])
    tailnet._validate_external_contexts(binding, cap['node'], document['contexts'])
    bind_contexts(contexts, host['address'], host['transport'], host['port'])
    if contexts != document['contexts'] or any(c['user'] != host['user'] for c in contexts):
        raise ValueError('ci-contexts-invalid')
    alias = host['alias'] if host['port'] == 22 else f"[{host['alias']}]:{host['port']}"
    matching = [line.split() for line in pin.decode().splitlines()
                if line and not line.startswith('#') and alias in line.split()[0].split(',')]
    if len(matching) != 1 or len(matching[0]) < 3 or matching[0][1] != 'ssh-ed25519':
        raise ValueError('ci-pin-invalid')
    if hashlib.sha256(base64.b64decode(matching[0][2], validate=True)).hexdigest() != binding['host_key_sha256']:
        raise ValueError('ci-pin-invalid')
    return {'approved_sources': binding['approved_sources']}
