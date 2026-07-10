"""End-to-end behavior at the liveness decision -> OTP promotion seam."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WATCHER = REPO_ROOT / "scripts" / "warm-spare-watcher.sh"
PROMOTE = REPO_ROOT / "scripts" / "promote-spare.sh"


def _exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _setup(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    config = tmp_path / "liveness.yaml"
    config.write_text("schema_version: 1\n")
    decision = tmp_path / "decision.json"
    evaluator = tmp_path / "protocol-liveness"
    _exe(evaluator, "#!/usr/bin/env bash\ncat \"$FAKE_DECISION\"\n")
    blue_green_log = tmp_path / "blue-green.log"
    blue_green = tmp_path / "blue-green"
    _exe(blue_green, "#!/usr/bin/env bash\nprintf 'called\\n' >> \"$BLUE_GREEN_LOG\"\n")
    env = os.environ.copy()
    env.update(
        {
            "LIVENESS_CONFIG": str(config),
            "PROTOCOL_LIVENESS": str(evaluator),
            "FAKE_DECISION": str(decision),
            "VPN_SPARE_STATE_DIR": str(tmp_path / "state"),
            "PROVIDER": "upcloud",
            "BLUE_ENV": "prod",
            "GREEN_ENV": "spare",
            "BLUE_GREEN_SCRIPT": str(blue_green),
            "BLUE_GREEN_LOG": str(blue_green_log),
        }
    )
    return env, decision, blue_green_log


def _decision(path: Path, decision: str, streak: int) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "decision": decision,
                "candidate_streak": streak,
                "failure_threshold": 3,
                "otp_ttl_seconds": 3600,
                "config_sha256": "config-hash",
                "candidate_policies": ["fullstack"] if decision == "rotation_candidate" else [],
                "failed_vantages": {"fullstack": 2},
                "monitoring_errors": [] if decision != "unknown" else ["sentinel unavailable"],
            }
        )
    )


def _run(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args], text=True, capture_output=True, env=env, check=False
    )


def test_otp_is_issued_only_after_sustained_quorum_failure(tmp_path: Path) -> None:
    env, decision, blue_green_log = _setup(tmp_path)
    otp = Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp"

    for streak in (1, 2):
        _decision(decision, "rotation_candidate", streak)
        result = _run(WATCHER, env)
        assert result.returncode == 0
        assert not otp.exists()
    _decision(decision, "rotation_candidate", 3)
    result = _run(WATCHER, env)

    assert result.returncode == 0
    assert otp.stat().st_mode & 0o777 == 0o600
    assert "make promote-spare OTP=" in result.stdout
    assert not blue_green_log.exists()


def test_unknown_or_recovered_evidence_invalidates_pending_otp(tmp_path: Path) -> None:
    env, decision, _ = _setup(tmp_path)
    _decision(decision, "rotation_candidate", 3)
    _run(WATCHER, env)
    otp = Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp"
    assert otp.exists()

    _decision(decision, "unknown", 0)
    result = _run(WATCHER, env)

    assert result.returncode == 0
    assert not otp.exists()
    assert "monitoring degraded" in result.stdout


def test_promotion_rechecks_and_refuses_a_recovered_signal(tmp_path: Path) -> None:
    env, decision, blue_green_log = _setup(tmp_path)
    _decision(decision, "rotation_candidate", 3)
    _run(WATCHER, env)
    otp_file = Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp"
    otp = otp_file.read_text().split("\t", 1)[0]
    _decision(decision, "healthy", 0)

    result = _run(PROMOTE, env, otp)

    assert result.returncode != 0
    assert "no longer a rotation candidate" in result.stderr
    assert not blue_green_log.exists()
    assert not otp_file.exists()


def test_promotion_accepts_only_the_bound_current_candidate(tmp_path: Path) -> None:
    env, decision, blue_green_log = _setup(tmp_path)
    _decision(decision, "rotation_candidate", 3)
    _run(WATCHER, env)
    otp = (Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp").read_text().split("\t", 1)[0]

    result = _run(PROMOTE, env, otp)

    assert result.returncode == 0, result.stderr
    assert blue_green_log.read_text() == "called\n"


def test_existing_otp_is_not_rebound_to_a_changed_policy(tmp_path: Path) -> None:
    env, decision, _ = _setup(tmp_path)
    _decision(decision, "rotation_candidate", 3)
    _run(WATCHER, env)
    otp_file = Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp"
    original = otp_file.read_text().split("\t", 1)[0]
    changed = json.loads(decision.read_text())
    changed["candidate_policies"] = ["alternate"]
    decision.write_text(json.dumps(changed))

    _run(WATCHER, env)

    replacement = otp_file.read_text().split("\t", 1)[0]
    assert replacement != original


@pytest.mark.parametrize("decision_name", ["healthy", "degraded", "unknown"])
def test_non_candidate_decisions_never_issue_or_execute_promotion(tmp_path: Path, decision_name: str) -> None:
    env, decision, blue_green_log = _setup(tmp_path)
    _decision(decision, decision_name, 0)

    result = _run(WATCHER, env)

    assert result.returncode == 0
    assert not (Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp").exists()
    assert not blue_green_log.exists()


def test_expired_otp_is_rejected_before_promotion(tmp_path: Path) -> None:
    env, decision, blue_green_log = _setup(tmp_path)
    _decision(decision, "rotation_candidate", 3)
    _run(WATCHER, env)
    otp_file = Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp"
    otp = otp_file.read_text().split("\t", 1)[0]
    otp_file.write_text(f"{otp}\t{int(time.time()) - 3601}\n")

    result = _run(PROMOTE, env, otp)

    assert result.returncode != 0
    assert "OTP expired" in result.stderr
    assert not blue_green_log.exists()


@pytest.mark.parametrize(
    ("changed_env", "changed_decision"),
    [
        ({"PROVIDER": "vultr"}, {}),
        ({"BLUE_ENV": "alternate"}, {}),
        ({"GREEN_ENV": "other-spare"}, {}),
        ({}, {"config_sha256": "changed-config"}),
    ],
)
def test_promotion_rejects_changed_binding(
    tmp_path: Path, changed_env: dict[str, str], changed_decision: dict[str, str]
) -> None:
    env, decision, blue_green_log = _setup(tmp_path)
    _decision(decision, "rotation_candidate", 3)
    _run(WATCHER, env)
    otp = (Path(env["VPN_SPARE_STATE_DIR"]) / "pending-otp").read_text().split("\t", 1)[0]
    env.update(changed_env)
    current = json.loads(decision.read_text())
    current.update(changed_decision)
    decision.write_text(json.dumps(current))

    result = _run(PROMOTE, env, otp)

    assert result.returncode != 0
    assert "binding changed" in result.stderr
    assert not blue_green_log.exists()
