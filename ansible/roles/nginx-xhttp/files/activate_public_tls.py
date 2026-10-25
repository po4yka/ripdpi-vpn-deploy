#!/usr/bin/env python3
"""Validate the cloud certificate authority and use guarded nginx publication."""

from __future__ import annotations

import argparse
import base64
import json
import ipaddress
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

CONFIG = Path('/etc/vpn-public-tls/config.json')
RENEWAL = Path('/etc/letsencrypt/renewal')
CA = 'https://acme-v02.api.letsencrypt.org/directory'
ISSUER = 'vpn-public-tls-issuer.service'
LIVE = Path('/etc/letsencrypt/live')
ARCHIVE = Path('/etc/letsencrypt/archive')
TLS = Path('/etc/nginx/tls')
HTTP = Path('/etc/nginx/conf.d/vpn-public-acme.conf')
HELPER = Path('/usr/local/libexec/vpn-nginx-transaction')
APPLICATION_RECEIPT = Path('/var/lib/vpn-nginx-publication/nginx.service/nginx-xhttp.activated.json')
PUBLIC_RECEIPT = Path('/var/lib/vpn-nginx-publication/nginx.service/public-tls.activated.json')
DOMAIN = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+')


class Refusal(ValueError):
    """A candidate has no safe publication authority."""


def read_owned(path: Path, *, private=False, archive=False) -> bytes:
    original = path
    if archive:
        path = path.resolve(strict=True)
        if not path.is_relative_to(ARCHIVE):
            raise Refusal('certificate-lineage-path')
        for parent in [ARCHIVE, *path.relative_to(ARCHIVE).parents]:
            parent = parent if parent.is_absolute() else ARCHIVE / parent
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise Refusal('certificate-lineage-owner')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or info.st_mode & 0o022
                or (private and info.st_mode & 0o077) or info.st_size > 131072):
            raise Refusal('unsafe-certificate-file')
        data = os.read(descriptor, 131073)
        if len(data) > 131072 or os.stat(original).st_ino != info.st_ino:
            raise Refusal('certificate-file-changed')
        return data
    finally:
        os.close(descriptor)


def configuration(value):
    if (not isinstance(value, dict) or set(value) != {'name', 'domains', 'http_vhost', 'email'}
            or not isinstance(value['email'], str) or len(value['email']) > 254
            or re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value['email']) is None
            or not isinstance(value['name'], str) or DOMAIN.fullmatch(value['name']) is None
            or not isinstance(value['domains'], list) or not 1 <= len(value['domains']) <= 4
            or any(not isinstance(name, str) or len(name) > 253 or DOMAIN.fullmatch(name) is None for name in value['domains'])
            or value['domains'][0] != value['name']
            or len(set(value['domains'])) != len(value['domains'])
            or not isinstance(value['http_vhost'], str) or not 1 <= len(value['http_vhost']) <= 16384):
        raise Refusal('invalid-certificate-contract')
    for name in value['domains']:
        try:
            ipaddress.ip_address(name)
        except ValueError:
            continue
        raise Refusal('invalid-certificate-contract')
    return value


def openssl(*args):
    result = subprocess.run(['openssl', *map(str, args)], input=b'', capture_output=True,
                            timeout=30, check=False)
    if result.returncode:
        raise Refusal('certificate-validation-failed')
    return result.stdout


def validate_pair(certificate: Path, key: Path, domains, *, retained=False):
    sans = set(re.findall(rb'DNS:([^,\s]+)', openssl('x509', '-in', certificate, '-noout', '-ext', 'subjectAltName')))
    if sans != {name.encode() for name in domains}:
        raise Refusal('certificate-domain-set')
    if not retained:
        openssl('x509', '-in', certificate, '-noout', '-checkend', '86400')
    openssl('verify', *(['-no_check_time'] if retained else []), '-purpose', 'sslserver', '-untrusted', certificate, certificate)
    if (openssl('x509', '-in', certificate, '-pubkey', '-noout').strip()
            != openssl('pkey', '-in', key, '-pubout').strip()):
        raise Refusal('certificate-key-mismatch')


def request(config, *, prepare=False, check=False):
    config = configuration(config)
    destinations = [TLS / (config['name'] + suffix) for suffix in ('.fullchain.pem', '.key')]
    if APPLICATION_RECEIPT.exists():
        previous = json.loads(read_owned(APPLICATION_RECEIPT, private=True))
        if any(str(path) in previous.get('files', {}) for path in destinations):
            raise Refusal('supplied-certificate-owner-requires-recreation')
    if prepare:
        sources = destinations
        present = [os.path.lexists(path) for path in sources]
        if any(present) and not all(present):
            raise Refusal('incomplete-active-certificate')
        if all(present):
            if not os.path.lexists(PUBLIC_RECEIPT):
                raise Refusal('unclaimed-active-certificate')
            accepted = json.loads(read_owned(PUBLIC_RECEIPT, private=True))
            if accepted.get('owner') != 'public-tls' or not all(str(path) in accepted.get('files', {}) for path in destinations):
                raise Refusal('unclaimed-active-certificate')
    else:
        sources = [LIVE / config['name'] / name for name in ('fullchain.pem', 'privkey.pem')]
        present = [True, True]
    rows = [{'path': str(HTTP), 'kind': 'file', 'content_b64': base64.b64encode(config['http_vhost'].encode()).decode(),
             'mode': 0o640, 'uid': 0, 'gid': 0}]
    if all(present):
        material = [read_owned(path, private=index == 1, archive=not prepare) for index, path in enumerate(sources)]
        # Certbot can change its lineage concurrently. Validate the exact captured bytes.
        with tempfile.TemporaryDirectory(prefix='vpn-public-tls-') as directory:
            copies = [Path(directory) / name for name in ('certificate.pem', 'key.pem')]
            for path, data in zip(copies, material):
                with path.open('xb') as stream:
                    path.chmod(0o600)
                    stream.write(data)
            validate_pair(*copies, config['domains'], retained=prepare)
        rows += [{'path': str(path), 'kind': 'file', 'content_b64': base64.b64encode(data).decode(),
                  'mode': mode, 'uid': 0, 'gid': 0}
                 for path, data, mode in zip(destinations, material, (0o644, 0o600))]
    else:
        rows += [{'path': str(path), 'kind': 'absent'} for path in destinations]
    if prepare:
        rows.append({'path': str(CONFIG), **({'kind': 'file', 'content_b64': base64.b64encode(read_owned(CONFIG, private=True)).decode(),
                     'mode': 0o600, 'uid': 0, 'gid': 0} if CONFIG.exists() else {'kind': 'absent'})})
    else:
        rows.append({'path': str(CONFIG), 'kind': 'file', 'content_b64': base64.b64encode(json.dumps(config).encode()).decode(),
                     'mode': 0o600, 'uid': 0, 'gid': 0})
    return {'owner': 'public-tls', 'roots': sorted({str(TLS.parent), str(CONFIG.parent)}), 'files': rows,
            'validate_argv': ['/usr/sbin/nginx', '-t'], 'unit': 'nginx.service', 'activation': 'reload',
            'credential_root': '', 'runtime_directories': [], 'activate_inactive': True,
            'desired_enabled': True, 'prune_releases': None, 'check': check}


def load_helper():
    loader = importlib.machinery.SourceFileLoader('vpn_nginx_publication', str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def lineage_claim(config):
    return {'schema': 1, 'name': config['name'], 'domains': config['domains'],
            'email': config['email'], 'ca': CA, 'challenge': 'http-01', 'webroot': '/var/lib/vpn-public-tls'}


def claim_lineage(helper, state, config):
    claim = lineage_claim(config)
    path = state / ('public-tls-lineage-' + config['name'] + '.json')
    if os.path.lexists(path):
        if json.loads(read_owned(path, private=True)) != claim:
            raise Refusal('certificate-lineage-authority-changed')
    else:
        if any(os.path.lexists(path) for path in (LIVE / config['name'], ARCHIVE / config['name'], RENEWAL / (config['name'] + '.conf'))):
            raise Refusal('foreign-certificate-lineage')
        helper.persist(path, claim)


def run_certbot(config):
    # PID1 gives the issuer a separate read-only view of all nginx authority.
    command = ['/usr/bin/systemd-run', '--unit=' + ISSUER, '--no-block', '--quiet',
               '--service-type=oneshot', '-p', 'RemainAfterExit=yes', '-p', 'User=root', '-p', 'UMask=0077',
               '-p', 'TimeoutStartSec=480', '-p', 'TimeoutStopSec=15', '-p', 'KillMode=control-group',
               '-p', 'StandardOutput=null', '-p', 'StandardError=null',
               '-p', 'NoNewPrivileges=true', '-p', 'PrivateTmp=true', '-p', 'ProtectHome=true',
               '-p', 'ProtectSystem=strict', '-p', 'ProtectKernelTunables=true', '-p', 'ProtectKernelModules=true',
               '-p', 'ProtectControlGroups=true', '-p', 'RestrictNamespaces=true', '-p', 'LockPersonality=true',
               '-p', 'RestrictRealtime=true', '-p', 'RestrictSUIDSGID=true', '-p', 'SystemCallArchitectures=native',
               '-p', 'CapabilityBoundingSet=', '-p', 'RestrictAddressFamilies=AF_INET AF_INET6',
               '-p', 'InaccessiblePaths=/run/systemd/private /run/dbus/system_bus_socket',
               '-p', 'ReadWritePaths=/etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt /var/lib/vpn-public-tls',
               '-p', 'ReadOnlyPaths=/etc/nginx /etc/vpn-public-tls',
               '/usr/bin/certbot', 'certonly', '--config', '/dev/null', '--non-interactive', '--agree-tos', '--no-eff-email',
               '--server', CA, '--webroot', '--webroot-path', '/var/lib/vpn-public-tls', '--cert-name', config['name'],
               '--email', config['email'], '--keep-until-expiring']
    command += ['--domain=' + domain for domain in config['domains']]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    if result.returncode:
        raise Refusal('certificate-issuance-failed')
    deadline = time.monotonic() + 490
    while time.monotonic() < deadline:
        status = issuer_state()
        if status['ActiveState'] == 'failed':
            raise Refusal('certificate-issuance-failed')
        if (status['ActiveState'], status['SubState'], status['MainPID'], status['Job']) in {
                ('active', 'exited', '0', ''), ('active', 'exited', '0', '0')}:
            return
        time.sleep(1)
    raise Refusal('certificate-issuance-timeout')


def boot_id():
    value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value) is None:
        raise Refusal('issuer-boot-identity')
    return value


def issuer_state():
    result = subprocess.run(['/usr/bin/systemctl', 'show', ISSUER,
        '--property=LoadState,ActiveState,SubState,MainPID,Job'], capture_output=True, timeout=15, check=False)
    if result.returncode not in (0, 1):
        raise Refusal('issuer-state-unconfirmed')
    status = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
    if set(status) != {'LoadState', 'ActiveState', 'SubState', 'MainPID', 'Job'}:
        raise Refusal('issuer-state-unconfirmed')
    return status


def stop_issuer():
    stopped = subprocess.run(['/usr/bin/systemctl', 'stop', ISSUER], capture_output=True, timeout=30, check=False)
    if stopped.returncode:
        raise Refusal('issuer-stop-unconfirmed')
    status = issuer_state()
    if status['LoadState'] == 'loaded' and status['ActiveState'] == 'failed':
        result = subprocess.run(['/usr/bin/systemctl', 'reset-failed', ISSUER], capture_output=True, timeout=15, check=False)
        if result.returncode:
            raise Refusal('issuer-stop-unconfirmed')
        status = issuer_state()
    return status


def recover_issuer(helper, state):
    path = state / 'public-tls-issuer.json'
    lease = helper.private_json(path)
    if lease is None:
        return
    if (not isinstance(lease, dict) or set(lease) != {'schema', 'unit', 'boot_id'}
            or type(lease['schema']) is not int or lease['schema'] != 1 or lease['unit'] != ISSUER
            or not isinstance(lease['boot_id'], str)
            or re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', lease['boot_id']) is None):
        raise Refusal('issuer-lease-authority')
    status = issuer_state()
    if status['MainPID'] != '0' or status['Job'] not in ('', '0'):
        raise Refusal('issuer-still-running')
    if status['LoadState'] == 'not-found':
        # Before PID1 acknowledges a launch, a surviving systemd-run may still submit it.
        if lease['boot_id'] == boot_id():
            raise Refusal('issuer-launch-unconfirmed-reboot-required')
    elif (status['LoadState'] != 'loaded'
            or (status['ActiveState'], status['SubState']) not in {
                ('active', 'exited'), ('inactive', 'dead'), ('failed', 'failed')}):
        raise Refusal('issuer-still-running')
    else:
        status = stop_issuer()
    if (status['LoadState'] not in ('loaded', 'not-found') or status['ActiveState'] not in ('inactive', 'failed')
            or status['SubState'] not in ('dead', 'failed') or status['MainPID'] != '0' or status['Job'] not in ('', '0')):
        raise Refusal('issuer-stop-unconfirmed')
    helper.clear(path)


def issue(helper, config=None, *, renewal=False):
    state = helper.STATE_ROOT / 'nginx.service'
    with helper.unit_lock(state, allow_issuer=True) as descriptor:
        recover_issuer(helper, state)
        if renewal and os.path.lexists(state / 'site.json'):
            raise Refusal('site-transaction-busy')
        if config is None:
            config = json.loads(read_owned(CONFIG, private=True))
        config = configuration(config)
        claim_lineage(helper, state, config)
        status = issuer_state()
        if (status['LoadState'], status['ActiveState'], status['SubState'], status['MainPID']) != (
                'not-found', 'inactive', 'dead', '0') or status['Job'] not in ('', '0'):
            raise Refusal('unclaimed-issuer-unit')
        helper.persist(state / 'public-tls-issuer.json', {'schema': 1, 'unit': ISSUER, 'boot_id': boot_id()})
        try:
            run_certbot(config)
        finally:
            recover_issuer(helper, state)
        return helper.publish(request(config), outside_site=renewal, lock_fd=descriptor)


def retire(helper):
    state = helper.STATE_ROOT / 'nginx.service'
    with helper.unit_lock(state, allow_issuer=True) as descriptor:
        recover_issuer(helper, state)
        receipt = helper.private_json(state / 'public-tls.activated.json')
        if receipt is None:
            return {'changed': False}
        helper.validate_receipt(receipt, 'public-tls', 'nginx.service')
        for path in receipt['files']:
            value = Path(path)
            if value not in {HTTP, CONFIG} and not (value.parent == TLS and re.fullmatch(
                    r'[a-z0-9.-]+[.](?:fullchain[.]pem|key)', value.name)):
                raise Refusal('unexpected-retired-tls-authority')
        document = {'owner': 'public-tls', 'roots': receipt['roots'],
                    'files': [{'path': path, 'kind': 'absent'} for path in receipt['files']],
                    'validate_argv': ['/usr/sbin/nginx', '-t'], 'unit': 'nginx.service', 'activation': 'reload',
                    'credential_root': '', 'runtime_directories': [], 'activate_inactive': False,
                    'desired_enabled': None, 'prune_releases': None, 'check': False}
        return helper.publish(document, lock_fd=descriptor)


def check_backup(helper):
    config = configuration(json.loads(read_owned(CONFIG, private=True)))
    state = helper.STATE_ROOT / 'nginx.service'
    helper.require_issuer_closed(state)
    if any(os.path.lexists(state / name) for name in ('site.json', 'pending.json')):
        raise Refusal('certificate-transaction-recovery-required')
    claim = json.loads(read_owned(state / ('public-tls-lineage-' + config['name'] + '.json'), private=True))
    if claim != lineage_claim(config):
        raise Refusal('certificate-lineage-authority-changed')
    receipt = json.loads(read_owned(PUBLIC_RECEIPT, private=True))
    helper.validate_receipt(receipt, 'public-tls', 'nginx.service')
    helper.verify_witnesses(receipt['files'])
    for path in (CONFIG, HTTP, TLS / (config['name'] + '.fullchain.pem'), TLS / (config['name'] + '.key')):
        if receipt['files'].get(str(path), {}).get('kind') != 'file':
            raise Refusal('certificate-recovery-incomplete')
    request(config)  # This checks the exact trusted live Certbot pair too.
    accounts = LIVE.parent / 'accounts'
    complete = False
    for private in accounts.rglob('private_key.json'):
        paths = (private, private.with_name('meta.json'), private.with_name('regr.json'))
        documents = [json.loads(read_owned(path, private=path == private)) for path in paths]
        if all(isinstance(document, dict) and document for document in documents):
            complete = True
    if not complete:
        raise Refusal('certificate-account-recovery-incomplete')
    return {'status': 'validated', 'changed': False}


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--issue', action='store_true')
    action.add_argument('--renewal', action='store_true')
    action.add_argument('--retire', action='store_true')
    action.add_argument('--check-backup', action='store_true')
    parser.add_argument('--config-stdin', action='store_true')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0 or ((args.renewal or args.retire or args.check_backup) == args.config_stdin):
            raise Refusal('invalid-invocation')
        helper = load_helper()
        if args.check_backup:
            result = check_backup(helper)
        elif args.retire:
            result = retire(helper)
        elif args.renewal:
            result = issue(helper, renewal=True)
        else:
            raw = sys.stdin.buffer.read(65537)
            if len(raw) > 65536:
                raise Refusal('certificate-contract-size')
            config = configuration(json.loads(raw))
            result = (helper.publish(request(config, prepare=True)) if args.prepare else issue(helper, config))
        print(json.dumps(result))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError):
        print('public TLS activation refused', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
