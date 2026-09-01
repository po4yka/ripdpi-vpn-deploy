"""Focused contract tests for control-plane expected-target artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib

import yaml

from scripts.template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
RENDERER = ROLE / "files/observability-expected-target-renderer.py"
ADAPTER = ROLE / "files/observability-control-plane-adapter.py"
PROMTOOL_VERSION = "3.14.0"


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
    assert result.stdout.strip() == "changed"
    assert (tmp_path / "expected.prom").read_text(encoding="utf-8") == (
        "# TYPE vpn_observability_expected_target gauge\n"
        'vpn_observability_expected_target{node="vpn-p0",role="edge"} 1\n'
        'vpn_observability_expected_target{node="vpn-p2",role="edge"} 1\n'
        'vpn_observability_expected_target_ever_seen{node="vpn-p2",role="edge",state="seen"} 1\n'
        'vpn_observability_expected_target_ever_seen{node="vpn-p0",role="edge",state="seen"} 1\n'
    )
    published = (tmp_path / "expected.prom").stat()
    repeated = _run_renderer(tmp_path, _inventory())
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout.strip() == "unchanged"
    assert (tmp_path / "expected.prom").stat().st_ino == published.st_ino


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


def test_renderer_accepts_shared_textfile_directory_and_publishes_collector_readable_output(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "textfile"
    shared.mkdir()
    shared.chmod(0o3775)
    source = tmp_path / "expected.json"
    source.write_text(json.dumps(_inventory()), encoding="utf-8")
    output = shared / "observability-expected-targets.prom"

    result = subprocess.run(
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

    assert result.returncode == 0, result.stderr
    output_stat = output.stat()
    assert stat.S_IMODE(output_stat.st_mode) == 0o640
    assert output_stat.st_gid == shared.stat().st_gid
    assert output_stat.st_mode & stat.S_IRGRP
    if os.geteuid() == 0:
        # Exercise the collector's group-read contract with a distinct uid.
        reader = (
            "import os,sys; "
            "os.setgroups([int(sys.argv[2])]); "
            "os.setgid(int(sys.argv[2])); os.setuid(65534); "
            "open(sys.argv[1]).read()"
        )
        assert (
            subprocess.run(
                [sys.executable, "-c", reader, str(output), str(output_stat.st_gid)]
            ).returncode
            == 0
        )


def test_renderer_exports_never_seen_separately_from_seen_target(
    tmp_path: Path,
) -> None:
    inventory = _inventory()
    inventory["targets"][0]["ever_seen"] = False
    result = _run_renderer(tmp_path, inventory)
    assert result.returncode == 0
    text = (tmp_path / "expected.prom").read_text()
    assert 'node="vpn-p2",role="edge",state="never-seen"' in text
    assert 'node="vpn-p0",role="edge",state="seen"' in text


def test_promtool_rules_require_matching_family_and_respect_ever_seen(
    tmp_path: Path,
) -> None:
    promtool = shutil.which("promtool")
    assert (
        promtool is not None
    ), f"promtool {PROMTOOL_VERSION} is required; run mise install"
    version = subprocess.run(
        [promtool, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert version.returncode == 0, version.stdout + version.stderr
    assert re.search(
        rf"\bversion {re.escape(PROMTOOL_VERSION)}\b",
        version.stdout + version.stderr,
    ), (
        version.stdout + version.stderr
    )

    inventory = _inventory()
    inventory["targets"][0]["ever_seen"] = False
    (tmp_path / "rules.yml").write_text(
        render_template(
            ROLE / "templates/observability-expected-target-rules.yml.j2",
            {
                "observability_control_plane": {
                    "expected_targets": {"inventory": inventory}
                }
            },
        ),
        encoding="utf-8",
    )
    (tmp_path / "rules.test.yml").write_text(
        "\n".join(
            [
                "rule_files:",
                "  - rules.yml",
                "evaluation_interval: 1m",
                "tests:",
                "  - interval: 1m",
                "    input_series:",
                '      - series: \'vpn_observability_expected_target{node="vpn-p0",role="edge"}\'',
                "        values: '1 1 1 1 1'",
                '      - series: \'vpn_observability_expected_target{node="vpn-p2",role="edge"}\'',
                "        values: '1 1 1 1 1'",
                '      - series: \'vpn_observability_expected_target_ever_seen{node="vpn-p0",role="edge",state="never-seen"}\'',
                "        values: '1 1 1 1 1'",
                '      - series: \'vpn_observability_expected_target_ever_seen{node="vpn-p2",role="edge",state="seen"}\'',
                "        values: '1 1 1 1 1'",
                '      - series: \'vpn_observability_evidence_state{node="vpn-p0",role="edge",state="fresh"}\'',
                "        values: '1 1 1 1 1'",
                '      - series: \'vpn_observability_evidence_state{node="vpn-p2",role="edge",state="fresh"}\'',
                "        values: '1 1 1 1 1'",
                '      - series: \'unrelated_metric{node="vpn-p0",role="edge"}\'',
                "        values: '1 1 1 1 1'",
                '      - series: \'vpn_watchdog_collection_success{node="vpn-p2",role="edge"}\'',
                "        values: '1 1 1 1 1'",
                "    alert_rule_test:",
                "      - eval_time: 4m",
                "        alertname: ObservabilityRequiredFamilyMissing_vpn_p0_edge_vpn_watchdog_collection_success",
                "        exp_alerts:",
                "          - exp_labels: {severity: warning, node: vpn-p0, role: edge}",
                "            exp_annotations: {summary: Required bounded evidence family is absent for an expected target.}",
                "      - eval_time: 4m",
                "        alertname: ObservabilityExpectedTargetNeverSeen_vpn_p0_edge",
                "        exp_alerts:",
                "          - exp_labels: {severity: warning, node: vpn-p0, role: edge, state: never-seen}",
                "            exp_annotations: {summary: Expected target has never produced its required evidence.}",
                "      - eval_time: 4m",
                "        alertname: ObservabilityRequiredFamilyMissing_vpn_p2_edge_vpn_watchdog_collection_success",
                "        exp_alerts: []",
                "      - eval_time: 4m",
                "        alertname: ObservabilityExpectedTargetNeverSeen_vpn_p2_edge",
                "        exp_alerts: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [promtool, "test", "rules", "rules.test.yml"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_promtool_parser_pin_is_canonical_across_local_and_hosted_gates() -> None:
    mise = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert mise["tools"]["aqua:prometheus/prometheus"] == PROMTOOL_VERSION
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert f"PROMTOOL_VERSION := {PROMTOOL_VERSION}" in makefile
    assert "promtool --version" in makefile
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert f'PROMTOOL_VERSION: "{PROMTOOL_VERSION}"' in workflow
    assert "PROMETHEUS_LINUX_AMD64_SHA256" in workflow


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
    rendered = render_template(
        ROLE / "templates/observability-expected-target-rules.yml.j2",
        {
            "observability_control_plane": {
                "expected_targets": {"inventory": _inventory()}
            }
        },
    )
    rules = yaml.safe_load(rendered)
    assert set(rules) == {"groups"}
    names = {rule["alert"] for group in rules["groups"] for rule in group["rules"]}
    assert names == {
        "ObservabilityExpectedTargetMissing",
        "ObservabilityTargetEvidenceStale",
        "ObservabilitySourceIdentityMismatch",
        "ObservabilityControlPlaneResourceOrPipelineUnhealthy",
        "ObservabilityRequiredFamilyMissing_vpn_p0_edge_vpn_watchdog_collection_success",
        "ObservabilityRequiredFamilyMissing_vpn_p2_edge_vpn_watchdog_collection_success",
        "ObservabilityExpectedTargetNeverSeen_vpn_p0_edge",
        "ObservabilityExpectedTargetNeverSeen_vpn_p2_edge",
    }
    template = (
        ROLE / "templates/observability-expected-target-rules.yml.j2"
    ).read_text()
    assert "alertmanager" not in template.lower()
    assert "telegram" not in template.lower()
    assert "deadman" not in template.lower()
    assert "vpn_watchdog_collection_success" in rendered
    assert 'node=~"^(vpn-p0)$"' in rendered
    assert 'role=~"^(edge)$"' in rendered


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
    enable = (ROLE / "tasks/enable.yml").read_text()
    assert "Remove disabled expected-target observation artifacts" in enable
    assert "expected-targets-disable.yml" in enable
    disable = (ROLE / "tasks/disable.yml").read_text()
    assert "observability-control-plane-adapter.timer" in disable
    assert "/usr/local/libexec/observability-expected-target-renderer.py" in disable
    assert "observability-control-plane.prom" in disable
    enabled_scenario = yaml.safe_load(
        (ROLE / "molecule/enabled/molecule.yml").read_text()
    )
    assert "side_effect" in enabled_scenario["scenario"]["test_sequence"]
    opt_out = (ROLE / "molecule/enabled/side_effect.yml").read_text()
    enabled_verify = (ROLE / "molecule/enabled/verify.yml").read_text()
    fixture_contract_path = ROLE / "molecule/enabled/tasks/fixture-contract.yml"
    fixture_contract = yaml.safe_load(fixture_contract_path.read_text())
    fixture_config = fixture_contract[-1]["ansible.builtin.set_fact"][
        "observability_control_plane"
    ]
    assert fixture_config["expected_targets"]["enabled"] is True
    assert "roles:" in opt_out
    assert "role: observability_control_plane" in opt_out
    assert "combine({'enabled': false})" in opt_out
    assert "tasks_from: expected-targets-disable.yml" not in opt_out
    assert "observability-prometheus" in enabled_verify
    assert "molecule-retained" in enabled_verify
    assert "observability-control-plane.prom" in enabled_verify


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
