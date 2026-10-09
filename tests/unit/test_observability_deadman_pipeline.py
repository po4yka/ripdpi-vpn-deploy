"""End-to-end contracts for the control-plane/dead-man heartbeat pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from collections.abc import Generator
from email.message import Message
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import shutil
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
AUTHORITY_SOURCE = CONTROL_ROLE / "files/observability-authority-snapshot.py"
RELAY_SOURCE = CONTROL_ROLE / "files/observability-telegram-relay.py"
DEADMAN_SOURCE = DEADMAN_ROLE / "files/observability-deadman.py"
TOKEN = b"bounded-deadman-pulse-token"
NOW = 1_800_000_000
GENERATION = "a" * 40


@pytest.fixture
def tmp_path() -> Generator[Path, None, None]:
    """Use a trusted owner-only root for positive pipeline fixtures.

    The pipeline correctly refuses a world-writable ancestor such as CI's
    ``/tmp``.  Negative cases below create unsafe descendants explicitly.
    """
    directory = Path(
        tempfile.mkdtemp(prefix=".observability-pipeline-", dir=Path.home())
    )
    directory.chmod(0o700)
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def _module(name: str, path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_mode(path: Path, mode: int) -> None:
    subprocess.run(["chmod", f"{mode:o}", str(path)], check=True, timeout=5)


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
    _set_mode(safe, 0o777)
    with pytest.raises(pipeline.PipelineError, match="unsafe directory"):
        pipeline._atomic_json(safe / "receipt.json", {"schema": 1})

    shared = tmp_path / "textfile"
    shared.mkdir(mode=0o700)
    _set_mode(shared, 0o3775)
    with pytest.raises(pipeline.PipelineError, match="unsafe directory"):
        pipeline._atomic_bytes(shared / "unsafe.prom", b"metric 1\n", mode=0o644)
    pipeline._atomic_bytes(
        shared / "owned.prom",
        b"metric 1\n",
        mode=0o644,
        allow_sticky_parent=True,
    )
    assert (shared / "owned.prom").read_text() == "metric 1\n"


def test_atomic_public_write_stays_private_until_content_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = _module("observability_deadman_pipeline_atomic_mode", PIPELINE_SOURCE)
    parent = tmp_path / "state"
    parent.mkdir(mode=0o700)
    observed_modes: list[int] = []
    real_write = pipeline.os.write

    def write(descriptor: int, content: bytes) -> int:
        observed_modes.append(stat.S_IMODE(os.fstat(descriptor).st_mode))
        return real_write(descriptor, content)

    monkeypatch.setattr(pipeline.os, "write", write)
    target = parent / "public.prom"
    pipeline._atomic_bytes(target, b"metric 1\n", mode=0o644)

    assert observed_modes == [0o600]
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert not list(parent.glob(".pipeline-*"))


def test_lock_open_failure_closes_the_trusted_parent_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = _module("observability_deadman_pipeline_lock_open", PIPELINE_SOURCE)
    state_dir = tmp_path / "state"
    state_dir.mkdir(mode=0o700)
    real_open = pipeline.os.open
    opened: list[int] = []

    def open_path(path, flags, mode=0o777, *, dir_fd=None):  # type: ignore[no-untyped-def]
        if path == ".pipeline.lock":
            raise OSError("injected lock open failure")
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(pipeline.os, "open", open_path)
    with pytest.raises(OSError, match="injected lock open failure"):
        with pipeline._lock(state_dir):
            pass

    assert opened
    with pytest.raises(OSError):
        os.fstat(opened[-1])


def test_authority_snapshot_accepts_only_the_owned_sticky_textfile_parent(
    tmp_path: Path,
) -> None:
    authority = _module("observability_authority_snapshot_textfile", AUTHORITY_SOURCE)
    root = tmp_path / "root"
    textfile = root / "var/lib/node_exporter/textfile"
    textfile.mkdir(parents=True, mode=0o700)
    _set_mode(textfile, 0o3775)
    snapshot = authority.Snapshot(root)

    assert snapshot.read(authority.DEADMAN_METRIC, allow_missing=True) == {
        "kind": "absent"
    }
    metric = root / authority.DEADMAN_METRIC
    metric.write_text("metric 1\n")
    _set_mode(metric, 0o644)
    assert snapshot.read(authority.DEADMAN_METRIC)["kind"] == "file"

    _set_mode(textfile, 0o0775)
    with pytest.raises(ValueError, match="unsafe-parent"):
        snapshot.read(authority.DEADMAN_METRIC)


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
    current = deadman._empty_state(GENERATION)
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


def test_current_collector_does_not_install_retired_pipeline_units() -> None:
    authority = (CONTROL_ROLE / "tasks/alerting-authority.yml").read_text()
    for name in (
        "observability-deadman-pipeline.service",
        "observability-deadman-pulse.service",
        "observability-deadman-pulse.timer",
        "observability-primary-canary.service",
        "observability-primary-canary.timer",
    ):
        assert name not in authority
        assert not (CONTROL_ROLE / "templates" / (name + ".j2")).exists()


def test_historical_alarm_route_is_refused_before_runtime_mutation() -> None:
    tasks = yaml.safe_load((CONTROL_ROLE / "tasks/enable.yml").read_text())
    names = [task["name"] for task in tasks]
    probe = next(task for task in tasks if task["name"].startswith("Inspect historical alarm services"))
    guard = next(task for task in tasks if task["name"].startswith("Preserve any working historical alarm"))
    assert probe["ansible.builtin.command"]["argv"] == ["systemctl", "is-active", "--quiet", "{{ item }}"]
    assert probe["loop"] == [
        "observability-deadman-pipeline.service",
        "observability-deadman-pulse.timer",
        "observability-primary-canary.timer",
    ]
    assert probe["check_mode"] is False
    assert guard["ansible.builtin.assert"]["that"] == ["item.rc != 0"]
    mutators = ("ansible.builtin.apt", "ansible.builtin.copy", "ansible.builtin.file",
                "ansible.builtin.template", "ansible.builtin.user", "ansible.builtin.systemd_service")
    first_mutation = next(index for index, task in enumerate(tasks) if any(key in task for key in mutators))
    assert names.index(guard["name"]) < first_mutation


def test_authority_snapshot_restores_only_current_authority_chain() -> None:
    tasks = yaml.safe_load((CONTROL_ROLE / "tasks/alerting-authority.yml").read_text())
    capture = next(task for task in tasks if task["name"] == "Capture previous active and enabled states")
    expected = [
        "observability-alertmanager.service",
        "observability-telegram-relay.service",
        "observability-silence-gateway.service",
        "observability-prometheus.service",
    ]
    assert capture["loop"] == expected
    activation = next(task for task in tasks if task["name"] == "Activate validated Alertmanager generation with rollback")
    restore_block = next(task["block"] for task in activation["rescue"]
                         if task["name"] == "Restore the captured authority and service credential snapshots")
    restore = next(task for task in restore_block
                   if task["name"] == "Restore previous service state and LoadCredential snapshots in dependency order")
    assert set(restore["loop"]) == set(expected)
    assert restore["ansible.builtin.systemd_service"]["enabled"] == "{{ _observability_authority.services[item].enabled }}"
    assert "services[item].active" in restore["ansible.builtin.systemd_service"]["state"]


def test_collector_disable_scopes_kuma_producers_without_erasing_legacy_credentials() -> None:
    tasks = yaml.safe_load((CONTROL_ROLE / "tasks/disable.yml").read_text())
    tasks += yaml.safe_load((CONTROL_ROLE / "tasks/alerting-disable.yml").read_text())
    producer = next(task for task in tasks if task.get("ansible.builtin.include_role", {}).get("tasks_from") == "producers-disable")
    assert producer["ansible.builtin.include_role"]["name"] == "observability_kuma"
    assert producer["vars"]["observability_push_disable_kinds"] == ["pipeline", "delivery"]
    removed = [item for task in tasks if task.get("ansible.builtin.file", {}).get("state") == "absent"
               for item in task.get("loop", [])]
    assert not any("deadman" in item for item in removed)
    assert not (CONTROL_ROLE / "tasks/alerting-deadman-disable.yml").exists()


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
