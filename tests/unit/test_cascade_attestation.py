"""Public CLI contract for the fail-closed cascade ASN attestation gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-cascade-attestation.py"


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": 1,
        "host_id": "candidate-a",
        "asn_id": "AS64500",
        "attestation_date": "2026-07-10",
        "verified_not_brand_inferred": True,
        "attested_by_role": "cascade-attestation-operator",
        "verification_method": {
            "class": "ru-side-active-comparison",
            "report_id": "candidate-a-2026-07-10",
            "report_sha256": "a" * 64,
        },
        "next_recheck_date": "2026-07-17",
    }
    record.update(overrides)
    return record


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--attestation", str(path), "--today", "2026-07-14"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_missing_attestation_hard_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path / "missing.json")

    assert result.returncode != 0
    assert "missing" in result.stderr.lower()


def test_stale_attestation_hard_blocks(tmp_path: Path) -> None:
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(_record(attestation_date="2026-07-01", next_recheck_date="2026-07-08")))

    result = _run(path)

    assert result.returncode != 0
    assert "stale" in result.stderr.lower()


def test_brand_only_attestation_hard_blocks(tmp_path: Path) -> None:
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(_record(verified_not_brand_inferred=False)))

    result = _run(path)

    assert result.returncode != 0
    assert "brand" in result.stderr.lower()


def test_fresh_measured_attestation_passes(tmp_path: Path) -> None:
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(_record()))

    result = _run(path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "asn_id": "AS64500",
        "host_id": "candidate-a",
        "next_recheck_date": "2026-07-17",
        "status": "verified",
    }


def test_cadence_mismatch_hard_blocks(tmp_path: Path) -> None:
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(_record(next_recheck_date="2026-07-18")))

    result = _run(path)

    assert result.returncode != 0
    assert "seven" in result.stderr.lower()
