"""Focused contracts for the independent dead-man receiver and role surface."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import io
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import threading
from urllib import error
from urllib import request
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest
import yaml

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_deadman"
SOURCE = ROLE / "files/observability-deadman.py"
SPEC = importlib.util.spec_from_file_location("observability_deadman", SOURCE)
assert SPEC is not None and SPEC.loader is not None
deadman = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deadman)

TOKEN = b"deadman-test-token-which-is-never-rendered"
NOW = 1_700_000_000


def config() -> dict[str, object]:
    return {
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
        "source_generation": "a" * 40,
        "required_units": ["observability-deadman.service"],
        "reverse_health_tls": {
            "ca_credential": "reverse-health-ca",
            "client_cert_credential": "reverse-health-client-cert",
            "client_key_credential": "reverse-health-client-key",
            "client_cn": "deadman-control",
            "client_cert_fingerprint_sha256": "b" * 64,
            "ca_fingerprint_sha256": "c" * 64,
        },
        "pulse_tls": {
            "server_name": "deadman.example.test",
            "server_cert_credential": "pulse-server-cert",
            "server_key_credential": "pulse-server-key",
        },
        "telegram": {"chat_id": "-100000000001", "topic_id": 7},
    }


def instant(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace("+00:00", "Z")


def pulse(*, sequence: int = 1, issued: int = NOW - 1, expiry: int = NOW + 20) -> bytes:
    payload: dict[str, object] = {
        "schema": 1,
        "generation": "a" * 40,
        "sequence": sequence,
        "issued_at": instant(issued),
        "expires_at": instant(expiry),
        "health": {
            "prometheus": True,
            "alertmanager": True,
            "canary": True,
            "primary_telegram": True,
        },
    }
    payload["signature"] = hmac.new(
        TOKEN, deadman._canonical(payload), hashlib.sha256
    ).hexdigest()
    return json.dumps(payload, separators=(",", ":")).encode()


def state() -> dict[str, object]:
    return deadman._empty_state()


def _reverse_health_tls() -> dict[str, str]:
    """Build a disposable mTLS identity matching the controller identity contract."""
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "deadman-fixture-ca")])
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
    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "deadman-control")])
        )
        .issuer_name(ca_name)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return {
        "ca_pem": ca.public_bytes(serialization.Encoding.PEM).decode(),
        "client_cert_pem": client.public_bytes(serialization.Encoding.PEM).decode(),
        "client_key_pem": client_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        "ca_fingerprint_sha256": ca.fingerprint(hashes.SHA256()).hex(),
        "client_cert_fingerprint_sha256": client.fingerprint(hashes.SHA256()).hex(),
        "client_cn": "deadman-control",
        "ca_credential": "reverse-health-ca",
        "client_cert_credential": "reverse-health-client-cert",
        "client_key_credential": "reverse-health-client-key",
    }


def _pulse_tls(
    *,
    purpose: x509.ObjectIdentifier = ExtendedKeyUsageOID.SERVER_AUTH,
    expired: bool = False,
) -> dict[str, str]:
    """Build a disposable TLS server identity for loopback-only transport tests."""
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pulse-fixture-ca")])
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
        .not_valid_before(
            now - timedelta(days=2) if expired else now - timedelta(minutes=1)
        )
        .not_valid_after(
            now - timedelta(days=1) if expired else now + timedelta(days=1)
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .add_extension(x509.ExtendedKeyUsage([purpose]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
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
        "server_name": "localhost",
        "server_cert_credential": "pulse-server-cert",
        "server_key_credential": "pulse-server-key",
    }


def test_defaults_are_inert_and_keep_status_loopback_only() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_deadman"
    ]
    assert defaults["enabled"] is False
    assert defaults["pulse_listen"] == "0.0.0.0:9444"
    assert defaults["status_listen"] == "127.0.0.1:19094"
    assert defaults["missed_pulse_limit"] == 5
    assert defaults["retry_attempts"] == 2
    assert defaults["max_future_seconds"] == 30


def test_dedicated_playbook_targets_only_the_deadman_inventory_group() -> None:
    playbook = yaml.safe_load(
        (ROOT / "ansible/playbooks/observability-deadman.yml").read_text()
    )

    assert len(playbook) == 1
    assert playbook[0]["hosts"] == "vpn-observability-deadman"
    assert playbook[0]["serial"] == 1
    assert playbook[0]["any_errors_fatal"] is True
    assert playbook[0]["roles"] == [{"role": "observability_deadman"}]


def test_valid_pulse_advances_state_without_exposing_token() -> None:
    accepted = deadman.accept_pulse(pulse(), TOKEN, state(), config(), NOW)
    assert accepted["last_sequence"] == 1
    assert accepted["last_pulse"] == NOW
    assert TOKEN.decode() not in repr(accepted)


def test_signed_unhealthy_pulse_fails_closed_without_resetting_incident() -> None:
    current = state()
    current.update(
        last_sequence=7,
        last_expiry=NOW + 10,
        last_pulse=NOW - 300,
        incident=True,
        last_delivery="firing",
    )
    raw = json.loads(pulse(sequence=8))
    raw["health"]["canary"] = False
    raw["signature"] = hmac.new(
        TOKEN, deadman._canonical(raw), hashlib.sha256
    ).hexdigest()
    with pytest.raises(deadman.DeadmanError, match="unhealthy pulse"):
        deadman.accept_pulse(
            json.dumps(raw, separators=(",", ":")).encode(),
            TOKEN,
            current,
            config(),
            NOW,
        )
    assert current["last_sequence"] == 7
    assert current["last_pulse"] == NOW - 300
    assert current["incident"] is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.replace(b'"sequence":1', b'"sequence":0'),
        lambda raw: raw.replace(b'"expires_at":"', b'"expires_at":"not-a-time'),
        lambda raw: raw[:-1] + b"0",
    ],
)
def test_invalid_or_replayed_pulse_fails_closed(mutate) -> None:  # type: ignore[no-untyped-def]
    previous = state()
    previous.update(last_sequence=1, last_expiry=NOW + 10, last_pulse=NOW - 5)
    with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
        deadman.accept_pulse(mutate(pulse()), TOKEN, previous, config(), NOW)
    assert previous["last_sequence"] == 1


def test_future_and_expired_pulses_fail_closed() -> None:
    for raw in (
        pulse(issued=NOW + 31, expiry=NOW + 32),
        pulse(issued=NOW - 30, expiry=NOW),
    ):
        with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
            deadman.accept_pulse(raw, TOKEN, state(), config(), NOW)


def test_control_pipeline_pulse_expiry_accepts_thirty_seconds_but_not_thirty_one() -> (
    None
):
    candidate = config()

    accepted = deadman.accept_pulse(
        pulse(expiry=NOW + 30), TOKEN, state(), candidate, NOW
    )
    assert accepted["last_expiry"] == NOW + 30
    with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
        deadman.accept_pulse(pulse(expiry=NOW + 31), TOKEN, state(), candidate, NOW)


def test_state_is_atomic_private_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    deadman._save_state(path, state())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert deadman._state(path)["last_delivery"] == "never"
    path.chmod(0o644)
    with pytest.raises(deadman.DeadmanError, match="unsafe state"):
        deadman._state(path)


def test_schema_one_legacy_state_upgrades_before_next_atomic_save(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    legacy = {
        "schema": 1,
        "last_sequence": 4,
        "last_expiry": NOW + 10,
        "last_pulse": NOW,
        "incident": False,
        "last_delivery": "recovery",
    }
    path.write_text(json.dumps(legacy))
    path.chmod(0o600)
    migrated = deadman._state(path)
    assert migrated["last_delivery_at"] == 0
    assert migrated["last_canary"] == 0
    assert migrated["last_canary_delivery"] == "never"
    deadman._save_state(path, migrated)
    assert deadman._state(path) == migrated


def test_prior_schema_one_state_migrates_through_tick_and_atomic_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    prior = {
        "schema": 1,
        "last_sequence": 4,
        "last_expiry": NOW + 10,
        "last_pulse": NOW - 300,
        "incident": False,
        "last_delivery": "never",
        "last_delivery_at": 0,
        "last_canary": NOW,
    }
    path.write_text(json.dumps(prior))
    path.chmod(0o600)
    monkeypatch.setattr(deadman, "_telegram", lambda *_args: True)
    monkeypatch.setattr(deadman, "_reverse_health", lambda *_args: True)

    migrated = deadman.tick(path, config(), TOKEN, TOKEN, NOW)
    assert migrated["last_delivery"] == "firing"
    persisted = deadman._state(path)
    assert set(persisted) == set(deadman._empty_state())
    assert persisted["pending_event"] == "none"


def test_state_write_retries_until_the_full_record_is_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    original = deadman.os.write

    def short_write(descriptor: int, data: bytes) -> int:
        return original(descriptor, data[:3])

    monkeypatch.setattr(deadman.os, "write", short_write)
    deadman._save_state(path, state())
    assert deadman._state(path) == state()


def test_missing_or_invalid_config_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(deadman.DeadmanError, match="invalid config"):
        deadman._load_config(missing)
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schema":1}')
    with pytest.raises(deadman.DeadmanError, match="invalid config"):
        deadman._load_config(invalid)


@pytest.mark.parametrize("value", [0, 29, 31])
def test_config_requires_exact_future_tolerance(tmp_path: Path, value: int) -> None:
    candidate = config()
    candidate["max_future_seconds"] = value
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate))
    with pytest.raises(deadman.DeadmanError, match="invalid config"):
        deadman._load_config(path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda candidate: candidate["pulse_tls"].update(server_name="not/a-hostname"),
        lambda candidate: candidate["pulse_tls"].update(
            server_cert_credential="wrong-cert"
        ),
        lambda candidate: candidate["pulse_tls"].update(
            server_key_credential="wrong-key"
        ),
    ],
)
def test_runtime_config_requires_exact_pulse_tls_identity(
    tmp_path: Path, mutate: object
) -> None:
    candidate = config()
    assert callable(mutate)
    mutate(candidate)
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate))

    with pytest.raises(deadman.DeadmanError, match="invalid config"):
        deadman._load_config(path)


def test_runtime_config_accepts_exact_pulse_tls_identity(tmp_path: Path) -> None:
    candidate = config()
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate))

    assert deadman._load_config(path) == candidate


@pytest.mark.parametrize(
    "mutate",
    [
        lambda candidate: candidate.update(
            reverse_health_url="https://reverse.example.test:9443/v1/health"
        ),
        lambda candidate: candidate.update(
            reverse_health_url=(
                "https://reverse.example.test:9444/observability/v1/deadman/reverse"
            )
        ),
        lambda candidate: candidate["reverse_health_tls"].update(
            client_cn="foreign-control"
        ),
        lambda candidate: candidate["reverse_health_tls"].update(
            client_cert_fingerprint_sha256="d" * 63
        ),
        lambda candidate: candidate["reverse_health_tls"].update(
            ca_fingerprint_sha256="b" * 64
        ),
    ],
)
def test_runtime_config_rejects_foreign_reverse_route_or_identity_pin(
    tmp_path: Path, mutate: object
) -> None:
    candidate = config()
    assert callable(mutate)
    mutate(candidate)
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate))

    with pytest.raises(deadman.DeadmanError, match="invalid config"):
        deadman._load_config(path)


def test_tick_fires_once_and_recovers_only_after_fresh_pulse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    deadman._save_state(path, state())
    events: list[str] = []
    monkeypatch.setattr(
        deadman,
        "_telegram",
        lambda _config, _token, event: events.append(event) or True,
    )
    monkeypatch.setattr(deadman, "_reverse_health", lambda *_args: True)
    first = deadman.tick(path, config(), TOKEN, TOKEN, NOW + 300)
    assert first["incident"] is True and events == ["firing"]
    assert deadman.tick(path, config(), TOKEN, TOKEN, NOW + 301)["incident"] is True
    fresh = deadman._state(path)
    fresh.update(last_pulse=NOW + 301)
    deadman._save_state(path, fresh)
    recovered = deadman.tick(path, config(), TOKEN, TOKEN, NOW + 302)
    assert recovered["incident"] is False and events == ["firing", "recovery"]


def test_tick_retries_failed_delivery_sends_bounded_reminder_and_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    current = state()
    current.update(last_pulse=NOW - 300, last_delivery="failed")
    deadman._save_state(path, current)
    events: list[str] = []
    monkeypatch.setattr(
        deadman,
        "_telegram",
        lambda _config, _token, event: events.append(event) or True,
    )
    monkeypatch.setattr(deadman, "_reverse_health", lambda *_args: True)
    first = deadman.tick(path, config(), TOKEN, TOKEN, NOW + 300)
    second = deadman.tick(path, config(), TOKEN, TOKEN, NOW + 301)
    assert first["last_delivery"] == "firing"
    assert events == ["firing"]
    assert second["last_delivery"] == "firing"
    assert events == ["firing"]
    later = deadman.tick(path, config(), TOKEN, TOKEN, NOW + 3_900)
    assert later["last_delivery"] == "firing"
    assert events == ["firing", "firing"]
    fresh = deadman._state(path)
    fresh.update(last_pulse=NOW + 3_900)
    deadman._save_state(path, fresh)
    deadman.tick(path, config(), TOKEN, TOKEN, NOW + 4_001)
    deadman.tick(path, config(), TOKEN, TOKEN, NOW + 4_002)
    assert events[-1] == "canary"


def test_failed_canary_is_persisted_then_retried_at_the_bounded_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    current = state()
    current.update(last_pulse=NOW, last_canary=0)
    deadman._save_state(path, current)
    events: list[str] = []
    monkeypatch.setattr(
        deadman,
        "_telegram",
        lambda _config, _token, event: events.append(event) and False,
    )
    monkeypatch.setattr(deadman, "_reverse_health", lambda *_args: True)

    first = deadman.tick(path, config(), TOKEN, TOKEN, NOW + 1)
    assert first["last_canary_delivery"] == "failed"
    assert events == ["canary"]
    deadman.tick(path, config(), TOKEN, TOKEN, NOW + 2)
    assert events == ["canary"]
    healthy = deadman._state(path)
    healthy["last_pulse"] = NOW + 3_600
    deadman._save_state(path, healthy)
    second = deadman.tick(path, config(), TOKEN, TOKEN, NOW + 3_601)
    assert second["last_canary_delivery"] == "failed"
    assert events == ["canary", "canary"]
    assert (
        json.loads(deadman._status_payload(second))["last_canary_delivery"] == "failed"
    )


def test_telegram_rate_limit_honours_bounded_retry_after_without_secret_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bytes, int]] = []
    sleeps: list[int] = []

    class Response:
        status = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def post(outbound, timeout):  # type: ignore[no-untyped-def]
        calls.append((outbound.full_url, outbound.data, timeout))
        if len(calls) == 1:
            raise error.HTTPError(
                outbound.full_url,
                429,
                "rate limited",
                {},
                io.BytesIO(
                    b'{"ok":false,"error_code":429,"description":"bounded",'
                    b'"parameters":{"retry_after":99}}'
                ),
            )
        return Response()

    monkeypatch.setattr(deadman.request, "urlopen", post)
    monkeypatch.setattr(deadman.time, "sleep", sleeps.append)

    assert deadman._telegram(config(), TOKEN, "firing") is True
    assert len(calls) == 2
    assert sleeps == [5]
    assert all(timeout == 5 for _url, _body, timeout in calls)
    assert all(TOKEN.decode() in url for url, _body, _timeout in calls)
    payload = json.loads(calls[0][1])
    assert payload == {
        "chat_id": "-100000000001",
        "text": "[secondary dead-man] monitoring-plane firing",
        "disable_web_page_preview": True,
        "message_thread_id": 7,
    }
    assert TOKEN.decode() not in json.dumps(payload)


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("timeout"), OSError("network"), ValueError("invalid transport")],
)
def test_telegram_transient_transport_failure_uses_bounded_backoff_then_recovers(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    attempts = 0
    sleeps: list[int] = []

    class Response:
        status = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def post(*_args: object, **_kwargs: object) -> Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise failure
        return Response()

    monkeypatch.setattr(deadman.request, "urlopen", post)
    monkeypatch.setattr(deadman.time, "sleep", sleeps.append)

    assert deadman._telegram(config(), TOKEN, "recovery") is True
    assert attempts == 2
    assert sleeps == [1]


@pytest.mark.parametrize(
    ("seam", "affected"),
    [
        ("cpu", {"cpu"}),
        ("memory", {"memory"}),
        ("filesystem", {"disk", "inode"}),
        ("network", {"network"}),
        ("unit", {"unit"}),
    ],
)
def test_host_health_preserves_categorical_errors_for_bounded_collection_failures(
    monkeypatch: pytest.MonkeyPatch, seam: str, affected: set[str]
) -> None:
    monkeypatch.setattr(deadman.os, "getloadavg", lambda: (0.0, 0.0, 0.0))
    monkeypatch.setattr(deadman.os, "sysconf", lambda _name: 1)
    monkeypatch.setattr(
        deadman.os,
        "statvfs",
        lambda _path: type("Filesystem", (), {"f_bavail": 1, "f_favail": 1})(),
    )
    monkeypatch.setattr(
        deadman.Path,
        "iterdir",
        lambda _path: iter([Path("/tmp/eth0")]),
    )
    monkeypatch.setattr(deadman.Path, "read_text", lambda *_args, **_kwargs: "up")
    monkeypatch.setattr(
        deadman.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )
    if seam == "cpu":
        monkeypatch.setattr(
            deadman.os, "getloadavg", lambda: (_ for _ in ()).throw(OSError())
        )
    elif seam == "memory":
        monkeypatch.setattr(
            deadman.os, "sysconf", lambda _name: (_ for _ in ()).throw(ValueError())
        )
    elif seam == "filesystem":
        monkeypatch.setattr(
            deadman.os, "statvfs", lambda _path: (_ for _ in ()).throw(OSError())
        )
    elif seam == "network":
        monkeypatch.setattr(
            deadman.Path, "iterdir", lambda _path: (_ for _ in ()).throw(OSError())
        )
    else:
        monkeypatch.setattr(
            deadman.subprocess,
            "run",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("systemctl", 3)
            ),
        )

    health = deadman._host_health(config(), state(), NOW)

    assert all(health[axis] == "error" for axis in affected)
    assert all(
        health[axis] == "ok"
        for axis in {"cpu", "memory", "disk", "inode", "network", "unit"} - affected
    )


def test_telegram_server_error_retries_but_client_rejection_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []
    sleeps: list[int] = []

    def server_error(outbound, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 5
        attempts.append(503)
        raise error.HTTPError(outbound.full_url, 503, "unavailable", {}, None)

    monkeypatch.setattr(deadman.request, "urlopen", server_error)
    monkeypatch.setattr(deadman.time, "sleep", sleeps.append)
    assert deadman._telegram(config(), TOKEN, "canary") is False
    assert attempts == [503, 503]
    assert sleeps == [1]

    attempts.clear()
    sleeps.clear()

    def client_error(outbound, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 5
        attempts.append(400)
        raise error.HTTPError(outbound.full_url, 400, "bad request", {}, None)

    monkeypatch.setattr(deadman.request, "urlopen", client_error)
    assert deadman._telegram(config(), TOKEN, "canary") is False
    assert attempts == [400]
    assert sleeps == []


def test_pulse_state_update_does_not_wait_for_outbound_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    deadman._save_state(path, state())
    monkeypatch.setattr(deadman, "_reverse_health", lambda *_args: True)
    started = threading.Event()
    release = threading.Event()

    def delayed_telegram(*_args: object) -> bool:
        started.set()
        release.wait(timeout=2)
        return True

    monkeypatch.setattr(deadman, "_telegram", delayed_telegram)
    worker = threading.Thread(
        target=deadman.tick, args=(path, config(), TOKEN, TOKEN, NOW + 300)
    )
    worker.start()
    assert started.wait(timeout=1)
    accepted = deadman.accept_and_save(path, pulse(), TOKEN, config(), NOW)
    assert accepted["last_sequence"] == 1
    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert deadman._state(path)["last_sequence"] == 1


def test_templates_keep_credentials_systemd_only_and_harden_services() -> None:
    service = (ROLE / "templates/observability-deadman.service.j2").read_text()
    tick = (ROLE / "templates/observability-deadman-tick.service.j2").read_text()
    assert "LoadCredential=pulse-token:" in service
    assert "LoadCredential=pulse-server-cert:" in service
    assert "LoadCredential=pulse-server-key:" in service
    assert "LoadCredential=telegram-bot-token:" in service + tick
    assert "Environment=" not in service + tick
    for hardening in (
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "MemoryMax=64M",
        "TasksMax=",
    ):
        assert hardening in service + tick
    assert "TimeoutStartSec=60s" in tick
    assert "ReadWritePaths={{ observability_deadman.state_dir }}" in service + tick


def test_canonical_deadman_config_renders_schema_one_telegram_destination() -> None:
    rendered = render_template(
        ROLE / "templates/observability-deadman.json.j2", merge_render_vars()
    )

    assert json.loads(rendered)["schema"] == 1
    assert json.loads(rendered)["pulse_tls"] == {
        "server_name": "",
        "server_cert_credential": "pulse-server-cert",
        "server_key_credential": "pulse-server-key",
    }
    assert json.loads(rendered)["telegram"] == {"chat_id": "", "topic_id": 0}


def test_enable_rolls_back_and_restarts_previous_but_disable_never_cleans_after_stop_failure() -> (
    None
):
    enable = (ROLE / "tasks/enable.yml").read_text()
    disable = (ROLE / "tasks/disable.yml").read_text()
    assert "Stop candidate dead-man units before rollback" in enable
    assert "Gather candidate dead-man unit facts before rollback" in enable
    assert "Restart restored dead-man generation" in enable
    assert "observability-deadman-tick.timer" in enable
    assert "failed_when: false" not in enable
    assert "Gather dead-man service facts before disable" in disable
    assert "item in ansible_facts.services" in disable
    assert "failed_when: false" not in disable
    assert disable.index("Stop and disable") < disable.index("Remove dead-man owned")


def test_http_server_has_bounded_queue_concurrency_and_read_timeout() -> None:
    assert deadman.BoundedPulseServer.request_queue_size == 4
    assert deadman.BoundedPulseServer.daemon_threads is True
    assert "BoundedSemaphore(4)" in SOURCE.read_text()
    assert "settimeout(5)" in SOURCE.read_text()


def test_slow_or_short_pulse_body_fails_closed_without_state_write() -> None:
    class SlowReader:
        def read(self, _length: int) -> bytes:
            raise TimeoutError("slowloris")

    class ShortReader:
        def read(self, _length: int) -> bytes:
            return b"{}"

    for reader in (SlowReader(), ShortReader()):
        with pytest.raises(deadman.DeadmanError, match="invalid pulse"):
            deadman._read_pulse_body(reader, 10, 4096)


def test_reverse_health_is_signed_bounded_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Response:
        status = 204

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Opener:
        def open(self, outbound, timeout):  # type: ignore[no-untyped-def]
            captured["url"] = outbound.full_url
            captured["body"] = outbound.data
            captured["timeout"] = timeout
            return Response()

    def opener(context):  # type: ignore[no-untyped-def]
        captured["context"] = context
        return Opener()

    monkeypatch.setattr(deadman, "_reverse_opener", opener)
    current = state()
    current.update(last_sequence=4, last_pulse=NOW, last_delivery="recovery")
    assert deadman._reverse_health(config(), TOKEN, current, NOW) is True
    assert captured["context"] is None
    body = captured["body"]
    assert isinstance(body, bytes) and len(body) <= 1024
    rendered = body.decode()
    assert TOKEN.decode() not in rendered
    assert "receiver" in rendered and "signature" in rendered


def test_reverse_health_opener_disables_proxies_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[request.BaseHandler] = []

    class Opener:
        pass

    def build(*handlers: request.BaseHandler) -> Opener:
        captured.extend(handlers)
        return Opener()

    monkeypatch.setattr(deadman.request, "build_opener", build)

    assert isinstance(deadman._reverse_opener(None), Opener)
    proxy = next(
        handler for handler in captured if isinstance(handler, request.ProxyHandler)
    )
    redirects = next(
        handler for handler in captured if isinstance(handler, deadman._RejectRedirects)
    )
    assert proxy.proxies == {}
    assert redirects.redirect_request(None, None, None, None, None, None) is None


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_reverse_health_redirect_is_rejected_without_retry(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    attempts = 0

    class Opener:
        def open(self, outbound, timeout):  # type: ignore[no-untyped-def]
            nonlocal attempts
            attempts += 1
            assert timeout == 5
            raise error.HTTPError(
                outbound.full_url,
                status,
                "redirect refused",
                {"Location": "https://foreign.example.test/collect"},
                None,
            )

    monkeypatch.setattr(deadman, "_reverse_opener", lambda _context: Opener())

    assert deadman._post_reverse(config(), TOKEN, {"schema": 1}, None) is False
    assert attempts == 1


def test_tick_completes_state_after_slow_429_body_then_publishes_reverse_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    current = state()
    current["last_pulse"] = NOW - 300
    deadman._save_state(path, current)
    calls: list[str] = []
    sleeps: list[int] = []

    class Response:
        def __init__(self, status: int, *, slow_body: bool = False) -> None:
            self.status = status
            self.headers = {"Retry-After": "5"}
            self.slow_body = slow_body

        def read(self, _maximum: int) -> bytes:
            calls.append("slow-429-body")
            if self.slow_body:
                raise TimeoutError("bounded response body timeout")
            return b""

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def post(outbound, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 5
        if urlsplit(outbound.full_url).hostname == "api.telegram.org":
            calls.append("telegram")
            return (
                Response(429, slow_body=True)
                if calls.count("telegram") == 1
                else Response(200)
            )
        calls.append("reverse-health")
        persisted = deadman._state(path)
        assert persisted["pending_event"] == "none"
        assert persisted["last_delivery"] == "firing"
        if calls.count("reverse-health") == 1:
            raise TimeoutError("bounded reverse-health timeout")
        return Response(204)

    class ReverseOpener:
        def open(self, outbound, timeout):  # type: ignore[no-untyped-def]
            return post(outbound, timeout)

    monkeypatch.setattr(deadman.request, "urlopen", post)
    monkeypatch.setattr(deadman, "_reverse_opener", lambda _context: ReverseOpener())
    monkeypatch.setattr(deadman.time, "sleep", sleeps.append)

    completed = deadman.tick(path, config(), TOKEN, TOKEN, NOW)

    assert completed["pending_event"] == "none"
    assert completed["last_delivery"] == "firing"
    assert calls == [
        "telegram",
        "slow-429-body",
        "telegram",
        "reverse-health",
        "reverse-health",
    ]
    assert sleeps == [5]


def test_each_tick_reserves_a_distinct_durable_reverse_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    current = state()
    current.update(last_pulse=NOW, last_canary=NOW, last_canary_delivery="success")
    deadman._save_state(path, current)
    observed: list[int] = []

    def reverse(_config, _token, snapshot, _now):  # type: ignore[no-untyped-def]
        observed.append(snapshot["last_reverse_sequence"])
        return True

    monkeypatch.setattr(deadman, "_reverse_health", reverse)

    deadman.tick(path, config(), TOKEN, TOKEN, NOW + 1)
    deadman.tick(path, config(), TOKEN, TOKEN, NOW + 2)

    assert observed == [1, 2]
    assert deadman._state(path)["last_reverse_sequence"] == 2


def test_role_contract_refuses_unbounded_or_nonprivate_configuration() -> None:
    source = (ROLE / "tasks/enable.yml").read_text()
    for expected in (
        "pulse_listen == '0.0.0.0:9444'",
        "status_listen == '127.0.0.1:19094'",
        "missed_pulse_limit | int == 5",
        "max_future_seconds | int == 30",
        "retry_attempts | int <= 2",
        "no_log: true",
    ):
        assert expected in source


@pytest.mark.parametrize(
    ("field", "value", "expected_task"),
    [
        (
            "reverse_health_url",
            "https://control.example.test:9443/v1/health",
            "Require complete bounded dead-man contract before host mutation",
        ),
        (
            "client_cn",
            "wrong-deadman",
            "Require complete bounded dead-man contract before host mutation",
        ),
        (
            "client_cert_fingerprint_sha256",
            "0" * 64,
            "Refuse a reverse-heartbeat certificate that differs from the controller identity",
        ),
        (
            "ca_fingerprint_sha256",
            "f" * 64,
            "Refuse a reverse-heartbeat certificate that differs from the controller identity",
        ),
        (
            "pulse_tls_server_name",
            "wrong.example.test",
            "Verify pulse TLS server certificate against the dedicated CA",
        ),
        (
            "pulse_tls_server_key_pem",
            "",
            "Refuse pulse TLS material without the exact key and server identity",
        ),
        (
            "pulse_tls_ca_pem",
            "",
            "Verify pulse TLS server certificate against the dedicated CA",
        ),
        (
            "pulse_tls_non_ca_pem",
            "",
            "Refuse pulse TLS CA without an explicit CA constraint",
        ),
        (
            "pulse_tls_client_auth_only",
            "",
            "Verify pulse TLS server certificate against the dedicated CA",
        ),
        (
            "pulse_tls_expired",
            "",
            "Verify pulse TLS server certificate against the dedicated CA",
        ),
    ],
)
def test_reverse_heartbeat_contract_refuses_route_or_mtls_pin_before_host_writes(
    tmp_path: Path, field: str, value: str, expected_task: str
) -> None:
    pulse_tls = _pulse_tls()
    contract = {
        "enabled": True,
        "service_user": "observability-deadman-fixture",
        "service_group": "observability-deadman-fixture",
        "config_root": str(tmp_path / "config"),
        "state_dir": str(tmp_path / "state"),
        "pulse_credential_path": str(tmp_path / "credentials" / "pulse-token"),
        "telegram_credential_path": str(
            tmp_path / "credentials" / "telegram-bot-token"
        ),
        "pulse_listen": "0.0.0.0:9444",
        "status_listen": "127.0.0.1:19094",
        "pulse_path": "/v1/pulse",
        "pulse_tls": {
            "server_name": pulse_tls["server_name"],
            "server_cert_credential": pulse_tls["server_cert_credential"],
            "server_key_credential": pulse_tls["server_key_credential"],
        },
        "reverse_health_url": (
            "https://control.example.test:9443/observability/v1/deadman/reverse"
        ),
        "reverse_health_max_bytes": 1024,
        "source_generation": "a" * 40,
        "required_units": ["observability-deadman.service"],
        "reverse_health_tls": _reverse_health_tls(),
        "pulse_interval_seconds": 60,
        "missed_pulse_limit": 5,
        "max_future_seconds": 30,
        "max_pulse_bytes": 4096,
        "retry_attempts": 2,
        "retry_timeout_seconds": 5,
        "reminder_interval_seconds": 3600,
        "canary_interval_seconds": 86400,
        "telegram": {"chat_id": "-100000000001", "topic_id": 7},
    }
    if field == "reverse_health_url":
        contract[field] = value
    elif field == "pulse_tls_server_name":
        contract["pulse_tls"]["server_name"] = value
    elif field == "pulse_tls_server_key_pem":
        value = contract["reverse_health_tls"]["client_key_pem"]
    elif field == "pulse_tls_ca_pem":
        value = _pulse_tls()["ca_pem"]
    elif field == "pulse_tls_non_ca_pem":
        value = pulse_tls["server_cert_pem"]
    elif field == "pulse_tls_client_auth_only":
        replacement = _pulse_tls(purpose=ExtendedKeyUsageOID.CLIENT_AUTH)
        pulse_tls["server_cert_pem"] = replacement["server_cert_pem"]
        pulse_tls["server_key_pem"] = replacement["server_key_pem"]
    elif field == "pulse_tls_expired":
        replacement = _pulse_tls(expired=True)
        pulse_tls["server_cert_pem"] = replacement["server_cert_pem"]
        pulse_tls["server_key_pem"] = replacement["server_key_pem"]
    else:
        contract["reverse_health_tls"][field] = value
    playbook = tmp_path / "deadman-contract.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "observability_contract": {
                            "schema_version": 1,
                            "credential_mode": "systemd",
                        },
                        "observability_deadman": contract,
                        "observability_deadman_secrets": {
                            "schema_version": 1,
                            "pulse_token": "fixture-pulse-token-0123456789",
                            "pulse_tls": {
                                "ca_pem": (
                                    value
                                    if field
                                    in {"pulse_tls_ca_pem", "pulse_tls_non_ca_pem"}
                                    else pulse_tls["ca_pem"]
                                ),
                                "server_cert_pem": pulse_tls["server_cert_pem"],
                                "server_key_pem": (
                                    value
                                    if field == "pulse_tls_server_key_pem"
                                    else pulse_tls["server_key_pem"]
                                ),
                            },
                            "telegram": {
                                "bot_token": "fixture-telegram-token-012345678"
                            },
                        },
                    },
                    "roles": [{"role": "observability_deadman"}],
                }
            ]
        )
    )

    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode != 0
    assert expected_task in result.stdout + result.stderr
    assert "Create dedicated dead-man group" not in result.stdout + result.stderr
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "state").exists()
    assert "fixture-pulse-token" not in result.stdout + result.stderr


def test_molecule_lifecycle_scenarios_cover_deadman_enable_disable_and_refusal() -> (
    None
):
    molecule = ROLE / "molecule"
    default = yaml.safe_load((molecule / "default/molecule.yml").read_text())
    enabled = yaml.safe_load((molecule / "enabled/molecule.yml").read_text())
    default_verify = (molecule / "default/verify.yml").read_text()
    enabled_converge = (molecule / "enabled/converge.yml").read_text()
    enabled_verify = (molecule / "enabled/verify.yml").read_text()
    enabled_verify_play = yaml.safe_load(enabled_verify)[0]
    enabled_prepare = (molecule / "enabled/prepare.yml").read_text()

    assert "ProxyHandler({})" in enabled_verify
    assert "HTTPSHandler(context=context)" in enabled_verify
    assert "class NoRedirect(HTTPRedirectHandler)" in enabled_verify
    assert "with opener.open(request, timeout=5)" in enabled_verify
    assert "with urlopen(request" not in enabled_verify

    for scenario in (default, enabled):
        assert scenario["scenario"]["test_sequence"] == [
            "dependency",
            "syntax",
            "create",
            "prepare",
            "converge",
            "idempotence",
            "verify",
            "destroy",
        ]
    assert "Require invalid contract to fail before mutation" in default_verify
    assert "role: observability_deadman" in enabled_converge
    assert "Include disabled dead-man role" in enabled_verify
    assert enabled["platforms"][0]["etc_hosts"] == {
        "api.telegram.org": "127.0.0.1",
        "reverse.fixture.invalid": "127.0.0.1",
    }
    assert "ansible.builtin.lineinfile" not in enabled_prepare
    assert "- files" in enabled_prepare
    assert "match('^127\\\\.0\\\\.0\\\\.1\\\\s')" in enabled_prepare
    assert "client_cn: deadman-control" in enabled_converge + enabled_verify
    assert "client_cert_fingerprint_sha256" in enabled_converge + enabled_verify
    assert "ca_fingerprint_sha256" in enabled_converge + enabled_verify
    assert "client.sha256" in enabled_prepare
    assert "ca.sha256" in enabled_prepare
    assert "pulse-server.pem" in enabled_prepare
    assert "pulse-server.key" in enabled_prepare
    assert "pulse-ca.pem" in enabled_prepare + enabled_converge + enabled_verify
    assert "-CA /var/tmp/observability-deadman-fixture/pulse-ca.pem" in enabled_prepare
    assert "set -euo pipefail" in enabled_prepare
    exact_reverse_health_url = (
        "https://reverse.fixture.invalid:9443/observability/v1/deadman/reverse"
    )
    assert enabled_converge.count(exact_reverse_health_url) == 1
    assert enabled_verify.count(exact_reverse_health_url) == 3
    assert "19445" not in enabled_converge + enabled_verify
    assert "pulse_tls:" in enabled_converge + enabled_verify
    assert "https://reverse.fixture.invalid:9444/v1/pulse" in enabled_verify
    assert "deadman_rotation_probe" in enabled_verify
    assert "expected = (400, 204)" in enabled_verify
    assert "expected = (400,)" in enabled_verify
    rotation_names = [task["name"] for task in enabled_verify_play["tasks"]]
    assert (
        rotation_names.index("Include token-only rotated dead-man role")
        < rotation_names.index("Require token-only receiver credential reload")
        < rotation_names.index("Include config-only rotated dead-man role")
        < rotation_names.index("Require config-only receiver generation reload")
    )
    assert (
        enabled_verify_play["vars"]["token_rotated_deadman"]["max_pulse_bytes"] == 4096
    )
    assert enabled_verify_play["vars"]["rotated_deadman"]["max_pulse_bytes"] == 512


def test_activation_restarts_changed_receiver_inputs_inside_rollback_block() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    handlers = (ROLE / "handlers/main.yml").read_text()
    credentials = next(
        task
        for task in tasks
        if task["name"] == "Install root-owned systemd credential inputs"
    )
    verifier = next(
        task
        for task in tasks
        if task["name"]
        == "Install dead-man verifier and immutable candidate configuration"
    )
    activation = next(
        task
        for task in tasks
        if task["name"] == "Activate dead-man candidate with last-known-good rollback"
    )["block"]
    names = [task["name"] for task in activation]
    restart = next(
        task
        for task in activation
        if task["name"] == "Restart changed dead-man receiver before acceptance"
    )
    readiness = next(
        task
        for task in activation
        if task["name"] == "Require activated dead-man private status readiness"
    )

    assert credentials["register"] == "_observability_deadman_credentials"
    assert verifier["register"] == "_observability_deadman_verifier"
    assert (
        names.index("Point dead-man at validated generation")
        < names.index("Restart changed dead-man receiver before acceptance")
        < names.index("Require activated dead-man private status readiness")
    )
    assert restart["when"] == [
        "not ansible_check_mode",
        "_observability_deadman_credentials.changed or _observability_deadman_verifier.changed or _observability_deadman_current_link.changed or _observability_deadman_units.changed",
    ]
    assert readiness["ansible.builtin.uri"]["url"] == "http://127.0.0.1:19094/v1/status"
    assert readiness["ansible.builtin.uri"]["use_proxy"] is False
    assert readiness["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert "Restart observability dead-man" not in str(activation)
    assert "Restart observability dead-man" not in handlers
