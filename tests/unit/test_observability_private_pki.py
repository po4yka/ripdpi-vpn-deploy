"""Real local OpenSSL/SOPS evidence, never a live host or credential claim."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def module():
    specification = importlib.util.spec_from_file_location(
        "private_observability_pki", ROOT / "scripts/prepare-observability-pki.py"
    )
    result = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(result)
    return result


def configuration():
    return {
        "schema_version": 1,
        "collector_address": "100.64.0.2",
        "observer_address": "100.64.0.3",
        "node_ids": ["node-a", "node-b"],
        "recipient": "age1" + "q" * 58,
    }


def command(argv, cwd, **kwargs):
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, timeout=20, check=False, **kwargs
    )


def test_real_ip_san_unique_clients_and_revocation(module, tmp_path):
    directory = tmp_path.resolve()
    bundle = module.generate(configuration(), directory)
    senders = bundle["runtime"]["observability_secrets"]["senders"]
    assert len({sender["private_key_pem"] for sender in senders}) == 2
    verify = [
        "openssl",
        "verify",
        "-x509_strict",
        "-CAfile",
        "observability-receiver-ca.crt",
        "-purpose",
        "sslserver",
        "-verify_ip",
    ]
    assert command([*verify, "100.64.0.2", "ingress.crt"], directory).returncode == 0
    assert command([*verify, "100.64.0.3", "ingress.crt"], directory).returncode != 0
    verify_client = [
        "openssl",
        "verify",
        "-x509_strict",
        "-CAfile",
        "observability-receiver-ca.crt",
        "-purpose",
        "sslclient",
        "-crl_check",
        "-CRLfile",
        "observability-receiver-ca.crl",
        "sender-0.crt",
    ]
    assert command(verify_client, directory).returncode == 0
    revoke = [
        "openssl",
        "ca",
        "-batch",
        "-config",
        "observability-receiver-ca-ca.cnf",
        "-revoke",
        "sender-0.crt",
    ]
    assert command(revoke, directory).returncode == 0
    refresh = [
        "openssl",
        "ca",
        "-batch",
        "-config",
        "observability-receiver-ca-ca.cnf",
        "-gencrl",
        "-out",
        "observability-receiver-ca.crl",
    ]
    assert command(refresh, directory).returncode == 0
    rejected = command(verify_client, directory)
    assert rejected.returncode != 0
    assert b"certificate revoked" in rejected.stderr
    assert command([*verify_client[:-1], "sender-1.crt"], directory).returncode == 0


@pytest.mark.parametrize(
    "fault",
    ["public", "loopback", "same-host", "duplicate-node", "eleven-nodes", "injection"],
)
def test_pki_preparation_rejects_unscoped_authority(module, fault):
    config = configuration()
    if fault == "public":
        config["collector_address"] = "8.8.8.8"
    elif fault == "loopback":
        config["collector_address"] = "127.0.0.1"
    elif fault == "same-host":
        config["observer_address"] = config["collector_address"]
    elif fault == "duplicate-node":
        config["node_ids"] = ["node-a", "node-a"]
    elif fault == "eleven-nodes":
        config["node_ids"] = [f"node-{index}" for index in range(11)]
    else:
        config["node_ids"] = ["node-a/CN=foreign"]
    with pytest.raises(ValueError):
        module.validate_config(config)


def test_real_sops_round_trip_no_clobber_and_no_plaintext_output(module, tmp_path):
    directory = tmp_path.resolve()
    directory.chmod(0o700)
    identity = directory / "identity"
    assert command(["age-keygen", "-o", str(identity)], directory).returncode == 0
    recipient = (
        command(["age-keygen", "-y", str(identity)], directory).stdout.decode().strip()
    )
    config = configuration()
    config["recipient"] = recipient
    config_path = directory / "config.json"
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    output = directory / "pki.sops.yaml"
    module.prepare(config_path, output)
    encrypted = output.read_bytes()
    assert b"BEGIN PRIVATE" not in encrypted
    assert b"ENC[AES256_GCM" in encrypted
    assert output.stat().st_mode & 0o777 == 0o600
    decrypted = command(
        ["sops", "--decrypt", str(output)],
        directory,
        env={**os.environ, "SOPS_AGE_KEY_FILE": str(identity)},
    )
    assert decrypted.returncode == 0
    document = yaml.safe_load(decrypted.stdout)
    assert document["schema_version"] == 1
    assert len(document["runtime"]["observability_secrets"]["senders"]) == 2
    assert "private_key" in document["authorities"]["receiver"]
    with pytest.raises(ValueError, match="output exists"):
        module.prepare(config_path, output)
    assert output.read_bytes() == encrypted


def test_symlink_output_parent_refused(module, tmp_path):
    directory = tmp_path.resolve()
    directory.chmod(0o700)
    config_path = directory / "config.json"
    config_path.write_text(json.dumps(configuration()))
    config_path.chmod(0o600)
    linked = directory / "linked"
    linked.symlink_to(directory, target_is_directory=True)
    with pytest.raises(module.helpers.PreparationError):
        module.prepare(config_path, linked / "pki.sops.yaml")
    assert not (directory / "pki.sops.yaml").exists()


def test_duplicate_authority_input_refused_before_generation(module, tmp_path):
    directory = tmp_path.resolve()
    directory.chmod(0o700)
    config_path = directory / "config.json"
    config_path.write_text('{"schema_version":1,"schema_version":1}')
    config_path.chmod(0o600)
    with pytest.raises(ValueError, match="duplicate field"):
        module.prepare(config_path, directory / "pki.sops.yaml")
    assert not (directory / "pki.sops.yaml").exists()


def test_changed_output_parent_cannot_report_success(module, tmp_path, monkeypatch):
    directory = tmp_path.resolve()
    directory.chmod(0o700)
    config_path = directory / "config.json"
    config_path.write_text(json.dumps(configuration()))
    config_path.chmod(0o600)
    output_parent = directory / "output"
    output_parent.mkdir(mode=0o700)
    retained_parent = directory / "retained"
    write = module.helpers._write_private_at

    def replace_parent(descriptor, name, content):
        write(descriptor, name, content)
        output_parent.rename(retained_parent)
        output_parent.mkdir(mode=0o700)

    monkeypatch.setattr(module, "generate", lambda *_: {})
    monkeypatch.setattr(
        module.helpers, "_encrypt_sops", lambda *_: b"synthetic ciphertext"
    )
    monkeypatch.setattr(module.helpers, "_write_private_at", replace_parent)
    with pytest.raises(ValueError, match="output changed"):
        module.prepare(config_path, output_parent / "pki.sops.yaml")
    assert not (output_parent / "pki.sops.yaml").exists()
    assert (retained_parent / "pki.sops.yaml").read_bytes() == b"synthetic ciphertext"
