#!/usr/bin/env python3
"""Admit a node address into a client bundle only on fresh, signed filtered-side TCP and TLS evidence."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import ipaddress
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'contract' / 'node-address-check.schema.json'
MAX_AGE = dt.timedelta(days=7)
CLOCK_SKEW = dt.timedelta(minutes=5)
MAX_FILE_BYTES = 16384

NOT_CONFIGURED = 'address-admission: set ADDRESS_ATTESTATION_DIR and ADDRESS_VANTAGE_KEYS before bundle admission'
INVALID = 'address-admission: an attestation is malformed, unsigned, from the future or from an untrusted vantage'
NO_RESULT = ('address-admission: no fresh filtered-side TCP and TLS result for a node address; '
             'run the address check before bundle admission')
ONE_FAILED = ('address-admission: one filtered-side vantage failed a node address; '
              'recheck from a second independent vantage or recreate the node')
BLOCK_CLOSED = ('address-admission: two independent filtered-side vantages failed the /24 block of a node; '
                'recreate the node with a new address')


class AdmissionRefused(ValueError):
    """The node address must not enter a client bundle."""


Evidence = tuple  # (address, vantage key bytes, checked_at, outcome)


def signed_bytes(record: dict) -> bytes:
    """RFC 8785 bytes for the ASCII-only, integer-only document without its signature."""
    body = {key: value for key, value in record.items() if key != 'signature'}
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def outcome(probes: dict) -> str:
    # ICMP never decides: only a completed TCP and TLS check passes, only a failed one fails.
    if probes['tcp'] == 'pass' and probes['tls'] == 'pass':
        return 'pass'
    if 'fail' in (probes['tcp'], probes['tls']):
        return 'fail'
    return 'inconclusive'


def trusted_keys(path: Path) -> set[bytes]:
    keys = set()
    for line in path.read_text(encoding='ascii').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            key = base64.b64decode(line, validate=True)
            if len(key) != 32:
                raise ValueError('vantage key is not a raw Ed25519 public key')
            keys.add(key)
    return keys


def verify(record: object, keys: set[bytes], validator, now: dt.datetime) -> Evidence | None:
    """Return the evidence of a valid fresh record, None when stale."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(record, dict) or any(validator.iter_errors(record)):
        raise AdmissionRefused(INVALID)
    # JSON Schema accepts 443.0 as an integer; RFC 8785 signers never emit it.
    if type(record['schema_version']) is not int or type(record['port']) is not int:
        raise AdmissionRefused(INVALID)
    probes, signature = record['probes'], record['signature']
    key = base64.b64decode(signature['public_key'])
    try:
        address = ipaddress.ip_address(record['address'])
        checked = dt.datetime.strptime(record['checked_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
        if str(address) != record['address'] or (probes['tls'] != 'not_run' and probes['tcp'] != 'pass'):
            raise ValueError('inconsistent attestation')
        if key not in keys:
            raise ValueError('untrusted vantage')
        Ed25519PublicKey.from_public_bytes(key).verify(base64.b64decode(signature['value']), signed_bytes(record))
    except (ValueError, InvalidSignature):
        raise AdmissionRefused(INVALID) from None
    if checked > now + CLOCK_SKEW:
        raise AdmissionRefused(INVALID)
    if now - checked > MAX_AGE:
        return None
    return address, key, checked, outcome(probes)


def load(directory: Path, keys_path: Path, now: dt.datetime) -> list[Evidence]:
    import jsonschema

    try:
        validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding='utf-8')))
        keys = trusted_keys(keys_path)
    except (OSError, ValueError):
        raise AdmissionRefused(NOT_CONFIGURED) from None
    evidence = []
    for path in sorted(directory.glob('*.json')):
        try:
            if not path.is_file() or path.is_symlink():
                raise ValueError('attestation is not a regular file')
            with path.open('rb') as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise ValueError('attestation too large')
            record = json.loads(data.decode('utf-8'))
        except (OSError, ValueError):
            raise AdmissionRefused(INVALID) from None
        result = verify(record, keys, validator, now)
        if result is not None:
            evidence.append(result)
    return evidence


def decide(evidence: list[Evidence], address: str) -> None:
    try:
        node = ipaddress.ip_address(address)
    except ValueError:
        raise AdmissionRefused(INVALID) from None
    # Only the newest result of each vantage for each address counts.
    latest: dict[tuple[bytes, object], tuple[dt.datetime, str]] = {}
    for seen, key, checked, result in evidence:
        if (key, seen) not in latest or checked > latest[key, seen][0]:
            latest[key, seen] = (checked, result)
    # Two independent control points close a /24 even when another vantage passed; IPv6 is judged per address.
    block = ipaddress.ip_network(f'{node}/24', strict=False) if node.version == 4 else ipaddress.ip_network(node)
    failed = {key for (key, seen), (_, result) in latest.items() if result == 'fail' and seen in block}
    if len(failed) >= 2:
        raise AdmissionRefused(BLOCK_CLOSED)
    if any(seen == node and result == 'pass' for (_, seen), (_, result) in latest.items()):
        return
    raise AdmissionRefused(ONE_FAILED if failed else NO_RESULT)


def require(address: str, *, env=os.environ, now: dt.datetime | None = None) -> None:
    """Raise AdmissionRefused unless a trusted filtered-side vantage reached the address."""
    directory, keys = env.get('ADDRESS_ATTESTATION_DIR'), env.get('ADDRESS_VANTAGE_KEYS')
    if not directory or not keys or not Path(directory).is_dir():
        raise AdmissionRefused(NOT_CONFIGURED)
    decide(load(Path(directory), Path(keys), now or dt.datetime.now(dt.timezone.utc)), address)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address', help='node address exactly as the bundle publishes it')
    args = parser.parse_args()
    try:
        require(args.address)
    except AdmissionRefused as error:
        print(error, file=sys.stderr)
        return 1
    print('address-admission: admitted')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
