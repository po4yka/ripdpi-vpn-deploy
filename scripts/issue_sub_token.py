"""Issue or refresh an exact payload within the private encrypted transaction."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys

import yaml

from client_delivery_identity import authority, digest
from client_payload import ROOT, command, materialize, options, validate_options, paths
from encrypted_client_document import CommittedPublication, operate


def issue(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.client):
        raise ValueError('invalid-client')
    if 'VPN_SECRETS_FILE' in os.environ:
        raise ValueError('encrypted-issuance-input-required')
    environment = os.environ.get('ENV', 'prod')
    path = Path(os.environ.get('SOPS_FILE') or Path.home() / '.config/vpn-provision' / (environment + '.secrets.sops.yaml'))
    directory = os.environ.get('SUBSCRIPTION_DIR', '/var/lib/vpn-subscription')
    if not re.fullmatch(r'/[A-Za-z0-9_][A-Za-z0-9_./-]*', directory) or '..' in directory:
        raise ValueError('invalid-subscription-directory')
    token = args.refresh_token or secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    publication = {}

    def transform(doc):
        registry = doc.setdefault('client_registry', {})
        existing = registry.get(args.client, {})
        if not isinstance(existing, dict):
            raise ValueError('invalid-client-registry')
        if args.refresh_token:
            matches = [name for name, value in registry.items() if isinstance(value, dict) and value.get('token_hash_prefix') == token_hash[:8]]
            if not matches:
                raise ValueError('no client_registry entry; re-issue the token')
            if len(matches) != 1:
                raise ValueError('ambiguous client_registry entries; re-issue')
            if matches[0] != args.client:
                raise ValueError('token does not belong to requested client')
            if not existing.get('formats') or not existing.get('hosts') or not isinstance(existing.get('awg_delivery_host'), str):
                raise ValueError('registry lacks AWG delivery selection or delivery options; re-issue')
            # Old records can be explicitly redelivered, never compared as current.
            saved = existing.get('delivery_options')
            o = dict(saved) if saved is not None else options(existing['formats'][-1], hosts=existing['hosts'], cohorts=existing['cohorts'], awg_host=existing['awg_delivery_host'], expires=existing['token_expires'], utls='')
            o.update(hosts=existing['hosts'], cohorts=existing['cohorts'], awg_host=existing['awg_delivery_host'], expires=existing['token_expires'])
            if args.format is not None:
                o['format'] = args.format
        else:
            o = options(args.format or 'singbox')
        if args.expires is not None:
            o['expires'] = command([sys.executable, str(ROOT / 'scripts/normalize-subscription-expiry.py'), args.expires]).decode().strip() if args.expires else ''
        validate_options(o)
        auth = authority(doc, create=True)
        source_paths = existing.get('delivery_sources') if args.refresh_token else None
        source_paths = source_paths or [str(Path(p).absolute()) for p in paths(o['hosts'])]
        payload, bindings = materialize(args.client, o, private_only=True, source_paths=source_paths, documents={str(path.absolute()): doc}, extended=o['format'] == 'ripdpi')
        # These exact bytes are retained only in memory until the publication hook.
        publication['payload'] = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        publication['expires'] = o['expires']
        publication['options'] = o
        publication['sub_host'] = (doc.get('subscription') or {}).get('server_name') or (doc.get('nginx_xhttp') or {}).get('server_name')
        registry[args.client] = dict(awg_binding=None, awg_private_key='', awg_public_key_fingerprint='') | existing | dict(
            status='delivered', issued_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            formats=[o['format']], hosts=o['hosts'], cohorts=o['cohorts'], token_hash_prefix=token_hash[:8], token_expires=o['expires'], awg_delivery_host=o['awg_host'],
            delivery_sources=source_paths, delivery_options=o, last_payload_identity=digest(args.client, o, payload, bindings, auth))
        return doc, {}

    def publish():
        server_ip = command([str(ROOT / 'scripts/terraform-env.sh'), 'output', '-raw', 'server_ipv4']).decode().strip()
        admin = command([str(ROOT / 'scripts/terraform-env.sh'), 'output', '-raw', 'admin_user']).decode().strip()
        hostname = command([str(ROOT / 'scripts/terraform-env.sh'), 'output', '-raw', 'server_hostname']).decode().strip()
        # Only fixed, validated endpoint/user syntax enters the SSH destination.
        if not re.fullmatch(r'[A-Za-z0-9_.:-]+', server_ip) or not re.fullmatch(r'[a-z_][a-z0-9_-]*', admin):
            raise ValueError('invalid-delivery-endpoint')
        sub_host = publication['sub_host'] or hostname
        if not isinstance(sub_host, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', sub_host):
            raise ValueError('invalid-subscription-origin')
        port = command([sys.executable, str(ROOT / 'scripts/resolve-subscription-port.py'), '--host', hostname]).decode().strip()
        if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError('invalid-subscription-port')
        publication['url'] = 'https://' + sub_host + ':' + port + '/sub/' + token
        remote = directory + '/sub/' + token_hash
        target = admin + '@' + server_ip
        try:
            command(['ssh', target, "sudo test ! -e '" + directory + "/.vpn-sub-mirror-generations' -a ! -L '" + directory + "/.vpn-sub-mirror-current'"])
        except ValueError:
            raise ValueError('subscription mirror mode is active or delivery unavailable') from None
        # Refresh always replaces expiry metadata, including clearing an old expiry.
        meta = dict(client=args.client)
        if publication['expires']:
            meta['expires'] = publication['expires']
        command(['ssh', target, "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '" + remote + ".meta'"], data=json.dumps(meta).encode())
        command(['ssh', target, "sudo install -o vpn-bootstrap -g vpn-bootstrap -m 0600 /dev/stdin '" + remote + "'"], data=publication['payload'])

    operate(path, transform, before_publish=publish)
    # Only categorical audit fields; payload, authority and keyed digest stay private.
    try:
        subprocess.run([str(ROOT / 'scripts/audit-log.sh'), 'append-best-effort', '--action', 'issue-sub-token', '--client', args.client,
                    '--note', 'format=' + publication['options']['format'] + ' refresh=' + str(bool(args.refresh_token)).lower()
                    + ' overridden=' + ','.join(name for name in ('format', 'expires') if getattr(args, name) is not None)], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        print('subscription-delivery: audit unavailable after committed delivery', file=sys.stderr)
    if args.print_token_only:
        print(token)
        return 0
    else:
        if args.refresh_token:
            print('refresh options — reused: format,expires; overridden: ' + ('format' if args.format is not None else 'none'))
            if os.environ.get('HOSTS') or os.environ.get('COHORTS'):
                print('ignored: emitter HOSTS/COHORTS from the environment — registry authoritative on refresh')
        print('Subscription URL (long-lived, refresh-able):\n  ' + publication['url'])
        print('Revoke: append the token hash to subscription.revoked_tokens and re-deploy.')
    if args.qr:
        if shutil.which('qrencode') is None:
            print('qrencode not installed; skip --qr', file=sys.stderr)
            return 0
        # Recipient QR output remains private and never receives the URL in argv.
        import tempfile
        descriptor, temporary = tempfile.mkstemp(prefix='.' + args.client + '.qr.', dir=Path.cwd())
        os.close(descriptor)
        try:
            command(['qrencode', '-t', 'PNG', '-o', temporary], data=publication['url'].encode())
            os.replace(temporary, args.client + '.sub.qr.png')
        except (OSError, ValueError, subprocess.SubprocessError):
            print('subscription-delivery: delivery committed; QR unavailable', file=sys.stderr)
            return 3
        finally:
            Path(temporary).unlink(missing_ok=True)

    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client')
    parser.add_argument('--format', choices=['singbox', 'ripdpi'])
    parser.add_argument('--expires')
    parser.add_argument('--refresh-token')
    parser.add_argument('--print-token-only', action='store_true')
    parser.add_argument('--qr', action='store_true')
    args = parser.parse_args()
    try:
        return issue(args)
    except CommittedPublication:
        print('subscription-delivery: committed-durability-uncertain; inspect before retrying', file=sys.stderr)
        return 3
    except ValueError as error:
        # Only our fixed categories are exposed; downstream parsers may echo input.
        allowed = {'no client_registry entry; re-issue the token', 'ambiguous client_registry entries; re-issue', 'token does not belong to requested client',
                   'registry lacks AWG delivery selection or delivery options; re-issue', 'subscription mirror mode is active or delivery unavailable'}
        print('subscription-delivery: ' + (str(error) if str(error) in allowed else 'private transaction refused'), file=sys.stderr)
        return 2
    except (OSError, KeyError, TypeError, AttributeError, RecursionError, StopIteration, subprocess.SubprocessError, yaml.YAMLError):
        print('subscription-delivery: private transaction unavailable', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
