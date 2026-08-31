#!/usr/bin/env python3
"""Validate a locally reviewed signed artifact; never fetch or apply policy."""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import jsonschema
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = ('ingress', 'host_egress', 'forwarded')
MODES = ('disabled', 'log_only', 'canary', 'enforce')


class InvalidArtifact(ValueError):
    """Only categorical diagnostics may cross the operator-output boundary."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise InvalidArtifact('duplicate-field')
        value[key] = item
    return value


def read_owned(path, *, private):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        metadata = os.fstat(handle.fileno())
        forbidden_mode = 0o077 if private else 0o022
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.getuid()}
            or metadata.st_nlink != 1
            or metadata.st_mode & forbidden_mode
        ):
            raise InvalidArtifact('unsafe-file')
        if metadata.st_size > 4 * 1024 * 1024:
            raise InvalidArtifact('oversized-file')
        data = handle.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise InvalidArtifact('oversized-file')
        return data


def openssl(args, *, data=None):
    result = subprocess.run(['openssl', *args], input=data, capture_output=True, timeout=10, check=False)
    if result.returncode:
        raise InvalidArtifact('signature-or-key')
    return result.stdout


def validate_schema(artifact):
    policy = json.loads((ROOT / 'contract/network-exposure-policy.schema.json').read_text())
    schema = json.loads((ROOT / 'contract/network-exposure-artifact.schema.json').read_text())
    registry = Registry().with_resource(policy['$id'], Resource.from_contents(policy))
    validator = jsonschema.Draft202012Validator(schema, registry=registry, format_checker=jsonschema.FormatChecker())
    if not validator.is_valid(artifact):
        raise InvalidArtifact('schema-or-review')


def parse_rfc3339(value):
    normalized = value.upper()
    if normalized.endswith('-00:00'):
        raise InvalidArtifact('stale-or-future')
    if normalized.startswith('0000-'):
        # RFC 3339 admits year zero, which is older than every value used by
        # this gate but is outside datetime's supported range.
        return datetime.min.replace(tzinfo=timezone.utc)
    leap_second = re.search(r':60(?:[.,][0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$', normalized)
    if leap_second is not None:
        replacement = leap_second.group().replace(':60', ':59', 1)
        normalized = normalized[:leap_second.start()] + replacement
    parsed = datetime.fromisoformat(normalized.replace('Z', '+00:00'))
    try:
        return parsed + (timedelta(seconds=1) if leap_second is not None else timedelta())
    except OverflowError:
        return datetime.max.replace(tzinfo=timezone.utc)


def validate(args):
    if args.mode == 'disabled':
        return {'validation': 'disabled', 'counts': {direction: 0 for direction in DIRECTIONS}}, {}
    raw = read_owned(args.artifact, private=True)
    artifact = json.loads(raw, object_pairs_hook=unique_object)
    validate_schema(artifact)
    if artifact['source_id'] != args.source_id:
        raise InvalidArtifact('untrusted-source')
    created = parse_rfc3339(artifact['created_at'])
    expires = parse_rfc3339(artifact['expires_at'])
    now = datetime.now(timezone.utc)
    if not created <= now < expires or expires <= created:
        raise InvalidArtifact('stale-or-future')
    policy = artifact['policy']
    for ranges in policy.values():
        for prefix in ranges:
            if str(ipaddress.ip_network(prefix, strict=True)) != prefix:
                raise InvalidArtifact('noncanonical-prefix')
    if hashlib.sha256(canonical(policy)).hexdigest() != artifact['content_sha256']:
        raise InvalidArtifact('content-digest')
    key = read_owned(args.trusted_key, private=False)
    der = openssl(['rsa', '-pubin', '-pubout', '-outform', 'DER'], data=key)
    description = openssl(['rsa', '-pubin', '-text', '-noout'], data=key).decode('ascii')
    size = re.search(r'Public-Key: \(([0-9]+) bit\)', description)
    if size is None or int(size.group(1)) < 2048:
        raise InvalidArtifact('weak-signing-key')
    if not re.fullmatch('[0-9a-f]{64}', args.trusted_key_sha256) or hashlib.sha256(der).hexdigest() != args.trusted_key_sha256:
        raise InvalidArtifact('untrusted-key')
    unsigned = {key: value for key, value in artifact.items() if key != 'signature'}
    signature = base64.b64decode(artifact['signature']['value'], validate=True)
    # Private local temp files are required by the OpenSSL verify interface.
    # Only their paths enter argv; neither policy nor signatures enter logs.
    with tempfile.TemporaryDirectory(prefix='network-exposure-') as directory:
        paths = [Path(directory) / name for name in ('public.pem', 'signature', 'signed.json')]
        for path, data in zip(paths, (key, signature, canonical(unsigned)), strict=True):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(data)
        openssl(['dgst', '-sha256', '-verify', str(paths[0]), '-signature', str(paths[1]), str(paths[2])])
    artifact_digest = hashlib.sha256(raw).hexdigest()
    plan = {}
    if args.mode in ('canary', 'enforce'):
        hosts = json.loads(args.authorized_hosts_json)
        if (args.promotion_approved != 'true' or args.promotion_digest != artifact_digest
                or not isinstance(hosts, list) or not hosts
                or any(not isinstance(host, str) or not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_.-]*', host) for host in hosts)
                or not args.inventory_host or args.inventory_host not in hosts):
            raise InvalidArtifact('promotion-not-authorized')
        plan = {'mode': args.mode, 'directions': policy}
    summary = {'validation': 'valid', 'source_id': artifact['source_id'],
               'counts': {direction: len(policy[direction]) for direction in DIRECTIONS},
               'content_sha256': artifact['content_sha256'], 'artifact_sha256': artifact_digest}
    return summary, plan


def check_fixtures(directory):
    """Feature fixtures describe shape only; address/rule payloads stay outside Git."""
    expected = {'schema_version', 'source_id', 'created_at', 'expires_at', 'review', 'content_sha256', 'policy', 'signature'}
    for path in sorted(Path(directory).rglob('*.json')):
        value = json.loads(path.read_text(), object_pairs_hook=unique_object)
        valid = isinstance(value, dict) and set(value) == expected
        if valid:
            policy = value.get('policy', {})
            valid = (set(policy) == set(DIRECTIONS) and value.get('review', {}).get('approved') is False
                     and all(isinstance(ranges, list) and all(isinstance(prefix, str) and re.fullmatch('<[A-Z_]+>', prefix) for prefix in ranges) for ranges in policy.values()))
        def strings(item):
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                for child in item.values():
                    yield from strings(child)
            elif isinstance(item, list):
                for child in item:
                    yield from strings(child)
        for text in strings(value):
            try:
                ipaddress.ip_network(text)
            except ValueError:
                pass
            else:
                valid = False
            if re.search(r'\b(nft|iptables|ip6tables)\s|\b(add|delete|flush)\s+(table|chain|rule)\b', text):
                valid = False
        if not valid:
            raise InvalidArtifact(f'non-placeholder fixture: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=MODES, default='disabled')
    for option in ('artifact', 'trusted-key', 'trusted-key-sha256', 'source-id', 'promotion-digest', 'inventory-host'):
        parser.add_argument('--' + option, default='')
    parser.add_argument('--promotion-approved', choices=('true', 'false'), default='false')
    parser.add_argument('--authorized-hosts-json', default='[]')
    parser.add_argument('--check-fixtures', action='store_true')
    parser.add_argument('--internal-plan', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.check_fixtures:
            check_fixtures(ROOT / 'tests/fixtures/network-exposure-gate')
            print(json.dumps({'validation': 'placeholders-only'}))
            return 0
        summary, plan = validate(args)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError, jsonschema.exceptions.SchemaError) as error:
        category = str(error) if isinstance(error, InvalidArtifact) else 'invalid-input'
        print(f'network exposure validation failed: {category}', file=sys.stderr)
        return 2
    print(json.dumps({'summary': summary, 'plan': plan} if args.internal_plan else summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
