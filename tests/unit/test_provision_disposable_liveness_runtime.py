"""Offline boundaries of the disposable executor runtime provisioner; no VM or network."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import re
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load("provision_runtime", ROOT / "scripts/provision-disposable-liveness-runtime.py")


def test_inputs_come_from_the_sentinel_role_plus_a_new_enough_go(module):
    packages, commits = module.role_inputs()
    assert {"build-essential", "git", "iproute2", "nftables", "python3", "curl", "golang-1.24-go"} <= set(packages)
    assert commits == {"go": "2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf",
                       "tools": "c0b400c6dfc046f5cae8f3051b14cb61686fcf55"}


def test_engine_pins_match_the_ci_pins_of_the_same_releases(module):
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    environment = {key: str(value) for job in ci["jobs"].values() for step in job.get("steps", [])
                   for key, value in (step.get("env") or {}).items()}
    environment.update({key: str(value) for job in ci["jobs"].values() for key, value in (job.get("env") or {}).items()})
    sing_box = module.ENGINES["sing-box"]
    assert sing_box["version"] == environment["SING_BOX_CLIENT_VERSION"]
    assert sing_box["archives"]["amd64"][1] == environment["SING_BOX_CLIENT_LINUX_AMD64_SHA256"]
    action = yaml.safe_load((ROOT / ".github/actions/install-xray/action.yml").read_text())
    xray_env = action["runs"]["steps"][0]["env"]
    assert "v" + module.ENGINES["xray"]["version"] == xray_env["XRAY_VERSION"]
    assert module.ENGINES["xray"]["archives"]["amd64"][1] == xray_env["XRAY_SHA256"]
    # The local parser pins of the liveness installer must name the same versions.
    make = (ROOT / "Makefile").read_text()
    assert f"--sing-box-version {sing_box['version']} --xray-version {module.ENGINES['xray']['version']}" in make


@pytest.mark.parametrize("kind", ["tar", "zip"])
def test_engine_binary_reads_only_the_pinned_member(module, kind):
    name, archive_name = ("sing-box", "sing-box-1.14.3-linux-arm64.tar.gz") if kind == "tar" else ("xray", "Xray-linux-arm64-v8a.zip")
    member = "sing-box-1.14.3-linux-arm64/sing-box" if kind == "tar" else "xray"
    def archive_with(path: str) -> bytes:
        buffer = io.BytesIO()
        if kind == "tar":
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                info = tarfile.TarInfo(path)
                info.size = 6
                archive.addfile(info, io.BytesIO(b"engine"))
        else:
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(path, b"engine")
        return buffer.getvalue()

    assert module.engine_binary(name, archive_name, archive_with(member), "arm64") == b"engine"
    with pytest.raises(module.ProvisionError, match="archive-member"):
        module.engine_binary(name, archive_name, archive_with("README.md"), "arm64")


def test_vendor_archive_is_deterministic_and_accepted_by_the_offline_builder(module, tmp_path):
    installer = load("awg_installer", ROOT / "scripts/install-real-vps-awg-client-tools.py")
    source = tmp_path / "source"
    (source / "vendor/example.org/lib").mkdir(parents=True)
    (source / "vendor/modules.txt").write_text("# example.org/lib v1.0.0\n")
    (source / "vendor/example.org/lib/lib.go").write_text("package lib\n")
    (source / "go.mod").write_text("module example\n")
    first = module.vendor_archive(source, tmp_path / "one.tar")
    os.utime(source / "vendor/modules.txt", (1, 1))
    second = module.vendor_archive(source, tmp_path / "two.tar")
    assert first == second == hashlib.sha256((tmp_path / "one.tar").read_bytes()).hexdigest()
    with tarfile.open(tmp_path / "one.tar") as archive:
        members = archive.getmembers()
        installer.validate_vendor(members)
    assert {member.name for member in members} == {
        "vendor", "vendor/modules.txt", "vendor/example.org", "vendor/example.org/lib", "vendor/example.org/lib/lib.go"}


@pytest.mark.parametrize("fault", ["mode", "nonempty"])
def test_work_directory_must_be_private_and_empty(module, tmp_path, fault):
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    if fault == "mode":
        work.chmod(0o755)
    else:
        (work / "stale").write_text("")
    with pytest.raises(module.ProvisionError, match="^work-directory$"):
        module.private_work_directory(work)


def test_version_parser_reads_engine_and_awg_banners(module):
    assert module.version_of("sing-box version 1.14.3\n\nEnvironment: go1.24") == "1.14.3"
    assert module.version_of("Xray 26.10.31 (Xray, Penetrates Everything.)") == "26.10.31"
    assert re.fullmatch(r"\d+\.\d+\.\d+", module.version_of("awg v1.0.20241018 - https://amnezia.org"))



def _certificate(tmp_path: Path, name: str, *, ca: bool | None = True, valid=(-1, 30), san="dns", signer=None):
    """Write one PEM certificate whose issuer name is its subject; `signer` signs with another key."""
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now + datetime.timedelta(days=valid[0]))
               .not_valid_after(now + datetime.timedelta(days=valid[1])))
    if ca is not None:
        builder = builder.add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    if san == "dns":
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
    elif san == "ip":
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("192.0.2.1"))]), critical=False)
    cert = builder.sign(signer or key, hashes.SHA256())
    path = tmp_path / f"{name}.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return path, cert, key


def _der_sha256(path: Path) -> str:
    # Independent of the implementation: the openssl CLI re-encodes the certificate.
    import subprocess

    der = subprocess.run(["openssl", "x509", "-in", str(path), "-outform", "DER"], check=True,
                         capture_output=True).stdout
    return hashlib.sha256(der).hexdigest()


def _generator_certificate(tmp_path: Path) -> Path:
    """The staging generator's own command (scripts/ci-bootstrap-secrets.sh)."""
    import subprocess

    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30",
                    "-keyout", str(tmp_path / "key.pem"), "-out", str(tmp_path / "generated.pem"),
                    "-subj", "/CN=vpn-ci-staging-fixture", "-addext", "subjectAltName=DNS:vpn-ci-staging-fixture"],
                   check=True, capture_output=True)
    return tmp_path / "generated.pem"


@pytest.mark.parametrize("shape", ["generator", "ca-true", "ca-false", "no-basic-constraints", "leading-text"])
def test_trust_anchor_accepts_one_valid_self_signed_certificate(module, tmp_path, shape):
    if shape == "generator":
        path = _generator_certificate(tmp_path)
    else:
        path = _certificate(tmp_path, "vpn-ci-staging-fixture",
                            ca={"ca-false": False, "no-basic-constraints": None}.get(shape, True))[0]
        if shape == "leading-text":
            path.write_bytes(b"subject=CN=vpn-ci-staging-fixture\n" + path.read_bytes())

    pem, digest = module.trust_anchor(path)

    assert pem.startswith(b"-----BEGIN CERTIFICATE-----") and pem.count(b"-----BEGIN ") == 1
    assert digest == _der_sha256(path)


@pytest.mark.parametrize("fault", ["bundle", "private-key", "ca-issued", "foreign-key-same-name", "expired",
                                   "not-yet-valid", "no-san", "ip-only-san", "not-pem", "oversized"])
def test_trust_anchor_refuses_unsuitable_input_before_the_executor(module, tmp_path, monkeypatch, fault):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    valid = {"expired": (-10, -1), "not-yet-valid": (1, 30)}.get(fault, (-1, 30))
    san = {"no-san": None, "ip-only-san": "ip"}.get(fault, "dns")
    signer = ec.generate_private_key(ec.SECP256R1()) if fault == "foreign-key-same-name" else None
    path, cert, key = _certificate(tmp_path, "vpn-ci-staging-fixture", valid=valid, san=san, signer=signer)
    if fault == "bundle":
        path.write_bytes(path.read_bytes() + _certificate(tmp_path, "other")[0].read_bytes())
    elif fault == "private-key":
        path.write_bytes(path.read_bytes() + key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    elif fault == "ca-issued":
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes

        leaf_key = ec.generate_private_key(ec.SECP256R1())
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(
            x509.oid.NameOID.COMMON_NAME, "leaf.example.test")])).issuer_name(cert.subject)
            .public_key(leaf_key.public_key()).serial_number(1)
            .not_valid_before(cert.not_valid_before_utc).not_valid_after(cert.not_valid_after_utc)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("leaf.example.test")]), critical=False)
            .sign(key, hashes.SHA256()))
        path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    elif fault == "not-pem":
        path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
    elif fault == "oversized":
        path.write_bytes(path.read_bytes() + b"\n" * (64 * 1024))
    contacted = []
    monkeypatch.setattr(module, "load_live_executor", lambda *a, **k: contacted.append("manifest"))
    monkeypatch.setattr(module.Executor, "run", lambda *a, **k: contacted.append("run"))
    work = tmp_path / "work"
    work.mkdir(mode=0o700)

    with pytest.raises(module.ProvisionError, match="^trust-anchor"):
        module.provision(tmp_path / "executor.json", work, path)
    assert contacted == []


class _Stop(Exception):
    pass


@pytest.mark.parametrize("anchor", [True, False])
def test_provision_installs_the_anchor_into_the_executor_store_only_when_given(module, tmp_path, monkeypatch, anchor):
    path = _generator_certificate(tmp_path) if anchor else None
    commands: list[tuple[str, bytes]] = []

    def run(self, command, *, input_bytes=b"", timeout=120):
        commands.append((command, input_bytes))
        return "aarch64\n" if command == "uname -m" else ""

    def stop(*_args):
        raise _Stop  # the AWG build is outside this boundary

    monkeypatch.setattr(module, "load_live_executor", lambda *a, **k: {"profile": "vpn-liveness-fixture"})
    monkeypatch.setattr(module, "role_inputs", lambda: (["curl"], {}))
    monkeypatch.setattr(module, "ENGINES", {})
    monkeypatch.setattr(module, "awg_sources", stop)
    monkeypatch.setattr(module.Executor, "run", run)
    work = tmp_path / "work"
    work.mkdir(mode=0o700)

    with pytest.raises(_Stop):
        module.provision(tmp_path / "executor.json", work, path)

    store = "/usr/local/share/ca-certificates/ripdpi-staging-anchor.crt"
    installs = [payload for command, payload in commands if store in command]
    updates = [command for command, _ in commands if "update-ca-certificates" in command]
    apt = next(command for command, _ in commands if "apt-get install" in command)
    if anchor:
        assert len(installs) == 1 and installs[0].startswith(b"-----BEGIN CERTIFICATE-----")
        assert "chmod 0644" in next(command for command, _ in commands if store in command)
        assert updates == ["sudo -n update-ca-certificates"]
        assert "ca-certificates" in apt.split()
    else:
        assert installs == [] and updates == [] and "ca-certificates" not in apt.split()
