"""Focused contracts for the independent dead-man receiver and role surface."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import stat
import threading

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
    return deadman._empty_state()


def test_defaults_are_inert_and_keep_status_loopback_only() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_deadman"
    ]
    assert defaults["enabled"] is False
    assert defaults["pulse_listen"] == "0.0.0.0:9444"
    assert defaults["status_listen"] == "127.0.0.1:19094"
    assert defaults["missed_pulse_limit"] == 5
    assert defaults["retry_attempts"] == 2


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


def test_config_rejects_zero_future_tolerance(tmp_path: Path) -> None:
    candidate = config()
    candidate["max_future_seconds"] = 0
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


def test_canonical_deadman_config_renders_schema_one_telegram_destination() -> None:
    rendered = render_template(
        ROLE / "templates/observability-deadman.json.j2", merge_render_vars()
    )

    assert json.loads(rendered)["schema"] == 1
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


def test_molecule_lifecycle_scenarios_cover_deadman_enable_disable_and_refusal() -> None:
    molecule = ROLE / "molecule"
    default = yaml.safe_load((molecule / "default/molecule.yml").read_text())
    enabled = yaml.safe_load((molecule / "enabled/molecule.yml").read_text())
    default_verify = (molecule / "default/verify.yml").read_text()
    enabled_converge = (molecule / "enabled/converge.yml").read_text()
    enabled_verify = (molecule / "enabled/verify.yml").read_text()
    enabled_verify_play = yaml.safe_load(enabled_verify)[0]
    enabled_prepare = (molecule / "enabled/prepare.yml").read_text()

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
    assert enabled_verify_play["vars"]["token_rotated_deadman"]["max_pulse_bytes"] == 4096
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
        if task["name"] == "Install dead-man verifier and immutable candidate configuration"
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
    assert names.index("Point dead-man at validated generation") < names.index(
        "Restart changed dead-man receiver before acceptance"
    ) < names.index("Require activated dead-man private status readiness")
    assert restart["when"] == [
        "not ansible_check_mode",
        "_observability_deadman_credentials.changed or _observability_deadman_verifier.changed or _observability_deadman_current_link.changed or _observability_deadman_units.changed",
    ]
    assert readiness["ansible.builtin.uri"]["url"] == "http://127.0.0.1:19094/v1/status"
    assert readiness["ansible.builtin.uri"]["use_proxy"] is False
    assert readiness["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert "Restart observability dead-man" not in str(activation)
    assert "Restart observability dead-man" not in handlers
