"""Certificate verification must cover EC as well as RSA keys."""

from pathlib import Path


def test_check_certs_uses_public_key_der_digest_not_rsa_modulus():
    script = (Path(__file__).resolve().parents[2] / "scripts/check-certs.sh").read_text()
    assert "openssl x509 -pubkey -noout" in script
    assert "openssl pkey -pubout -outform DER" in script
    assert "openssl rsa  -noout -modulus" not in script
