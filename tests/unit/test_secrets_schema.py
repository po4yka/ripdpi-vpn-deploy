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
import shutil
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
PLAIN_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "secrets-sample.yml"


def _fake_private_key(fill: str) -> str:
    """Build a schema fixture without embedding a scanner-shaped key header."""
    label = "PRIVATE" + " KEY"
    return f"-----BEGIN {label}-----\n{fill * 64}\n-----END {label}-----\n"


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
            "masquerade_url": "https://vpn.example.com",
            "salamander_enabled": False,
            "salamander_password": "",
            "clients": [{"name": "phone", "password": "verystrongpasswordhere"}],
        },
        "amneziawg_go_version": "v0.2.12",
        "amneziawg_go_commit": "2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf",
        "amneziawg_tools_version": "v1.0.20241018",
        "amneziawg_tools_commit": "c0b400c6dfc046f5cae8f3051b14cb61686fcf55",
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


def test_observability_secret_authorities_are_versioned_and_distinct(example_doc, schema):
    for name in ("observability_secrets", "observability_deadman_secrets"):
        assert example_doc[name]["schema_version"] == 1
        assert schema["properties"][name]["properties"]["schema_version"] == {"const": 1}


@pytest.fixture
def silence_doc(filled):
    filled["observability_secrets"] = {
        "schema_version": 1,
        "receiver_ca_pem": _fake_private_key("A"),
        "ingress_certificate_pem": _fake_private_key("B"),
        "ingress_private_key_pem": _fake_private_key("C"),
        "senders": [
            {
                "node_id": "node-a",
                "certificate_pem": _fake_private_key("D"),
                "private_key_pem": _fake_private_key("E"),
            }
        ],
        "telegram": {
            "bot_token": "f" * 64,
            "chat_id": "-1001234567890",
            "relay_auth_token": "d" * 64,
        },
        "silence_gateway": {
            "operators": [{"owner": "operator-a", "token": "a" * 64}],
            "sender_token": "b" * 64,
            "backend_ca_pem": _fake_private_key("F"),
            "backend_server_cert_pem": _fake_private_key("G"),
            "backend_server_key_pem": _fake_private_key("H"),
            "backend_client_cert_pem": _fake_private_key("I"),
            "backend_client_key_pem": _fake_private_key("J"),
        },
    }
    return filled


def test_silence_gateway_complete_credentials_validate_and_block_is_optional(
    silence_doc, tmp_path
):
    result = _validate_cli(silence_doc, tmp_path)
    assert result.returncode == 0, result.stderr
    del silence_doc["observability_secrets"]["silence_gateway"]
    result = _validate_cli(silence_doc, tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation",
    [
        "empty",
        "overflow",
        "owner",
        "owner-newline",
        "operator-token",
        "sender-token",
        "relay-auth-token",
        "token-newline",
        "unknown",
        "operator-unknown",
        "pem",
    ],
)
def test_silence_gateway_schema_rejects_malformed_credentials(silence_doc, mutation):
    gateway = silence_doc["observability_secrets"]["silence_gateway"]
    if mutation == "empty":
        gateway["operators"] = []
    elif mutation == "overflow":
        gateway["operators"] *= 33
    elif mutation == "owner":
        gateway["operators"][0]["owner"] = "Invalid Owner"
    elif mutation == "owner-newline":
        gateway["operators"][0]["owner"] += "\n"
    elif mutation == "operator-token":
        gateway["operators"][0]["token"] = "A" * 64
    elif mutation == "sender-token":
        gateway["sender_token"] = "a" * 63
    elif mutation == "relay-auth-token":
        silence_doc["observability_secrets"]["telegram"]["relay_auth_token"] = "D" * 64
    elif mutation == "token-newline":
        gateway["sender_token"] += "\n"
    elif mutation == "unknown":
        gateway["extra"] = "unrecognized"
    elif mutation == "operator-unknown":
        gateway["operators"][0]["extra"] = "unrecognized"
    else:
        gateway["backend_ca_pem"] = "short"
    assert list(_validator().iter_errors(silence_doc))


@pytest.mark.parametrize(
    "field",
    [
        "operators",
        "sender_token",
        "backend_ca_pem",
        "backend_server_cert_pem",
        "backend_server_key_pem",
        "backend_client_cert_pem",
        "backend_client_key_pem",
    ],
)
def test_silence_gateway_schema_requires_complete_block(silence_doc, field):
    del silence_doc["observability_secrets"]["silence_gateway"][field]
    assert list(_validator().iter_errors(silence_doc))


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "operator-token",
        "sender-token",
        "relay-auth-token",
        "relay-auth-operator",
        "relay-auth-bot",
        "receiver-ca",
        "ingress-key",
        "sender-cert",
        "telegram-token",
        "backend-key",
        "rotation",
    ],
)
def test_silence_gateway_reused_authorities_are_rejected_without_values(
    silence_doc, tmp_path, mutation
):
    control = silence_doc["observability_secrets"]
    gateway = control["silence_gateway"]
    gateway["operators"].append({"owner": "operator-b", "token": "c" * 64})
    if mutation == "owner":
        gateway["operators"][1]["owner"] = "operator-a"
    elif mutation == "operator-token":
        gateway["operators"][1]["token"] = gateway["operators"][0]["token"]
    elif mutation == "sender-token":
        gateway["sender_token"] = gateway["operators"][0]["token"]
    elif mutation == "relay-auth-token":
        control["telegram"]["relay_auth_token"] = gateway["sender_token"]
    elif mutation == "relay-auth-operator":
        control["telegram"]["relay_auth_token"] = gateway["operators"][0]["token"]
    elif mutation == "relay-auth-bot":
        control["telegram"]["relay_auth_token"] = control["telegram"]["bot_token"]
    elif mutation == "receiver-ca":
        gateway["backend_ca_pem"] = control["receiver_ca_pem"]
    elif mutation == "ingress-key":
        gateway["backend_server_key_pem"] = control["ingress_private_key_pem"]
    elif mutation == "sender-cert":
        gateway["backend_client_cert_pem"] = control["senders"][0]["certificate_pem"]
    elif mutation == "telegram-token":
        gateway["sender_token"] = control["telegram"]["bot_token"]
    elif mutation == "backend-key":
        gateway["backend_client_key_pem"] = gateway["backend_server_key_pem"]
    else:
        control["rotation"] = {
            "authority": "telegram",
            "next_token": gateway["sender_token"],
            "started_at": "2026-09-04T00:00:00Z",
            "expires_at": "2026-09-04T01:00:00Z",
        }
    result = _validate_cli(silence_doc, tmp_path)
    assert result.returncode == 1
    assert "credential authority" in result.stderr or "duplicate owner" in result.stderr
    for value in [
        gateway["sender_token"],
        *(item["token"] for item in gateway["operators"]),
        *(value for key, value in gateway.items() if key.endswith("_pem")),
    ]:
        assert value not in result.stderr


@pytest.mark.parametrize(
    "mutation",
    [
        "sender-node",
        "sender-certificate",
        "sender-private-key",
        "bot-token",
        "pulse-token",
        "ui-password",
    ],
)
def test_observability_duplicate_authority_is_rejected(filled, tmp_path, mutation):
    pem_a = _fake_private_key("A")
    pem_b = _fake_private_key("B")
    cert_a = "-----BEGIN CERTIFICATE-----\n" + "C" * 64 + "\n-----END CERTIFICATE-----\n"
    cert_b = "-----BEGIN CERTIFICATE-----\n" + "D" * 64 + "\n-----END CERTIFICATE-----\n"
    filled["observability_secrets"] = {
        "schema_version": 1,
        "receiver_ca_pem": cert_a,
        "ingress_certificate_pem": cert_b,
        "ingress_private_key_pem": pem_a,
        "senders": [
            {"node_id": "node-a", "certificate_pem": cert_a + "A", "private_key_pem": pem_a + "A"},
            {"node_id": "node-b", "certificate_pem": cert_b + "B", "private_key_pem": pem_b + "B"},
        ],
        "telegram": {
            "bot_token": "primary-bot-token-aaaaaaaa",
            "chat_id": "-100000000001",
            "relay_auth_token": "e" * 64,
        },
        "ui_username": "operator",
        "ui_password": "observability-ui-password-dddddd",
    }
    filled["observability_deadman_secrets"] = {
        "schema_version": 1,
        "pulse_token": "deadman-pulse-token-bbbbbbbb",
        "telegram": {"bot_token": "secondary-bot-token-cccccc", "chat_id": "-100000000002"},
    }
    senders = filled["observability_secrets"]["senders"]
    if mutation == "sender-node":
        senders[1]["node_id"] = senders[0]["node_id"]
    elif mutation == "sender-certificate":
        senders[1]["certificate_pem"] = senders[0]["certificate_pem"]
    elif mutation == "sender-private-key":
        senders[1]["private_key_pem"] = senders[0]["private_key_pem"]
    elif mutation == "bot-token":
        filled["observability_deadman_secrets"]["telegram"]["bot_token"] = filled["observability_secrets"]["telegram"]["bot_token"]
    elif mutation == "pulse-token":
        filled["observability_deadman_secrets"]["pulse_token"] = filled["observability_secrets"]["telegram"]["bot_token"]
    elif mutation == "ui-password":
        filled["observability_secrets"]["ui_password"] = filled["observability_secrets"]["telegram"]["bot_token"]

    result = _validate_cli(filled, tmp_path)

    assert result.returncode == 1
    assert "observability credential authority" in result.stderr


@pytest.mark.parametrize("mutation", ["partial", "parallel", "unbounded"])
def test_observability_rotation_is_single_authority_complete_and_bounded(
    filled, tmp_path, mutation
):
    cert = "-----BEGIN CERTIFICATE-----\n" + "C" * 64 + "\n-----END CERTIFICATE-----\n"
    private = _fake_private_key("P")
    filled["observability_secrets"] = {
        "schema_version": 1,
        "receiver_ca_pem": cert,
        "ingress_certificate_pem": cert + "I",
        "ingress_private_key_pem": private,
        "senders": [
            {"node_id": "node-a", "certificate_pem": cert + "A", "private_key_pem": private + "A"}
        ],
        "telegram": {
            "bot_token": "primary-bot-token-aaaaaaaa",
            "chat_id": "-100000000001",
            "relay_auth_token": "e" * 64,
        },
        "rotation": {
            "authority": "sender",
            "sender_node_id": "node-a",
            "next_certificate_pem": cert + "NEXT",
            "next_private_key_pem": private + "NEXT",
            "started_at": "2026-09-01T00:00:00Z",
            "expires_at": "2026-09-01T06:00:00Z",
        },
    }
    filled["observability_deadman_secrets"] = {
        "schema_version": 1,
        "pulse_token": "deadman-pulse-token-bbbbbbbb",
        "telegram": {"bot_token": "secondary-bot-token-cccccc", "chat_id": "-100000000002"},
    }
    if mutation == "partial":
        del filled["observability_secrets"]["rotation"]["next_private_key_pem"]
    elif mutation == "parallel":
        filled["observability_deadman_secrets"]["rotation"] = {
            "authority": "pulse",
            "next_token": "next-deadman-pulse-token-dddd",
            "started_at": "2026-09-01T00:00:00Z",
            "expires_at": "2026-09-01T06:00:00Z",
        }
    elif mutation == "unbounded":
        filled["observability_secrets"]["rotation"]["expires_at"] = "2026-09-03T00:00:01Z"

    result = _validate_cli(filled, tmp_path)

    assert result.returncode == 1
    assert "observability rotation" in result.stderr


def test_one_bounded_observability_rotation_validates(filled, tmp_path):
    cert = "-----BEGIN CERTIFICATE-----\n" + "C" * 64 + "\n-----END CERTIFICATE-----\n"
    private = _fake_private_key("P")
    filled["observability_secrets"] = {
        "schema_version": 1,
        "receiver_ca_pem": cert,
        "ingress_certificate_pem": cert + "I",
        "ingress_private_key_pem": private,
        "senders": [
            {"node_id": "node-a", "certificate_pem": cert + "A", "private_key_pem": private + "A"}
        ],
        "telegram": {
            "bot_token": "primary-bot-token-aaaaaaaa",
            "chat_id": "-100000000001",
            "relay_auth_token": "e" * 64,
        },
        "rotation": {
            "authority": "sender",
            "sender_node_id": "node-a",
            "next_certificate_pem": cert + "NEXT",
            "next_private_key_pem": private + "NEXT",
            "started_at": "2026-09-01T00:00:00Z",
            "expires_at": "2026-09-01T06:00:00Z",
        },
    }
    filled["observability_deadman_secrets"] = {
        "schema_version": 1,
        "pulse_token": "deadman-pulse-token-bbbbbbbb",
        "telegram": {"bot_token": "secondary-bot-token-cccccc", "chat_id": "-100000000002"},
    }

    result = _validate_cli_with_selector(filled, tmp_path, enabled=True)

    assert result.returncode == 0, result.stderr


def test_strict_disabled_observability_exempts_secret_blocks(filled, tmp_path):
    filled.pop("observability_secrets", None)
    filled.pop("observability_deadman_secrets", None)

    result = _validate_cli_with_selector(filled, tmp_path, enabled=False)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "present",
    [None, "observability_secrets", "observability_deadman_secrets"],
)
def test_strict_enabled_observability_requires_both_secret_blocks(
    filled, tmp_path, present
):
    control = {
        "schema_version": 1,
        "receiver_ca_pem": "receiver-ca-material-not-real-000000000000",
        "ingress_certificate_pem": "ingress-cert-material-not-real-0000000000",
        "ingress_private_key_pem": "ingress-key-material-not-real-00000000000",
        "senders": [
            {
                "node_id": "node-a",
                "certificate_pem": "sender-cert-material-not-real-00000000000",
                "private_key_pem": "sender-key-material-not-real-000000000000",
            }
        ],
        "telegram": {
            "bot_token": "primary-bot-token-aaaaaaaa",
            "chat_id": "-100000000001",
            "relay_auth_token": "e" * 64,
        },
    }
    deadman = {
        "schema_version": 1,
        "pulse_token": "deadman-pulse-token-bbbbbbbb",
        "telegram": {
            "bot_token": "secondary-bot-token-cccccc",
            "chat_id": "-100000000002",
        },
    }
    if present == "observability_secrets":
        filled[present] = control
    elif present == "observability_deadman_secrets":
        filled[present] = deadman

    result = _validate_cli_with_selector(filled, tmp_path, enabled=True)

    assert result.returncode == 1
    assert "observability secrets required when enabled" in result.stderr


@pytest.mark.parametrize("field", ["ui_username", "ui_password"])
def test_observability_ui_credentials_are_complete_when_enabled(
    filled, tmp_path, field
):
    cert = "-----BEGIN CERTIFICATE-----\n" + "C" * 64 + "\n-----END CERTIFICATE-----\n"
    private = _fake_private_key("P")
    filled["observability_secrets"] = {
        "schema_version": 1,
        "receiver_ca_pem": cert,
        "ingress_certificate_pem": cert + "I",
        "ingress_private_key_pem": private,
        "senders": [
            {
                "node_id": "node-a",
                "certificate_pem": cert + "A",
                "private_key_pem": private + "A",
            }
        ],
        "telegram": {
            "bot_token": "primary-bot-token-aaaaaaaa",
            "chat_id": "-100000000001",
            "relay_auth_token": "e" * 64,
        },
        field: "operator" if field == "ui_username" else "ui-password-aaaaaaaaaaaa",
    }

    result = _validate_cli(filled, tmp_path)

    assert result.returncode == 1
    assert "observability UI credentials" in result.stderr


def test_awg_evidence_example_covers_every_schema_secret(example_doc, schema):
    contract = schema["properties"]["real_vps_awg_nat_secrets"]

    assert set(example_doc["real_vps_awg_nat_secrets"]) == set(contract["required"])


def test_awg_evidence_secret_block_rejects_missing_value(example_doc):
    doc = deepcopy(example_doc)
    del doc["real_vps_awg_nat_secrets"]["sentinel_ssh_private_key"]

    assert list(_validator().iter_errors(doc))


def test_filled_validates_strict_via_cli(filled, tmp_path):
    p = tmp_path / "filled.yaml"
    p.write_text(yaml.safe_dump(filled))
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(p), "--strict"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_hysteria_masquerade_requires_https(filled, tmp_path):
    doc = deepcopy(filled)
    doc["hysteria"]["masquerade_url"] = "http://vpn.example.com"

    proc = _validate_cli(doc, tmp_path)

    assert proc.returncode == 1
    assert "hysteria.masquerade_url" in proc.stderr


def test_plaintext_secrets_fixture_covers_required_hysteria_masquerade_url():
    fixture = yaml.safe_load(PLAIN_FIXTURE.read_text())

    assert fixture["hysteria"]["masquerade_url"] == "https://vpn.example.com"
    assert list(_validator().iter_errors(fixture)) == []


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


def test_cascade_proxy_password_rejects_json_significant_characters(example_doc):
    example_doc["cascade_secrets"]["classifier_proxy_password"] = 'unsafe"password' + "x" * 40
    errors = list(_validator().iter_errors(example_doc))

    assert errors


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


def _validate_cli_with_selector(doc, tmp_path, *, enabled):
    root = tmp_path / "selector-repo"
    (root / "scripts").mkdir(parents=True)
    (root / "secrets").mkdir()
    (root / "ansible" / "group_vars").mkdir(parents=True)
    shutil.copyfile(VALIDATOR, root / "scripts" / "validate-secrets.py")
    shutil.copyfile(SCHEMA, root / "secrets" / "schema.json")
    (root / "ansible" / "group_vars" / "all.yml").write_text(
        yaml.safe_dump(
            {
                "observability_contract": {
                    "enabled": enabled,
                    "schema_version": 1,
                    "credential_mode": "systemd",
                }
            }
        )
    )
    target = root / "secrets.yaml"
    target.write_text(yaml.safe_dump(doc))
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "validate-secrets.py"), str(target), "--strict"],
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
    assert "unknown xray client reference" in proc.stderr
    assert "missing" not in proc.stderr


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
    assert peer["public_key"] not in proc.stderr


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


# ---------------------------------------------------------------------------
# client_registry — per-device configuration registry contract
# ---------------------------------------------------------------------------

def _registry_entry(**overrides):
    entry = {
        "status": "delivered",
        "issued_at": "2026-08-23T12:00:00Z",
        "formats": ["ripdpi"],
        "hosts": ["upcloud:prod", "scaleway:prod"],
        "cohorts": [],
        "token_hash_prefix": "9f86d081",
        "token_expires": "2026-12-31",
        "awg_public_key_fingerprint": "REPLACE_" + "WITH_AWG_KEY_FINGERPRINT",
        "awg_private_key": "PRIVATEKEYPRIVATEKEYPRIVATEKEY",
        "last_payload_identity": {"source": "", "outputs": ""},
    }
    entry.update(overrides)
    return entry


def test_registry_entry_validates(filled):
    filled["client_registry"] = {"phone": _registry_entry()}
    errors = list(_validator().iter_errors(filled))
    assert not [e for e in errors if e.absolute_path[0] == "client_registry"]


def test_registry_missing_field_names_device(filled):
    entry = _registry_entry()
    del entry["token_hash_prefix"]
    filled["client_registry"] = {"phone": entry}
    errors = [
        e for e in _validator().iter_errors(filled)
        if e.absolute_path and e.absolute_path[0] == "client_registry"
    ]
    assert any("phone" in ".".join(str(p) for p in e.absolute_path) for e in errors)


def test_registry_rejects_unknown_status_and_format(filled):
    filled["client_registry"] = {
        "phone": _registry_entry(status="forgotten"),
    }
    assert list(_validator().iter_errors(filled))
    filled["client_registry"] = {"phone": _registry_entry(formats=["yaml"])}
    assert list(_validator().iter_errors(filled))


def test_registry_token_prefix_must_be_8_hex_or_empty(filled):
    for bad in ("9f86d0", "z" * 8, "9f86d0818"):
        filled["client_registry"] = {"phone": _registry_entry(token_hash_prefix=bad)}
        assert list(_validator().iter_errors(filled)), bad
    filled["client_registry"] = {"phone": _registry_entry(token_hash_prefix="")}
    assert not [
        e for e in _validator().iter_errors(filled)
        if e.absolute_path and e.absolute_path[0] == "client_registry"
    ]


def test_registry_fingerprint_placeholder_is_schema_valid(filled):
    filled["client_registry"] = {"phone": _registry_entry()}
    assert not [
        e for e in _validator().iter_errors(filled)
        if e.absolute_path and e.absolute_path[0] == "client_registry"
    ]


def _run_validator_on(doc: dict, tmp_path):
    path = tmp_path / "doc.yaml"
    path.write_text(yaml.safe_dump(doc))
    import os

    return subprocess.run(
        ["python3", str(VALIDATOR), str(path)],
        capture_output=True, text=True,
        env={**os.environ, "VPN_SECRETS_FILE": ""},
    )


def test_registry_semantic_mismatch_fails_naming_device(filled, tmp_path):
    filled["client_registry"] = {
        "phone": _registry_entry(awg_public_key_fingerprint="sha256:" + "0" * 16)
    }
    result = _run_validator_on(filled, tmp_path)
    assert result.returncode == 1
    assert "client_registry.phone.awg_public_key_fingerprint" in result.stderr


def test_registry_semantic_match_passes(filled, tmp_path):
    import hashlib

    pubkey = "PUBLICKEYPUBLICKEYPUBLIC"
    good = "sha256:" + hashlib.sha256(pubkey.encode()).hexdigest()[:16]
    filled["client_registry"] = {
        "phone": _registry_entry(awg_public_key_fingerprint=good)
    }
    result = _run_validator_on(filled, tmp_path)
    assert result.returncode == 0, result.stderr


def test_example_file_contains_client_registry_block(example_doc):
    assert isinstance(example_doc.get("client_registry"), dict)


def test_coverage_checker_requires_client_registry():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_secrets_coverage", REPO_ROOT / "scripts" / "check-secrets-coverage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "client_registry" in module.EXPECTED_SECRET_TOPLEVEL
