#!/usr/bin/env python3
"""Controller-only preflight for dedicated silence-backend certificate authority."""

from datetime import UTC, datetime
import ipaddress
import json
import sys

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID


def public_key(value):
    return value.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def validate(contract):
    gateway = contract["alerting"]["silence_gateway"]
    authorities = x509.load_pem_x509_certificates(gateway["backend_ca_pem"].encode())
    if len(authorities) != 1:
        raise ValueError("backend-single-ca")
    ca = authorities[0]
    if (
        gateway["backend_ca_pem"].replace("\r\n", "\n").strip()
        != ca.public_bytes(serialization.Encoding.PEM).decode().strip()
    ):
        raise ValueError("backend-ca-content")
    ingest = x509.load_pem_x509_certificates(contract["tls"]["client_ca_pem"].encode())
    if not ingest:
        raise ValueError("ingest-ca")
    ingest_keys = [public_key(cert) for cert in ingest]
    if (
        public_key(ca) in ingest_keys
        or not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    ):
        raise ValueError("dedicated-ca")
    ca.verify_directly_issued_by(ca)
    now = datetime.now(UTC)
    if not ca.not_valid_before_utc <= now < ca.not_valid_after_utc:
        raise ValueError("ca-validity")
    keys = [public_key(ca), *ingest_keys]
    for identity, purpose in [
        ("server", ExtendedKeyUsageOID.SERVER_AUTH),
        ("client", ExtendedKeyUsageOID.CLIENT_AUTH),
    ]:
        cert = x509.load_pem_x509_certificate(
            gateway[f"backend_{identity}_cert_pem"].encode()
        )
        key = serialization.load_pem_private_key(
            gateway[f"backend_{identity}_key_pem"].encode(), password=None
        )
        cert.verify_directly_issued_by(ca)
        if public_key(cert) != public_key(key) or public_key(cert) in keys:
            raise ValueError("key-separation")
        keys.append(public_key(cert))
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError("leaf-validity")
        if set(
            cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        ) != {purpose}:
            raise ValueError("leaf-purpose")
        try:
            if cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                raise ValueError("leaf-ca")
        except x509.ExtensionNotFound:
            pass
        if identity == "server" and ipaddress.ip_address(
            "127.0.0.1"
        ) not in cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(
            x509.IPAddress
        ):
            raise ValueError("server-san")


if __name__ == "__main__":
    try:
        validate(json.load(sys.stdin))
    except Exception:
        print("silence-backend: certificate-contract-refused", file=sys.stderr)
        raise SystemExit(1) from None
