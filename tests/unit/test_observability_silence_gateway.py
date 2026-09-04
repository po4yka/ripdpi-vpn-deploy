"""Gateway HTTP behavior; the TLS upstream is a fixture, not real Alertmanager C13."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

ROLE = Path(__file__).resolve().parents[2] / "ansible/roles/observability_control_plane"
OWNER_TOKEN = "a1" * 32
SENDER_TOKEN = "b2" * 32
SILENCE_ID = "12345678-1234-4234-8234-123456789012"
NOW = 1_700_000_000


def _tls(tmp_path: Path):
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture-backend-ca")])
    now = datetime.now(UTC)
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    (tmp_path / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for purpose, eku in [
        ("server", ExtendedKeyUsageOID.SERVER_AUTH),
        ("client", ExtendedKeyUsageOID.CLIENT_AUTH),
    ]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, purpose)]))
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        (tmp_path / (purpose + ".pem")).write_bytes(
            cert.public_bytes(serialization.Encoding.PEM)
        )
        (tmp_path / (purpose + ".key")).write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = ssl.TLSVersion.TLSv1_2
    server.load_cert_chain(tmp_path / "server.pem", tmp_path / "server.key")
    server.load_verify_locations(tmp_path / "ca.pem")
    server.verify_mode = ssl.CERT_REQUIRED
    client = ssl.create_default_context(cafile=str(tmp_path / "ca.pem"))
    client.load_cert_chain(tmp_path / "client.pem", tmp_path / "client.key")
    return server, client


@contextmanager
def _running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.fixture
def clock():
    return [NOW]


@pytest.fixture
def journal_fault():
    return set()


@pytest.fixture
def gateway(tmp_path, clock, journal_fault):
    spec = importlib.util.spec_from_file_location(
        "silence_gateway", ROLE / "files/observability-silence-gateway.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.command, self.path, body))
            payload = json.dumps({"silenceID": SILENCE_ID}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            calls.append((self.command, self.path, None))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"backend":"ready"}')

        def do_DELETE(self):
            calls.append((self.command, self.path, None))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args):
            pass

    server_tls, client_tls = _tls(tmp_path)
    upstream = HTTPServer(("127.0.0.1", 0), Upstream)
    upstream.socket = server_tls.wrap_socket(upstream.socket, server_side=True)
    auth = {
        "schema_version": 1,
        "owners": [
            {
                "owner": "operator-a",
                "token_sha256": hashlib.sha256(OWNER_TOKEN.encode()).hexdigest(),
            },
            {
                "owner": "operator-b",
                "token_sha256": hashlib.sha256(("d4" * 32).encode()).hexdigest(),
            },
        ],
        "sender_token_sha256": hashlib.sha256(SENDER_TOKEN.encode()).hexdigest(),
    }
    policy = {"schema_version": 1, "environment": "staging", "max_ttl_seconds": 14400}
    backend = module.AlertmanagerBackend(
        f"https://127.0.0.1:{upstream.server_port}", client_tls
    )
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    server = module.GatewayServer(
        ("127.0.0.1", 0), policy, auth, backend, state, clock=lambda: clock[0]
    )
    append = server.journal.append

    def injected_append(action, result, owner, **kwargs):
        if result in journal_fault:
            raise module.GatewayError("audit-unavailable")
        return append(action, result, owner, **kwargs)

    server.journal.append = injected_append
    with _running(upstream), _running(server):
        yield f"http://127.0.0.1:{server.server_port}", calls


def _request(url, body, token=OWNER_TOKEN, method="POST", path="/v1/silences"):
    request = Request(
        url + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def _silence():
    return {
        "schema_version": 1,
        "reason": "planned-maintenance",
        "starts_at": "2023-11-14T22:13:20Z",
        "ends_at": "2023-11-14T23:13:20Z",
        "matchers": {"environment": "staging", "node": "node-a"},
    }


def test_startup_refusal_logs_only_the_fixed_gateway_category(monkeypatch):
    result = subprocess.run(
        [sys.executable, str(ROLE / "files/observability-silence-gateway.py")],
        env={**os.environ, "CREDENTIALS_DIRECTORY": ""},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "silence-gateway: credential-directory\n"

    spec = importlib.util.spec_from_file_location(
        "silence_gateway_startup", ROLE / "files/observability-silence-gateway.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv(
        "CREDENTIALS_DIRECTORY",
        "/run/credentials/observability-silence-gateway.service",
    )

    monkeypatch.setattr(module, "private_bytes", lambda *_args: b"fixture-ca")

    def unavailable_context(**kwargs):
        assert kwargs == {"cadata": "fixture-ca"}
        raise OSError("fixture detail must not cross the category boundary")

    monkeypatch.setattr(module.ssl, "create_default_context", unavailable_context)
    with pytest.raises(module.GatewayError, match="^backend-ca$"):
        module.main()

    class RefusingContext:
        minimum_version = None

        def load_cert_chain(self, *_args):
            raise OSError("fixture detail must not cross the category boundary")

    monkeypatch.setattr(
        module.ssl, "create_default_context", lambda **_kwargs: RefusingContext()
    )
    with pytest.raises(module.GatewayError, match="^backend-client-identity$"):
        module.main()


def test_authenticated_finite_silence_reaches_backend_with_derived_owner(gateway):
    url, calls = gateway
    status, result = _request(url, _silence())
    assert status == 201
    assert result == {"silence_id": SILENCE_ID}
    assert calls == [
        (
            "POST",
            "/api/v2/silences",
            {
                "createdBy": "operator-a",
                "comment": "planned-maintenance",
                "startsAt": "2023-11-14T22:13:20Z",
                "endsAt": "2023-11-14T23:13:20Z",
                "matchers": [
                    {
                        "name": "environment",
                        "value": "staging",
                        "isRegex": False,
                        "isEqual": True,
                    },
                    {
                        "name": "node",
                        "value": "node-a",
                        "isRegex": False,
                        "isEqual": True,
                    },
                ],
            },
        )
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"owner": "forged-owner"},
        {"matchers": {}},
        {"matchers": {"environment": "staging"}},
        {"matchers": {"environment": "production", "node": "node-a"}},
        {"matchers": {"environment": "staging", "node": ".*"}},
        {
            "matchers": {
                "environment": "staging",
                "node": "node-a",
                "endpoint": "secret",
            }
        },
        {"matchers": [{"name": "node", "value": "node-a", "isRegex": True}]},
        {"reason": ""},
        {"reason": "https://private.example/secret"},
        {"ends_at": "2023-11-15T03:13:20Z"},
        {"ends_at": "2023-11-14T22:13:20Z"},
        {"starts_at": "2023-11-13T22:13:20Z"},
        {"schema_version": True},
    ],
)
def test_invalid_silence_is_rejected_before_any_backend_write(gateway, change):
    url, calls = gateway
    request = {**_silence(), **change}
    status, result = _request(url, request)
    assert status == 400
    assert calls == []
    assert set(result) == {"error"}


def test_unknown_token_cannot_submit_a_silence(gateway):
    url, calls = gateway
    assert _request(url, _silence(), token="c3" * 32)[0] == 401
    assert calls == []


@pytest.mark.parametrize(
    "method,path,token,expected",
    [
        ("GET", "/-/ready", SENDER_TOKEN, 200),
        ("GET", "/metrics", SENDER_TOKEN, 200),
        ("GET", "/api/v2/alerts", OWNER_TOKEN, 200),
        ("POST", "/api/v2/alerts", SENDER_TOKEN, 200),
        ("POST", "/api/v2/alerts", OWNER_TOKEN, 200),
        ("GET", "/api/v2/alerts", SENDER_TOKEN, 403),
        ("POST", "/v1/silences", SENDER_TOKEN, 403),
        ("POST", "/api/v2/silences", OWNER_TOKEN, 403),
        ("GET", "/api/v2/silences", OWNER_TOKEN, 403),
        ("DELETE", "/api/v2/silence/" + SILENCE_ID, OWNER_TOKEN, 403),
        ("POST", "/api/v2/alerts?next=/api/v2/silences", OWNER_TOKEN, 403),
    ],
)
def test_authenticated_roles_have_only_fixed_routes(
    gateway, method, path, token, expected
):
    url, calls = gateway
    status, _ = _request(url, [] if method == "POST" else None, token, method, path)
    assert status == expected
    assert bool(calls) is (expected == 200)


def test_only_creator_can_delete_and_audit_excludes_credentials(gateway, tmp_path):
    url, calls = gateway
    assert _request(url, _silence())[0] == 201
    assert (
        _request(url, None, "d4" * 32, "DELETE", "/v1/silences/" + SILENCE_ID)[0] == 403
    )
    assert len(calls) == 1
    assert _request(url, None, OWNER_TOKEN, "DELETE", "/v1/silences/" + SILENCE_ID) == (
        200,
        {"silence_id": SILENCE_ID, "deleted": True},
    )
    assert calls[-1] == ("DELETE", "/api/v2/silence/" + SILENCE_ID, None)
    artifact = (tmp_path / "state/silences.json").read_text()
    audit = json.loads(artifact)["audit"]
    assert [("create", "created"), ("delete", "deleted")] == [
        (item["action"], item["result"])
        for item in audit
        if item["result"] in {"created", "deleted"}
    ]
    assert all(
        token not in artifact for token in [OWNER_TOKEN, SENDER_TOKEN, "d4" * 32]
    )
    assert "Authorization" not in artifact


def test_expiry_is_audited_without_touching_source_alerts(gateway, tmp_path, clock):
    url, calls = gateway
    assert _request(url, _silence())[0] == 201
    clock[0] = NOW + 3601
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        artifact = json.loads((tmp_path / "state/silences.json").read_text())
        if any(row["action"] == "expiry" for row in artifact["audit"]):
            break
        time.sleep(0.02)
    assert artifact["silences"] == {}
    assert [(row["action"], row["result"]) for row in artifact["audit"]][-1] == (
        "expiry",
        "elapsed",
    )
    assert len(calls) == 1  # No alert resolve/update or expiry HTTP call.


def test_duplicate_scope_json_is_rejected_before_backend(gateway):
    url, calls = gateway
    body = json.dumps(_silence()).replace(
        '"node": "node-a"', '"node": "node-a", "node": "node-b"'
    )
    request = Request(
        url + "/v1/silences",
        data=body.encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + OWNER_TOKEN,
        },
    )
    with pytest.raises(HTTPError) as caught:
        urlopen(request, timeout=3)
    assert caught.value.code == 400
    assert json.load(caught.value) == {"error": "duplicate-json-key"}
    assert calls == []


def test_backend_certificate_contract_rejects_ingestion_authority_and_wrong_key(
    tmp_path,
):
    spec = importlib.util.spec_from_file_location(
        "silence_backend_preflight", ROLE / "files/validate-silence-backend.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _tls(tmp_path)
    gateway = {
        "backend_ca_pem": (tmp_path / "ca.pem").read_text(),
        "backend_server_cert_pem": (tmp_path / "server.pem").read_text(),
        "backend_server_key_pem": (tmp_path / "server.key").read_text(),
        "backend_client_cert_pem": (tmp_path / "client.pem").read_text(),
        "backend_client_key_pem": (tmp_path / "client.key").read_text(),
    }
    contract = {
        "alerting": {"silence_gateway": gateway},
        "tls": {"client_ca_pem": gateway["backend_ca_pem"]},
    }
    with pytest.raises(ValueError, match="dedicated-ca"):
        module.validate(contract)
    _tls(tmp_path)
    contract["tls"]["client_ca_pem"] = (tmp_path / "ca.pem").read_text()
    module.validate(contract)
    original_ca = gateway["backend_ca_pem"]
    gateway["backend_ca_pem"] += contract["tls"]["client_ca_pem"]
    with pytest.raises(ValueError, match="backend-single-ca"):
        module.validate(contract)
    gateway["backend_ca_pem"] = original_ca + gateway["backend_client_key_pem"]
    with pytest.raises(ValueError, match="backend-ca-content"):
        module.validate(contract)
    gateway["backend_ca_pem"] = original_ca
    gateway["backend_client_key_pem"] = gateway["backend_server_key_pem"]
    with pytest.raises(ValueError, match="key-separation"):
        module.validate(contract)


def test_backend_acceptance_then_audit_failure_never_reports_success(
    gateway, journal_fault, tmp_path
):
    url, calls = gateway
    journal_fault.add("created")
    status, response = _request(url, _silence())
    assert status >= 400
    assert response == {"error": "audit-unavailable"}
    assert [(method, path) for method, path, _ in calls] == [
        ("POST", "/api/v2/silences")
    ]
    state = json.loads((tmp_path / "state/silences.json").read_text())
    assert [row["result"] for row in state["audit"]] == ["attempt", "audit-unavailable"]
    assert state["silences"] == {}
