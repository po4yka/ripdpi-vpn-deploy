"""Focused contracts for bounded control-plane alerting and Telegram routing."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import yaml

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
PROMTOOL_VERSION = "3.14.0"


def _contract(*, token: str = "123456789:fixture-token-value-not-real") -> dict:
    return {
        "service_user": "prometheus",
        "service_group": "prometheus",
        "config_root": "/etc/observability-control-plane",
        "prometheus": {
            "promtool_archive_members": {
                "amd64": "prometheus-fixture/promtool",
                "arm64": "prometheus-fixture/promtool",
            }
        },
        "alerting": {
            "enabled": True,
            "source_generation": "c" * 40,
            "listen": "127.0.0.1:9093",
            "install_root": "/opt/observability-alertmanager",
            "binary_link": "/usr/local/libexec/observability-alertmanager",
            "amtool_install_root": "/opt/observability-amtool",
            "amtool_binary_link": "/usr/local/libexec/observability-amtool",
            "promtool_install_root": "/opt/observability-promtool",
            "promtool_binary_link": "/usr/local/libexec/observability-promtool",
            "credential_path": (
                "/etc/observability-control-plane/credentials/telegram-bot-token"
            ),
            "alertmanager": {
                "version": "0.28.1",
                "urls": {
                    "amd64": "file:///fixture/alertmanager.tar.gz",
                    "arm64": "file:///fixture/alertmanager.tar.gz",
                },
                "sha256": {"amd64": "a" * 64, "arm64": "b" * 64},
                "archive_members": {
                    "amd64": "alertmanager-fixture/alertmanager",
                    "arm64": "alertmanager-fixture/alertmanager",
                },
                "amtool_archive_members": {
                    "amd64": "alertmanager-fixture/amtool",
                    "arm64": "alertmanager-fixture/amtool",
                },
            },
            "telegram": {
                "bot_token": token,
                "chat_id": "-100000000001",
                "topic_id": 42,
                "parse_mode": "HTML",
                "max_alerts": 5,
            },
            "group_wait": "30s",
            "group_interval": "5m",
            "critical_repeat_interval": "1h",
            "warning_repeat_interval": "6h",
            "recovery_stability": "3m",
            "deadman": {
                "enabled": True,
                "receiver_url": "http://127.0.0.1:19093/alerts",
                "repeat_interval": "1m",
            },
        },
    }


def test_alerting_defaults_are_inert_and_secret_free() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())[
        "observability_control_plane"
    ]
    alerting = defaults["alerting"]

    assert alerting["enabled"] is False
    assert alerting["source_generation"] == ""
    assert alerting["telegram"]["bot_token"] == ""
    assert alerting["telegram"]["chat_id"] == ""
    assert alerting["deadman"]["enabled"] is False
    assert alerting["listen"] == "127.0.0.1:9093"


def test_missing_telegram_contract_refuses_without_changes_or_secret_output(
    tmp_path: Path,
) -> None:
    secret = "123456789:must-not-appear-in-output"
    playbook = tmp_path / "contract.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "contract refusal",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {"observability_control_plane": _contract(token=secret)},
                    "tasks": [
                        {
                            "name": "Remove required destination",
                            "ansible.builtin.set_fact": {
                                "observability_control_plane": (
                                    "{{ observability_control_plane | combine("
                                    "{'alerting': observability_control_plane.alerting "
                                    "| combine({'telegram': "
                                    "observability_control_plane.alerting.telegram "
                                    "| combine({'chat_id': ''})})}) }}"
                                )
                            },
                            "no_log": True,
                        },
                        {
                            "name": "Exercise production alerting contract",
                            "ansible.builtin.include_tasks": str(
                                ROLE / "tasks/alerting-contract.yml"
                            ),
                        },
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode != 0
    assert "changed=0" in result.stdout
    assert secret not in result.stdout + result.stderr


def test_complete_alerting_contract_passes_without_changes_or_secret_output(
    tmp_path: Path,
) -> None:
    secret = "123456789:complete-token-must-not-appear"
    playbook = tmp_path / "contract.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "complete contract",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {"observability_control_plane": _contract(token=secret)},
                    "tasks": [
                        {
                            "name": "Exercise production alerting contract",
                            "ansible.builtin.include_tasks": str(
                                ROLE / "tasks/alerting-contract.yml"
                            ),
                        }
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed=0" in result.stdout
    assert secret not in result.stdout + result.stderr


def test_alertmanager_route_and_message_are_deterministic_and_secret_free() -> None:
    contract = _contract()
    first = render_template(
        ROLE / "templates/observability-alertmanager.yml.j2",
        {
            "observability_control_plane": contract,
            "_observability_telegram_generation": "c" * 64,
        },
    )
    second = render_template(
        ROLE / "templates/observability-alertmanager.yml.j2",
        {
            "observability_control_plane": contract,
            "_observability_telegram_generation": "c" * 64,
        },
    )
    message = render_template(
        ROLE / "templates/observability-telegram.tmpl.j2",
        {"observability_control_plane": contract},
    )
    parsed = yaml.safe_load(first)

    assert first == second
    assert parsed["route"]["group_wait"] == "30s"
    assert parsed["route"]["group_interval"] == "5m"
    assert parsed["route"]["group_by"] == [
        "alertname",
        "environment",
        "node",
        "component",
        "policy",
        "profile",
        "vantage",
        "severity",
    ]
    primary = next(
        receiver
        for receiver in parsed["receivers"]
        if receiver["name"] == "telegram-primary"
    )["telegram_configs"][0]
    assert primary["bot_token_file"] == (
        "/run/credentials/observability-alertmanager.service/telegram-bot-token"
    )
    assert primary["chat_id"] == -100000000001
    assert primary["message_thread_id"] == 42
    assert primary["send_resolved"] is True
    assert primary["max_alerts"] == 5
    assert parsed["inhibit_rules"] == [
        {
            "source_matchers": ['alertname="ObservabilityBackupStageFailed"'],
            "target_matchers": ['alertname="ObservabilityBackupEvidenceStale"'],
            "equal": ["node", "component"],
        }
    ]
    assert "fixture-token" not in first + message
    assert message.count(".CommonAnnotations.") == 1
    assert "reReplaceAll" in message
    assert ".Annotations.summary" in message
    assert ".Annotations.runbook" in message
    assert ".CommonAnnotations.source_generation" in message
    assert ".TruncatedAlerts" in message


def test_canonical_alertmanager_template_uses_exact_telegram_generation_path() -> None:
    vars_ = merge_render_vars()
    rendered = render_template(
        ROLE / "templates/observability-alertmanager.yml.j2", vars_
    )

    assert yaml.safe_load(rendered)["templates"] == [
        "/etc/observability-control-plane/generations/telegram-" + "4" * 64 + ".tmpl"
    ]


def test_prometheus_loads_alert_rules_and_scrapes_only_loopback_alertmanager() -> None:
    contract = _contract()
    contract["expected_targets"] = {"enabled": False}
    rendered = render_template(
        ROLE / "templates/prometheus.yml.j2",
        {
            "observability_control_plane": contract,
            "_observability_alert_rules_generation": "d" * 64,
        },
    )
    parsed = yaml.safe_load(rendered)

    assert parsed["rule_files"] == [
        "/etc/observability-control-plane/generations/alerts-" + "d" * 64 + ".rules.yml"
    ]
    assert parsed["alerting"]["alertmanagers"][0]["static_configs"] == [
        {"targets": ["127.0.0.1:9093"]}
    ]
    assert parsed["scrape_configs"][-1] == {
        "job_name": "observability-alertmanager",
        "static_configs": [{"targets": ["127.0.0.1:9093"]}],
    }


def test_rules_have_fixed_severity_recovery_and_deadman_boundaries(
    tmp_path: Path,
) -> None:
    contract = _contract()
    rules = render_template(
        ROLE / "templates/observability-alert-rules.yml.j2",
        {"observability_control_plane": contract},
    )
    parsed = yaml.safe_load(rules)
    alerts = [rule for group in parsed["groups"] for rule in group["rules"]]

    assert {rule["alert"] for rule in alerts} >= {
        "ObservabilityWatchdogEvidenceStale",
        "ObservabilityWatchdogRecoveryUnresolved",
        "ObservabilityBackupEvidenceStale",
        "ObservabilityBackupStageFailed",
        "ObservabilityRestoreReadinessStale",
        "ObservabilityPipelineWatchdog",
    }
    for rule in alerts:
        assert rule["labels"]["severity"] in {"warning", "critical", "watchdog"}
        assert rule["for"]
        assert rule["keep_firing_for"] == "3m"
        assert rule["annotations"]["incident_family"]
        assert rule["annotations"]["evidence_class"]
        assert rule["annotations"]["runbook"].startswith("docs/")
        assert (ROOT / rule["annotations"]["runbook"]).is_file()
        assert rule["annotations"]["source_generation"] == "c" * 40
        assert "token" not in str(rule).lower()
    assert (
        next(
            rule for rule in alerts if rule["alert"] == "ObservabilityPipelineWatchdog"
        )["expr"]
        == "vector(1)"
    )

    promtool = shutil.which("promtool")
    assert promtool is not None, f"promtool {PROMTOOL_VERSION} is required"
    version = subprocess.run(
        [promtool, "--version"], capture_output=True, text=True, timeout=10
    )
    assert re.search(
        rf"\bversion {re.escape(PROMTOOL_VERSION)}\b",
        version.stdout + version.stderr,
    )
    rules_path = tmp_path / "alerts.yml"
    rules_path.write_text(rules)
    check = subprocess.run(
        [promtool, "check", "rules", str(rules_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_promtool_rule_cases_cover_firing_stale_recovery_and_absent(
    tmp_path: Path,
) -> None:
    contract = _contract()
    rules_path = tmp_path / "alerts.yml"
    rules_path.write_text(
        render_template(
            ROLE / "templates/observability-alert-rules.yml.j2",
            {"observability_control_plane": contract},
        )
    )
    test_path = tmp_path / "alerts.test.yml"
    test_path.write_text(
        render_template(
            ROLE / "templates/observability-alert-rules.test.yml.j2",
            {"observability_control_plane": contract},
        )
    )
    promtool = shutil.which("promtool")
    assert promtool is not None
    result = subprocess.run(
        [promtool, "test", "rules", str(test_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_alerting_tasks_validate_before_activation_and_rollback() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/alerting.yml").read_text())
    names = [task["name"] for task in tasks]
    assert names.index("Validate immutable alert rules") < names.index(
        "Activate validated Alertmanager generation with rollback"
    )
    assert names.index("Validate immutable Alertmanager generation") < names.index(
        "Activate validated Alertmanager generation with rollback"
    )
    activation = next(
        task
        for task in tasks
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    rescue_names = [task["name"] for task in activation["rescue"]]
    assert "Restore previous ready Alertmanager configuration" in rescue_names
    assert "Fail closed after Alertmanager candidate failure" in rescue_names
    restart = next(
        task
        for task in activation["block"]
        if task["name"] == "Restart Alertmanager with candidate generation"
    )
    assert restart["when"] == (
        "_observability_alertmanager_runtime_changed | bool or "
        "_observability_alertmanager_credential.changed or "
        "_observability_alertmanager_unit.changed or "
        "_observability_alertmanager_current_link.changed"
    )
    assert "Capture Alertmanager runtime publication change" in names
    assert names.index("Capture Alertmanager runtime publication change") < names.index(
        "Install pinned amtool through runtime-release"
    )
    assert "Ensure unchanged Alertmanager generation is running" in [
        task["name"] for task in activation["block"]
    ]


def test_alertmanager_restart_condition_uses_one_ansible_expression(tmp_path: Path) -> None:
    tasks = yaml.safe_load((ROLE / "tasks/alerting.yml").read_text())
    activation = next(
        task
        for task in tasks
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    condition = next(
        task["when"]
        for task in activation["block"]
        if task["name"] == "Restart Alertmanager with candidate generation"
    )
    playbook = tmp_path / "restart-condition.yml"
    source = (
        """---
- hosts: localhost
  gather_facts: false
  vars:
    cases:
      - {name: all_false, runtime: false, credential: false, unit: false, link: false, expected: false}
      - {name: runtime, runtime: true, credential: false, unit: false, link: false, expected: true}
      - {name: credential, runtime: false, credential: true, unit: false, link: false, expected: true}
      - {name: unit, runtime: false, credential: false, unit: true, link: false, expected: true}
      - {name: link, runtime: false, credential: false, unit: false, link: true, expected: true}
  tasks:
    - ansible.builtin.debug:
        msg: "restart-{{ item.name }}"
      vars:
        _observability_alertmanager_runtime_changed: "{{ item.runtime }}"
        _observability_alertmanager_credential: {changed: "{{ item.credential }}"}
        _observability_alertmanager_unit: {changed: "{{ item.unit }}"}
        _observability_alertmanager_current_link: {changed: "{{ item.link }}"}
      loop: "{{ cases }}"
      when: >-
        __WHEN__
      register: decisions
    - ansible.builtin.assert:
        that: >-
          (item.item.expected | bool) == (not (item.skipped | default(false)))
      loop: "{{ decisions.results }}"
"""
    ).replace("__WHEN__", condition)
    playbook.write_text(source, encoding="utf-8")
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_alerting_contract_precedes_first_control_plane_host_mutation() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    names = [task["name"] for task in tasks]
    assert names.index("Require the opt-in alerting contract before host mutation") < (
        names.index("Create dedicated control-plane account")
    )


def test_alertmanager_unit_uses_systemd_credential_without_argv_secret() -> None:
    unit = (ROLE / "templates/observability-alertmanager.service.j2").read_text()
    assert "LoadCredential=telegram-bot-token:" in unit
    assert "bot_token" not in next(
        line for line in unit.splitlines() if line.startswith("ExecStart=")
    )
    assert (
        "--web.listen-address={{ observability_control_plane.alerting.listen }}" in unit
    )
    assert "ProtectSystem=strict" in unit
    assert "NoNewPrivileges=true" in unit


def test_alerting_disable_removes_owned_runtime_but_preserves_tsdb() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/alerting-disable.yml").read_text())
    text = (ROLE / "tasks/alerting-disable.yml").read_text()
    names = {task["name"] for task in tasks}
    assert "Stop disabled Alertmanager service" in names
    assert "Remove disabled alerting surfaces" in names
    assert "observability-alertmanager.service" in text
    assert "observability_control_plane.alerting.credential_path" in text
    assert "/var/lib/observability-prometheus" not in text
