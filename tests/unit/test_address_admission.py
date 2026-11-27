"""Filtered-side node address admission: contract, signature, freshness and the /24 refusal rule."""
from __future__ import annotations

import base64
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

import address_admission as gate
from address_attestation import TEST_SEEDS, attestation, write_vantage

ROOT = Path(__file__).resolve().parents[2]
NOW = dt.datetime(2026, 11, 27, 12, 0, tzinfo=dt.timezone.utc)
FRESH = NOW - dt.timedelta(hours=2)
A, B, C = TEST_SEEDS


def refusal(tmp_path, records, address='192.0.2.10', seeds=TEST_SEEDS):
    try:
        gate.require(address, env=write_vantage(tmp_path, records, seeds), now=NOW)
    except gate.AdmissionRefused as error:
        return str(error)
    return None


def test_golden_fixture_pins_schema_and_canonical_signed_bytes():
    golden = json.loads((ROOT / 'contract/node-address-check.golden.json').read_text())
    schema = json.loads((ROOT / 'contract/node-address-check.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(golden)
    # The producer signs exactly these bytes; this literal is the cross-repo canonicalization pin.
    assert gate.signed_bytes(golden) == (
        b'{"address":"192.0.2.10","checked_at":"2026-11-27T09:00:00Z","port":443,'
        b'"probes":{"icmp":"no_reply","tcp":"pass","tls":"pass"},"schema_version":1,'
        b'"vantage":{"network_type":"cellular","side":"filtered"}}')
    assert golden['signature']['public_key'] == 'iojj3XQJ8ZX9UtstPLpdcspnCb8dlBIb83SIAbQPb1w='
    key = base64.b64decode(golden['signature']['public_key'])
    assert gate.verify(golden, {key}, jsonschema.Draft202012Validator(schema), NOW) == (
        gate.ipaddress.ip_address('192.0.2.10'), key, dt.datetime(2026, 11, 27, 9, tzinfo=dt.timezone.utc), 'pass')


@pytest.mark.parametrize(('records', 'address', 'expected'), (
    pytest.param([attestation('192.0.2.10', icmp='no_reply', checked_at=FRESH)], '192.0.2.10', None,
                 id='icmp-silent-but-tls-passes-is-admitted'),
    pytest.param([attestation('192.0.2.10', tcp='not_run', tls='not_run', icmp='reply', checked_at=FRESH)],
                 '192.0.2.10', gate.NO_RESULT, id='icmp-only-is-not-evidence'),
    pytest.param([attestation('192.0.2.10', tls='fail', icmp='reply', checked_at=FRESH)], '192.0.2.10',
                 gate.ONE_FAILED, id='icmp-reply-but-tls-fails-is-refused'),
    pytest.param([attestation('192.0.2.10', checked_at=NOW - dt.timedelta(days=8))], '192.0.2.10', gate.NO_RESULT,
                 id='stale-pass'),
    pytest.param([attestation('192.0.2.11', checked_at=FRESH)], '192.0.2.10', gate.NO_RESULT,
                 id='pass-for-another-address'),
    pytest.param([attestation('192.0.2.10', tcp='fail', tls='not_run', checked_at=FRESH),
                  attestation('192.0.2.10', tls='fail', checked_at=FRESH)], '192.0.2.10', gate.ONE_FAILED,
                 id='one-vantage-failing-twice-is-one-control-point'),
    pytest.param([attestation('192.0.2.10', tcp='fail', tls='not_run', checked_at=FRESH),
                  attestation('192.0.2.200', tcp='fail', tls='not_run', seed=B, checked_at=FRESH)], '192.0.2.10',
                 gate.BLOCK_CLOSED, id='two-vantages-close-the-block'),
    pytest.param([attestation('192.0.2.10', tcp='fail', tls='not_run', checked_at=FRESH),
                  attestation('198.51.100.10', tcp='fail', tls='not_run', seed=B, checked_at=FRESH)], '192.0.2.10',
                 gate.ONE_FAILED, id='other-block-failure-does-not-count'),
    pytest.param([attestation('192.0.2.10', tcp='fail', tls='not_run', checked_at=FRESH),
                  attestation('192.0.2.11', tcp='fail', tls='not_run', seed=B, checked_at=FRESH),
                  attestation('192.0.2.10', seed=C, checked_at=FRESH)], '192.0.2.10', gate.BLOCK_CLOSED,
                 id='closed-block-refuses-despite-a-pass'),
    pytest.param([attestation('192.0.2.10', checked_at=FRESH - dt.timedelta(hours=1)),
                  attestation('192.0.2.10', tls='fail', checked_at=FRESH)], '192.0.2.10', gate.ONE_FAILED,
                 id='newer-fail-overrides-older-pass'),
    pytest.param([attestation('192.0.2.10', tls='fail', checked_at=FRESH - dt.timedelta(hours=1)),
                  attestation('192.0.2.10', checked_at=FRESH)], '192.0.2.10', None,
                 id='newer-pass-overrides-older-fail'),
    pytest.param([attestation('2001:db8::1', tcp='fail', tls='not_run', checked_at=FRESH),
                  attestation('2001:db8::2', tcp='fail', tls='not_run', seed=B, checked_at=FRESH)], '2001:db8::1',
                 gate.ONE_FAILED, id='ipv6-judged-by-its-own-address'),
    pytest.param([], '192.0.2.10', gate.NO_RESULT, id='no-result'),
))
def test_admission_decision(tmp_path, records, address, expected):
    assert refusal(tmp_path, records, address) == expected


def tampered(record):
    record['probes']['tcp'] = 'pass'
    return record


def resigned(record, **changes):
    """Re-sign a structurally altered record so only the semantic check can refuse it."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    record = {**record, **changes}
    value = Ed25519PrivateKey.from_private_bytes(A).sign(gate.signed_bytes(record))
    record['signature'] = {**record['signature'], 'value': base64.b64encode(value).decode()}
    return record


@pytest.mark.parametrize('record', (
    pytest.param(tampered(attestation('192.0.2.10', tcp='fail', tls='not_run', checked_at=FRESH)), id='tampered'),
    pytest.param(attestation('192.0.2.10', seed=b'\x09' * 32, checked_at=FRESH), id='untrusted-key'),
    pytest.param(attestation('192.0.2.10', checked_at=NOW + dt.timedelta(hours=1)), id='future'),
    pytest.param(resigned(attestation('192.0.2.10', checked_at=FRESH), probes={'tcp': 'fail', 'tls': 'pass',
                                                                              'icmp': 'not_run'}),
                 id='tls-pass-without-tcp'),
    pytest.param(resigned(attestation('192.0.2.10', checked_at=FRESH), address='192.0.2.010'), id='non-canonical'),
    pytest.param(resigned(attestation('192.0.2.10', checked_at=FRESH), checked_at='2026-02-31T00:00:00Z'),
                 id='impossible-date'),
    pytest.param(resigned(attestation('192.0.2.10', checked_at=FRESH), port=443.0), id='non-integer-port'),
    pytest.param({**attestation('192.0.2.10', checked_at=FRESH), 'padding': 'x' * gate.MAX_FILE_BYTES},
                 id='oversized'),
    pytest.param([], id='not-an-object'),
    pytest.param({**attestation('192.0.2.10', checked_at=FRESH), 'vantage': {'side': 'unfiltered',
                                                                             'network_type': 'wired'}},
                 id='unfiltered-vantage'),
))
def test_invalid_attestation_refuses_every_admission(tmp_path, record):
    assert refusal(tmp_path, [attestation('192.0.2.10', checked_at=FRESH), record]) == gate.INVALID


def test_missing_vantage_configuration_refuses(tmp_path):
    for env in ({}, {'ADDRESS_ATTESTATION_DIR': str(tmp_path / 'absent'), 'ADDRESS_VANTAGE_KEYS': str(tmp_path / 'k')}):
        with pytest.raises(gate.AdmissionRefused, match='set ADDRESS_ATTESTATION_DIR'):
            gate.require('192.0.2.10', env=env, now=NOW)
    env = write_vantage(tmp_path, [attestation('192.0.2.10', checked_at=FRESH)])
    keys = Path(env['ADDRESS_VANTAGE_KEYS'])
    for broken in ('AAAA\n', 'not base64!\n', None):
        keys.unlink(missing_ok=True)
        if broken is not None:
            keys.write_text(broken)
        with pytest.raises(gate.AdmissionRefused, match='set ADDRESS_ATTESTATION_DIR'):
            gate.require('192.0.2.10', env=env, now=NOW)


def test_cli_reports_the_operator_message(tmp_path, monkeypatch):
    env = write_vantage(tmp_path, [attestation('192.0.2.10', tcp='fail', tls='not_run'),
                                   attestation('192.0.2.99', tcp='fail', tls='not_run', seed=B)])
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/address_admission.py'), '192.0.2.10'],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and 'recreate the node with a new address' in result.stderr
