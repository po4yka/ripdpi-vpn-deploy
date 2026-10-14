"""Producer/consumer regressions for truthful monitoring source evidence."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.template_render import merge_render_vars, render_template
from tests.unit import test_observability_agent_health_adapter as health

ROOT = Path(__file__).resolve().parents[2]
tmp_path = health.tmp_path


@pytest.mark.parametrize("previous_mode", [None, 0o640])
def test_actual_watchdog_writer_output_is_consumed(
    tmp_path: Path, previous_mode
) -> None:
    root = tmp_path
    paths = health._write_inputs(root)
    state = paths[0]
    if previous_mode is None:
        state.unlink()
    else:
        state.chmod(previous_mode)
    writer = ROOT / "ansible/roles/watchdog/files/vpn-watchdog-state.py"
    result = subprocess.run(
        [sys.executable, str(writer), "write", str(state)],
        input=health._watchdog_state(consecutive_fails=3, kicks_this_hour=1),
        text=True,
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert state.stat().st_mode & 0o777 == 0o600
    adapter = health._adapter_module()
    evidence = adapter._parse_watchdog(state, 900, int(adapter.time.time()))
    metrics = "\n".join(adapter._render_watchdog("vpn-p0", evidence))
    assert 'state="failed"' in metrics
    assert 'state="unresolved"' in metrics
    recovered = subprocess.run(
        [sys.executable, str(writer), "write", str(state)],
        input=health._watchdog_state(consecutive_fails=0, kicks_this_hour=1),
        text=True,
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert recovered.returncode == 0, recovered.stderr
    evidence = adapter._parse_watchdog(state, 900, int(adapter.time.time()))
    metrics = "\n".join(adapter._render_watchdog("vpn-p0", evidence))
    assert 'state="healthy"' in metrics
    assert 'state="recovered"' in metrics


@pytest.mark.parametrize("field", ["stage", "restore"])
@pytest.mark.parametrize("value", [[], {}])
def test_nested_scalar_replaces_prior_healthy_metrics(tmp_path, field, value):
    root = tmp_path
    ok, before, _ = health._run(root)
    assert ok.returncode == 0, ok.stderr
    assert 'state="healthy"' in before
    if field == "stage":
        stage = health._backup_stage(local_backup={"result": value})
        result, after, _ = health._run(root, stage=stage)
        assert (
            'vpn_backup_collection_success{node="edge-prod",role="stage-status"} 0'
            in after
        )
        assert "vpn_backup_result" not in after
    else:
        restore = health._restore_marker()
        restore["repository_source"] = value
        result, after, _ = health._run(root, restore=restore)
        assert (
            'vpn_backup_collection_success{node="edge-prod",role="restore-drill"} 0'
            in after
        )
        assert "vpn_backup_restore_source" not in after
    assert result.returncode == 2
    assert result.stderr == "observability-health-adapter: collection failed\n"


def test_health_output_carries_producer_and_completion_deadlines(tmp_path):
    root = tmp_path
    result, metrics, _ = health._run(root)
    assert result.returncode == 0, result.stderr
    for role, maximum in [
        ("watchdog", 900),
        ("stage-status", 129600),
        ("restore-drill", 3024000),
        ("restore-snapshot", 3153600),
        ("health-adapter", 180),
    ]:
        labels = f'{{node="edge-prod",role="{role}"}}'
        assert f"vpn_observability_evidence_timestamp_seconds{labels}" in metrics
        assert (
            f"vpn_observability_evidence_max_age_seconds{labels} {maximum}" in metrics
        )


def test_service_expectations_follow_effective_profile():
    template = (
        ROOT
        / "ansible/roles/observability_agent/templates/observability-agent-health-adapter.service.j2"
    )
    values = merge_render_vars()
    values.update(
        {
            "vpn": {
                "enable_xray_reality": True,
                "enable_nginx_xhttp": False,
                "enable_naive": False,
                "enable_hysteria": False,
            },
            "observability_agent": {
                "enabled": True,
                "credential_dir": "/etc/observability-agent/credentials",
                "node_id": "vpn-p0",
            },
            "observability_control_plane": {"enabled": False},
            "observability_alert_policy": {
                "required_systemd_units": [
                    "nginx.service",
                    "xray.service",
                    "observability-agent.service",
                ]
            },
        }
    )
    rendered = render_template(template, values)
    assert "--required-service xray" in rendered
    assert "--required-service observability-agent" in rendered
    assert "--required-service nginx" not in rendered


def _rules(*, expected_nodes=("vpn-p0",), optional_enabled=False):
    import yaml

    from tests.unit.test_observability_control_plane_alerting import _alert_policy

    context = {
        "observability_alert_policy": _alert_policy(),
        "observability_push": {
            "node_id": "vpn-p0",
            "expected_nodes": list(expected_nodes),
        },
        "observability_control_plane": {
            "expected_targets": {"enabled": optional_enabled},
            "protocol_liveness": {"enabled": optional_enabled},
            "alerting": {
                "source_generation": "c" * 40,
                "recovery_stability": "3m",
                "silence_gateway": {"environment": "staging"},
            },
        },
    }
    path = (
        ROOT
        / "ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2"
    )
    return yaml.safe_load(render_template(path, context))


def _run_rule_cases(tmp_path, document, cases, evaluation_interval="1m"):
    import shutil

    import yaml

    binary = shutil.which("promtool")
    assert binary is not None
    rules_path = tmp_path / "rules.yml"
    rules_path.write_text(yaml.safe_dump(document))
    test_path = tmp_path / "rules.test.yml"
    test_path.write_text(
        yaml.safe_dump(
            {
                "rule_files": [str(rules_path)],
                "evaluation_interval": evaluation_interval,
                "tests": cases,
            }
        )
    )
    result = subprocess.run(
        [binary, "test", "rules", str(test_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _rule(document, name):
    return next(
        rule
        for group in document["groups"]
        for rule in group["rules"]
        if rule.get("alert") == name
    )


def _expected(rule, role):
    return {
        "exp_labels": {**rule["labels"], "node": "edge-prod", "role": role},
        "exp_annotations": rule["annotations"],
    }


def _deadline_pair(metrics, role):
    labels = f'{{node="edge-prod",role="{role}"}}'
    samples = {}
    for line in metrics.splitlines():
        if labels in line and line.startswith("vpn_observability_evidence_"):
            name, raw = line.rsplit(" ", 1)
            samples[name] = int(raw)
    assert len(samples) == 2
    return samples


@pytest.mark.parametrize(
    "role",
    ["watchdog", "stage-status", "restore-drill", "restore-snapshot", "health-adapter"],
)
def test_real_health_deadlines_expire_frozen_scrapes_and_recover(tmp_path, role):
    result, metrics, _ = health._run(tmp_path)
    assert result.returncode == 0, result.stderr
    pair = _deadline_pair(metrics, role)
    deadline = next(value for name, value in pair.items() if "max_age" in name)
    minutes = (deadline // 3600 + 3) * 60
    recovery = minutes * 60
    series = [
        {
            "series": name,
            "values": (
                f"0x{minutes - 1} {recovery}+60x360"
                if "timestamp" in name
                else f"{value}x{minutes + 360}"
            ),
        }
        for name, value in pair.items()
    ]
    document = _rules()
    rule = _rule(document, "ObservabilityProducerEvidenceUnavailable")
    # Evaluate the actual deadline rule alone over its multi-week producer budget;
    # the unrelated 30-second canary does not participate in this boundary.
    document = {"groups": [{"name": "producer-deadlines", "rules": [rule]}]}
    _run_rule_cases(
        tmp_path,
        document,
        [
            {
                "interval": "1m",
                "input_series": series,
                "alert_rule_test": [
                    {"eval_time": "0m", "alertname": rule["alert"], "exp_alerts": []},
                    {
                        "eval_time": f"{minutes - 60}m",
                        "alertname": rule["alert"],
                        "exp_alerts": [_expected(rule, role)],
                    },
                    {
                        "eval_time": f"{minutes + 240}m",
                        "alertname": rule["alert"],
                        "exp_alerts": [],
                    },
                ],
            }
        ],
        evaluation_interval="1h",
    )


@pytest.mark.parametrize(
    "fault", ["timestamp-absent", "age-absent", "future", "invalid-age"]
)
def test_central_deadlines_reject_incomplete_future_or_invalid_pairs(tmp_path, fault):
    result, metrics, _ = health._run(tmp_path)
    assert result.returncode == 0, result.stderr
    pair = _deadline_pair(metrics, "watchdog")
    series = []
    for name, value in pair.items():
        is_clock = "timestamp" in name
        if (fault == "timestamp-absent" and is_clock) or (
            fault == "age-absent" and not is_clock
        ):
            values = "_x9 " + ("600x6" if is_clock else f"{value}x6")
        elif is_clock:
            values = ("86400x9" if fault == "future" else "0x9") + " 600x6"
        else:
            values = ("0x9" if fault == "invalid-age" else f"{value}x9") + f" {value}x6"
        series.append({"series": name, "values": values})
    document = _rules()
    rule = _rule(document, "ObservabilityProducerEvidenceUnavailable")
    _run_rule_cases(
        tmp_path,
        document,
        [
            {
                "interval": "1m",
                "input_series": series,
                "alert_rule_test": [
                    {
                        "eval_time": "4m",
                        "alertname": rule["alert"],
                        "exp_alerts": [_expected(rule, "watchdog")],
                    },
                    {"eval_time": "15m", "alertname": rule["alert"], "exp_alerts": []},
                ],
            }
        ],
    )


@pytest.mark.parametrize("coverage", ["partial", "all", "failed", "disabled"])
def test_required_service_pairs_distinguish_absence_failure_and_recovery(
    tmp_path, coverage
):
    adapter = health._adapter_module()
    desired = [
        adapter._sample(
            "vpn_observability_required_service", 1, node="edge-prod", role=role
        )
        for role in ["nginx", "xray"]
    ]
    series = [
        {"series": sample.rsplit(" ", 1)[0], "values": "1x15"} for sample in desired
    ]
    for role in ["nginx", "xray", "caddy-naive"]:
        if coverage == "all" or (coverage == "partial" and role == "xray"):
            values = "_x9 1x6"
        elif coverage == "failed" and role == "xray":
            values = "0x9 1x6"
        elif role == "caddy-naive":
            values = "0x15"
        else:
            values = "1x15"
        series.append(
            {
                "series": f'node_systemd_unit_state{{node="edge-prod",name="{role}.service",state="active"}}',
                "values": values,
            }
        )
    document = _rules()
    missing = _rule(document, "ObservabilityRequiredServiceEvidenceMissing")
    failed = _rule(document, "ObservabilityRequiredServiceNotActive")
    absent_roles = (
        ["nginx", "xray"]
        if coverage == "all"
        else ["xray"]
        if coverage == "partial"
        else []
    )
    checks = []
    for rule, roles in [
        (missing, absent_roles),
        (failed, ["xray"] if coverage == "failed" else []),
    ]:
        checks.extend(
            [
                {
                    "eval_time": "4m",
                    "alertname": rule["alert"],
                    "exp_alerts": [_expected(rule, role) for role in roles],
                },
                {"eval_time": "15m", "alertname": rule["alert"], "exp_alerts": []},
            ]
        )
    _run_rule_cases(
        tmp_path,
        document,
        [{"interval": "1m", "input_series": series, "alert_rule_test": checks}],
    )


def test_expected_targets_use_real_health_families_and_exact_role_bindings(tmp_path):
    import yaml

    result, metrics, _ = health._run(tmp_path)
    assert result.returncode == 0, result.stderr
    inventory = {
        "targets": [
            {
                "target": "edge-prod",
                "role": role,
                "lifecycle": "enabled",
                "label_values": {"node": ["edge-prod"], "role": [role]},
                "required_families": [family],
            }
            for role, family in [
                ("watchdog", "vpn_watchdog_collection_success"),
                ("stage-status", "vpn_backup_collection_success"),
            ]
        ]
    }
    template = (
        ROOT
        / "ansible/roles/observability_control_plane/templates/observability-expected-target-rules.yml.j2"
    )
    document = yaml.safe_load(
        render_template(
            template,
            {
                "observability_control_plane": {
                    "expected_targets": {
                        "inventory": inventory,
                        "expected_source_revision": "c" * 40,
                    }
                }
            },
        )
    )
    series = []
    for target in inventory["targets"]:
        role = target["role"]
        family = target["required_families"][0]
        line = next(
            line
            for line in metrics.splitlines()
            if line.startswith(family + "{") and f'role="{role}"' in line
        )
        series.append({"series": line.rsplit(" ", 1)[0], "values": "1x4 stale _x4 1x5"})
        series.append(
            {
                "series": f'vpn_observability_expected_target{{node="edge-prod",role="{role}"}}',
                "values": "1x15",
            }
        )
    # A real family under an unexpected role cannot approve another target.
    series.append(
        {
            "series": 'vpn_watchdog_collection_success{node="edge-prod",role="unrelated"}',
            "values": "1x15",
        }
    )
    rule = _rule(document, "ObservabilityExpectedTargetMissing")
    _run_rule_cases(
        tmp_path,
        document,
        [
            {
                "interval": "1m",
                "input_series": series,
                "alert_rule_test": [
                    {"eval_time": "4m", "alertname": rule["alert"], "exp_alerts": []},
                    {
                        "eval_time": "9m",
                        "alertname": rule["alert"],
                        "exp_alerts": [
                            _expected(rule, role)
                            for role in ["watchdog", "stage-status"]
                        ],
                    },
                    {"eval_time": "14m", "alertname": rule["alert"], "exp_alerts": []},
                ],
            }
        ],
    )


@pytest.mark.parametrize(
    "flags,subscription_only,expected",
    [
        (
            {
                "enable_xray_reality": False,
                "enable_nginx_xhttp": True,
                "enable_hysteria": False,
                "enable_naive": False,
            },
            False,
            {"xray", "nginx", "observability-agent"},
        ),
        (
            {
                "enable_xray_reality": True,
                "enable_nginx_xhttp": True,
                "enable_hysteria": True,
                "enable_naive": True,
                "enable_subscription_host": False,
            },
            True,
            {"nginx", "observability-agent"},
        ),
        (
            {
                "enable_xray_reality": False,
                "enable_nginx_xhttp": False,
                "enable_hysteria": False,
                "enable_naive": False,
            },
            False,
            {"observability-agent"},
        ),
    ],
)
def test_profile_service_matrix_matches_effective_site_roles(
    flags, subscription_only, expected
):
    import re

    values = merge_render_vars()
    values.update(
        {
            "vpn": flags,
            "vpn_subscription_only": subscription_only,
            "observability_agent": {
                "enabled": True,
                "credential_dir": "/etc/observability-agent/credentials",
                "node_id": "vpn-p0",
            },
            "observability_control_plane": {"enabled": False},
        }
    )
    path = (
        ROOT
        / "ansible/roles/observability_agent/templates/observability-agent-health-adapter.service.j2"
    )
    rendered = render_template(path, values)
    assert set(re.findall(r"--required-service ([a-z0-9_-]+)", rendered)) == expected


@pytest.mark.parametrize(
    "producer", ["health", "liveness", "liveness-future", "control-plane"]
)
def test_actual_failure_outputs_cannot_remove_central_failure_anchor(
    tmp_path, producer
):
    if producer == "health":
        result, metrics, _ = health._run(
            tmp_path, stage=health._backup_stage(local_backup={"result": []})
        )
        node, role = "edge-prod", "stage-status"
    elif producer in {"liveness", "liveness-future"}:
        from tests.unit import test_observability_protocol_liveness_adapter as liveness

        result = (
            liveness._run(tmp_path, liveness._evidence(), now=1_799_999_969)
            if producer == "liveness-future"
            else liveness._run(tmp_path, {})
        )
        metrics = (tmp_path / "protocol-liveness.prom").read_text()
        node, role = "protocol-liveness", "liveness-published-evidence"
    else:
        inventory = tmp_path / "inventory.json"
        inventory.write_text("{}")
        output = tmp_path / "control-plane.prom"
        program = (
            ROOT
            / "ansible/roles/observability_control_plane/files/observability-control-plane-adapter.py"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(program),
                "--inventory",
                str(inventory),
                "--output",
                str(output),
                "--data-dir",
                str(tmp_path),
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
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        metrics = output.read_text()
        node, role = "observability-control-plane", "control-plane-adapter"
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    metadata = [
        line
        for line in metrics.splitlines()
        if line.startswith("vpn_observability_evidence_") and f'role="{role}"' in line
    ]
    deadline = [line for line in metadata if "max_age_seconds" in line]
    assert len(deadline) == 1
    assert not any("timestamp_seconds" in line for line in metadata)
    document = _rules()
    rule = _rule(document, "ObservabilityProducerEvidenceUnavailable")
    expected = _expected(rule, role)
    expected["exp_labels"]["node"] = node
    _run_rule_cases(
        tmp_path,
        document,
        [
            {
                "interval": "1m",
                "input_series": [
                    {
                        "series": deadline[0].rsplit(" ", 1)[0],
                        "values": deadline[0].rsplit(" ", 1)[1] + "x5",
                    }
                ],
                "alert_rule_test": [
                    {
                        "eval_time": "4m",
                        "alertname": rule["alert"],
                        "exp_alerts": [expected],
                    }
                ],
            }
        ],
    )


@pytest.mark.parametrize("missing", ["health", "manifest", "both"])
def test_never_started_node_adapters_have_reviewed_expected_node_anchor(
    tmp_path, missing
):
    # The desired enrollment set exists before either runtime publishes anything.
    document = _rules(expected_nodes=["edge-prod"])
    rule = _rule(document, "ObservabilityAdapterCompletionMissing")
    series = [
        {
            "series": 'vpn_observability_evidence_timestamp_seconds{node="edge-prod",role="health-adapter"}',
            "values": "_x9 600+60x6" if missing in {"health", "both"} else "0+60x15",
        },
        {
            "series": 'vpn_observability_adapter_collected_timestamp_seconds{node="edge-prod"}',
            "values": "_x9 600+60x6" if missing in {"manifest", "both"} else "0+60x15",
        },
    ]
    expected = {"exp_labels": rule["labels"], "exp_annotations": rule["annotations"]}
    _run_rule_cases(
        tmp_path,
        document,
        [
            {
                "interval": "1m",
                "input_series": series,
                "alert_rule_test": [
                    {
                        "eval_time": "4m",
                        "alertname": rule["alert"],
                        "exp_alerts": [expected],
                    },
                    {"eval_time": "15m", "alertname": rule["alert"], "exp_alerts": []},
                ],
            }
        ],
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_collector_adapter_absence_uses_reviewed_enablement_and_recovers(
    tmp_path, enabled
):
    document = _rules(optional_enabled=enabled)
    clocks = [
        ("observability-control-plane", "control-plane-adapter"),
        ("protocol-liveness", "liveness-published-evidence"),
    ]
    rules = [
        rule
        for group in document["groups"]
        for rule in group["rules"]
        if rule.get("alert") == "ObservabilityOptionalAdapterCompletionMissing"
    ]
    assert bool(rules) is enabled
    expected = [
        {"exp_labels": rule["labels"], "exp_annotations": rule["annotations"]}
        for rule in rules
    ]
    series = [
        {
            "series": f'vpn_observability_evidence_timestamp_seconds{{node="{node}",role="{role}"}}',
            "values": "_x9 600+60x6",
        }
        for node, role in clocks
    ]
    _run_rule_cases(
        tmp_path,
        document,
        [
            {
                "interval": "1m",
                "input_series": series,
                "alert_rule_test": [
                    {
                        "eval_time": "4m",
                        "alertname": "ObservabilityOptionalAdapterCompletionMissing",
                        "exp_alerts": expected,
                    },
                    {
                        "eval_time": "15m",
                        "alertname": "ObservabilityOptionalAdapterCompletionMissing",
                        "exp_alerts": [],
                    },
                ],
            }
        ],
    )


def test_alert_rule_template_uses_coverage_recognized_local_bindings():
    from tests.unit.test_secrets_coverage import checker

    template = (
        ROOT
        / "ansible/roles/observability_control_plane/templates/observability-alert-rules.yml.j2"
    )
    actual = checker.extract_toplevel_vars(template.read_text())
    assert not ({"adapter", "node", "role", "enabled"} & actual)
