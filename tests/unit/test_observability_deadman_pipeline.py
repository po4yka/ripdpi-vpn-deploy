"""End-to-end contracts for the control-plane/dead-man heartbeat pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import Message
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from urllib import error, request

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROLE = ROOT / "ansible/roles/observability_control_plane"
DEADMAN_ROLE = ROOT / "ansible/roles/observability_deadman"
PIPELINE_SOURCE = CONTROL_ROLE / "files/observability-deadman-pipeline.py"
RELAY_SOURCE = CONTROL_ROLE / "files/observability-telegram-relay.py"
DEADMAN_SOURCE = DEADMAN_ROLE / "files/observability-deadman.py"
TOKEN = b"bounded-deadman-pulse-token"
NOW = 1_800_000_000
GENERATION = "a" * 40


def _module(name: str, path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _instant(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace("+00:00", "Z")


def _loopback_pulse_tls() -> dict[str, str]:
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pulse-test-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return {
        "ca_pem": ca.public_bytes(serialization.Encoding.PEM).decode(),
        "server_cert_pem": server.public_bytes(serialization.Encoding.PEM).decode(),
        "server_key_pem": server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    }


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _watchdog() -> bytes:
    return json.dumps(
        {
            "version": "4",
            "groupKey": "watchdog",
            "truncatedAlerts": 0,
            "status": "firing",
            "receiver": "deadman-canary",
            "groupLabels": {"alertname": "ObservabilityPipelineWatchdog"},
            "commonLabels": {
                "alertname": "ObservabilityPipelineWatchdog",
                "component": "observability-pipeline",
                "severity": "watchdog",
            },
            "commonAnnotations": {"source_generation": GENERATION},
            "externalURL": "",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "ObservabilityPipelineWatchdog",
                        "component": "observability-pipeline",
                        "severity": "watchdog",
                    },
                    "annotations": {"source_generation": GENERATION},
                    "startsAt": _instant(NOW - 60),
                    "endsAt": "0001-01-01T00:00:00Z",
                    "generatorURL": "",
                    "fingerprint": "b" * 16,
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _initialize_generation(pipeline, state_dir: Path, generation: str = GENERATION) -> None:  # type: ignore[no-untyped-def]
    assert pipeline.reconcile_state(state_dir, generation) is True


def test_canary_receiver_accepts_only_exact_watchdog_and_writes_private_receipt(
    tmp_path: Path,
) -> None:
    pipeline = _module("observability_deadman_pipeline", PIPELINE_SOURCE)
    receipt = tmp_path / "canary.json"
    _initialize_generation(pipeline, tmp_path)

    observed = pipeline.record_canary(receipt, _watchdog(), GENERATION, NOW)

    assert observed == {
        "schema": 1,
        "kind": "alertmanager-watchdog",
        "generation": GENERATION,
        "observed_at": NOW,
    }
    assert pipeline._read_private_json(receipt, pipeline.CANARY_FIELDS) == observed
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600

    hostile = json.loads(_watchdog())
    hostile["commonLabels"]["alertname"] = "OtherAlert"
    with pytest.raises(pipeline.PipelineError, match="invalid canary"):
        pipeline.record_canary(
            receipt, json.dumps(hostile).encode(), GENERATION, NOW + 1
        )
    assert pipeline._read_private_json(receipt, pipeline.CANARY_FIELDS) == observed


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], False),
        (["Basic fixture"], False),
        (["Bearer wrong-deadman-canary-token"], False),
        (
            [
                "Bearer bounded-deadman-canary-token",
                "Bearer bounded-deadman-canary-token",
            ],
            False,
        ),
        (["Bearer bounded-deadman-canary-token"], True),
    ],
)
def test_canary_receiver_requires_one_dedicated_bearer_authority(
    values: list[str], expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = _module("observability_deadman_pipeline_canary_auth", PIPELINE_SOURCE)
    headers = Message()
    for value in values:
        headers.add_header("Authorization", value)
    comparisons: list[tuple[str, str]] = []
    compare_digest = pipeline.hmac.compare_digest

    def observed(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return compare_digest(left, right)

    monkeypatch.setattr(pipeline.hmac, "compare_digest", observed)

    assert (
        pipeline._canary_authorized(headers, b"bounded-deadman-canary-token")
        is expected
    )
    if len(values) == 1 and values[0].startswith("Bearer "):
        assert len(comparisons) == 1
    else:
        assert comparisons == []


@pytest.mark.parametrize(
    ("mutation", "generation", "now"),
    [
        (lambda value: value.update(groupLabels={}), GENERATION, NOW),
        (lambda value: value["alerts"][0].update(extra=True), GENERATION, NOW),
        (
            lambda value: value["alerts"][0]["annotations"].update(extra="x"),
            GENERATION,
            NOW,
        ),
        (
            lambda value: value["alerts"][0].update(fingerprint="not-hex"),
            GENERATION,
            NOW,
        ),
        (lambda value: value["alerts"][0].update(startsAt="invalid"), GENERATION, NOW),
        (lambda _value: None, "a" * 41, NOW),
        (lambda _value: None, GENERATION, True),
    ],
)
def test_canary_receiver_rejects_noncanonical_payload_without_overwriting_receipt(
    tmp_path: Path, mutation, generation: str, now: int  # type: ignore[no-untyped-def]
) -> None:
    pipeline = _module("observability_deadman_pipeline_strict", PIPELINE_SOURCE)
    receipt = tmp_path / "canary.json"
    _initialize_generation(pipeline, tmp_path)
    original = pipeline.record_canary(receipt, _watchdog(), GENERATION, NOW)
    payload = json.loads(_watchdog())
    mutation(payload)

    with pytest.raises(pipeline.PipelineError, match="invalid canary"):
        pipeline.record_canary(
            receipt,
            json.dumps(payload, separators=(",", ":")).encode(),
            generation,
            now,
        )

    assert pipeline._read_private_json(receipt, pipeline.CANARY_FIELDS) == original


def test_readiness_accepts_bounded_text_body_and_rejects_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = _module("observability_deadman_pipeline_ready", PIPELINE_SOURCE)

    class Response:
        status = 200

        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self, maximum: int) -> bytes:
            return self.body[:maximum]

    bodies = iter((b"Prometheus is Ready.\n", b"x" * 4097))
    monkeypatch.setattr(
        pipeline.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(next(bodies)),
    )

    assert pipeline._ready("http://127.0.0.1:9090/-/ready", 5) is True
    assert pipeline._ready("http://127.0.0.1:19094/-/ready", 5) is False


def test_pulse_transport_disables_proxy_and_redirects_and_retries_only_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = _module("observability_deadman_pipeline_transport", PIPELINE_SOURCE)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    body = b'{"signature":"not-a-secret-fixture"}'
    attempts: list[object] = []
    handlers: list[object] = []

    class Response:
        status = 204

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self, maximum: int) -> bytes:
            assert maximum == 4097
            return b""

    class Opener:
        def open(self, outbound, timeout):  # type: ignore[no-untyped-def]
            attempts.append(outbound)
            assert timeout == 5
            assert outbound.get_header("Authorization") is None
            if len(attempts) == 1:
                raise error.URLError("transient")
            return Response()

    def build_opener(*values):  # type: ignore[no-untyped-def]
        handlers.extend(values)
        return Opener()

    monkeypatch.setattr(pipeline.request, "build_opener", build_opener)
    assert pipeline._post("https://deadman.example/v1/pulse", body, 5, context) == 204
    assert len(attempts) == 2
    assert any(
        isinstance(handler, pipeline.request.ProxyHandler) and handler.proxies == {}
        for handler in handlers
    )
    assert any(isinstance(handler, pipeline._NoRedirect) for handler in handlers)

    class RefusingOpener:
        def __init__(self, code: int) -> None:
            self.code = code
            self.calls = 0

        def open(self, outbound, timeout):  # type: ignore[no-untyped-def]
            self.calls += 1
            raise error.HTTPError(outbound.full_url, self.code, "refused", {}, None)

    redirect = RefusingOpener(302)
    monkeypatch.setattr(pipeline.request, "build_opener", lambda *_handlers: redirect)
    with pytest.raises(
        pipeline.PipelineError, match="pulse redirect refused"
    ) as failure:
        pipeline._post("https://deadman.example/v1/pulse", body, 5, context)
    assert redirect.calls == 1
    assert body.decode() not in str(failure.value)

    refused = RefusingOpener(503)
    monkeypatch.setattr(pipeline.request, "build_opener", lambda *_handlers: refused)
    assert pipeline._post("https://deadman.example/v1/pulse", body, 5, context) == 503
    assert refused.calls == 1


def test_pulse_tls_context_uses_only_the_fixed_ca_and_verifies_hostnames() -> None:
    pipeline = _module("observability_deadman_pipeline_pulse_ca", PIPELINE_SOURCE)
    tls = _loopback_pulse_tls()

    context = pipeline._pulse_tls_context(tls["ca_pem"].encode())

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    with pytest.raises(pipeline.PipelineError, match="pulse CA unavailable"):
        pipeline._pulse_tls_context(b"not a CA")


def test_state_writes_refuse_symlink_or_writable_parent(tmp_path: Path) -> None:
    pipeline = _module("observability_deadman_pipeline_paths", PIPELINE_SOURCE)
    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    redirected = tmp_path / "redirected"
    redirected.mkdir(mode=0o700)
    link = safe / "state"
    link.symlink_to(redirected, target_is_directory=True)

    with pytest.raises(pipeline.PipelineError, match="unsafe directory"):
        with pipeline._lock(link):
            pass
    os.chmod(safe, 0o777)
    with pytest.raises(pipeline.PipelineError, match="unsafe directory"):
        pipeline._atomic_json(safe / "receipt.json", {"schema": 1})

    shared = tmp_path / "textfile"
    shared.mkdir(mode=0o700)
    os.chmod(shared, 0o3775)
    with pytest.raises(pipeline.PipelineError, match="unsafe directory"):
        pipeline._atomic_bytes(shared / "unsafe.prom", b"metric 1\n", mode=0o644)
    pipeline._atomic_bytes(
        shared / "owned.prom",
        b"metric 1\n",
        mode=0o644,
        allow_sticky_parent=True,
    )
    assert (shared / "owned.prom").read_text() == "metric 1\n"


def test_pulse_requires_fresh_watchdog_and_primary_delivery_then_advances_sequence(
    tmp_path: Path,
) -> None:
    pipeline = _module("observability_deadman_pipeline_pulse", PIPELINE_SOURCE)
    _initialize_generation(pipeline, tmp_path)
    pipeline._atomic_json(
        tmp_path / "canary.json",
        {
            "schema": 1,
            "kind": "alertmanager-watchdog",
            "generation": GENERATION,
            "observed_at": NOW - 10,
        },
    )
    primary = {
        "schema": 1,
        "kind": "primary-telegram-canary",
        "generation": GENERATION,
        "attempted_at": NOW - 20,
        "successful_at": NOW - 20,
        "status": "success",
    }
    captured: list[bytes] = []

    def send(_url: str, body: bytes, _timeout: int, _context=None) -> int:
        captured.append(body)
        return 204

    result = pipeline.publish_pulse(
        state_dir=tmp_path,
        primary_status=primary,
        token=TOKEN,
        generation=GENERATION,
        deadman_url="https://deadman.example/v1/pulse",
        now=NOW,
        freshness_seconds=180,
        primary_freshness_seconds=90000,
        timeout_seconds=5,
        tls_context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        sender=send,
    )

    assert result["sequence"] == 1
    pulse = json.loads(captured[0])
    assert set(pulse) == {
        "schema",
        "generation",
        "sequence",
        "issued_at",
        "expires_at",
        "health",
        "signature",
    }
    assert pulse["health"] == {
        "prometheus": True,
        "alertmanager": True,
        "canary": True,
        "primary_telegram": True,
    }
    assert pulse["expires_at"] == _instant(NOW + 30)
    expected = hmac.new(TOKEN, pipeline._canonical(pulse), hashlib.sha256).hexdigest()
    assert pulse["signature"] == expected
    assert stat.S_IMODE((tmp_path / "pulse-state.json").stat().st_mode) == 0o600

    with pytest.raises(pipeline.PipelineError, match="pipeline unhealthy"):
        pipeline.publish_pulse(
            state_dir=tmp_path,
            primary_status={**primary, "successful_at": NOW - 90001},
            token=TOKEN,
            generation=GENERATION,
            deadman_url="https://deadman.example/v1/pulse",
            now=NOW,
            freshness_seconds=180,
            primary_freshness_seconds=90000,
            timeout_seconds=5,
            tls_context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            sender=send,
        )
    assert len(captured) == 1


def test_publish_pulse_reaches_actual_deadman_only_over_verified_loopback_tls(
    tmp_path: Path,
) -> None:
    pipeline = _module("observability_deadman_pipeline_tls", PIPELINE_SOURCE)
    deadman = _module("observability_deadman_tls", DEADMAN_SOURCE)
    tls = _loopback_pulse_tls()
    credentials = tmp_path / "credentials"
    credentials.mkdir(mode=0o700)
    for name, content in {
        "pulse-token": TOKEN,
        "telegram-bot-token": b"bounded-telegram-token-not-a-real-secret",
        "pulse-server-cert": tls["server_cert_pem"].encode(),
        "pulse-server-key": tls["server_key_pem"].encode(),
    }.items():
        path = credentials / name
        path.write_bytes(content)
        path.chmod(0o600)
    config_path = tmp_path / "deadman.json"
    config_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "pulse_path": "/v1/pulse",
                "pulse_interval_seconds": 60,
                "missed_pulse_limit": 5,
                "max_future_seconds": 30,
                "max_pulse_bytes": 4096,
                "retry_attempts": 2,
                "retry_timeout_seconds": 5,
                "reminder_interval_seconds": 3600,
                "canary_interval_seconds": 86400,
                "reverse_health_url": (
                    "https://reverse.example.test:9443/observability/v1/deadman/reverse"
                ),
                "reverse_health_max_bytes": 1024,
                "source_generation": GENERATION,
                "required_units": ["observability-deadman.service"],
                "pulse_tls": {
                    "server_name": "localhost",
                    "server_cert_credential": "pulse-server-cert",
                    "server_key_credential": "pulse-server-key",
                },
                "reverse_health_tls": {
                    "ca_credential": "reverse-health-ca",
                    "client_cert_credential": "reverse-health-client-cert",
                    "client_key_credential": "reverse-health-client-key",
                    "client_cn": "deadman-control",
                    "client_cert_fingerprint_sha256": "b" * 64,
                    "ca_fingerprint_sha256": "c" * 64,
                },
                "telegram": {"chat_id": "-100000000001", "topic_id": 7},
            }
        )
    )
    pulse_port = _free_tcp_port()
    status_port = _free_tcp_port()
    state_path = tmp_path / "deadman-state.json"
    environment = {
        **os.environ,
        "CREDENTIALS_DIRECTORY": str(credentials),
    }
    receiver = subprocess.Popen(
        [
            sys.executable,
            str(DEADMAN_SOURCE),
            "serve",
            "--config",
            str(config_path),
            "--state",
            str(state_path),
            "--listen",
            f"127.0.0.1:{pulse_port}",
            "--status-listen",
            f"127.0.0.1:{status_port}",
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                with request.urlopen(
                    f"http://127.0.0.1:{status_port}/v1/status", timeout=1
                ) as response:
                    assert response.status == 200
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

        pipeline_state = tmp_path / "pipeline"
        _initialize_generation(pipeline, pipeline_state)
        pipeline._atomic_json(
            pipeline_state / "canary.json",
            {
                "schema": 1,
                "kind": "alertmanager-watchdog",
                "generation": GENERATION,
                "observed_at": int(time.time()),
            },
        )
        current = int(time.time())
        primary = {
            "schema": 1,
            "kind": "primary-telegram-canary",
            "generation": GENERATION,
            "attempted_at": current,
            "successful_at": current,
            "status": "success",
        }
        client_context = pipeline._pulse_tls_context(tls["ca_pem"].encode())

        pulse = pipeline.publish_pulse(
            state_dir=pipeline_state,
            primary_status=primary,
            token=TOKEN,
            generation=GENERATION,
            deadman_url=f"https://localhost:{pulse_port}/v1/pulse",
            now=current,
            freshness_seconds=180,
            primary_freshness_seconds=90000,
            timeout_seconds=5,
            tls_context=client_context,
        )
        assert pulse["sequence"] == 1
        assert deadman._state(state_path)["last_sequence"] == 1

        with pytest.raises(OSError):
            request.urlopen(f"https://localhost:{pulse_port}/v1/pulse", timeout=1).read(
                1
            )
        with pytest.raises(OSError):
            request.urlopen(f"http://127.0.0.1:{pulse_port}/v1/pulse", timeout=1).read(
                1
            )
    finally:
        receiver.terminate()
        try:
            stdout, stderr = receiver.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            receiver.kill()
            stdout, stderr = receiver.communicate(timeout=5)
        assert TOKEN.decode() not in stdout + stderr


def test_generation_reconciliation_clears_only_valid_stale_pipeline_state(
    tmp_path: Path,
) -> None:
    pipeline = _module("observability_deadman_pipeline_reconcile", PIPELINE_SOURCE)
    previous = "b" * 40
    documents = {
        "generation.json": {
            "schema": 1,
            "generation": previous,
        },
        "canary.json": {
            "schema": 1,
            "kind": "alertmanager-watchdog",
            "generation": previous,
            "observed_at": NOW,
        },
        "primary-canary.json": {
            "schema": 1,
            "kind": "primary-telegram-canary",
            "generation": previous,
            "attempted_at": NOW,
            "successful_at": NOW,
            "status": "success",
        },
        "pulse-state.json": {
            "schema": 1,
            "generation": previous,
            "last_sequence": 4,
            "last_attempt": NOW,
        },
        "reverse-state.json": {
            "schema": 1,
            "generation": previous,
            "last_sequence": 7,
            "last_received": NOW,
        },
    }
    for name, document in documents.items():
        pipeline._atomic_json(tmp_path / name, document)

    assert pipeline.reconcile_state(tmp_path, GENERATION) is True
    assert pipeline._read_private_json(
        tmp_path / "generation.json", pipeline.STATE_FIELDS["generation.json"]
    ) == {"schema": 1, "generation": GENERATION}
    assert not any(
        (tmp_path / name).exists() for name in documents if name != "generation.json"
    )
    assert pipeline.reconcile_state(tmp_path, GENERATION) is False

    current = {**documents["canary.json"], "generation": GENERATION}
    pipeline._atomic_json(tmp_path / "canary.json", current)
    inode = (tmp_path / "canary.json").stat().st_ino
    assert pipeline.reconcile_state(tmp_path, GENERATION) is False
    assert (tmp_path / "canary.json").stat().st_ino == inode


def test_disable_reconcile_removes_receipts_and_allows_clean_reenable(
    tmp_path: Path,
) -> None:
    pipeline = _module("observability_deadman_pipeline_reenable", PIPELINE_SOURCE)
    _initialize_generation(pipeline, tmp_path)
    pipeline.record_canary(tmp_path / "canary.json", _watchdog(), GENERATION, NOW)

    assert pipeline.reconcile_state(tmp_path, GENERATION, disable=True) is True
    assert not (tmp_path / "canary.json").exists()
    assert pipeline.reconcile_state(tmp_path, "b" * 40) is True
    receipt = pipeline.record_canary(
        tmp_path / "canary.json",
        _watchdog().replace(GENERATION.encode(), b"b" * 40),
        "b" * 40,
        NOW,
    )
    assert receipt["generation"] == "b" * 40


def test_generation_fence_rejects_old_writers_after_reconcile(tmp_path: Path) -> None:
    pipeline = _module(
        "observability_deadman_pipeline_generation_fence", PIPELINE_SOURCE
    )
    previous = "b" * 40
    _initialize_generation(pipeline, tmp_path, previous)
    pipeline.record_canary(
        tmp_path / "canary.json",
        _watchdog().replace(GENERATION.encode(), previous.encode()),
        previous,
        NOW,
    )

    assert pipeline.reconcile_state(tmp_path, GENERATION) is True
    before = {
        path.name: (path.stat().st_ino, path.read_bytes())
        for path in tmp_path.glob("*.json")
    }
    with pytest.raises(pipeline.PipelineError, match="generation mismatch"):
        pipeline.record_canary(
            tmp_path / "canary.json",
            _watchdog().replace(GENERATION.encode(), previous.encode()),
            previous,
            NOW + 1,
        )
    assert {
        path.name: (path.stat().st_ino, path.read_bytes())
        for path in tmp_path.glob("*.json")
    } == before


def test_generation_reconciliation_refuses_mixed_or_unsafe_state(
    tmp_path: Path,
) -> None:
    pipeline = _module(
        "observability_deadman_pipeline_reconcile_unsafe", PIPELINE_SOURCE
    )
    pipeline._atomic_json(
        tmp_path / "generation.json",
        {"schema": 1, "generation": GENERATION},
    )
    pipeline._atomic_json(
        tmp_path / "canary.json",
        {
            "schema": 1,
            "kind": "alertmanager-watchdog",
            "generation": GENERATION,
            "observed_at": NOW,
        },
    )
    pipeline._atomic_json(
        tmp_path / "pulse-state.json",
        {
            "schema": 1,
            "generation": "b" * 40,
            "last_sequence": 1,
            "last_attempt": NOW,
        },
    )
    before = {
        path.name: (path.stat().st_ino, path.read_bytes())
        for path in tmp_path.glob("*.json")
    }
    with pytest.raises(pipeline.PipelineError, match="unsafe state"):
        pipeline.reconcile_state(tmp_path, GENERATION)
    assert {
        path.name: (path.stat().st_ino, path.read_bytes())
        for path in tmp_path.glob("*.json")
    } == before


def test_primary_canary_uses_real_relay_contract_and_persists_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = _module("observability_deadman_pipeline_primary", PIPELINE_SOURCE)
    relay = _module("observability_deadman_pipeline_relay", RELAY_SOURCE)
    _initialize_generation(pipeline, tmp_path)
    captured: list[bytes] = []

    class Response:
        status = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args):  # type: ignore[no-untyped-def]
            return None

        def read(self, _maximum: int) -> bytes:
            return b"{}"

    def post(outbound, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 5
        captured.append(outbound.data)
        return Response()

    class Opener:
        open = staticmethod(post)

    def primary_opener(*handlers):  # type: ignore[no-untyped-def]
        assert any(
            isinstance(handler, pipeline.request.ProxyHandler) and handler.proxies == {}
            for handler in handlers
        )
        assert any(isinstance(handler, pipeline._NoRedirect) for handler in handlers)
        return Opener()

    monkeypatch.setattr(pipeline.request, "build_opener", primary_opener)
    receipt = pipeline.send_primary_canary(
        state_dir=tmp_path,
        generation=GENERATION,
        relay_url="http://127.0.0.1:19095/alert",
        relay_token=b"a" * 64,
        now=NOW,
        timeout_seconds=5,
    )

    assert relay.parse_payload(captured[0])["receiver"] == "telegram-canary"
    assert receipt["status"] == "success"
    assert (
        pipeline._read_private_json(
            tmp_path / "primary-canary.json", pipeline.PRIMARY_FIELDS
        )
        == receipt
    )

    class FailedOpener:
        @staticmethod
        def open(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise TimeoutError()

    monkeypatch.setattr(
        pipeline.request, "build_opener", lambda *_handlers: FailedOpener()
    )
    with pytest.raises(pipeline.PipelineError, match="primary canary failed"):
        pipeline.send_primary_canary(
            state_dir=tmp_path,
            generation=GENERATION,
            relay_url="http://127.0.0.1:19095/alert",
            relay_token=b"a" * 64,
            now=NOW + 1,
            timeout_seconds=5,
        )
    failed = pipeline._read_private_json(
        tmp_path / "primary-canary.json", pipeline.PRIMARY_FIELDS
    )
    assert failed["status"] == "failed"
    assert failed["successful_at"] == 0


def test_reverse_receiver_rejects_replay_and_publishes_bounded_one_hot_metrics(
    tmp_path: Path,
) -> None:
    pipeline = _module("observability_deadman_pipeline_reverse", PIPELINE_SOURCE)
    _initialize_generation(pipeline, tmp_path)
    payload = {
        "schema": 1,
        "generation": GENERATION,
        "sequence": 7,
        "issued_at": _instant(NOW),
        "health": {
            name: "ok"
            for name in (
                "receiver",
                "delivery",
                "cpu",
                "memory",
                "disk",
                "inode",
                "clock",
                "network",
                "unit",
                "collector",
                "source",
            )
        },
    }
    payload["signature"] = hmac.new(
        TOKEN, pipeline._canonical(payload), hashlib.sha256
    ).hexdigest()
    raw = json.dumps(payload, separators=(",", ":")).encode()
    metrics = tmp_path / "deadman.prom"

    accepted = pipeline.accept_reverse(
        state_dir=tmp_path,
        metrics_path=metrics,
        raw=raw,
        token=TOKEN,
        generation=GENERATION,
        now=NOW,
        max_future_seconds=30,
    )

    assert accepted["last_sequence"] == 7
    exposition = metrics.read_text()
    assert (
        'vpn_observability_deadman_reverse_fresh{generation="'
        + GENERATION
        + '",state="fresh"} 1'
        in exposition
    )
    assert (
        'vpn_observability_deadman_health{check="cpu",generation="'
        + GENERATION
        + '",state="ok"} 1'
        in exposition
    )
    assert "deadman.example" not in exposition
    assert stat.S_IMODE(metrics.stat().st_mode) == 0o644
    with pytest.raises(pipeline.PipelineError, match="invalid reverse"):
        pipeline.accept_reverse(
            state_dir=tmp_path,
            metrics_path=metrics,
            raw=raw,
            token=TOKEN,
            generation=GENERATION,
            now=NOW + 1,
            max_future_seconds=30,
        )


def test_deadman_reverse_summary_contains_every_bounded_health_axis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deadman = _module("observability_deadman_summary", DEADMAN_SOURCE)
    monkeypatch.setattr(
        deadman,
        "_host_health",
        lambda *_args: {name: "ok" for name in deadman.HEALTH_AXES},
    )
    captured: list[dict[str, object]] = []

    def post(_config, _token, payload, _context=None):  # type: ignore[no-untyped-def]
        captured.append(payload)
        return True

    monkeypatch.setattr(deadman, "_post_reverse", post)
    current = deadman._empty_state()
    current.update(last_sequence=4, last_pulse=NOW, last_delivery="recovery")

    assert deadman._reverse_health({}, TOKEN, current, NOW) is True
    assert set(captured[0]["health"]) == {
        "receiver",
        "delivery",
        *deadman.HEALTH_AXES,
    }
    assert set(captured[0]["health"].values()) <= {
        "ok",
        "error",
        "healthy",
        "incident",
        "never",
        "firing",
        "recovery",
        "failed",
    }


def test_roles_install_pipeline_units_and_remove_them_on_disable() -> None:
    control_enable = (CONTROL_ROLE / "tasks/alerting-authority.yml").read_text()
    control_disable = (CONTROL_ROLE / "tasks/alerting-disable.yml").read_text()
    deadman_unit = (
        DEADMAN_ROLE / "templates/observability-deadman-tick.service.j2"
    ).read_text()

    for name in (
        "observability-deadman-pipeline.service",
        "observability-deadman-pulse.service",
        "observability-deadman-pulse.timer",
        "observability-primary-canary.service",
        "observability-primary-canary.timer",
    ):
        assert name in control_enable
        assert name in control_disable
    assert "reverse-health-ca" in deadman_unit
    assert "reverse-health-client-cert" in deadman_unit
    assert "reverse-health-client-key" in deadman_unit


def test_authority_quiesces_old_pipeline_generation_before_reconcile_and_restarts_in_order() -> (
    None
):
    tasks = yaml.safe_load(
        (CONTROL_ROLE / "tasks/alerting-authority.yml").read_text(encoding="utf-8")
    )
    activation = next(
        task
        for task in tasks
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    body = activation["block"]
    by_name = {task["name"]: task for task in body}
    disable_schedules = by_name["Disable previous dead-man pipeline schedules"]
    assert disable_schedules["ansible.builtin.systemd_service"] == {
        "name": "{{ item }}",
        "enabled": False,
        "state": "stopped",
    }
    assert disable_schedules["loop"] == [
        "observability-deadman-pulse.timer",
        "observability-primary-canary.timer",
    ]
    stop_workers = by_name["Stop previous dead-man pipeline workers"]
    assert stop_workers["ansible.builtin.systemd_service"] == {
        "name": "{{ item }}",
        "state": "stopped",
    }
    assert stop_workers["loop"] == [
        "observability-deadman-pulse.service",
        "observability-primary-canary.service",
        "observability-deadman-pipeline.service",
    ]
    names = [task["name"] for task in body]
    assert names.index("Disable previous dead-man pipeline schedules") < names.index(
        "Reconcile generation-bound dead-man pipeline state"
    )
    assert names.index("Stop previous dead-man pipeline workers") < names.index(
        "Reconcile generation-bound dead-man pipeline state"
    )
    assert names.index(
        "Ensure authenticated dead-man pipeline is running"
    ) < names.index("Ensure dead-man canary schedules are running")
    capture = next(
        task
        for task in tasks
        if task["name"] == "Capture previous active and enabled states"
    )
    quiesced = set(disable_schedules["loop"] + stop_workers["loop"])
    assert quiesced <= set(capture["loop"])
    reboot_state = {
        name: {"enabled": True, "active": True} for name in disable_schedules["loop"]
    }
    for name in disable_schedules["loop"]:
        reboot_state[name].update(enabled=False, active=False)
    for state in reboot_state.values():
        state["active"] = state["enabled"]
    assert all(not state["active"] for state in reboot_state.values())
    restore_block = next(
        task
        for task in activation["rescue"]
        if task["name"]
        == "Restore the captured authority and service credential snapshots"
    )["block"]
    restore = next(
        task
        for task in restore_block
        if task["name"]
        == "Restore previous service state and LoadCredential snapshots in dependency order"
    )
    assert quiesced <= set(restore["loop"])
    assert restore["ansible.builtin.systemd_service"]["enabled"] == (
        "{{ _observability_authority.services[item].enabled }}"
    )
    assert (
        "services[item].active" in restore["ansible.builtin.systemd_service"]["state"]
    )


def test_authority_failure_disables_schedules_across_reboot_before_exact_restore(
    tmp_path: Path,
) -> None:
    tasks = yaml.safe_load(
        (CONTROL_ROLE / "tasks/alerting-authority.yml").read_text(encoding="utf-8")
    )
    activation = next(
        task
        for task in tasks
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    body = {task["name"]: task for task in activation["block"]}
    restore_block = next(
        task
        for task in activation["rescue"]
        if task["name"]
        == "Restore the captured authority and service credential snapshots"
    )["block"]
    rescue = {task["name"]: task for task in restore_block}
    enable_pipeline = body["Ensure authenticated dead-man pipeline is running"]
    enable_schedules = body["Ensure dead-man canary schedules are running"]
    disable = rescue["Disable attempted dead-man persistent writers before rollback"]
    restore = rescue[
        "Restore previous service state and LoadCredential snapshots in dependency order"
    ]
    persistent_writers = [
        "observability-primary-canary.timer",
        "observability-deadman-pulse.timer",
        "observability-deadman-pipeline.service",
    ]
    assert disable["loop"] == [
        "observability-deadman-pulse.timer",
        "observability-primary-canary.timer",
        "observability-deadman-pipeline.service",
    ]
    assert disable["ansible.builtin.systemd_service"] == {
        "name": "{{ item }}",
        "enabled": False,
        "state": "stopped",
    }
    assert restore_block.index(disable) < restore_block.index(restore)

    initial = {
        persistent_writers[0]: {"enabled": True, "active": True},
        persistent_writers[1]: {"enabled": False, "active": False},
        persistent_writers[2]: {"enabled": False, "active": False},
    }
    state_path = tmp_path / "systemd.json"
    reboot_path = tmp_path / "reboot.json"
    state_path.write_text(json.dumps(initial), encoding="utf-8")
    adapter = tmp_path / "systemd-adapter.py"
    adapter.write_text(
        """import json,sys
from pathlib import Path
state_path=Path(sys.argv[1]); action=sys.argv[2]
state=json.loads(state_path.read_text())
if action=='reboot':
 for row in state.values(): row['active']=row['enabled']
 Path(sys.argv[3]).write_text(json.dumps(state))
else:
 name=sys.argv[3]; desired=sys.argv[4]; enabled=sys.argv[5].lower()
 row=state.setdefault(name,{'enabled':False,'active':False})
 if enabled in ('true','false'): row['enabled']=enabled=='true'
 if desired in ('started','restarted'): row['active']=True
 elif desired=='stopped': row['active']=False
state_path.write_text(json.dumps(state))
""",
        encoding="utf-8",
    )

    def adapt(task: dict[str, object]) -> dict[str, object]:
        adapted = json.loads(json.dumps(task))
        module = adapted.pop("ansible.builtin.systemd_service")
        adapted["ansible.builtin.command"] = {
            "argv": [
                sys.executable,
                str(adapter),
                str(state_path),
                "control",
                module["name"],
                module.get("state", "unchanged"),
                str(module.get("enabled", "unchanged")),
            ]
        }
        adapted["changed_when"] = True
        return adapted

    captured = {
        name: {
            "exists": name in initial,
            "active": initial.get(name, {}).get("active", False),
            "enabled": initial.get(name, {}).get("enabled", False),
        }
        for name in restore["loop"]
    }
    playbook = tmp_path / "rollback-schedules.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "observability_control_plane": {
                            "alerting": {"deadman": {"enabled": True}}
                        },
                        "ansible_facts": {"services": {name: {} for name in initial}},
                        "_observability_authority": {"services": captured},
                    },
                    "tasks": [
                        {
                            "block": [
                                adapt(enable_pipeline),
                                adapt(enable_schedules),
                                {
                                    "name": "Inject failure after candidate schedule enable",
                                    "ansible.builtin.fail": {"msg": "fixture-failure"},
                                },
                            ],
                            "rescue": [
                                adapt(disable),
                                {
                                    "name": "Simulate reboot before snapshot restore",
                                    "ansible.builtin.command": {
                                        "argv": [
                                            sys.executable,
                                            str(adapter),
                                            str(state_path),
                                            "reboot",
                                            str(reboot_path),
                                        ]
                                    },
                                    "changed_when": False,
                                },
                                adapt(restore),
                            ],
                        }
                    ],
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    after_reboot = json.loads(reboot_path.read_text(encoding="utf-8"))
    assert all(not after_reboot[name]["active"] for name in persistent_writers)
    assert json.loads(state_path.read_text(encoding="utf-8")) == initial


def test_nested_deadman_disable_preserves_alerting_and_is_reboot_idempotent() -> None:
    disable_tasks = CONTROL_ROLE / "tasks/alerting-deadman-disable.yml"
    alerting_tasks = yaml.safe_load(
        (CONTROL_ROLE / "tasks/alerting-authority.yml").read_text(encoding="utf-8")
    )
    activation = next(
        task
        for task in alerting_tasks
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    nested = next(
        task
        for task in activation["block"]
        if task["name"] == "Converge nested dead-man opt-out"
    )
    assert nested["ansible.builtin.include_tasks"] == "alerting-deadman-disable.yml"
    assert "not (observability_control_plane.alerting.deadman.enabled | bool)" in str(
        nested["when"]
    )
    tasks = yaml.safe_load(disable_tasks.read_text(encoding="utf-8"))
    names = {task["name"] for task in tasks}
    assert {
        "Stop and disable nested dead-man pipeline",
        "Reconcile nested dead-man state before removing its helper",
        "Remove nested dead-man pipeline surfaces",
    } <= names

    with tempfile.TemporaryDirectory(
        prefix=".observability-deadman-disable-", dir=Path.home()
    ) as directory:
        root = Path(directory)
        credentials = root / "etc/observability-control-plane/credentials"
        state_dir = root / "var/lib/observability-pipeline"
        units = root / "etc/systemd/system"
        libexec = root / "usr/local/libexec"
        metrics = root / "var/lib/node_exporter/textfile/observability-deadman.prom"
        for path, mode in (
            (credentials, 0o700),
            (state_dir, 0o700),
            (units, 0o755),
            (libexec, 0o755),
            (metrics.parent, 0o755),
        ):
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(mode)
        pipeline = _module("nested_disable_pipeline", PIPELINE_SOURCE)
        assert pipeline.reconcile_state(state_dir, GENERATION) is True
        (state_dir / "canary.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "generation": GENERATION,
                    "kind": "alertmanager-watchdog",
                    "observed_at": NOW,
                }
            ),
            encoding="utf-8",
        )
        (state_dir / "canary.json").chmod(0o600)
        surface_names = [
            "observability-deadman-pipeline.service",
            "observability-deadman-pulse.service",
            "observability-primary-canary.service",
            "observability-deadman-pulse.timer",
            "observability-primary-canary.timer",
        ]
        for name in surface_names:
            (units / name).write_text("owned\n", encoding="utf-8")
        helper = libexec / "observability-deadman-pipeline.py"
        helper.write_text(PIPELINE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        helper.chmod(0o755)
        for name in (
            "deadman-pulse-token",
            "deadman-pulse-ca.pem",
            "deadman-canary-auth-token",
        ):
            path = credentials / name
            path.write_text("private\n", encoding="utf-8")
            path.chmod(0o600)
        metrics.write_text("observability_deadman_reverse_ok 1\n", encoding="utf-8")
        metrics.chmod(0o644)
        global_unit = units / "observability-alertmanager.service"
        global_unit.write_text("global-alerting\n", encoding="utf-8")
        global_config = credentials.parent / "alertmanager-current.yml"
        global_config.write_text("global-config\n", encoding="utf-8")

        service_state = root / "service-state.json"
        service_state.write_text(
            json.dumps(
                {
                    **{
                        name: {"state": "running", "status": "enabled"}
                        for name in surface_names
                    },
                    "observability-alertmanager.service": {
                        "state": "running",
                        "status": "enabled",
                    },
                }
            ),
            encoding="utf-8",
        )
        adapter = root / "systemd-adapter.py"
        adapter.write_text(
            """import json,sys
from pathlib import Path
state_path=Path(sys.argv[1]); action=sys.argv[2]
state=json.loads(state_path.read_text())
if action=='reboot':
 for row in state.values(): row['state']='running' if row['status']=='enabled' else 'stopped'
 state_path.write_text(json.dumps(state))
else:
 name=sys.argv[3]; row=state[name]; row.update(state='stopped',status='disabled')
 state_path.write_text(json.dumps(state))
""",
            encoding="utf-8",
        )

        def rooted(value: object) -> object:
            if isinstance(value, str):
                value = value.replace(".stat.uid == 0", f".stat.uid == {os.geteuid()}")
                for prefix in ("/etc/", "/usr/local/", "/var/lib/"):
                    if value.startswith(prefix):
                        return str(root) + value
                return value
            if isinstance(value, list):
                return [rooted(item) for item in value]
            if not isinstance(value, dict):
                return value
            result = {key: rooted(item) for key, item in value.items()}
            if "ansible.builtin.service_facts" in result:
                result.pop("ansible.builtin.service_facts")
                result["ansible.builtin.set_fact"] = {
                    "ansible_facts": {
                        "services": "{{ lookup('file', '"
                        + str(service_state)
                        + "') | from_json }}"
                    }
                }
                result["changed_when"] = False
            elif "ansible.builtin.systemd_service" in result:
                module = result.pop("ansible.builtin.systemd_service")
                if "name" in module:
                    result["ansible.builtin.command"] = {
                        "argv": [
                            sys.executable,
                            str(adapter),
                            str(service_state),
                            "stop",
                            module["name"],
                        ]
                    }
                    result["changed_when"] = True
                else:
                    result["ansible.builtin.debug"] = {"msg": "reload"}
                    result["changed_when"] = False
            elif "ansible.builtin.command" in result:
                argv = result["ansible.builtin.command"]["argv"]
                if argv and str(argv[0]).endswith("observability-deadman-pipeline.py"):
                    result["ansible.builtin.command"]["argv"] = [
                        sys.executable,
                        "-c",
                        PIPELINE_SOURCE.read_text(encoding="utf-8"),
                        *argv[1:],
                    ]
            for module_name in ("ansible.builtin.file", "ansible.builtin.stat"):
                if module_name in result:
                    result[module_name].pop("owner", None)
                    result[module_name].pop("group", None)
            return result

        adapted = [rooted(task) for task in tasks]
        playbook = root / "nested-disable.yml"
        playbook.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "ansible_python_interpreter": sys.executable,
                            "observability_control_plane": {
                                "alerting": {
                                    "deadman": {
                                        "state_dir": str(state_dir),
                                        "metrics_path": str(metrics),
                                        "pulse_credential_path": str(
                                            credentials / "deadman-pulse-token"
                                        ),
                                        "pulse_ca_path": str(
                                            credentials / "deadman-pulse-ca.pem"
                                        ),
                                        "canary_auth_path": str(
                                            credentials / "deadman-canary-auth-token"
                                        ),
                                    }
                                }
                            },
                        },
                        "tasks": adapted,
                    }
                ],
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["ansible-playbook", "-i", "localhost,", str(playbook)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        first = run()
        assert first.returncode == 0, first.stdout + first.stderr
        state = json.loads(service_state.read_text(encoding="utf-8"))
        for name in surface_names:
            assert state[name] == {"state": "stopped", "status": "disabled"}
        subprocess.run(
            [sys.executable, str(adapter), str(service_state), "reboot"],
            check=True,
        )
        state = json.loads(service_state.read_text(encoding="utf-8"))
        assert all(state[name]["state"] == "stopped" for name in surface_names)
        assert state["observability-alertmanager.service"] == {
            "state": "running",
            "status": "enabled",
        }
        for path in [
            *(units / name for name in surface_names),
            helper,
            credentials / "deadman-pulse-token",
            credentials / "deadman-pulse-ca.pem",
            credentials / "deadman-canary-auth-token",
            metrics,
        ]:
            assert not path.exists()
        assert not any(state_dir.glob("*.json"))
        assert global_unit.read_text(encoding="utf-8") == "global-alerting\n"
        assert global_config.read_text(encoding="utf-8") == "global-config\n"
        first_tree = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
        second = run()
        assert second.returncode == 0, second.stdout + second.stderr
        assert (
            sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            == first_tree
        )


@pytest.mark.parametrize(
    ("generation", "expected"),
    [
        (
            {"schema": 1},
            [
                "/etc/observability-control-plane/credentials/"
                "telegram-relay-auth-token"
            ],
        ),
        (
            {
                "schema": 1,
                "relay_auth_path": (
                    "/etc/observability-control-plane/credentials/"
                    "telegram-relay-auth-token"
                ),
            },
            [
                "/etc/observability-control-plane/credentials/"
                "telegram-relay-auth-token"
            ],
        ),
    ],
)
def test_alerting_disable_resolves_partial_generation_paths_without_writes(
    tmp_path: Path, generation: dict[str, object], expected: list[str]
) -> None:
    tasks = yaml.safe_load(
        (CONTROL_ROLE / "tasks/alerting-disable.yml").read_text(encoding="utf-8")
    )
    resolver = next(
        task
        for task in tasks
        if task["name"] == "Resolve current and retained relay credential paths"
    )
    playbook = tmp_path / "disable-paths.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "observability_control_plane": {
                            "alerting": {
                                "telegram": {
                                    "relay_auth_path": (
                                        "/etc/observability-control-plane/credentials/"
                                        "telegram-relay-auth-token"
                                    )
                                }
                            }
                        },
                        "observability_control_plane_alerting_generation": generation,
                    },
                    "tasks": [
                        resolver,
                        {
                            "ansible.builtin.assert": {
                                "that": [
                                    "_observability_disabled_relay_auth_paths == expected"
                                ]
                            },
                            "vars": {"expected": expected},
                        },
                    ],
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "changed=0" in completed.stdout
