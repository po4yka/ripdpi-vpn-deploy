"""Certificate verification must cover EC keys and indented SAN output."""

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[2]


def test_check_certs_never_prompts_for_a_key_passphrase():
    # Without a controlling terminal a prompt fails like a mismatch, so a run cannot show this.
    assert 'openssl pkey -in "$key_file" -passin pass: ' in (ROOT / "scripts/check-certs.sh").read_text()


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
        env={**os.environ, "VPN_SECRETS_FILE": str(secrets)},
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
    authority, authority_key = issue_ca()
    material = issue_leaf(authority, authority_key, hostname=hostname, dns_names=dns_names)
    result = run_check(tmp_path, {
        "vpn": {"enable_naive": True},
        **{name: material for name in ("nginx_xhttp", "hysteria", "naive_secrets")},
    }, authority)
    assert result.returncode == (0 if accepted else 1), result.stdout + result.stderr
    if accepted:
        assert "OK — supplied certs healthy" in result.stdout
    else:
        assert result.stdout.count("SAN does not cover") == 3


def pem(certificate):
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


def issue_ca(issuer=None, issuer_key=None):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic intermediate CA" if issuer else "Synthetic test CA")])
    now = datetime.now(UTC)
    certificate = (x509.CertificateBuilder().subject_name(subject)
                   .issuer_name(issuer.subject if issuer else subject).public_key(key.public_key())
                   .serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                   .sign(issuer_key or key, hashes.SHA256()))
    return certificate, key


def issue_leaf(authority, authority_key, *, hostname="node.example.test", dns_names=None,
               start=-1, end=30, purpose=ExtendedKeyUsageOID.SERVER_AUTH):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
               .issuer_name(authority.subject).public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now + timedelta(days=start)).not_valid_after(now + timedelta(days=end))
               .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
               .add_extension(x509.ExtendedKeyUsage([purpose]), critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()), critical=False))
    if dns_names is None:
        dns_names = [hostname]
    if dns_names:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name) for name in dns_names]), critical=False)
    certificate = builder.sign(authority_key, hashes.SHA256())
    return {"server_name": hostname, "cert_pem": pem(certificate), "key_pem": key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}


def run_check(tmp_path, document, authority, *, environment=None, script=None, command=None, cwd=None):
    secrets = tmp_path / "synthetic-certificates.yaml"
    secrets.write_text(yaml.safe_dump(document))
    secrets.chmod(0o600)
    trust = tmp_path / "root.pem"
    trust.write_text(pem(authority))
    ca_directory = tmp_path / "ca-directory"
    ca_directory.mkdir(exist_ok=True)
    result = subprocess.run(command or [str(script or ROOT / "scripts/check-certs.sh"), str(secrets)], cwd=cwd,
                            env={**{name: value for name, value in os.environ.items()
                                    if not name.startswith("VPN_CERT_")},
                                 "VPN_SECRETS_FILE": str(secrets), "SSL_CERT_FILE": str(trust),
                                 "SSL_CERT_DIR": str(ca_directory), **(environment or {})},
                            text=True, capture_output=True, check=False, timeout=20)
    assert "BEGIN PRIVATE KEY" not in result.stdout + result.stderr
    assert "BEGIN CERTIFICATE" not in result.stdout + result.stderr
    return result


@pytest.mark.parametrize("failure", ["untrusted", "future", "expired", "near-expiry", "client-only", "key-mismatch"])
def test_check_certs_refuses_unusable_certificate(tmp_path, failure):
    authority, key = issue_ca()
    material = issue_leaf(authority, key, **{
        "future": {"start": 3}, "expired": {"start": -30, "end": -1},
        "near-expiry": {"end": 3}, "client-only": {"purpose": ExtendedKeyUsageOID.CLIENT_AUTH},
    }.get(failure, {}))
    if failure == "untrusted":
        authority, _key = issue_ca()
    if failure == "key-mismatch":
        material["key_pem"] = issue_leaf(authority, key)["key_pem"]
    result = run_check(tmp_path, {"nginx_xhttp": material, "hysteria": material}, authority)
    assert result.returncode == 1, result.stdout + result.stderr
    if failure in ("untrusted", "future", "expired", "client-only"):
        assert "certificate trust, validity, or TLS server purpose verification failed" in result.stdout


@pytest.mark.parametrize(("chain", "accepted"), [
    ("leaf-and-intermediate", True), ("leaf-intermediate-root", True),
    ("leaf-only", False), ("leaf-root-only", False), ("untrusted-root-in-chain", False),
])
def test_check_certs_requires_chain_to_operator_trust_store(tmp_path, chain, accepted):
    root, root_key = issue_ca()
    intermediate, intermediate_key = issue_ca(root, root_key)
    material = issue_leaf(intermediate, intermediate_key)
    if chain in ("leaf-and-intermediate", "leaf-intermediate-root", "untrusted-root-in-chain"):
        material["cert_pem"] += pem(intermediate)
    if chain in ("leaf-intermediate-root", "leaf-root-only", "untrusted-root-in-chain"):
        material["cert_pem"] += pem(root)
    if chain == "untrusted-root-in-chain":
        root, _key = issue_ca()
    result = run_check(tmp_path, {"nginx_xhttp": material, "hysteria": material}, root)
    assert result.returncode == (0 if accepted else 1), result.stdout + result.stderr


@pytest.mark.parametrize("enabled", [False, True])
def test_check_certs_requires_naive_only_when_enabled(tmp_path, enabled):
    root, key = issue_ca()
    material = issue_leaf(root, key)
    result = run_check(tmp_path, {"vpn": {"enable_naive": enabled},
                                "nginx_xhttp": material, "hysteria": material}, root)
    assert result.returncode == int(enabled), result.stdout + result.stderr
    assert ("[naive_secrets]" in result.stdout) == enabled


@pytest.mark.parametrize("identity", ["nginx-fallback", "ech-inner"])
def test_check_certs_resolves_hysteria_default_identity(tmp_path, identity):
    root, key = issue_ca()
    material = issue_leaf(root, key)
    hysteria = {name: value for name, value in material.items() if name != "server_name"}
    if identity == "ech-inner":
        hysteria["ech"] = {"inner_name": material["server_name"]}
        frontend = {**material, "server_name": "wrong.example.test"}
        vpn = {"enable_nginx_xhttp": False}
    else:
        frontend, vpn = material, {}
    result = run_check(tmp_path, {"vpn": vpn, "nginx_xhttp": frontend, "hysteria": hysteria}, root)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(("enabled", "valid"), [(False, False), (True, False), (True, True)])
def test_check_certs_checks_distinct_fallback_authority_only_when_enabled(tmp_path, enabled, valid):
    root, key = issue_ca()
    material = issue_leaf(root, key)
    fallback = issue_leaf(root, key, hostname="fallback.example.test")
    frontend = {**material, "fallback_enabled": enabled, "fallback_server_name": "fallback.example.test"}
    if valid:
        frontend.update(fallback_cert_pem=fallback["cert_pem"], fallback_key_pem=fallback["key_pem"])
    result = run_check(tmp_path, {"nginx_xhttp": frontend, "hysteria": material}, root)
    assert result.returncode == int(enabled and not valid), result.stdout + result.stderr
    assert ("[nginx_xhttp_fallback]" in result.stdout) == enabled


def test_check_certs_disabled_profile_ignores_absent_certificate_blocks(tmp_path):
    root, _key = issue_ca()
    result = run_check(tmp_path, {"vpn": {"enable_nginx_xhttp": False, "enable_hysteria": False}}, root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_certs_uses_exact_ordered_deployment_variables(tmp_path):
    root, key = issue_ca()
    material = issue_leaf(root, key)
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump({"vpn": {"enable_nginx_xhttp": True, "enable_hysteria": False}}))
    override = tmp_path / "override.yaml"
    override.write_text(yaml.safe_dump({"vpn": {"enable_nginx_xhttp": False, "enable_hysteria": False}}))
    source = tmp_path / "synthetic-certificates.yaml"
    environment = {"VPN_CERT_VARS_FILES": json.dumps([str(profile), str(source), str(override)])}
    result = run_check(tmp_path, {"nginx_xhttp": material}, root, environment=environment)
    assert result.returncode == 0 and "[nginx_xhttp]" not in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("environment", [
    {"VPN_CERT_COHORTS": "p0-minimal,p1-p2"}, {"VPN_CERT_COHORTS": "../private"},
    {"VPN_CERT_LIMIT": "node-one"}, {"VPN_CERT_VARS_FILES": "[]"},
])
def test_check_certs_refuses_ambiguous_or_invalid_profile(tmp_path, environment):
    root, _key = issue_ca()
    result = run_check(tmp_path, {}, root, environment=environment)
    assert result.returncode == 1
    assert "certificate profile selection failed" in result.stderr


@pytest.mark.parametrize(("limit", "has_material", "accepted"), [
    ("direct-only", False, True), ("vpn", True, True), ("vpn", False, False),
])
@pytest.mark.parametrize("through_make", [False, True])
def test_check_certs_resolves_exact_inventory_profiles_without_cohort_flags(
    tmp_path, limit, has_material, accepted, through_make
):
    """Use the real strict selector locally with synthetic private paths."""
    import shutil

    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    for name in ("check-certs.sh", "deploy-controller.py", "fleet_inspection.py", "bootstrap_readiness.py",
                 "sshd_bundle_source.py", "sshd_contexts.py", "sshd_transaction_limits.py", "transport_semantics.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    group_vars = repo / "ansible/group_vars"
    group_vars.mkdir(parents=True)
    for name, value in {
        "all": {"vpn": {"enable_nginx_xhttp": True, "enable_hysteria": True}},
        "vpn": {},
        "vpn-direct-only": {"vpn": {"enable_nginx_xhttp": False, "enable_hysteria": False}},
        "vpn-web-only": {"vpn": {"enable_nginx_xhttp": True, "enable_hysteria": False}},
    }.items():
        (group_vars / (name + ".yml")).write_text(yaml.safe_dump(value))
    private_key = tmp_path / "inventory-key"
    private_key.write_text("synthetic-private-key-path-fixture")
    private_key.chmod(0o600)
    inventory = repo / "ansible/inventory/generated.ini"
    inventory.parent.mkdir()
    inventory.write_text(
        "[vpn]\n"
        "direct-only ansible_host=192.0.2.1 ansible_user=deploy ansible_port=22\n"
        "web-only ansible_host=192.0.2.2 ansible_user=deploy ansible_port=22\n"
        "[vpn-direct-only]\ndirect-only\n[vpn-web-only]\nweb-only\n"
        f"[vpn:vars]\nansible_ssh_private_key_file={private_key}\n"
    )
    inventory.chmod(0o600)
    root, key = issue_ca()
    document = {"nginx_xhttp": issue_leaf(root, key)} if has_material else {}
    command = None
    if through_make:
        shutil.copy2(ROOT / "Makefile", repo / "Makefile")
        command = ["make", "check-certs", "ANSIBLE_LIMIT=" + limit,
                   "SECRETS_FILE=" + str(tmp_path / "synthetic-certificates.yaml")]
    result = run_check(tmp_path, document, root, environment={
        "VPN_CERT_INVENTORY": str(inventory), "VPN_CERT_LIMIT": limit,
    }, script=scripts / "check-certs.sh", command=command, cwd=repo)
    assert result.returncode == (0 if accepted else (2 if through_make else 1)), result.stdout + result.stderr
    assert "[hysteria]" not in result.stdout
    assert "192.0.2." not in result.stdout + result.stderr
    if limit == "direct-only":
        assert "[nginx_xhttp]" not in result.stdout


@pytest.mark.parametrize("valid", [False, True])
def test_check_certs_checks_enabled_self_steal_authority(tmp_path, valid):
    root, key = issue_ca()
    document = {"vpn": {"enable_nginx_xhttp": False, "enable_hysteria": False,
                        "enable_reality_self_steal": True}}
    if valid:
        document["reality_self_steal"] = issue_leaf(root, key)
    result = run_check(tmp_path, document, root)
    assert result.returncode == int(not valid), result.stdout + result.stderr
    assert "[reality_self_steal]" in result.stdout


def test_check_certs_subscription_only_does_not_require_transport_certificates(tmp_path):
    root, _key = issue_ca()
    result = run_check(tmp_path, {"vpn_subscription_only": True}, root)
    assert result.returncode == 0, result.stdout + result.stderr
