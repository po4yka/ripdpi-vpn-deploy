#!/usr/bin/env python3
"""Seal and verify private operator recovery without backing up working keys."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request

from operator_maintenance_io import (LIMIT, MaintenanceError, command_environment, digest_file,
                                    encrypted_command, new_file, private_directory,
                                    read_bytes, update_document, write_document)
from bootstrap_readiness import ReadinessError
from recovery_io import canonical, unique, document

FIELDS = {'schema_version', 'kit', 'recipient', 'identity', 'rclone', 'rclone_sha256',
          'bucket_id', 'bucket_name', 'required_paths'}
PREFIX = 'operator-kit/'
CAPABILITIES = {'listBuckets', 'readBucketEncryption', 'listFiles', 'readFiles', 'writeFiles'}


def absolute_path(value):
    if (not isinstance(value, str) or not Path(value).is_absolute()
            or '..' in Path(value).parts):
        raise MaintenanceError('absolute-private-path-required')
    return value


def configuration(path):
    value = document(path)
    if (set(value) != FIELDS or value['schema_version'] != 1
            or not re.fullmatch('age1[0-9a-z]{58}', value['recipient'])
            or not re.fullmatch('[0-9a-f]{64}', value['rclone_sha256'])
            or not re.fullmatch('[0-9a-f]+', value['bucket_id'])
            or not re.fullmatch('[a-zA-Z0-9-]{6,63}', value['bucket_name'])
            or not isinstance(value['required_paths'], list) or not value['required_paths']):
        raise MaintenanceError('invalid-kit-configuration')
    for field in ('kit', 'identity', 'rclone'):
        absolute_path(value[field])
    private_directory(value['kit'])
    if Path(value['identity']).resolve().is_relative_to(Path(value['kit']).resolve()) and not Path(value['identity']).resolve().is_relative_to(Path(value['kit']).resolve() / 'runtime'):
        raise MaintenanceError('working-identity-must-be-excluded')
    digest_file(value['identity'])
    result = subprocess.run(['age-keygen', '-y', value['identity']], capture_output=True, timeout=15, check=True)
    if result.stdout.decode().strip() != value['recipient']:
        raise MaintenanceError('recipient-identity-mismatch')
    return value


def snapshot(config):
    kit = Path(config['kit']).resolve()
    files = {}
    selected = [kit / 'README.md', kit / 'catalog.json']
    for name in ('config', 'plans', 'receipts', 'recovery'):
        root = kit / name
        private_directory(root)
        selected.extend(root.rglob('*'))
    selected.extend(private_directory(kit / 'state-backups').rglob('*.tfstate.age'))
    size = 0
    for path in sorted(set(selected)):
        if '__pycache__' in path.parts:
            continue
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            private_directory(path)
            continue
        if not stat.S_ISREG(info.st_mode):
            raise MaintenanceError('nonregular-kit-input')
        raw = read_bytes(path, allow_empty=True)
        if not raw and path.name.endswith(('.tfstate.age', '.sops.yaml', '.sops.yml', '.sops.json')):
            raise MaintenanceError('empty-encrypted-authority')
        if (re.search(rb'AGE-SECRET-KEY-1[0-9A-Z]{58}', raw)
                or re.search(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----', raw)):
            raise MaintenanceError('plaintext-private-key-in-snapshot')
        size += len(raw)
        if size > LIMIT or len(files) >= 20000:
            raise MaintenanceError('kit-snapshot-limit')
        files[path.relative_to(kit).as_posix()] = raw
    if not files or 'catalog.json' not in files:
        raise MaintenanceError('incomplete-kit')
    required = config.get('required_paths', [])
    if not required or any(name not in files for name in required):
        raise MaintenanceError('required-recovery-input-missing')
    return files


def manifest(files):
    return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}


def seal(config, files, output):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as tar:
        for name, data in [*files.items(), ('MANIFEST.json', canonical(manifest(files)))]:
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), 0o600
            tar.addfile(member, io.BytesIO(data))
    cipher = subprocess.run(['age', '--encrypt', '--recipient', config['recipient']],
                            input=archive.getvalue(), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=120, check=True).stdout
    with new_file(output) as stream:
        stream.write(cipher)
    return cipher


def verify(config, ciphertext):
    if len(ciphertext) > LIMIT + 1024 * 1024:
        raise MaintenanceError('ciphertext-limit')
    plain = subprocess.run(['age', '--decrypt', '--identity', config['identity']],
                           input=ciphertext, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=120, check=True).stdout
    actual, expected, total, seen = {}, None, 0, set()
    with tarfile.open(fileobj=io.BytesIO(plain), mode='r:gz') as archive:
        for count, member in enumerate(archive):
            path = PurePosixPath(member.name)
            total += member.size
            if (count > 20000 or total > LIMIT + 4 * 1024 * 1024 or member.size < 0
                    or not member.isfile() or member.name in seen or path.is_absolute()
                    or '..' in path.parts or '\\' in member.name or str(path) != member.name
                    or member.name.startswith('runtime/') or member.name in {'runtime', ''}):
                raise MaintenanceError('unsafe-or-oversized-recovery-archive')
            seen.add(member.name)
            with archive.extractfile(member) as stream:
                raw = stream.read(member.size + 1)
            if len(raw) != member.size:
                raise MaintenanceError('incomplete-archive-member')
            if member.name == 'MANIFEST.json':
                expected = json.loads(raw, object_pairs_hook=unique)
            else:
                actual[member.name] = hashlib.sha256(raw).hexdigest()
    if expected != actual or not actual or 'catalog.json' not in actual:
        raise MaintenanceError('recovery-manifest-mismatch')
    return actual


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise MaintenanceError('provider-redirect-refused')


class Storage:
    def __init__(self, config):
        self.config = config
        credential = {'key_id': os.environ.get('B2_APPLICATION_KEY_ID'),
                      'application_key': os.environ.get('B2_APPLICATION_KEY')}
        if not all(isinstance(v, str) and v for v in credential.values()):
            raise MaintenanceError('invalid-operator-credential-scope')
        self.credential = credential
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        basic = base64.b64encode((credential['key_id'] + ':' + credential['application_key']).encode()).decode()
        self.auth = self.request('https://api.backblazeb2.com/b2api/v4/b2_authorize_account',
                                 headers={'Authorization': 'Basic ' + basic})
        storage = self.auth['apiInfo']['storageApi']
        self.api = self.origin(storage['apiUrl'])
        self.download = self.origin(storage['downloadUrl'])
        allowed = storage['allowed']
        if (allowed['buckets'] != [{'id': config['bucket_id'], 'name': config['bucket_name']}]
                or allowed['namePrefix'] != PREFIX or set(allowed['capabilities']) != CAPABILITIES):
            raise MaintenanceError('restricted-operator-backup-key-required')
        buckets = self.call('b2_list_buckets', {'accountId': self.auth['accountId'], 'bucketId': config['bucket_id']})['buckets']
        if (len(buckets) != 1 or buckets[0]['bucketId'] != config['bucket_id']
                or buckets[0]['bucketName'] != config['bucket_name'] or buckets[0]['bucketType'] != 'allPrivate'
                or buckets[0]['defaultServerSideEncryption']['value'] != {'algorithm': 'AES256', 'mode': 'SSE-B2'}):
            raise MaintenanceError('private-encrypted-bucket-required')

    @staticmethod
    def origin(url):
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not parsed.hostname or not parsed.hostname.endswith('.backblazeb2.com')
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise MaintenanceError('unexpected-provider-origin')
        return url.rstrip('/')

    def request(self, url, *, data=None, headers=None):
        request = urllib.request.Request(url, data=None if data is None else canonical(data), headers=headers or {})
        with self.opener.open(request, timeout=30) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise MaintenanceError('provider-response-limit')
        return json.loads(raw, object_pairs_hook=unique)

    def call(self, verb, data):
        return self.request(self.api + '/b2api/v4/' + verb, data=data,
                            headers={'Authorization': self.auth['authorizationToken'], 'Content-Type': 'application/json'})

    def upload(self, archive, ciphertext, log):
        config = self.config
        absolute_path(config['rclone'])
        if digest_file(config['rclone'], private=False) != config['rclone_sha256']:
            raise MaintenanceError('rclone-identity-mismatch')
        environment = command_environment({'RCLONE_CONFIG_KIT_TYPE': 'b2',
                      'RCLONE_CONFIG_KIT_ACCOUNT': self.credential['key_id'],
                      'RCLONE_CONFIG_KIT_KEY': self.credential['application_key'], 'GOMAXPROCS': '2'})
        name = PREFIX + 'current.tar.age'
        code = encrypted_command([config['rclone'], '--config', '/dev/null', 'copyto', str(archive),
                                  'kit:' + config['bucket_name'] + '/' + name,
                                  '--ignore-times', '--transfers', '1', '--checkers', '1',
                                  # Verified ciphertext is at most 257 MiB; use one upload request.
                                  '--b2-upload-cutoff', '512Mi', '--b2-chunk-size', '10Mi',
                                  '--b2-upload-concurrency', '1', '--retries', '2', '--low-level-retries', '2',
                                  '--contimeout', '10s', '--timeout', '30s', '--stats', '30s',
                                  '--stats-one-line', '--stats-log-level', 'NOTICE'], log, config['recipient'],
                                 environment=environment, cwd=config['kit'], timeout=900)
        if code:
            raise MaintenanceError('operator-kit-upload-failed')
        rows = self.call('b2_list_file_names', {'bucketId': config['bucket_id'], 'prefix': name,
                                              'startFileName': name, 'maxFileCount': 1})['files']
        if len(rows) != 1 or rows[0]['fileName'] != name:
            raise MaintenanceError('uploaded-object-not-found')
        info = self.call('b2_get_file_info', {'fileId': rows[0]['fileId']})
        if (info['bucketId'] != config['bucket_id'] or info['fileName'] != name
                or info['contentLength'] != len(ciphertext)
                or info['serverSideEncryption'] != {'algorithm': 'AES256', 'mode': 'SSE-B2'}):
            raise MaintenanceError('uploaded-object-identity-mismatch')
        url = self.download + '/b2api/v4/b2_download_file_by_id?' + urllib.parse.urlencode({'fileId': info['fileId']})
        request = urllib.request.Request(url, headers={'Authorization': self.auth['authorizationToken']})
        with self.opener.open(request, timeout=120) as response:
            downloaded = response.read(LIMIT + 1024 * 1024 + 1)
        if hashlib.sha256(downloaded).digest() != hashlib.sha256(ciphertext).digest():
            raise MaintenanceError('downloaded-ciphertext-mismatch')
        try:
            with self.opener.open(url, timeout=30) as response:
                denied = response.status
        except urllib.error.HTTPError as error:
            denied = error.code
        if denied not in (401, 403):
            raise MaintenanceError('anonymous-download-not-denied')
        return downloaded, {'bucket_id': config['bucket_id'], 'object_name': name,
                            'file_id': info['fileId'], 'anonymous_status': denied}


def backup(config, output, *, remote):
    kit = Path(config['kit'])
    files = snapshot(config)
    expected = manifest(files)
    archive = kit / 'state-backups' / ('operator-kit-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.tar.age')
    cipher = seal(config, files, archive)
    if verify(config, cipher) != expected:
        raise MaintenanceError('local-manifest-mismatch')
    delivery = {'remote_verified': False}
    if remote:
        storage = Storage(config)
        cipher, delivery = storage.upload(archive, cipher, kit / 'runtime' / (archive.stem + '-upload.log.age'))
        delivery['remote_verified'] = True
    if verify(config, cipher) != expected:
        raise MaintenanceError('downloaded-manifest-mismatch')
    if manifest(snapshot(config)) != expected:
        raise MaintenanceError('kit-inputs-changed-during-verification')
    receipt = {'schema_version': 1, 'phase': 'offsite-download-decrypt-manifest-verified' if remote else 'local-decrypt-manifest-verified',
               'at': datetime.now(timezone.utc).isoformat(), 'files_verified': len(files),
               'archive': str(archive.relative_to(kit)), 'ciphertext_bytes': len(cipher),
               'ciphertext_sha256': hashlib.sha256(cipher).hexdigest(),
               'manifest_sha256': hashlib.sha256(canonical(expected)).hexdigest(),
               'working_identities_excluded': True, 'delivery': delivery,
               'acknowledgement': 'This receipt is written after the verified snapshot and is not part of that snapshot.'}
    write_document(output, receipt)
    catalog_path = kit / 'catalog.json'
    catalog = json.loads(files['catalog.json'])
    reference = str(output.relative_to(kit)) if output.is_relative_to(kit) else str(output)
    catalog['offsite_operator_kit' if remote else 'local_operator_kit'] = {
        'receipt': reference, 'status': receipt['phase'], 'verified_at': receipt['at'],
        'snapshot_manifest_sha256': receipt['manifest_sha256'],
        'post_snapshot_acknowledgement_only': True}
    update_document(catalog_path, expected['catalog.json'], catalog)
    return {key: receipt[key] for key in ('phase', 'files_verified', 'ciphertext_bytes')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('audit', 'seal', 'backup', 'verify'))
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    try:
        config = configuration(args.config)
        if args.action == 'audit':
            result = {'phase': 'local-kit-inputs-verified', 'files': len(snapshot(config)), 'remote_verified': False}
        elif args.action == 'verify':
            if args.archive is None:
                raise MaintenanceError('archive-required')
            result = {'phase': 'archive-manifest-verified', 'files': len(verify(config, read_bytes(args.archive, limit=LIMIT + 1024 * 1024)))}
        else:
            if args.output is None:
                raise MaintenanceError('receipt-output-required')
            result = backup(config, args.output, remote=args.action == 'backup')
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ReadinessError, tarfile.TarError, subprocess.SubprocessError):
        print('operator-kit: recovery operation refused; no current-coverage claim', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
