"""Focused contracts for the independent dead-man receiver and role surface."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import stat

import pytest
import yaml

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
        "reverse_health_url": "https://reverse.example.test/v1/health",
        "reverse_health_max_bytes": 1024,
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
    return {
        "schema": 1,
        "last_sequence": 0,
        "last_expiry": 0,
        "last_pulse": 0,
        "incident": False,
        "last_delivery": "never",
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


def test_valid_pulse_advances_state_without_exposing_token() -> None:
    accepted = deadman.accept_pulse(pulse(), TOKEN, state(), config(), NOW)
    assert accepted["last_sequence"] == 1
    assert accepted["last_pulse"] == NOW
    assert TOKEN.decode() not in repr(accepted)


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


def test_state_is_atomic_private_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    deadman._save_state(path, state())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert deadman._state(path)["last_delivery"] == "never"
    path.chmod(0o644)
    with pytest.raises(deadman.DeadmanError, match="unsafe state"):
        deadman._state(path)


def test_missing_or_invalid_config_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(deadman.DeadmanError, match="invalid config"):
        deadman._load_config(missing)
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schema":1}')
    with pytest.raises(deadman.DeadmanError, match="invalid config"):
        deadman._load_config(invalid)


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


def test_templates_keep_credentials_systemd_only_and_harden_services() -> None:
    service = (ROLE / "templates/observability-deadman.service.j2").read_text()
    tick = (ROLE / "templates/observability-deadman-tick.service.j2").read_text()
    assert "LoadCredential=pulse-token:" in service
    assert "LoadCredential=telegram-bot-token:" in service + tick
    assert "Environment=" not in service + tick
    for hardening in (
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "MemoryMax=64M",
        "TasksMax=",
    ):
        assert hardening in service + tick
    assert "ReadWritePaths={{ observability_deadman.state_dir }}" in service + tick


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

    def post(request, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(deadman.request, "urlopen", post)
    current = state()
    current.update(last_sequence=4, last_pulse=NOW, last_delivery="recovery")
    assert deadman._reverse_health(config(), TOKEN, current, NOW) is True
    body = captured["body"]
    assert isinstance(body, bytes) and len(body) <= 1024
    rendered = body.decode()
    assert TOKEN.decode() not in rendered
    assert "receiver" in rendered and "signature" in rendered


def test_role_contract_refuses_unbounded_or_nonprivate_configuration() -> None:
    source = (ROLE / "tasks/enable.yml").read_text()
    for expected in (
        "pulse_listen == '0.0.0.0:9444'",
        "status_listen == '127.0.0.1:19094'",
        "missed_pulse_limit | int == 5",
        "retry_attempts | int <= 2",
        "no_log: true",
    ):
        assert expected in source
