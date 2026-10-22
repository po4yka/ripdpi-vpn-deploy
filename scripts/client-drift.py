#!/usr/bin/env python3
"""Re-materialize a delivered device; print only current/stale/unknown (0/1/2)."""
from __future__ import annotations

import argparse
import hmac
import os
from pathlib import Path
import subprocess
import sys

import yaml

from client_delivery_identity import authority, comparable, digest
from client_payload import materialize, read_document, validate_options
from device_migration import wrap_payload


def secrets_file():
    return Path(os.environ.get('SOPS_FILE') or Path.home() / '.config/vpn-provision' / (os.environ.get('ENV', 'prod') + '.secrets.sops.yaml'))


def _verdict(client):
    try:
        path = secrets_file()
        doc = read_document(path)
        entry = doc.get('client_registry', {}).get(client)
        if not isinstance(entry, dict):
            return 'unknown', 'no client_registry entry'
        auth = authority(doc)
        record = entry.get('last_payload_identity')
        if not comparable(record, auth):
            return 'unknown', 'delivery identity unavailable or authority changed; reissue required'
        o = entry.get('delivery_options')
        validate_options(o)
        # Mutable registry expiry/selection is part of the current consumed contract.
        o = dict(o, expires=entry['token_expires'], hosts=entry['hosts'], cohorts=entry['cohorts'], awg_host=entry['awg_delivery_host'])
        payload, bindings = materialize(client, o, private_only=True, documents={str(path.absolute()): doc}, source_paths=entry['delivery_sources'], extended=o['format'] == 'ripdpi')
        if 'migration_delivery' in entry:
            payload = wrap_payload(payload, entry['migration_delivery'])
        current = digest(client, o, payload, bindings, auth)
        if hmac.compare_digest(record['digest'], current['digest']):
            return 'current', 'payload identity matches the last delivery'
        return 'stale', 'changed: consumed payload or delivery options'
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration, RecursionError, subprocess.SubprocessError, yaml.YAMLError):
        return 'unknown', 'private input or materialization unavailable'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client')
    args = parser.parse_args()
    verdict, detail = _verdict(args.client)
    print(verdict + ': ' + detail)
    return {'current': 0, 'stale': 1, 'unknown': 2}[verdict]


if __name__ == '__main__':
    sys.exit(main())
