"""Fail-closed registration contract for cascade per-leg health evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-cascade-leg-health.py"


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": 1,
        "host_id": "candidate-a",
        "leg_id": "primary-leg",
        "checked_at": "2026-07-11T06:00:00Z",
        "signal_class": "authenticated-protocol-completion",
        "status": "healthy",
        "consecutive_failures": 0,
        "ingress_local_control": "healthy",
        "protocol_completed": True,
        "evidence": {"report_id": "primary-leg-2026-07-11t060000z", "report_sha256": "b" * 64},
    }
    record.update(overrides)
    return record


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--health-record", str(path), "--now", "2026-07-11T06:09:00Z"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_missing_health_record_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path / "missing.json")

    assert result.returncode != 0
    assert "missing" in result.stderr


def test_stale_health_record_blocks(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    path.write_text(json.dumps(_record(checked_at="2026-07-11T05:58:59Z")))

    result = _run(path)

    assert result.returncode != 0
    assert "stale" in result.stderr


def test_transient_degraded_state_blocks(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    path.write_text(json.dumps(_record(status="degraded", consecutive_failures=1, protocol_completed=False)))

    result = _run(path)

    assert result.returncode != 0
    assert "degraded" in result.stderr


def test_far_leg_down_state_blocks(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    path.write_text(json.dumps(_record(status="far-leg-down", consecutive_failures=3, protocol_completed=False)))

    result = _run(path)

    assert result.returncode != 0
    assert "far-leg-down" in result.stderr


def test_fresh_authenticated_completion_passes(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    path.write_text(json.dumps(_record()))

    result = _run(path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"host_id": "candidate-a", "leg_id": "primary-leg", "status": "healthy"}
