"""Schema tests for topology-aware probe-matrix operator artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "contract" / name).read_text(encoding="utf-8"))


def test_matrix_config_example_conforms_to_v2_schema() -> None:
    document = yaml.safe_load((ROOT / "vpnd/config/probe-matrix.example.yaml").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(_schema("probe-matrix-config.schema.json")).validate(document)


def test_target_profile_example_conforms_to_schema_without_real_secrets() -> None:
    document = json.loads((ROOT / "vpnd/config/probe-matrix-target.example.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(_schema("probe-matrix-target.schema.json")).validate(document)
    assert "REPLACE_WITH" in json.dumps(document)


def test_report_snapshot_conforms_to_v3_schema_and_contains_no_endpoint() -> None:
    snapshot = (ROOT / "vpnd/tests/snapshots/probe_matrix_snapshot__probe_matrix_report.snap").read_text(encoding="utf-8")
    document = json.loads(snapshot.rsplit("---\n", 1)[1])
    jsonschema.Draft202012Validator(_schema("probe-matrix-report.schema.json")).validate(document)
    assert document["schema_version"] == 3
    assert document["completed"] is True
    assert document["interrupted"] is False
    assert "endpoint" not in json.dumps(document)


def test_report_contract_rejects_an_impossible_terminal_state() -> None:
    snapshot = (ROOT / "vpnd/tests/snapshots/probe_matrix_snapshot__probe_matrix_report.snap").read_text(encoding="utf-8")
    document = json.loads(snapshot.rsplit("---\n", 1)[1])
    document["completed"] = True
    document["interrupted"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_schema("probe-matrix-report.schema.json")).validate(document)


def test_report_contract_accepts_an_interrupted_terminal_state() -> None:
    snapshot = (ROOT / "vpnd/tests/snapshots/probe_matrix_snapshot__probe_matrix_report.snap").read_text(encoding="utf-8")
    document = json.loads(snapshot.rsplit("---\n", 1)[1])
    document["completed"] = False
    document["interrupted"] = True
    jsonschema.Draft202012Validator(_schema("probe-matrix-report.schema.json")).validate(document)
