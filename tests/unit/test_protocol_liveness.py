"""Behavior tests for the protocol-liveness operator interface."""

from __future__ import annotations

import json
import os
import runpy
import stat
import subprocess
import time
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "protocol-liveness.py"
SCHEMA = REPO_ROOT / "contract" / "protocol-liveness.schema.json"
PROFILES = ["p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"]


def _report(sentinel: str, verdicts: dict[str, str], *, control: str = "ok", age: int = 0) -> dict:
    return {
        "schema_version": 1,
        "sentinel": sentinel,
        "observed_at": int(time.time()) - age,
        "control": {"verdict": control, "duration_ms": 20},
        "profiles": [
            {
                "profile": profile,
                "verdict": verdict,
                "duration_ms": 40,
                **(
                    {"variants": [{"variant": 1, "verdict": verdict, "duration_ms": 40}]}
                    if profile != "p2-amneziawg"
                    else {}
                ),
            }
            for profile, verdict in verdicts.items()
        ],
        "runtime": {"sing_box": "1.14.0", "awg": "1.0.0"},
    }


def _config(tmp_path: Path, *, quorum: int = 2) -> Path:
    path = tmp_path / "liveness.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "probe_url": "https://www.gstatic.com/generate_204",
                "expected_status": 204,
                "probe_timeout_seconds": 15,
                "degraded_after_ms": 3000,
                "stale_after_seconds": 120,
                "failure_threshold": 3,
                "otp_ttl_seconds": 3600,
                "expected_runtime": {"sing_box": "1.14.0", "awg": "1.0.0"},
                "policies": [
                    {
                        "id": "fullstack",
                        "required_profiles": PROFILES,
                        "min_failed_vantages": quorum,
                    }
                ],
                "sentinels": [
                    {"id": "tls-freeze-a", "ssh_target": "sentinel-a", "policy": "fullstack"},
                    {"id": "udp-filtered-b", "ssh_target": "sentinel-b", "policy": "fullstack"},
                ],
            },
            sort_keys=False,
        )
    )
    return path


def _fake_ssh(tmp_path: Path, reports: dict[str, dict | str]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    reports_path = tmp_path / "reports.json"
    reports_path.write_text(json.dumps(reports))
    ssh = bin_dir / "ssh"
    ssh.write_text(
        """#!/usr/bin/env python3
import json, os, sys, time
reports = json.load(open(os.environ['FAKE_REPORTS'], encoding='utf-8'))
target = next((arg for arg in sys.argv[1:] if arg in reports), '')
value = reports.get(target)
if isinstance(value, dict) and 'payload' in value:
    time.sleep(value.get('delay_seconds', 0))
    value = value['payload']
if isinstance(value, str):
    print(value)
    raise SystemExit(0)
if value is None:
    print('unreachable', file=sys.stderr)
    raise SystemExit(255)
print(json.dumps(value))
"""
    )
    ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _run(
    tmp_path: Path,
    config: Path,
    reports: dict[str, dict | str],
    *extra: str,
    evaluated_at: int | None = None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = _fake_ssh(tmp_path, reports)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_REPORTS"] = str(tmp_path / "reports.json")
    if evaluated_at is not None:
        env["PROTOCOL_LIVENESS_EVALUATED_AT"] = str(evaluated_at)
    return subprocess.run(
        ["python3", str(SCRIPT), "--config", str(config), *extra],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _all(verdict: str) -> dict[str, str]:
    return dict.fromkeys(PROFILES, verdict)


def test_schema_accepts_the_documented_configuration(tmp_path: Path) -> None:
    import jsonschema

    schema = json.loads(SCHEMA.read_text())
    config = yaml.safe_load(_config(tmp_path).read_text())
    jsonschema.Draft202012Validator(schema).validate(config)
    module = runpy.run_path(str(SCRIPT))
    assert module["remote_probe_deadline"](config, config["sentinels"][0]) == 95


@pytest.mark.parametrize(
    ("reports", "decision"),
    [
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("ok")),
                "sentinel-b": _report("udp-filtered-b", _all("ok")),
            },
            "healthy",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", {**_all("ok"), "p0-reality": "blocked"}),
                "sentinel-b": _report("udp-filtered-b", _all("ok")),
            },
            "degraded",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("blocked")),
                "sentinel-b": _report("udp-filtered-b", _all("blocked")),
            },
            "rotation_candidate",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("blocked"), control="unknown"),
                "sentinel-b": _report("udp-filtered-b", _all("blocked")),
            },
            "unknown",
        ),
        (
            {
                "sentinel-a": _report("tls-freeze-a", _all("error")),
                "sentinel-b": _report("udp-filtered-b", _all("blocked")),
            },
            "unknown",
        ),
    ],
)
def test_evaluator_returns_the_expected_decision(
    tmp_path: Path, reports: dict[str, dict], decision: str
) -> None:
    for report in reports.values():
        report["observed_at"] = int(time.time())
    result = _run(tmp_path, _config(tmp_path), reports)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == decision


def test_collector_budget_covers_probe_stages_and_preserves_degraded(tmp_path: Path) -> None:
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["probe_timeout_seconds"] = 1
    config_path = tmp_path / "short-timeout.yaml"
    config_path.write_text(yaml.safe_dump(config))
    reports = {
        "sentinel-a": {
            "delay_seconds": 7,
            "payload": _report("tls-freeze-a", {**_all("ok"), "p0-reality": "throttled"}),
        },
        "sentinel-b": {"delay_seconds": 7, "payload": _report("udp-filtered-b", _all("ok"))},
    }

    result = _run(tmp_path, config_path, reports)

    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "degraded"


def test_one_fully_blocked_vantage_is_below_quorum(tmp_path: Path) -> None:
    reports = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("ok")),
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    payload = json.loads(result.stdout)
    assert payload["decision"] == "degraded"
    assert payload["candidate_policies"] == []
    assert payload["failed_vantages"] == {"fullstack": 1}


def test_policy_defaults_to_two_failed_vantages(tmp_path: Path) -> None:
    config = yaml.safe_load(_config(tmp_path).read_text())
    del config["policies"][0]["min_failed_vantages"]
    path = tmp_path / "default-quorum.yaml"
    path.write_text(yaml.safe_dump(config))
    reports = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }

    result = _run(tmp_path, path, reports)

    assert json.loads(result.stdout)["decision"] == "rotation_candidate"


def test_stale_and_malformed_reports_never_create_a_candidate(tmp_path: Path) -> None:
    reports = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked"), age=121),
        "sentinel-b": "not-json",
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    payload = json.loads(result.stdout)
    assert payload["decision"] == "unknown"
    assert len(payload["monitoring_errors"]) == 2


def test_missing_required_profile_never_counts_toward_quorum(tmp_path: Path) -> None:
    incomplete = _all("blocked")
    incomplete.pop("p2-amneziawg")
    reports = {
        "sentinel-a": _report("tls-freeze-a", incomplete),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    assert json.loads(result.stdout)["decision"] == "unknown"


def test_configuration_rejects_duplicate_ids_and_impossible_quorum(tmp_path: Path) -> None:
    config = yaml.safe_load(_config(tmp_path).read_text())
    config["sentinels"][1]["id"] = config["sentinels"][0]["id"]
    config["policies"][0]["min_failed_vantages"] = 3
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(config))

    result = _run(tmp_path, path, {})

    assert result.returncode == 2
    assert "duplicate sentinel id" in result.stderr
    assert "exceeds assigned sentinels" in result.stderr


def test_recorded_candidate_streak_resets_on_recovery(tmp_path: Path) -> None:
    config = _config(tmp_path)
    state_dir = tmp_path / "state"
    blocked = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }
    healthy = {
        "sentinel-a": _report("tls-freeze-a", _all("ok")),
        "sentinel-b": _report("udp-filtered-b", _all("ok")),
    }

    base = int(time.time())
    for index, expected in enumerate((1, 2, 3)):
        result = _run(
            tmp_path,
            config,
            blocked,
            "--state-dir",
            str(state_dir),
            evaluated_at=base + index * 120,
        )
        assert json.loads(result.stdout)["candidate_streak"] == expected

    recovered = _run(tmp_path, config, healthy, "--state-dir", str(state_dir))

    assert json.loads(recovered.stdout)["candidate_streak"] == 0
    assert stat.S_IMODE((state_dir / "decision-state.json").stat().st_mode) == 0o600


def test_duplicate_evaluation_in_the_same_interval_does_not_advance_streak(tmp_path: Path) -> None:
    config = _config(tmp_path)
    state_dir = tmp_path / "state"
    blocked = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }
    slot_time = int(time.time())

    first = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=slot_time)
    duplicate = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=slot_time + 1)

    assert json.loads(first.stdout)["candidate_streak"] == 1
    assert json.loads(duplicate.stdout)["candidate_streak"] == 1


def test_crossing_a_wall_clock_boundary_early_does_not_advance_streak(tmp_path: Path) -> None:
    config = _config(tmp_path)
    state_dir = tmp_path / "state"
    blocked = {
        "sentinel-a": _report("tls-freeze-a", _all("blocked")),
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }
    first_at = 119

    first = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=first_at)
    too_soon = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=121)
    next_interval = _run(tmp_path, config, blocked, "--state-dir", str(state_dir), evaluated_at=239)

    assert json.loads(first.stdout)["candidate_streak"] == 1
    assert json.loads(too_soon.stdout)["candidate_streak"] == 1
    assert json.loads(next_interval.stdout)["candidate_streak"] == 2


def test_unknown_profile_in_report_is_monitoring_error(tmp_path: Path) -> None:
    invalid = _report("tls-freeze-a", _all("blocked"))
    invalid["profiles"].append({"profile": "p9-unknown", "verdict": "blocked"})
    reports = {
        "sentinel-a": invalid,
        "sentinel-b": _report("udp-filtered-b", _all("blocked")),
    }

    result = _run(tmp_path, _config(tmp_path), reports)

    payload = json.loads(result.stdout)
    assert payload["decision"] == "unknown"
    assert any("invalid profile result" in error for error in payload["monitoring_errors"])
