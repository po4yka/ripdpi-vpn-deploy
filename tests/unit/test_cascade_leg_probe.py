"""Operator-side authenticated cascade leg probe behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "cascade-leg-probe.py"
CHECKER = ROOT / "scripts" / "check-cascade-leg-health.py"


def _write_fake_curl(tmp_path: Path) -> Path:
    script = tmp_path / "curl"
    script.write_text(
        """#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
interface = args[args.index('--interface') + 1]
output = pathlib.Path(args[args.index('--output') + 1])
config = sys.stdin.read()
scenario = json.loads(pathlib.Path(os.environ['CASCADE_PROBE_SCENARIO']).read_text())
assert 'Authorization: Bearer test-secret' in config
result = scenario['control' if interface == 'direct0' else 'leg']
if result['ok']:
    output.write_text(result.get('body', 'authenticated-ok'))
    print(result.get('status', '204'), end='')
    raise SystemExit(0)
print(result.get('status', '000'), end='')
raise SystemExit(22)
"""
    )
    script.chmod(0o755)
    return script


def _run(tmp_path: Path, *, leg_ok: bool, control_ok: bool) -> subprocess.CompletedProcess[str]:
    curl = _write_fake_curl(tmp_path)
    config = tmp_path / "config.json"
    token = tmp_path / "token"
    state = tmp_path / "state.json"
    health = tmp_path / "health.json"
    evidence = tmp_path / "evidence"
    scenario = tmp_path / "scenario.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "host_id": "candidate-entry",
                "leg_id": "entry-to-egress",
                "probe_url": "https://controlled.invalid/cascade-leg",
                "expected_status": 204,
                "expected_body_sha256": "8432ed21711566c6c045fe66af528b301cbb6dbd479023bd7047d23e86764391",
                "leg_interface": "csi0",
                "direct_interface": "direct0",
                "timeout_seconds": 5,
                "failure_threshold": 3,
            }
        )
    )
    token.write_text("test-secret\n")
    token.chmod(0o600)
    scenario.write_text(json.dumps({"leg": {"ok": leg_ok}, "control": {"ok": control_ok}}))
    env = {**os.environ, "CASCADE_PROBE_SCENARIO": str(scenario)}
    return subprocess.run(
        [
            sys.executable,
            str(PROBE),
            "--config",
            str(config),
            "--token-file",
            str(token),
            "--state-file",
            str(state),
            "--health-record",
            str(health),
            "--evidence-dir",
            str(evidence),
            "--curl-bin",
            str(curl),
            "--now",
            "2026-07-11T10:00:00Z",
        ],
        text=True,
        capture_output=True,
        env=env,
    )


def test_healthy_authenticated_completion_writes_valid_redacted_record(tmp_path: Path) -> None:
    result = _run(tmp_path, leg_ok=True, control_ok=True)
    health = json.loads((tmp_path / "health.json").read_text())
    report = next((tmp_path / "evidence").glob("*.json")).read_text()

    assert result.returncode == 0, result.stderr
    assert health["status"] == "healthy"
    assert health["protocol_completed"] is True
    assert health["consecutive_failures"] == 0
    assert "test-secret" not in report
    assert "controlled.invalid" not in report
    checked = subprocess.run(
        [sys.executable, str(CHECKER), "--health-record", str(tmp_path / "health.json"), "--now", "2026-07-11T10:01:00Z"],
        text=True,
        capture_output=True,
    )
    assert checked.returncode == 0, checked.stderr


def test_three_leg_failures_with_healthy_control_become_far_leg_down(tmp_path: Path) -> None:
    statuses = []
    for _ in range(3):
        result = _run(tmp_path, leg_ok=False, control_ok=True)
        assert result.returncode != 0
        statuses.append(json.loads((tmp_path / "health.json").read_text())["status"])

    assert statuses == ["degraded", "degraded", "far-leg-down"]


def test_unhealthy_direct_control_never_accuses_far_leg(tmp_path: Path) -> None:
    for _ in range(4):
        result = _run(tmp_path, leg_ok=False, control_ok=False)
        assert result.returncode != 0
        health = json.loads((tmp_path / "health.json").read_text())
        assert health["status"] == "degraded"
        assert health["ingress_local_control"] == "unhealthy"
        assert health["consecutive_failures"] == 1


def test_missing_token_blocks_without_health_claim(tmp_path: Path) -> None:
    curl = _write_fake_curl(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(PROBE),
            "--config",
            str(tmp_path / "missing-config.json"),
            "--token-file",
            str(tmp_path / "missing-token"),
            "--state-file",
            str(tmp_path / "state.json"),
            "--health-record",
            str(tmp_path / "health.json"),
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--curl-bin",
            str(curl),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert not (tmp_path / "health.json").exists()
