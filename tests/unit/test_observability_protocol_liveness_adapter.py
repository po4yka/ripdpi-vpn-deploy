"""Published protocol-liveness evidence adapter tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
ADAPTER = ROLE / "files/observability-protocol-liveness-adapter.py"


def _evidence(decision: str = "healthy", observed_at: int = 1_800_000_000) -> dict:
    return {
        "schema_version": 2,
        "evaluated_at": observed_at,
        "decision": decision,
        "candidate_policies": ["vpn-path"] if decision == "rotation_candidate" else [],
        "failed_vantages": {"vpn-path": 2},
        "monitoring_errors": [],
        "evidence": [
            {
                "sentinel": "sentinel-a",
                "policy": "vpn-path",
                "control": "ok",
                "profiles": {
                    "p0-reality": "ok",
                    "p1-xhttp": "blocked",
                    "p2-hysteria2": "throttled",
                    "p2-amneziawg": "error",
                },
                "observed_at": observed_at,
                "endpoint_variants": {
                    "p0-reality": [
                        {"variant": 1, "verdict": "blocked"},
                        {"variant": 2, "verdict": "ok"},
                    ]
                },
            }
        ],
    }


def _run(
    tmp_path: Path, document: dict, *, now: int = 1_800_000_010
) -> subprocess.CompletedProcess[str]:
    evidence = tmp_path / "last-evidence.json"
    output = tmp_path / "protocol-liveness.prom"
    evidence.write_text(json.dumps(document), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
            "--now",
            str(now),
            "--stale-after",
            "120",
            "--max-future",
            "30",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "decision",
    ["healthy", "degraded", "unknown", "rotation_candidate"],
)
def test_adapter_exports_every_canonical_decision_without_recomputing_it(
    tmp_path: Path, decision: str
) -> None:
    result = _run(tmp_path, _evidence(decision))

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    assert (
        f'role="liveness-decision-{decision.replace("_", "-")}",state="fresh"'
        in metrics
    )
    assert (
        'node="vpn-path",role="liveness-rotation-candidate",state="fresh"' in metrics
    ) is (decision == "rotation_candidate")
    assert "quorum" not in metrics


def test_adapter_exports_one_hot_profile_variant_control_and_timestamp_evidence(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, _evidence())

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    for role in (
        "liveness-control-ok",
        "liveness-p0-reality-ok",
        "liveness-p1-xhttp-blocked",
        "liveness-p2-hysteria2-throttled",
        "liveness-p2-amneziawg-error",
        "liveness-p0-reality-variant-1-blocked",
        "liveness-p0-reality-variant-2-ok",
        "liveness-evaluated-at",
        "liveness-observed-at",
    ):
        assert f'role="{role}",state="fresh"' in metrics
    assert "1800000000" in metrics
    assert "monitoring_errors" not in metrics


@pytest.mark.parametrize("verdict", ["ok", "blocked", "throttled", "error", "unknown"])
def test_adapter_preserves_each_canonical_profile_verdict_as_one_hot_evidence(
    tmp_path: Path, verdict: str
) -> None:
    document = _evidence()
    document["evidence"][0]["profiles"] = {"p0-reality": verdict}
    document["evidence"][0]["endpoint_variants"] = {}
    document["monitoring_errors"] = ["private-token-marker"]

    result = _run(tmp_path, document)

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    assert f'role="liveness-p0-reality-{verdict}",state="fresh"' in metrics
    assert "private-token-marker" not in metrics


@pytest.mark.parametrize(
    ("now", "expected"),
    [(1_800_000_121, "stale"), (1_799_999_969, "future")],
)
def test_adapter_fails_closed_for_stale_or_future_published_evidence(
    tmp_path: Path, now: int, expected: str
) -> None:
    result = _run(tmp_path, _evidence(), now=now)

    assert result.returncode == 2
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    assert f'role="liveness-published-evidence",state="{expected}"' in metrics
    assert "liveness-decision-healthy" not in metrics


def test_adapter_replaces_prior_verdict_with_malformed_evidence_state(
    tmp_path: Path,
) -> None:
    output = tmp_path / "protocol-liveness.prom"
    output.write_text("stale success\n", encoding="utf-8")
    invalid = _evidence()
    invalid["evidence"][0]["sentinel"] = "not an allowed label!"

    result = _run(tmp_path, invalid)

    assert result.returncode == 2
    assert 'role="liveness-published-evidence",state="malformed"' in output.read_text(
        encoding="utf-8"
    )
    assert "stale success" not in output.read_text(encoding="utf-8")


def test_adapter_refuses_symlinked_published_evidence(tmp_path: Path) -> None:
    target = tmp_path / "published.json"
    target.write_text(json.dumps(_evidence()), encoding="utf-8")
    evidence = tmp_path / "last-evidence.json"
    evidence.symlink_to(target)
    output = tmp_path / "protocol-liveness.prom"

    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
            "--now",
            "1800000010",
            "--stale-after",
            "120",
            "--max-future",
            "30",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert 'role="liveness-published-evidence",state="malformed"' in output.read_text(
        encoding="utf-8"
    )


def test_adapter_refuses_duplicate_sentinel_series_before_metric_publication(
    tmp_path: Path,
) -> None:
    document = _evidence()
    duplicate = dict(document["evidence"][0])
    duplicate["profiles"] = {"p2-amneziawg": "ok"}
    document["evidence"].append(duplicate)

    result = _run(tmp_path, document)

    assert result.returncode == 2
    assert 'role="liveness-published-evidence",state="malformed"' in (
        tmp_path / "protocol-liveness.prom"
    ).read_text(encoding="utf-8")


def test_adapter_template_consumes_only_published_evidence() -> None:
    service = (
        ROLE / "templates/observability-protocol-liveness-adapter.service.j2"
    ).read_text()
    assert "observability-protocol-liveness-adapter.py" in service
    assert "--evidence" in service
    assert "protocol-liveness.py" not in service
    assert "vpn-protocol-liveness" not in service
