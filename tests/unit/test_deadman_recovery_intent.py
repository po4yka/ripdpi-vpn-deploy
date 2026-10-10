"""Durable retained-receiver recovery intent, without enabling retired topology."""

import importlib.util
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "ansible/roles/observability_deadman/files/observability-deadman.py"
)
spec = importlib.util.spec_from_file_location("recovery_deadman", SOURCE)
deadman = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deadman)
NOW = 1700000000
CONFIG = dict(
    source_generation="a" * 40,
    retry_attempts=2,
    retry_timeout_seconds=5,
    pulse_interval_seconds=60,
    missed_pulse_limit=5,
    reminder_interval_seconds=60,
    canary_interval_seconds=86400,
)


def prepared(path):
    state = deadman._empty_state("a" * 40)
    state.update(
        incident=True,
        last_pulse=NOW,
        last_canary=NOW,
        last_canary_delivery="success",
        last_delivery="firing",
    )
    deadman._save_state(path, state)


def test_failed_recovery_survives_fresh_pulses_restart_and_matching_ack(tmp_path):
    path = tmp_path / "state.json"
    prepared(path)
    health, reservation = deadman._reserve_delivery(path, CONFIG, NOW)
    assert health["incident"] is False and reservation[0] == "recovery"
    first = reservation[1]
    deadman._complete_delivery(path, "recovery", first, False, NOW)
    health = deadman._state(path)
    health["last_pulse"] = NOW + 59
    deadman._save_state(path, health)
    assert deadman._reserve_delivery(path, CONFIG, NOW + 59)[1] is None
    _, retry = deadman._reserve_delivery(path, CONFIG, NOW + 60)
    assert retry == ("recovery", first + 1)
    # An old completion must never acknowledge the new reservation.
    deadman._complete_delivery(path, "recovery", first, True, NOW + 60)
    assert deadman._recovery_intent(path)["phase"] == "queued"
    deadman._complete_delivery(path, *retry, True, NOW + 60)
    assert deadman._recovery_intent(path)["phase"] == "complete"
    assert deadman._reserve_delivery(path, CONFIG, NOW + 61)[1] is None


def test_death_after_intent_before_health_and_ack_before_state_is_recoverable(
    tmp_path, monkeypatch
):
    path = tmp_path / "state.json"
    prepared(path)
    save = deadman._save_state

    def interrupt(target, data):
        if target == path:
            raise RuntimeError("synthetic process-death boundary")
        save(target, data)

    monkeypatch.setattr(deadman, "_save_state", interrupt)
    with pytest.raises(RuntimeError):
        deadman._reserve_delivery(path, CONFIG, NOW)
    assert deadman._state(path)["incident"] is True
    assert deadman._recovery_intent(path)["phase"] == "queued"
    monkeypatch.setattr(deadman, "_save_state", save)
    _, reservation = deadman._reserve_delivery(path, CONFIG, NOW)
    monkeypatch.setattr(deadman, "_save_state", interrupt)
    with pytest.raises(RuntimeError):
        deadman._complete_delivery(path, *reservation, True, NOW)
    assert deadman._recovery_intent(path)["phase"] == "complete"
    monkeypatch.setattr(deadman, "_save_state", save)
    assert deadman._reserve_delivery(path, CONFIG, NOW + 1)[1] is None
    assert deadman._state(path)["pending_event"] == "none"


def test_inflight_recovery_lease_expires_and_new_incident_remains_authoritative(
    tmp_path,
):
    path = tmp_path / "state.json"
    prepared(path)
    _, original = deadman._reserve_delivery(path, CONFIG, NOW)
    _, retry = deadman._reserve_delivery(path, CONFIG, NOW + 60)
    assert retry[0] == "recovery" and retry[1] > original[1]
    # Fresh incidents take precedence, without discarding outstanding recovery.
    _, firing = deadman._reserve_delivery(path, CONFIG, NOW + 400)
    assert firing[0] == "firing"
    assert deadman._recovery_intent(path)["phase"] == "queued"


def test_new_health_transition_fences_old_inflight_recovery_ack(tmp_path):
    path = tmp_path / "state.json"
    prepared(path)
    _, old = deadman._reserve_delivery(path, CONFIG, NOW)
    config = dict(CONFIG, missed_pulse_limit=1)
    health, _ = deadman._reserve_delivery(path, config, NOW + 5)
    assert health["incident"] is False
    # Model a new incident without waiting for a still-running old callback.
    health["last_pulse"] = NOW - 60
    deadman._save_state(path, health)
    health, _ = deadman._reserve_delivery(path, config, NOW + 6)
    assert health["incident"] is True
    health["last_pulse"] = NOW + 7
    deadman._save_state(path, health)
    health, _ = deadman._reserve_delivery(path, config, NOW + 7)
    assert health["incident"] is False
    assert deadman._recovery_intent(path)["attempt_nonce"] == 0
    deadman._complete_delivery(path, *old, True, NOW + 8)
    assert deadman._recovery_intent(path)["phase"] == "queued"
    _, retry = deadman._reserve_delivery(path, config, NOW + 11)
    assert retry[0] == "recovery" and retry[1] > old[1]


def test_actual_local_http_failed_recovery_then_restarted_receiver_retries(
    tmp_path, monkeypatch
):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import json
    import threading
    from urllib.request import Request, urlopen

    path = tmp_path / "state.json"
    prepared(path)
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.send_response(503 if len(received) <= 2 else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def local_api(outbound, timeout):
        assert timeout == 5
        return urlopen(
            Request(
                f"http://127.0.0.1:{server.server_port}/",
                data=outbound.data,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=timeout,
        )

    config = dict(CONFIG, telegram=dict(chat_id="-100000000001", topic_id=7))
    monkeypatch.setattr(deadman.request, "urlopen", local_api)
    monkeypatch.setattr(deadman, "_sleep", lambda delay: None)
    try:
        _, reservation = deadman._reserve_delivery(path, config, NOW)
        success = deadman._telegram(config, b"synthetic-secondary-token", "recovery")
        assert success is False
        deadman._complete_delivery(path, *reservation, success, NOW)
        # Reimport actual source to discard all process-local receiver state.
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        monkeypatch.setattr(fresh.request, "urlopen", local_api)
        health = fresh._state(path)
        health["last_pulse"] = NOW + 60
        fresh._save_state(path, health)
        _, retry = fresh._reserve_delivery(path, config, NOW + 60)
        assert retry[0] == "recovery"
        success = fresh._telegram(config, b"synthetic-secondary-token", "recovery")
        assert success is True
        fresh._complete_delivery(path, *retry, success, NOW + 60)
        assert fresh._reserve_delivery(path, config, NOW + 61)[1] is None
        assert len(received) == 3
        assert all(item["text"].endswith(" recovery") for item in received)
        assert fresh._recovery_intent(path)["phase"] == "complete"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_abandoned_recovery_cannot_suppress_new_incident_firing(tmp_path):
    path = tmp_path / "state.json"
    prepared(path)
    config = dict(CONFIG, reminder_interval_seconds=3600)
    _, old = deadman._reserve_delivery(path, config, NOW)
    health = deadman._state(path)
    health["last_pulse"] = NOW - 300
    deadman._save_state(path, health)
    health, pending = deadman._reserve_delivery(path, config, NOW + 6)
    assert health["incident"] is True and pending is None
    _, firing = deadman._reserve_delivery(path, config, NOW + 11)
    assert firing[0] == "firing" and firing[1] > old[1]
    assert deadman._recovery_intent(path)["phase"] == "queued"
