"""Certificate verification must cover EC keys and indented SAN output."""

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_check_certs_uses_public_key_der_digest_not_rsa_modulus():
    script = (ROOT / "scripts/check-certs.sh").read_text()
    assert 'openssl x509 -in "$cert_file" -pubkey -noout' in script
    assert 'openssl pkey -in "$key_file" -pubout -outform DER' in script
    assert "openssl rsa  -noout -modulus" not in script


def test_check_certs_accepts_indented_openssl_san_output_from_certificate_chain(tmp_path):
    pytest.importorskip("yaml")
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
            "-nodes",
            "-days",
            "30",
            "-subj",
            "/CN=example.test",
            "-addext",
            "subjectAltName=DNS:example.test,DNS:www.example.test",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    # A chain larger than the pipe buffer makes openssl close stdin after the
    # first certificate while the producer is still writing. The producer's
    # SIGPIPE must not turn a successfully parsed certificate into a finding.
    cert_text = cert.read_text() * 256
    key_text = key.read_text()
    secrets = tmp_path / "secrets.yaml"
    import yaml

    secrets.write_text(
        yaml.safe_dump(
            {
                name: {
                    "server_name": "example.test",
                    "cert_pem": cert_text,
                    "key_pem": key_text,
                }
                for name in ("nginx_xhttp", "hysteria", "naive_secrets")
            }
        )
    )

    result = subprocess.run(
        [str(ROOT / "scripts/check-certs.sh"), str(secrets)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "appears self-signed" in result.stdout
    assert "openssl could not parse cert_pem" not in result.stdout
    assert "SAN does not cover example.test" not in result.stdout
