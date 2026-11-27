"""Test-only signer for filtered-side node address check attestations."""
from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from address_admission import signed_bytes

# Test-only Ed25519 seeds; no real vantage uses them.
TEST_SEEDS = (b'\x01' * 32, b'\x02' * 32, b'\x03' * 32)


def public_key(seed: bytes) -> str:
    raw = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def attestation(address: str, *, tcp='pass', tls='pass', icmp='not_run', seed=TEST_SEEDS[0],
                checked_at: dt.datetime | None = None) -> dict:
    when = checked_at or dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    record = {
        'schema_version': 1, 'address': address, 'port': 443,
        'checked_at': when.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'vantage': {'side': 'filtered', 'network_type': 'cellular'},
        'probes': {'tcp': tcp, 'tls': tls, 'icmp': icmp},
    }
    value = Ed25519PrivateKey.from_private_bytes(seed).sign(signed_bytes(record))
    record['signature'] = {'algorithm': 'ed25519', 'public_key': public_key(seed),
                           'value': base64.b64encode(value).decode()}
    return record


def write_vantage(directory: Path, records: list[dict], seeds=TEST_SEEDS) -> dict[str, str]:
    """Write records and a trust file; return the gate environment."""
    evidence = directory / 'attestations'
    evidence.mkdir(parents=True)
    for index, record in enumerate(records):
        (evidence / f'{index}.json').write_text(json.dumps(record))
    keys = directory / 'vantage-keys.txt'
    keys.write_text('# test-only vantage keys\n' + ''.join(public_key(seed) + '\n' for seed in seeds))
    return {'ADDRESS_ATTESTATION_DIR': str(evidence), 'ADDRESS_VANTAGE_KEYS': str(keys)}
