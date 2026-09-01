"""Focused contract tests for control-plane expected-target artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import yaml

from scripts.template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
RENDERER = ROLE / "files/observability-expected-target-renderer.py"
ADAPTER = ROLE / "files/observability-control-plane-adapter.py"


def _inventory() -> dict:
    return {
        "schema_version": 1,
        "generation": "inventory-v1",
        "source_id": "inventory-source-v1",
        "max_future_seconds": 30,
        "targets": [
            {
                "target": "vpn-p2",
                "role": "edge",
                "lifecycle": "enabled",
                "ever_seen": True,
                "label_values": {"node": ["vpn-p2"], "role": ["edge"]},
                "required_families": ["vpn_watchdog_collection_success"],
            },
            {
                "target": "vpn-p0",
                "role": "edge",
                "lifecycle": "enabled",
                "ever_seen": True,
                "label_values": {"node": ["vpn-p0"], "role": ["edge"]},
                "required_families": ["vpn_watchdog_collection_success"],
            },
        ],
    }


def _run_renderer(tmp_path: Path, inventory: dict) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "expected.json"
    output = tmp_path / "expected.prom"
    source.write_text(json.dumps(inventory), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--inventory",
            str(source),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_renderer_validates_and_deterministically_renders_bounded_targets(
    tmp_path: Path,
) -> None:
    result = _run_renderer(tmp_path, _inventory())

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "expected.prom").read_text(encoding="utf-8") == (
        "# TYPE vpn_observability_expected_target gauge\n"
        'vpn_observability_expected_target{node="vpn-p0",role="edge"} 1\n'
        'vpn_observability_expected_target{node="vpn-p2",role="edge"} 1\n'
    )


def test_renderer_refuses_duplicate_identity_or_unbounded_labels(
    tmp_path: Path,
) -> None:
    duplicate = _inventory()
    duplicate["targets"].append(duplicate["targets"][0])
    assert _run_renderer(tmp_path, duplicate).returncode == 2

    unbounded = _inventory()
    unbounded["targets"][0]["label_values"]["node"] = [
        f"node-{index}" for index in range(33)
    ]
    assert _run_renderer(tmp_path, unbounded).returncode == 2


def test_renderer_excludes_disabled_target_from_missing_target_series(
    tmp_path: Path,
) -> None:
    inventory = _inventory()
    inventory["targets"][0]["lifecycle"] = "disabled"

    result = _run_renderer(tmp_path, inventory)

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "expected.prom").read_text(encoding="utf-8")
    assert 'node="vpn-p2"' not in metrics
    assert 'node="vpn-p0"' in metrics


def test_resource_adapter_reports_source_deploy_resource_and_pipeline_states(
    tmp_path: Path,
) -> None:
    source = tmp_path / "expected.json"
    output = tmp_path / "control-plane.prom"
    data_dir = tmp_path / "data"
    source.write_text(json.dumps(_inventory()), encoding="utf-8")
    data_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--inventory",
            str(source),
            "--output",
            str(output),
            "--data-dir",
            str(data_dir),
            "--required-free-bytes",
            "1",
            "--expected-source-revision",
            "a" * 40,
            "--observed-source-revision",
            "b" * 40,
            "--expected-deployable-digest",
            "c" * 64,
            "--observed-deployable-digest",
            "c" * 64,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    metrics = output.read_text(encoding="utf-8")
    assert 'role="source-revision",state="mismatch"' in metrics
    assert 'role="deployable-digest",state="match"' in metrics
    assert 'role="tsdb-capacity",state="fresh"' in metrics
    assert 'role="expected-target-pipeline",state="fresh"' in metrics
    assert "a" * 40 not in metrics
    assert "c" * 64 not in metrics


def test_resource_adapter_replaces_pipeline_success_after_validation_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "expected.json"
    output = tmp_path / "control-plane.prom"
    data_dir = tmp_path / "data"
    source.write_text("{}", encoding="utf-8")
    data_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--inventory",
            str(source),
            "--output",
            str(output),
            "--data-dir",
            str(data_dir),
            "--required-free-bytes",
            "1",
            "--expected-source-revision",
            "a" * 40,
            "--observed-source-revision",
            "a" * 40,
            "--expected-deployable-digest",
            "b" * 64,
            "--observed-deployable-digest",
            "b" * 64,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert 'role="expected-target-pipeline",state="stale"' in output.read_text(
        encoding="utf-8"
    )


def test_rules_are_prometheus_rule_documents_without_notification_routes() -> None:
    rules = yaml.safe_load(
        (ROLE / "templates/observability-expected-target-rules.yml.j2").read_text()
    )
    assert set(rules) == {"groups"}
    names = {rule["alert"] for group in rules["groups"] for rule in group["rules"]}
    assert names == {
        "ObservabilityExpectedTargetMissing",
        "ObservabilityTargetEvidenceStale",
        "ObservabilitySourceIdentityMismatch",
        "ObservabilityControlPlaneResourceOrPipelineUnhealthy",
    }
    rendered = (
        ROLE / "templates/observability-expected-target-rules.yml.j2"
    ).read_text()
    assert "alertmanager" not in rendered.lower()
    assert "telegram" not in rendered.lower()
    assert "deadman" not in rendered.lower()


def test_role_wires_only_opted_in_expected_targets_into_immutable_config() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/expected-targets.yml").read_text())
    names = {task["name"] for task in tasks}
    assert {
        "Require a complete bounded expected-target adapter contract",
        "Render bounded expected-target metrics",
        "Publish immutable expected-target rules",
        "Enable bounded control-plane adapter timer",
    }.issubset(names)
    adapter_unit = (
        ROLE / "templates/observability-control-plane-adapter.service.j2"
    ).read_text()
    assert "ProtectSystem=strict" in adapter_unit
    assert (
        "ReadWritePaths={{ observability_control_plane.expected_targets.textfile_directory }}"
        in adapter_unit
    )
    prometheus = (ROLE / "templates/prometheus.yml.j2").read_text()
    assert "rule_files:" in prometheus
    assert "_observability_rules_generation" in prometheus
    assert "expected_targets | default" in prometheus


def test_prometheus_config_references_only_the_immutable_rules_generation() -> None:
    rendered = render_template(
        ROLE / "templates/prometheus.yml.j2",
        {
            "observability_control_plane": {
                "prometheus_listen": "127.0.0.1:9090",
                "config_root": "/etc/observability-control-plane",
                "expected_targets": {"enabled": True},
            },
            "_observability_rules_generation": "a" * 64,
        },
    )
    parsed = yaml.safe_load(rendered)
    assert parsed["rule_files"] == [
        "/etc/observability-control-plane/generations/" + ("a" * 64) + ".rules.yml"
    ]
