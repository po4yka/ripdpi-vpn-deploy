"""Lock the contract for secrets/schema.json.

Two threats this catches:
  1. A role template gains a new required secret without the schema
     being extended — `make pre-deploy-check` would still pass, deploy
     would fail on the VPS.
  2. A schema field gets relaxed (regex weakened, required→optional)
     and no test fails. The strict-mode round-trip below would.
"""
from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "secrets" / "schema.json"
EXAMPLE = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"
VALIDATOR = REPO_ROOT / "scripts" / "validate-secrets.py"


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA.read_text())


@pytest.fixture(scope="module")
def example_doc():
    return yaml.safe_load(EXAMPLE.read_text())


@pytest.fixture
def filled():
    """A fully-filled, strict-mode-conformant secrets document."""
    sha = "a" * 64
    pem = (
        "-----BEGIN CERTIFICATE-----\n"
        + ("X" * 64 + "\n") * 4
        + "-----END CERTIFICATE-----\n"
    )
    return {
        "xray": {
            "version": "v26.3.27",
            "linux_amd64_sha256": sha,
            "linux_arm64_sha256": sha,
            "reality_private_key": "AAAAAAAAAAAAAAAAAAAAAAAA",
            "reality_public_key": "BBBBBBBBBBBBBBBBBBBBBBBB",
            "target": "mirror.example.com:443",
            "server_names": ["mirror.example.com"],
            "xhttp_path": "/sync",
            "clients": [
                {
                    "name": "phone",
                    "uuid": "12345678-1234-1234-1234-1234567890ab",
                    "short_id": "deadbeef",
                }
            ],
            "cohorts": [],
        },
        "nginx_xhttp": {
            "server_name": "vpn.example.com",
            "cert_pem": pem,
            "key_pem": pem,
        },
        "hysteria": {
            "version": "v2.9.0",
            "linux_amd64_sha256": sha,
            "linux_arm64_sha256": sha,
            "cert_pem": pem,
            "key_pem": pem,
            "bandwidth_up": "100 mbps",
            "bandwidth_down": "200 mbps",
            "salamander_enabled": False,
            "salamander_password": "",
            "clients": [{"name": "phone", "password": "verystrongpasswordhere"}],
        },
        "amneziawg_secrets": {
            "server_private_key": "PRIVATEKEYPRIVATEKEYPRIVATEKEY",
            "jc": 4,
            "jmin": 40,
            "jmax": 70,
            "s1": 50,
            "s2": 100,
            "h1": 1234567890,
            "h2": 2345678901,
            "h3": 3456789012,
            "h4": 234567890,
            "peers": [
                {
                    "name": "phone",
                    "public_key": "PUBLICKEYPUBLICKEYPUBLIC",
                    "preshared_key": "PSKPSKPSKPSKPSKPSKPSKPSK",
                    "allowed_ips": "10.66.66.2/32",
                }
            ],
            "instances": [],
        },
        "backup": {"restic_password": "longrandomrestcpw" + "x" * 20},
        "watchdog_secrets": {"ntfy_topic": "ci-topic-aaaa1111"},
    }


def _validator():
    """Return a configured Draft202012Validator. Requires `jsonschema`."""
    import jsonschema  # local import — the test pin makes this present

    return jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))


# ---------------------------------------------------------------------------
# Lenient pass on example, strict fail on example
# ---------------------------------------------------------------------------
def test_example_validates_lenient(example_doc):
    v = _validator()
    errors = list(v.iter_errors(example_doc))
    assert errors == [], "example schema must validate against itself in lenient mode"


def test_filled_validates_strict_via_cli(filled, tmp_path):
    p = tmp_path / "filled.yaml"
    p.write_text(yaml.safe_dump(filled))
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(p), "--strict"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_example_fails_strict_via_cli():
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(EXAMPLE), "--strict"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "REPLACE_WITH" in proc.stderr


# ---------------------------------------------------------------------------
# Required-key class
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "drop_path",
    [
        ("xray",),
        ("hysteria",),
        ("nginx_xhttp",),
        ("amneziawg_secrets",),
        ("backup",),
        ("watchdog_secrets",),
    ],
)
def test_dropping_required_top_level_fails(filled, drop_path):
    v = _validator()
    doc = filled
    target = doc
    for k in drop_path[:-1]:
        target = target[k]
    del target[drop_path[-1]]
    errs = list(v.iter_errors(doc))
    assert errs, f"dropping {'.'.join(drop_path)} must fail validation"


@pytest.mark.parametrize(
    "drop_path",
    [
        ("xray", "reality_private_key"),
        ("xray", "reality_public_key"),
        ("xray", "target"),
        ("xray", "clients"),
        ("hysteria", "linux_amd64_sha256"),
        ("amneziawg_secrets", "h1"),
        ("amneziawg_secrets", "peers"),
        ("backup", "restic_password"),
        ("watchdog_secrets", "ntfy_topic"),
    ],
)
def test_dropping_required_nested_fails(filled, drop_path):
    v = _validator()
    doc = filled
    target = doc
    for k in drop_path[:-1]:
        target = target[k]
    del target[drop_path[-1]]
    errs = list(v.iter_errors(doc))
    assert errs, f"dropping {'.'.join(drop_path)} must fail validation"


# ---------------------------------------------------------------------------
# Format class — catch the malformed-sha / malformed-uuid / malformed-version
# ---------------------------------------------------------------------------
def test_bad_sha256_rejected(filled):
    v = _validator()
    filled["xray"]["linux_amd64_sha256"] = "nope"
    errs = list(v.iter_errors(filled))
    assert errs


def test_bad_uuid_rejected(filled):
    v = _validator()
    filled["xray"]["clients"][0]["uuid"] = "not-a-uuid"
    errs = list(v.iter_errors(filled))
    assert errs


def test_bad_version_rejected(filled):
    v = _validator()
    filled["xray"]["version"] = "latest"
    errs = list(v.iter_errors(filled))
    assert errs


def test_bandwidth_unit_required(filled):
    v = _validator()
    filled["hysteria"]["bandwidth_up"] = "100"
    errs = list(v.iter_errors(filled))
    assert errs


def test_allowed_ips_must_be_cidrish(filled):
    v = _validator()
    filled["amneziawg_secrets"]["peers"][0]["allowed_ips"] = "wat"
    errs = list(v.iter_errors(filled))
    assert errs


def _validate_cli(doc, tmp_path):
    path = tmp_path / "secrets.yaml"
    path.write_text(yaml.safe_dump(doc))
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path), "--strict"],
        capture_output=True,
        text=True,
    )


def test_unknown_fields_are_rejected_at_root_and_nested_levels(filled):
    root_unknown = deepcopy(filled)
    root_unknown["typo"] = "value"
    nested_unknown = deepcopy(filled)
    nested_unknown["xray"]["typo"] = "value"
    cohort_unknown = deepcopy(filled)
    cohort_unknown["xray"]["cohorts"] = [
        {"name": "primary", "port": 443, "flow_mode": "vision", "typo": "value"}
    ]
    validator = _validator()

    assert list(validator.iter_errors(root_unknown))
    assert list(validator.iter_errors(nested_unknown))
    assert list(validator.iter_errors(cohort_unknown))


def test_duplicate_client_identity_is_rejected(filled, tmp_path):
    doc = deepcopy(filled)
    doc["xray"]["clients"].append(deepcopy(doc["xray"]["clients"][0]))

    proc = _validate_cli(doc, tmp_path)

    assert proc.returncode == 1
    assert "duplicate name" in proc.stderr
    assert "duplicate uuid" in proc.stderr
    assert "duplicate short_id" in proc.stderr


def test_cohort_client_reference_must_exist(filled, tmp_path):
    doc = deepcopy(filled)
    doc["xray"]["cohorts"] = [
        {"name": "primary", "port": 443, "flow_mode": "vision", "clients": ["missing"]}
    ]

    proc = _validate_cli(doc, tmp_path)

    assert proc.returncode == 1
    assert "unknown xray client: missing" in proc.stderr


def test_invalid_numeric_cidr_is_rejected_semantically(filled, tmp_path):
    doc = deepcopy(filled)
    doc["amneziawg_secrets"]["peers"][0]["allowed_ips"] = "999.66.66.2/32"

    proc = _validate_cli(doc, tmp_path)

    assert proc.returncode == 1
    assert "valid IPv4 or IPv6 CIDR" in proc.stderr


def test_awg_peer_public_keys_must_be_unique(filled, tmp_path):
    doc = deepcopy(filled)
    peer = deepcopy(doc["amneziawg_secrets"]["peers"][0])
    peer["name"] = "laptop"
    peer["allowed_ips"] = "10.66.66.3/32"
    doc["amneziawg_secrets"]["peers"].append(peer)

    proc = _validate_cli(doc, tmp_path)

    assert proc.returncode == 1
    assert "duplicate public_key" in proc.stderr


def test_awg_instance_cidr_is_validated_semantically(filled, tmp_path):
    doc = deepcopy(filled)
    source = doc["amneziawg_secrets"]
    doc["amneziawg_secrets"]["instances"] = [{
        "name": "awg1",
        "listen_port": 51820,
        "address_v4": "999.66.66.1/24",
        "address_v6": "fd42:42:42::1/64",
        "server_private_key": source["server_private_key"],
        "jc": source["jc"], "jmin": source["jmin"], "jmax": source["jmax"],
        "s1": source["s1"], "s2": source["s2"],
        "h1": source["h1"], "h2": source["h2"], "h3": source["h3"], "h4": source["h4"],
        "peers": source["peers"],
    }]

    proc = _validate_cli(doc, tmp_path)

    assert proc.returncode == 1
    assert "instances.0.address_v4" in proc.stderr
