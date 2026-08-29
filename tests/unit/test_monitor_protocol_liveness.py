"""End-to-end tests for the scheduled protocol-liveness monitor."""

from __future__ import annotations

import json
import os
import runpy
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MONITOR = REPO_ROOT / "scripts" / "monitor-protocol-liveness.py"


def test_monitor_deadline_outlives_maximum_parallel_collector(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))
    monitor = runpy.run_path(str(MONITOR))
    engine = runpy.run_path(str(REPO_ROOT / "scripts/liveness_generation.py"))
    collector = runpy.run_path(str(REPO_ROOT / "scripts/protocol-liveness.py"))
    deadlines = []
    def run(argv, **kwargs):
        deadlines.append(kwargs["timeout"])
        return subprocess.CompletedProcess(argv, 0, stdout='{"schema_version":2,"decision":"healthy"}')
    monkeypatch.setattr(subprocess, "run", run)
    assert monitor["evaluate"](tmp_path / "fixture.yaml", tmp_path / "state") == {
        "schema_version": 2, "decision": "healthy"}
    profiles = sorted(engine["PROFILES"])
    config = {"probe_timeout_seconds": 60, "policies": [{"id": "full", "required_profiles": profiles}]}
    remote = collector["remote_probe_deadline"](config, {"policy": "full"})
    assert engine["probe_deadline"](60, profiles) < remote < deadlines[0] == engine["JOB_TIMEOUT_SECONDS"] == 600


def _executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def monitor_env(tmp_path: Path):
    config = tmp_path / "liveness.yaml"
    config.write_text("schema_version: 2\n")
    decision = tmp_path / "decision.json"
    evaluator = tmp_path / "protocol-liveness"
    _executable(
        evaluator,
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > \"$EVALUATOR_ARGS\"\ncat \"$FAKE_DECISION\"\n",
    )

    requests: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib callback name
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(
                {
                    "path": self.path,
                    "title": self.headers.get("Title", ""),
                    "authorization": self.headers.get("Authorization", ""),
                    "body": self.rfile.read(length).decode(),
                }
            )
            self.send_response(200)
            self.end_headers()

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = os.environ.copy()
    env.update(
        {
            "PROTOCOL_LIVENESS": str(evaluator),
            "FAKE_DECISION": str(decision),
            "EVALUATOR_ARGS": str(tmp_path / "evaluator-args"),
            "NTFY_URL": f"http://127.0.0.1:{server.server_port}",
            "NTFY_TOPIC": "private-monitor-topic",
            "NTFY_TOKEN": "private-monitor-token",
        }
    )
    yield env, config, decision, tmp_path / "state", requests
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _decision(path: Path, decision: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "evaluated_at": 1_800_000_000,
                "decision": decision,
                "candidate_policies": ["vless-user-path"]
                if decision == "rotation_candidate"
                else [],
                "failed_vantages": {"vless-user-path": 1},
                "monitoring_errors": ["arm64-wifi-a: ssh exited 255"]
                if decision == "unknown"
                else [],
                "evidence": [
                    {
                        "sentinel": "arm64-wifi-a",
                        "policy": "vless-user-path",
                        "control": "ok",
                        "profiles": {
                            "p0-reality": "blocked"
                            if decision == "rotation_candidate"
                            else "ok"
                        },
                    }
                ],
            }
        )
    )


def _run(env: dict[str, str], config: Path, state: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(MONITOR), "--config", str(config), "--state-dir", str(state)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_healthy_probe_persists_redacted_state_without_alert(monitor_env) -> None:
    env, config, decision, state, requests = monitor_env
    _decision(decision, "healthy")

    result = _run(env, config, state)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["decision"] == "healthy"
    assert report["monitor_event"] == "none"
    assert report["alert_delivery"] == "not_requested"
    assert requests == []
    assert (state / "monitor-state.json").stat().st_mode & 0o777 == 0o600
    assert (state / "last-evidence.json").stat().st_mode & 0o777 == 0o600
    assert f"--config {config} --state-dir {state}" in Path(env["EVALUATOR_ARGS"]).read_text()


def test_unknown_probe_alerts_once_without_exposing_notification_secret(monitor_env) -> None:
    env, config, decision, state, requests = monitor_env
    _decision(decision, "unknown")

    first = _run(env, config, state)
    second = _run(env, config, state)
    third = _run(env, config, state)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert third.returncode == 0, third.stderr
    assert json.loads(first.stdout)["monitor_event"] == "alert"
    assert json.loads(second.stdout)["monitor_event"] == "none"
    assert json.loads(third.stdout)["monitor_event"] == "none"
    assert len(requests) == 1
    assert json.loads((state / "monitor-state.json").read_text())["alert_delivery"] == "sent"
    assert requests[0]["path"] == "/private-monitor-topic"
    assert requests[0]["authorization"] == "Bearer private-monitor-token"
    assert "arm64-wifi-a" in requests[0]["body"]
    assert "private-monitor-token" not in (
        first.stdout + first.stderr + second.stdout + second.stderr + third.stdout + third.stderr
    )


def test_recovery_sends_one_recovery_notification(monitor_env) -> None:
    env, config, decision, state, requests = monitor_env
    _decision(decision, "unknown")
    assert _run(env, config, state).returncode == 0
    _decision(decision, "healthy")

    recovered = _run(env, config, state)
    repeated = _run(env, config, state)

    assert recovered.returncode == 0, recovered.stderr
    assert json.loads(recovered.stdout)["monitor_event"] == "recovery"
    assert json.loads(repeated.stdout)["monitor_event"] == "none"
    assert len(requests) == 2
    assert "recovered" in requests[-1]["title"].lower()


def test_failed_alert_is_retried_on_next_evaluation(monitor_env) -> None:
    env, config, decision, state, _requests = monitor_env
    _decision(decision, "rotation_candidate")
    env.pop("NTFY_TOPIC")

    first = _run(env, config, state)
    second = _run(env, config, state)

    assert first.returncode == 4
    assert second.returncode == 4
    assert json.loads(first.stdout)["alert_delivery"] == "failed"
    assert json.loads(second.stdout)["monitor_event"] == "alert"


def test_evaluator_failure_alerts_and_persists_redacted_unknown(monitor_env) -> None:
    env, config, _decision_path, state, requests = monitor_env
    env.pop("NTFY_TOPIC")
    env.pop("NTFY_TOKEN")
    env["PROTOCOL_LIVENESS"] = str(state / "missing-evaluator")
    secrets = state.parent / "materialized-secrets.yaml"
    secrets.write_text(
        "watchdog_secrets:\n"
        "  ntfy_topic: private-monitor-topic\n"
        "  ntfy_token: private-monitor-token\n"
    )
    secrets.chmod(0o600)
    env["VPN_SECRETS_FILE"] = str(secrets)

    result = _run(env, config, state)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["decision"] == "unknown"
    assert report["monitor_event"] == "alert"
    assert report["alert_delivery"] == "sent"
    assert report["monitoring_errors"] == ["evaluator: evaluator unavailable: FileNotFoundError"]
    assert len(requests) == 1
    assert "private-monitor-token" not in result.stdout + result.stderr
    assert json.loads((state / "last-evidence.json").read_text())["decision"] == "unknown"


def test_monitor_refuses_legacy_evaluator_schema(monitor_env) -> None:
    env, config, decision, state, _requests = monitor_env
    _decision(decision, "healthy")
    payload = json.loads(decision.read_text())
    payload["schema_version"] = 1
    decision.write_text(json.dumps(payload))

    result = _run(env, config, state)

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["schema_version"] == 2
    assert report["decision"] == "unknown"
    assert report["monitoring_errors"] == ["evaluator: evaluator returned an unsupported decision"]
