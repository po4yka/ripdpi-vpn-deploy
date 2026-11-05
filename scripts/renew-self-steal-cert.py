#!/usr/bin/env python3
"""Reissue the REALITY self-steal certificate off-node before it expires.

The P0 node has no public HTTP listener, so the pair is issued here with an
ACME DNS-01 challenge on the Vultr zone and written into a new SOPS document
beside the source. Current values come only from the `make decrypt` output in
VPN_SECRETS_FILE, and the DNS API key only from VULTR_API_KEY in the process
environment. The source document is never changed, deployment stays a reviewed
step, and the issued key leaves the disk once it is in SOPS.
"""
import argparse
import datetime
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

LEGO_VERSION = '5.6.0'
RENEW_BEFORE = datetime.timedelta(days=30)
# Let's Encrypt is shortening certificate lifetimes; keep this below them.
MIN_NEW_LIFETIME = datetime.timedelta(days=40)
SELF_STEAL = '["reality_self_steal"]'
RENEWED = '-self-steal-renewed-'


class RenewalError(Exception):
    pass


def run(argv, *, env=None, data=None, timeout=120):
    try:
        result = subprocess.run(argv, input=data, env=env, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RenewalError(Path(argv[0]).name + '-unavailable') from None
    if result.returncode != 0:
        raise RenewalError(Path(argv[0]).name + '-failed')
    return result.stdout


def materialized_secrets():
    """Read only the canonical `make decrypt` output (the SOPS gate)."""
    path = os.environ.get('VPN_SECRETS_FILE', '')
    if not path or not Path(path).is_file():
        raise RenewalError('decrypted-secrets-required')
    with open(path) as handle:
        document = yaml.safe_load(handle)
    pair = document.get('reality_self_steal') if isinstance(document, dict) else None
    if not isinstance(pair, dict) or not all(isinstance(pair.get(k), str) for k in ('server_name', 'cert_pem')):
        raise RenewalError('self-steal-secrets-missing')
    nginx = document.get('nginx_xhttp') or {}
    return pair['server_name'].strip(), pair['cert_pem'], str(nginx.get('server_name', '') if isinstance(nginx, dict) else '')


def not_after(cert_pem):
    out = run(['openssl', 'x509', '-noout', '-enddate'], data=cert_pem.encode()).decode().strip()
    stamp = out.removeprefix('notAfter=')
    return datetime.datetime.strptime(stamp, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=datetime.timezone.utc)


def dns_names(cert_pem):
    # `-ext` is missing from the LibreSSL in macOS; `-text` works in both.
    text = run(['openssl', 'x509', '-noout', '-text'], data=cert_pem.encode()).decode().splitlines()
    for index, line in enumerate(text):
        if line.strip().startswith('X509v3 Subject Alternative Name'):
            return [name.strip() for name in text[index + 1].split(',')]
    return []


def check_pair(cert_pem, key_pem, server_name, now):
    if dns_names(cert_pem) != ['DNS:' + server_name]:
        raise RenewalError('issued-name-mismatch')
    if run(['openssl', 'x509', '-noout', '-pubkey'], data=cert_pem.encode()) != run(
            ['openssl', 'pkey', '-pubout'], data=key_pem.encode()):
        raise RenewalError('issued-key-mismatch')
    if not_after(cert_pem) - now < MIN_NEW_LIFETIME:
        raise RenewalError('issued-lifetime-too-short')


def renewed_documents(sops_file):
    stem, suffix = sops_file.name.split('.', 1)
    pattern = re.compile(re.escape(stem + RENEWED) + r'\d{8}\.' + re.escape(suffix) + '$')
    return sorted(p for p in sops_file.parent.iterdir() if pattern.fullmatch(p.name))


def renew(sops_file, lego_path, *, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    env = dict(os.environ)
    server_name, current_cert, nginx_name = materialized_secrets()
    expiry = not_after(current_cert)
    if expiry - now > RENEW_BEFORE:
        return {'state': 'not-due', 'days_remaining': (expiry - now).days}
    # A renewed document that is not deployed yet already holds the next pair.
    pending = renewed_documents(sops_file)
    if pending:
        return {'state': 'awaiting-deploy', 'output': str(pending[-1]), 'days_remaining': (expiry - now).days}
    if nginx_name.strip().lower() == server_name.lower():
        raise RenewalError('shared-hostname-needs-both-certificates')
    stem, suffix = sops_file.name.split('.', 1)
    output = sops_file.with_name(stem + RENEWED + now.strftime('%Y%m%d') + '.' + suffix)
    version = run(['lego', '--version']).decode().split()
    if len(version) < 3 or version[2] != LEGO_VERSION:
        raise RenewalError('lego-version-mismatch')
    lego_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    lego_path.chmod(0o700)
    if not env.get('VULTR_API_KEY'):
        raise RenewalError('dns-credential-required')
    lego_env = {**env,
                # Vultr publishes records slowly; the default 60s wait fails.
                'VULTR_PROPAGATION_TIMEOUT': '600', 'VULTR_POLLING_INTERVAL': '10'}
    issued = lego_path / 'certificates'
    candidate = None
    try:
        run(['lego', 'run', '--accept-tos', '--path', str(lego_path), '--dns', 'vultr',
             '--dns.resolvers', 'ns1.vultr.com:53', '--domains', server_name, '--key-type', 'EC256'],
            env=lego_env, timeout=900)
        cert_pem = (issued / (server_name + '.crt')).read_text()
        key_pem = (issued / (server_name + '.key')).read_text()
        check_pair(cert_pem, key_pem, server_name, now)
        # sops picks the document format from the extension, so the candidate keeps it.
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.renewal-', suffix='.' + suffix,
                                         delete=False) as handle:
            candidate = Path(handle.name)
        shutil.copy2(sops_file, candidate)
        for field, value in (('cert_pem', cert_pem), ('key_pem', key_pem)):
            run(['sops', 'set', '--value-stdin', str(candidate), SELF_STEAL + '["' + field + '"]'],
                env=env, data=json.dumps(value).encode())
        os.link(candidate, output)
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
        # The issued key is plaintext; SOPS is its only durable home.
        shutil.rmtree(issued, ignore_errors=True)
    return {'state': 'renewed', 'output': str(output), 'not_after': not_after(cert_pem).isoformat(),
            'next': 'review and deploy the P0 node with this SOPS document (make dry-run, then make deploy)'}


def notify(message):
    if shutil.which('osascript'):
        subprocess.run(['osascript', '-e', 'display notification ' + json.dumps(message) + ' with title "vpn-deploy"'],
                       capture_output=True, timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sops-file', type=Path, required=True)
    parser.add_argument('--lego-path', type=Path, required=True)
    args = parser.parse_args()
    try:
        args.lego_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        # One renewal at a time: the pending check, issuance and cleanup share lego state.
        with open(args.lego_path / 'renewal.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = renew(args.sops_file.resolve(), args.lego_path)
    except BlockingIOError:
        print('self-steal-renewal-refused: renewal-in-progress', file=sys.stderr)
        return 1
    except (RenewalError, OSError, ValueError, yaml.YAMLError) as error:
        category = str(error) if isinstance(error, RenewalError) else type(error).__name__
        print('self-steal-renewal-refused: ' + category, file=sys.stderr)
        notify('Self-steal certificate renewal failed: ' + category)
        return 1
    print(json.dumps(result, sort_keys=True))
    if result['state'] in ('renewed', 'awaiting-deploy'):
        notify('Self-steal certificate renewed; review and deploy the P0 node')
    return 0


if __name__ == '__main__':
    sys.exit(main())
