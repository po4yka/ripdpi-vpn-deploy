"""Exact released Realm parser and authenticated rendezvous on loopback TLS."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
import http.client
import io
import json
from pathlib import Path
import platform
import socket
import ssl
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest
from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.14.0-alpha.22"
PINS = {
    "aarch64": (
        "arm64",
        "5e87ab6c47d4040a50da0f7a714a42e6e63d7bce4c6dd1f810f5a587e858fb74",
    ),
    "x86_64": (
        "amd64",
        "ff1153696fd382a9922abbb7621e8659d3dd12b6fa9077c7e6994bb181889da3",
    ),
}


@pytest.mark.native_runtime
def test_exact_realm_pin_accepts_supported_config_and_authenticated_rendezvous(
    tmp_path,
    pytestconfig,
):
    assert sys.platform == "linux", "exact Realm runtime requires disposable Linux"
    arch, checksum = PINS[platform.machine()]
    filename = f"sing-box-{VERSION}-linux-{arch}"
    cache = Path(str(pytestconfig.cache.makedir("realm_artifacts"))) / (
        filename + ".tar.gz"
    )
    if cache.exists():
        archive = cache.read_bytes()
    else:
        try:
            with urlopen(
                f"https://github.com/SagerNet/sing-box/releases/download/v{VERSION}/{filename}.tar.gz",
                timeout=30,
            ) as response:
                archive = response.read(40_000_001)
        except Exception:
            raise AssertionError("exact Realm artifact retrieval failed") from None
        assert (
            len(archive) <= 40_000_000
        ), "Realm artifact exceeds its bounded archive size"
        assert hashlib.sha256(archive).hexdigest() == checksum
        cache.write_bytes(archive)
    assert hashlib.sha256(archive).hexdigest() == checksum
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        executable = bundle.extractfile(filename + "/sing-box").read()
    binary = tmp_path / "sing-box"
    binary.write_bytes(executable)
    binary.chmod(0o755)
    version = subprocess.run(
        [str(binary), "version"], capture_output=True, text=True, timeout=5
    )
    assert version.returncode == 0 and VERSION in version.stdout

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "tls.crt", tmp_path / "tls.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    variables = merge_render_vars()
    variables["hysteria_realm"].update(
        config_dir=str(tmp_path),
        log_dir=str(tmp_path),
        listen_addr="127.0.0.1",
        listen_port=port,
        tls_cert_path=str(cert_path),
        tls_key_path=str(key_path),
        sni="localhost",
        max_realms=2,
    )
    token = "synthetic-realm-native-authority"
    variables["hysteria_realm_secrets"]["auth_token"] = token
    configuration = tmp_path / "realm.json"
    configuration.write_text(
        render_template(
            ROOT / "ansible/roles/hysteria-realm/templates/config.json.j2", variables
        )
    )
    checked = subprocess.run(
        [str(binary), "check", "-c", str(configuration)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert checked.returncode == 0, checked.stderr
    context = ssl.create_default_context(cafile=str(cert_path))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["http/1.1"])

    def request(method, route, authorization, payload=None):
        connection = http.client.HTTPSConnection(
            "localhost", port, context=context, timeout=5
        )
        try:
            headers = {
                "Authorization": "Bearer " + authorization,
                "Content-Type": "application/json",
            }
            connection.request(
                method,
                route,
                body=json.dumps(payload).encode() if payload is not None else None,
                headers=headers,
            )
            response = connection.getresponse()
            status, body = response.status, response.read(4097)
            assert len(body) <= 4096
            return status, json.loads(body) if body else None
        finally:
            connection.close()

    process = subprocess.Popen(
        [str(binary), "run", "-c", str(configuration)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    stream = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.02)
        assert process.poll() is None
        addresses = ["127.0.0.1:41001"]
        refused, _ = request(
            "POST",
            "/v1/realm-a/",
            "wrong-synthetic-authority",
            {"addresses": addresses},
        )
        assert refused == 401
        registered, session = request(
            "POST", "/v1/realm-a/", token, {"addresses": addresses}
        )
        assert registered == 200 and len(session["session_id"]) == 32
        session_token = session["session_id"]
        heartbeat, renewal = request("POST", "/v1/realm-a/heartbeat", session_token)
        assert heartbeat == 200 and renewal == {"ttl": 60}
        second, _ = request("POST", "/v1/realm-b/", token, {"addresses": addresses})
        assert second == 200
        limited, _ = request("POST", "/v1/realm-c/", token, {"addresses": addresses})
        assert limited == 429
        stream = http.client.HTTPSConnection(
            "localhost", port, context=context, timeout=5
        )
        stream.request(
            "GET",
            "/v1/realm-a/events",
            headers={"Authorization": "Bearer " + session_token},
        )
        events = stream.getresponse()
        assert events.status == 200
        assert events.readline(4097) == b"event: heartbeat_ack\n"
        assert json.loads(events.readline(4097)[6:]) == {"ttl": 60}
        assert events.readline(4097) == b"\n"
        nonce, obfs = "1" * 32, "2" * 64
        with ThreadPoolExecutor(max_workers=1) as executor:
            connection = executor.submit(
                request,
                "POST",
                "/v1/realm-a/connect",
                token,
                {"addresses": ["127.0.0.1:41002"], "nonce": nonce, "obfs": obfs},
            )
            assert events.readline(4097) == b"event: punch\n"
            message = events.readline(4097)
            assert message.startswith(b"data: ") and len(message) <= 4096
            event = json.loads(message[6:])
            assert event == {
                "addresses": ["127.0.0.1:41002"],
                "nonce": nonce,
                "obfs": obfs,
            }
            assert events.readline(4097) == b"\n"
            acknowledged, _ = request(
                "POST",
                "/v1/realm-a/connects/" + nonce,
                session_token,
                {"addresses": addresses},
            )
            assert acknowledged == 204
            connected, result = connection.result(timeout=5)
            assert connected == 200 and result == {
                "addresses": addresses,
                "nonce": nonce,
                "obfs": obfs,
            }
        deleted, _ = request("DELETE", "/v1/realm-a/", session_token)
        assert deleted == 204
    finally:
        if stream is not None:
            stream.close()
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
