"""Behavioural coverage for the bounded node-manifest adapter."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "ansible" / "roles" / "observability_agent" / "files" / "observability-agent-adapter.py"


def _manifest(*, schema_version: int = 2, source_revision: str = "a" * 40) -> dict:
    return {
        "schema_version": schema_version,
        "source_revision": source_revision,
        "deployable_digest": "b" * 64,
        "environment": "prod",
        "provider": "test-provider",
    }


def _run(tmp_path: Path, document: dict) -> subprocess.CompletedProcess[str]:
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "observability-agent.prom"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    manifest.chmod(0o644)
    return subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--node-id",
            "edge-prod",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_adapter_emits_only_schema2_manifest_identity(tmp_path: Path) -> None:
    result = _run(tmp_path, _manifest())

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "observability-agent.prom").read_text(encoding="utf-8")
    assert 'vpn_observability_node_manifest_info{deployable_digest="' + "b" * 64 in metrics
    assert 'environment="prod",node_id="edge-prod",provider="test-provider"' in metrics
    assert "vpn_observability_adapter_collection_success 1" in metrics
    assert (tmp_path / "observability-agent.prom").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "document",
    [
        _manifest(schema_version=1),
        _manifest(source_revision="not-a-revision"),
        {"schema_version": 2},
    ],
)
def test_adapter_refuses_non_schema2_or_unbounded_manifest(tmp_path: Path, document: dict) -> None:
    result = _run(tmp_path, document)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "observability-agent-adapter:" in result.stderr
    assert "vpn_observability_adapter_collection_success 0" in (
        tmp_path / "observability-agent.prom"
    ).read_text(encoding="utf-8")
