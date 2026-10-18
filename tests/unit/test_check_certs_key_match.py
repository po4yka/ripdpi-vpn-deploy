"""Certificate verification must cover EC keys and indented SAN output."""

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

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


@pytest.mark.parametrize(
    ("hostname", "dns_names", "accepted"),
    [
        ("node.alpha.example.test", ["node.alpha.example.test"], True),
        ("node.alpha.example.test", ["*.alpha.example.test"], True),
        ("NODE.alpha.example.test", ["*.ALPHA.example.test"], True),
        ("node.alpha.example.test", ["other.example.test", "node.alpha.example.test"], True),
        ("node.alpha.example.test", ["*.alphaXexample.test"], False),
        ("deep.node.alpha.example.test", ["*.alpha.example.test"], False),
        ("alpha.example.test", ["*.alpha.example.test"], False),
        ("node.alpha.example.test", ["n*.alpha.example.test"], False),
        ("node.alpha.example.test", ["other.example.test"], False),
        ("node.alpha.example.test", [], False),
    ],
)
def test_check_certs_matches_only_exact_or_complete_wildcard_dns_san(
    tmp_path, hostname, dns_names, accepted
):
    """Exercise the complete operator script with actual issued certificates."""
    authority_key = ec.generate_private_key(ec.SECP256R1())
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic test CA")])
    # A matching CN must never rescue a missing or mismatched DNS SAN.
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
    )
    if dns_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in dns_names]),
            critical=False,
        )
    certificate = builder.sign(authority_key, hashes.SHA256())
    material = {
        "server_name": hostname,
        "cert_pem": certificate.public_bytes(serialization.Encoding.PEM).decode(),
        "key_pem": leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    }
    secrets = tmp_path / "synthetic-certificates.yaml"
    secrets.write_text(
        yaml.safe_dump({name: material for name in ("nginx_xhttp", "hysteria", "naive_secrets")})
    )
    secrets.chmod(0o600)
    result = subprocess.run(
        [str(ROOT / "scripts/check-certs.sh"), str(secrets)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if accepted else 1), result.stdout + result.stderr
    if accepted:
        assert "OK — certs healthy" in result.stdout
    else:
        assert result.stdout.count("SAN does not cover") == 3
