"""Focused contracts for bounded control-plane alerting and Telegram routing."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from tests.unit.test_observability_silence_gateway import _tls

import yaml
import pytest

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
PROMTOOL_VERSION = "3.14.0"


def _contract(*, token: str = "123456789:fixture-token-value-not-real") -> dict:
    with tempfile.TemporaryDirectory() as directory:
        tls_dir = Path(directory)
        _tls(tls_dir)
        gateway = {
            "enabled": True,
            "listen": "127.0.0.1:19094",
            "environment": "staging",
            "max_ttl_seconds": 14400,
            "operators": [{"owner": "operator-a", "token": "a1" * 32}],
            "sender_token": "b2" * 32,
            "backend_ca_pem": (tls_dir / "ca.pem").read_text(),
            "backend_server_cert_pem": (tls_dir / "server.pem").read_text(),
            "backend_server_key_pem": (tls_dir / "server.key").read_text(),
            "backend_client_cert_pem": (tls_dir / "client.pem").read_text(),
            "backend_client_key_pem": (tls_dir / "client.key").read_text(),
        }
        _tls(tls_dir)
        ingest_ca = (tls_dir / "ca.pem").read_text()
    return {
        "tls": {"client_ca_pem": ingest_ca},
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
            "silence_gateway": gateway,
            "source_generation": "c" * 40,
            "listen": "127.0.0.1:9093",
            "data_dir": "/var/lib/observability-alertmanager",
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
                    "vars": {
                        "observability_control_plane": _contract(token=secret),
                        "role_path": str(ROLE),
                    },
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
                    "vars": {
                        "observability_control_plane": _contract(token=secret),
                        "role_path": str(ROLE),
                    },
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
        {"targets": ["127.0.0.1:19094"]}
    ]
    assert parsed["scrape_configs"][-1] == {
        "job_name": "observability-alertmanager",
        "authorization": {
            "type": "Bearer",
            "credentials_file": "/run/credentials/observability-prometheus.service/silence-sender-token",
        },
        "static_configs": [{"targets": ["127.0.0.1:19094"]}],
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
        for task in yaml.safe_load((ROLE / "tasks/alerting-authority.yml").read_text())
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    preserve = next(
        task
        for task in activation["block"]
        if task["name"] == "Preserve previous ready Alertmanager generation"
    )
    assert preserve["when"] == [
        "_observability_alertmanager_current.stat.exists | default(false)",
        "_observability_alertmanager_current.stat.lnk_source != "
        "observability_control_plane.config_root ~ '/generations/alertmanager-' ~ "
        "_observability_alertmanager_generation ~ '.yml'",
    ]
    rescue_names = [task["name"] for task in activation["rescue"]]
    assert (
        "Restore the captured authority and service credential snapshots"
        in rescue_names
    )
    assert "Fail candidate after observed complete authority rollback" in rescue_names
    status = next(
        task
        for task in activation["rescue"]
        if task["name"] == "Capture categorical gateway service state before rollback"
    )
    assert status["ansible.builtin.command"]["argv"] == [
        "systemctl",
        "show",
        "observability-silence-gateway.service",
        "--property=LoadState,ActiveState,SubState,Result,ExecMainCode,ExecMainStatus,NRestarts",
    ]
    reason = next(
        task
        for task in activation["rescue"]
        if task["name"] == "Capture allowlisted gateway startup refusal before rollback"
    )
    assert reason["ansible.builtin.command"]["argv"][0] == "journalctl"
    assert reason["ansible.builtin.command"]["argv"][4] == (
        "--grep=^silence-gateway: [a-z-]{1,32}$"
    )
    assert status["no_log"] is True and reason["no_log"] is True
    assert rescue_names.index(status["name"]) < rescue_names.index(
        "Restore the captured authority and service credential snapshots"
    )
    restart = next(
        task
        for task in activation["block"]
        if task["name"] == "Restart Alertmanager with candidate generation"
    )
    assert restart["when"] == (
        "not ansible_check_mode and (_observability_alertmanager_runtime_changed | bool or "
        "_observability_alertmanager_credential.changed or "
        "_observability_silence_credentials.changed or "
        "_observability_silence_web.changed or "
        "_observability_alertmanager_unit.changed or "
        "_observability_alertmanager_current_link.changed)"
    )
    assert "Capture Alertmanager runtime publication change" in names
    assert names.index("Capture Alertmanager runtime publication change") < names.index(
        "Install pinned amtool through runtime-release"
    )
    assert "Ensure unchanged Alertmanager generation is running" in [
        task["name"] for task in activation["block"]
    ]


def test_alertmanager_restart_condition_uses_one_ansible_expression(
    tmp_path: Path,
) -> None:
    tasks = yaml.safe_load((ROLE / "tasks/alerting.yml").read_text())
    activation = next(
        task
        for task in yaml.safe_load((ROLE / "tasks/alerting-authority.yml").read_text())
        if task["name"] == "Activate validated Alertmanager generation with rollback"
    )
    condition = next(
        task["when"]
        for task in activation["block"]
        if task["name"] == "Restart Alertmanager with candidate generation"
    )
    playbook = tmp_path / "restart-condition.yml"
    source = ("""---
- hosts: localhost
  gather_facts: false
  vars:
    cases:
      - {name: silence, silence: true, runtime: false, credential: false, unit: false, link: false, expected: true}
      - {name: web, web: true, runtime: false, credential: false, unit: false, link: false, expected: true}
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
        _observability_silence_credentials: {changed: "{{ item.silence | default(false) }}"}
        _observability_silence_web: {changed: "{{ item.web | default(false) }}"}
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
""").replace("__WHEN__", condition)
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


def test_gateway_uses_private_systemd_credentials_without_cwd_dependency() -> None:
    enable = yaml.safe_load((ROLE / "tasks/enable.yml").read_text(encoding="utf-8"))
    alerting = yaml.safe_load((ROLE / "tasks/alerting.yml").read_text(encoding="utf-8"))
    silence = (ROLE / "tasks/silence-gateway.yml").read_text(encoding="utf-8")
    gateway_unit = (
        ROLE / "templates/observability-silence-gateway.service.j2"
    ).read_text(encoding="utf-8")

    directories = next(
        task
        for task in enable
        if task["name"] == "Create private control-plane directories"
    )["loop"]
    assert directories[0]["path"] == "{{ observability_control_plane.config_root }}"
    assert directories[0]["mode"] == "0750"
    credential_directory = next(
        task
        for task in alerting
        if task["name"] == "Create private alerting credential directory"
    )["ansible.builtin.file"]
    assert credential_directory["owner"] == "root"
    assert credential_directory["group"] == "root"
    assert credential_directory["mode"] == "0700"
    assert silence.count("mode: '0600'") >= 3
    assert silence.count("owner: root") >= 3
    assert silence.count("group: root") >= 3
    credential_names = (
        "silence-policy.json",
        "silence-auth.json",
        "silence-backend-ca.pem",
        "silence-backend-client.crt",
        "silence-backend-client.key",
    )
    assert gateway_unit.count("LoadCredential=") == len(credential_names)
    assert "WorkingDirectory=" not in gateway_unit
    gateway = (ROLE / "files/observability-silence-gateway.py").read_text(
        encoding="utf-8"
    )
    for name in credential_names:
        assert gateway_unit.count(f"LoadCredential={name}:") == 1
        assert f'credentials / "{name}"' in gateway
    molecule = yaml.safe_load(
        (ROLE / "molecule/enabled/molecule.yml").read_text(encoding="utf-8")
    )
    assert molecule["platforms"][0]["tmpfs"] == ["/run:rw,rshared"]


def test_alerting_disable_removes_owned_runtime_but_preserves_tsdb() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/alerting-disable.yml").read_text())
    text = (ROLE / "tasks/alerting-disable.yml").read_text()
    names = {task["name"] for task in tasks}
    assert "Stop disabled Alertmanager service" in names
    assert "Remove disabled alerting surfaces" in names
    assert "observability-alertmanager.service" in text
    assert "observability_control_plane.alerting.credential_path" in text
    assert "/var/lib/observability-prometheus" not in text


def test_silence_gateway_is_the_only_authenticated_alertmanager_route() -> None:
    contract = _contract()
    contract["alerting"]["silence_gateway"] = {
        "enabled": True,
        "environment": "staging",
        "max_ttl_seconds": 14400,
    }
    values = {
        "observability_control_plane": contract,
        "_observability_alert_rules_generation": "a" * 64,
    }
    prometheus = yaml.safe_load(
        render_template(ROLE / "templates/prometheus.yml.j2", values)
    )
    sender = "/run/credentials/observability-prometheus.service/silence-sender-token"
    assert prometheus["alerting"]["alertmanagers"][0]["static_configs"][0][
        "targets"
    ] == ["127.0.0.1:19094"]
    assert (
        prometheus["alerting"]["alertmanagers"][0]["authorization"]["credentials_file"]
        == sender
    )
    am_scrape = next(
        row
        for row in prometheus["scrape_configs"]
        if row["job_name"] == "observability-alertmanager"
    )
    assert am_scrape["static_configs"][0]["targets"] == ["127.0.0.1:19094"]
    assert am_scrape["authorization"]["credentials_file"] == sender
    web = yaml.safe_load(
        render_template(
            ROLE / "templates/observability-alertmanager-web.yml.j2", values
        )
    )
    assert web["tls_server_config"]["client_auth_type"] == "RequireAndVerifyClientCert"
    am_unit = render_template(
        ROLE / "templates/observability-alertmanager.service.j2", values
    )
    gateway_unit = render_template(
        ROLE / "templates/observability-silence-gateway.service.j2", values
    )
    assert "--web.config.file=" in am_unit
    assert "silence-backend-client.key" not in am_unit
    assert "silence-backend-client.key" in gateway_unit
    assert "User=observability-silence" in gateway_unit
    assert "silence-sender-token" not in gateway_unit
    assert "silence-owner-" not in gateway_unit


@pytest.mark.parametrize("field", ["owner", "token", "sender_token", "environment"])
def test_gateway_contract_rejects_trailing_newline_before_host_changes(tmp_path, field):
    contract = _contract()
    gateway = contract["alerting"]["silence_gateway"]
    target = gateway["operators"][0] if field in ("owner", "token") else gateway
    target[field] += "\n"
    playbook = tmp_path / "gateway-contract.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {
                        "observability_control_plane": contract,
                        "role_path": str(ROLE),
                    },
                    "tasks": [
                        {
                            "ansible.builtin.include_tasks": str(
                                ROLE / "tasks/alerting-contract.yml"
                            )
                        }
                    ],
                }
            ]
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert "changed=0" in result.stdout
    assert gateway["operators"][0]["token"].strip() not in result.stdout + result.stderr


def test_real_gateway_credential_templates_publish_only_token_digests(tmp_path):
    contract = _contract()
    gateway = contract["alerting"]["silence_gateway"]
    values = {"observability_control_plane": contract}
    rendered = render_template(ROLE / "templates/silence-auth.json.j2", values)
    auth = json.loads(rendered)
    assert auth == {
        "schema_version": 1,
        "sender_token_sha256": hashlib.sha256(
            gateway["sender_token"].encode()
        ).hexdigest(),
        "owners": [
            {
                "owner": "operator-a",
                "token_sha256": hashlib.sha256(
                    gateway["operators"][0]["token"].encode()
                ).hexdigest(),
            }
        ],
    }
    assert gateway["sender_token"] not in rendered
    assert gateway["operators"][0]["token"] not in rendered
    policy = json.loads(
        render_template(ROLE / "templates/silence-policy.json.j2", values)
    )
    assert policy == {
        "schema_version": 1,
        "environment": "staging",
        "max_ttl_seconds": 14400,
    }
    unsupported = tmp_path / "unsupported.j2"
    unsupported.write_text("{{ 'token' | hash('md5') }}")
    with pytest.raises(ValueError, match="sha256"):
        render_template(unsupported, {})


@pytest.mark.parametrize(
    "initial",
    [
        "active",
        "inactive",
        "absent",
        "restore-failure",
        "partial-active",
        "prometheus-only",
        "check-noop",
        "check-rotation",
        "check-inactive",
        "check-fresh",
        "check-manual",
        "check-unsafe",
    ],
)
def test_authority_rotation_failure_restores_files_and_service_snapshots(
    tmp_path, initial
):
    """Real Ansible transaction; temp filesystem and HTTP-process systemd adapters."""
    import socket
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    check_case = initial if initial.startswith("check-") else None
    if check_case:
        initial = "absent" if check_case == "check-fresh" else "active"
    restore_fault = initial == "restore-failure"
    partial_active = initial == "partial-active"
    prometheus_only = initial == "prometheus-only"
    if prometheus_only:
        initial = "absent"
    if restore_fault or partial_active:
        initial = "active"
    transaction = ROLE / "tasks/alerting-authority.yml"
    assert transaction.exists(), "publication needs one recoverable authority boundary"
    root = tmp_path / "root"
    credentials = root / "etc/observability-control-plane/credentials"
    credentials.mkdir(parents=True, mode=0o700)
    (root / "etc/systemd/system").mkdir(parents=True)
    (root / "usr/local/libexec").mkdir(parents=True)
    generations = credentials.parent / "generations"
    generations.mkdir()
    (generations / ("alertmanager-" + "a" * 64 + ".yml")).write_text("old\n")
    (generations / ("alertmanager-" + "b" * 64 + ".yml")).write_text("candidate\n")
    ports = {}
    for name in ("alertmanager", "silence-gateway", "prometheus"):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            ports[name] = listener.getsockname()[1]
    old_token, new_token = "a1" * 32, "b2" * 32
    contract = _contract()
    contract["config_root"] = str(credentials.parent)
    gateway = contract["alerting"]["silence_gateway"]
    gateway["sender_token"] = new_token
    gateway["operators"] = [{"owner": "operator-b", "token": "c3" * 32}]
    contract["alerting"]["credential_path"] = str(credentials / "telegram-bot-token")
    contract["alerting"]["silence_gateway"]["listen"] = "127.0.0.1:19094"
    prior = {
        "silence-auth.json": json.dumps(
            {
                "schema_version": 1,
                "owners": [{"owner": "operator-a", "token_sha256": "d" * 64}],
                "sender_token_sha256": hashlib.sha256(old_token.encode()).hexdigest(),
            }
        ),
        "silence-sender-token": old_token,
        "silence-owner-operator-a-token": "d4" * 32,
        "telegram-bot-token": "previous-telegram-token",
    }
    if initial != "absent":
        for name, content in prior.items():
            (credentials / name).write_text(content)
            (credentials / name).chmod(0o600)
        (credentials.parent / "alertmanager-current.yml").symlink_to(
            generations / ("alertmanager-" + "a" * 64 + ".yml")
        )
        for name in ports:
            (
                root / "etc/systemd/system" / ("observability-" + name + ".service")
            ).write_text("prior unit\n")
        (root / "usr/local/libexec/observability-silence-gateway").write_text(
            "prior program\n"
        )
        (root / "usr/local/libexec/observability-silence-gateway").chmod(0o755)
    facts = (
        {
            "observability-"
            + name
            + ".service": {"state": "stopped", "status": "disabled"}
            for name in ports
        }
        if initial != "absent"
        else {}
    )
    if initial == "inactive":
        for row in facts.values():
            row["state"] = "inactive"
    if prometheus_only:
        facts["observability-prometheus.service"] = {
            "state": "stopped",
            "status": "disabled",
        }
        (root / "etc/systemd/system/observability-prometheus.service").write_text(
            "prior unit\n"
        )
    (tmp_path / "facts.json").write_text(json.dumps(facts))
    (tmp_path / "ports.json").write_text(json.dumps(ports))
    control = tmp_path / "services.py"
    control.write_text("""import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.request import Request,urlopen
base=Path(sys.argv[1]); action=sys.argv[2]
ports=json.loads((base/'ports.json').read_text()); creds=base/'root/etc/observability-control-plane/credentials'
if action=='serve':
 name=sys.argv[3]
 token=(creds/'silence-sender-token').read_text() if name=='prometheus' and (creds/'silence-sender-token').exists() else ''
 digest=json.loads((creds/'silence-auth.json').read_text())['sender_token_sha256'] if name=='silence-gateway' else ''
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   code=200
   if name=='silence-gateway':
    supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
    code=200 if hashlib.sha256(supplied.encode()).hexdigest()==digest else 403
    if (base/'fail-candidate').exists() and digest==hashlib.sha256(('b2'*32).encode()).hexdigest(): code=503
   if name=='prometheus' and token:
    try:
     with urlopen(Request('http://127.0.0.1:'+str(ports['silence-gateway'])+'/-/ready',headers={'Authorization':'Bearer '+token}),timeout=1): pass
    except Exception: code=503
   self.send_response(code);self.end_headers()
  def log_message(self,*args): pass
 HTTPServer(('127.0.0.1',ports[name]),Handler).serve_forever()
else:
 name=sys.argv[3].removeprefix('observability-').removesuffix('.service'); state=sys.argv[4]; enabled=sys.argv[5] if len(sys.argv)>5 else 'unchanged'
 path=base/(name+'.pid'); facts=json.loads((base/'facts.json').read_text()); key='observability-'+name+'.service'
 row=facts.setdefault(key,{'state':'stopped','status':'disabled'})
 if state=='stopped' and name=='silence-gateway' and (base/'fail-restore').exists():
  target=creds/'silence-policy.json'
  if os.path.lexists(target): target.unlink()
  target.symlink_to(base/'foreign-file')
 if state in ('restarted','stopped') and path.exists():
  try: os.kill(int(path.read_text()),signal.SIGTERM)
  except ProcessLookupError: pass
  path.unlink();time.sleep(.1);row['state']='stopped'
 if state=='stopped': row['state']='stopped'
 if state in ('restarted','started') and not path.exists():
  child=subprocess.Popen([sys.executable,__file__,str(base),'serve',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  path.write_text(str(child.pid));time.sleep(.15);row['state']='running'
 if enabled in ('True','true','False','false'): row['status']='enabled' if enabled.lower()=='true' else 'disabled'
 (base/'facts.json').write_text(json.dumps(facts))
""")

    def service(name, state, enabled):
        subprocess.run(
            [
                os.sys.executable,
                str(control),
                str(tmp_path),
                "control",
                name,
                state,
                enabled,
            ],
            check=True,
            timeout=5,
        )

    if initial == "active" or prometheus_only:
        for name in ports:
            if (not partial_active or name == "alertmanager") and (
                not prometheus_only or name == "prometheus"
            ):
                service(name, "started", "true")
    mirror = tmp_path / "tasks"
    mirror.mkdir()

    def adapt(value):
        if isinstance(value, str):
            if value == "/usr/bin/python3":
                return os.sys.executable
            if value == "/":
                return str(root)
            for prefix in ("/etc/", "/usr/local/"):
                if value.startswith(prefix):
                    value = str(root) + value
            return value.replace(
                "http://127.0.0.1:19094",
                "http://127.0.0.1:" + str(ports["silence-gateway"]),
            ).replace(
                "http://127.0.0.1:9090", "http://127.0.0.1:" + str(ports["prometheus"])
            )
        if isinstance(value, list):
            return [adapt(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: adapt(item) for key, item in value.items()}
        if "ansible.builtin.service_facts" in result:
            del result["ansible.builtin.service_facts"]
            result["ansible.builtin.set_fact"] = {
                "ansible_facts": {
                    "services": "{{ lookup('file', '"
                    + str(tmp_path / "facts.json")
                    + "') | from_json }}"
                }
            }
        if "ansible.builtin.systemd_service" in result:
            module = result.pop("ansible.builtin.systemd_service")
            result["ansible.builtin.command"] = {
                "argv": [
                    os.sys.executable,
                    str(control),
                    str(tmp_path),
                    "control",
                    module.get("name", "observability-alertmanager"),
                    module.get("state", "unchanged"),
                    str(module.get("enabled", "unchanged")),
                ]
            }
            result["changed_when"] = True
        for module in (
            "ansible.builtin.copy",
            "ansible.builtin.template",
            "ansible.builtin.file",
        ):
            if module in result:
                result[module].pop("owner", None)
                result[module].pop("group", None)
                if (
                    module != "ansible.builtin.file"
                    and "src" in result[module]
                    and not result[module]["src"].startswith("/")
                ):
                    result[module]["src"] = str(
                        ROLE
                        / ("templates" if module.endswith("template") else "files")
                        / result[module]["src"]
                    )
        if "retries" in result:
            result["retries"], result["delay"] = 1, 0
        return result

    for source in (ROLE / "tasks").glob("*.yml"):
        (mirror / source.name).write_text(
            yaml.safe_dump(adapt(yaml.safe_load(source.read_text())), sort_keys=False)
        )
    variables = {
        "ansible_python_interpreter": os.sys.executable,
        "observability_control_plane": contract,
        "role_path": str(ROLE),
        "_observability_alertmanager_runtime_changed": False,
        "_observability_alertmanager_generation": "b" * 64,
        "_observability_alertmanager_current": {
            "stat": {
                "exists": initial != "absent",
                "lnk_source": str(generations / ("alertmanager-" + "a" * 64 + ".yml")),
            }
        },
    }
    playbook = tmp_path / "rotation.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": variables,
                    "tasks": [
                        {
                            "ansible.builtin.include_tasks": str(
                                mirror / "alerting-authority.yml"
                            )
                        }
                    ],
                }
            ]
        )
    )

    def run(check=False):
        return subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(playbook)]
            + (["--check"] if check else []),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=40,
        )

    def request(token):
        try:
            with urlopen(
                Request(
                    "http://127.0.0.1:" + str(ports["silence-gateway"]) + "/-/ready",
                    headers={"Authorization": "Bearer " + token},
                ),
                timeout=2,
            ) as response:
                return response.status
        except HTTPError as error:
            return error.code

    try:
        if check_case:
            if check_case != "check-fresh":
                prepared = run()
                assert prepared.returncode == 0, prepared.stdout + prepared.stderr
                current = credentials.parent / "alertmanager-current.yml"
                previous = credentials.parent / "alertmanager-previous.yml"
                previous.unlink()
                previous.symlink_to(os.readlink(current))
                variables["_observability_alertmanager_current"]["stat"][
                    "lnk_source"
                ] = os.readlink(current)
            if check_case == "check-inactive":
                for name in ports:
                    service(name, "stopped", "false")
            if check_case == "check-rotation":
                gateway["sender_token"] = "e5" * 32
            if check_case == "check-fresh":
                shutil.rmtree(credentials.parent)
                (root / "usr/local/libexec").rmdir()
                (root / "etc/systemd/system").rmdir()
            if check_case == "check-manual":
                recovery = credentials.parent / ".authority-rollback"
                recovery.mkdir(mode=0o700)
                (recovery / "manual-recovery").write_text("retained")
            if check_case == "check-unsafe":
                credentials.rename(tmp_path / "retained-credentials")
                credentials.symlink_to(tmp_path / "retained-credentials")
            playbook.write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "localhost",
                            "connection": "local",
                            "gather_facts": False,
                            "vars": variables,
                            "tasks": [
                                {
                                    "ansible.builtin.include_tasks": str(
                                        mirror / "alerting-authority.yml"
                                    )
                                }
                            ],
                        }
                    ]
                )
            )

            def tree():
                result = {}
                for parent, dirs, files in os.walk(root, followlinks=False):
                    for name in [*dirs, *files]:
                        path = Path(parent) / name
                        info = path.lstat()
                        content = (
                            os.readlink(path)
                            if path.is_symlink()
                            else path.read_bytes() if path.is_file() else None
                        )
                        result[str(path.relative_to(root))] = (
                            info.st_ino,
                            info.st_mode,
                            info.st_uid,
                            info.st_gid,
                            content,
                        )
                return result

            before_tree = tree()
            before_services = (tmp_path / "facts.json").read_bytes()
            checked = run(check=True)
            assert tree() == before_tree
            assert (tmp_path / "facts.json").read_bytes() == before_services
            assert gateway["sender_token"] not in checked.stdout + checked.stderr
            if check_case in ("check-manual", "check-unsafe"):
                assert checked.returncode != 0
                assert "changed=0" in checked.stdout
            else:
                assert checked.returncode == 0, checked.stdout + checked.stderr
                changes = int(re.search(r"changed=(\d+)", checked.stdout).group(1))
                assert (changes == 0) == (check_case == "check-noop")
            if check_case != "check-manual":
                assert not (credentials.parent / ".authority-rollback").exists()
            return
        (tmp_path / "fail-candidate").touch()
        if restore_fault:
            (tmp_path / "fail-restore").touch()
            (tmp_path / "foreign-file").write_text("untouched")
        before_facts = (tmp_path / "facts.json").read_text()
        failed = run()
        if partial_active:
            assert failed.returncode != 0
            assert "Unsupported previous active authority topology" in failed.stdout
            assert (tmp_path / "facts.json").read_text() == before_facts
            assert not (credentials.parent / ".authority-rollback").exists()
            for name, content in prior.items():
                assert (credentials / name).read_text() == content
            return
        if restore_fault:
            assert failed.returncode != 0
            assert "Authority rollback incomplete" in failed.stdout
            assert "authority rollback completed" not in failed.stdout
            snapshot = credentials.parent / ".authority-rollback/snapshot.json"
            assert json.loads(snapshot.read_text())["phase"] == "manual-recovery"
            before = (tmp_path / "facts.json").read_text()
            retry = run()
            assert retry.returncode != 0
            assert (tmp_path / "facts.json").read_text() == before
            assert (tmp_path / "foreign-file").read_text() == "untouched"
            assert snapshot.exists()
            return
        assert failed.returncode != 0
        assert "authority rollback completed" in failed.stdout, (
            failed.stdout + failed.stderr
        )
        assert new_token not in failed.stdout + failed.stderr
        state = json.loads((tmp_path / "facts.json").read_text())
        if prometheus_only:
            assert state["observability-prometheus.service"] == {
                "state": "running",
                "status": "enabled",
            }
            assert state["observability-alertmanager.service"] == {
                "state": "stopped",
                "status": "disabled",
            }
            assert state["observability-silence-gateway.service"] == {
                "state": "stopped",
                "status": "disabled",
            }
            assert not list(credentials.iterdir())
            with urlopen(
                "http://127.0.0.1:" + str(ports["prometheus"]) + "/-/ready", timeout=2
            ) as response:
                assert response.status == 200
            return
        assert all(
            row["state"] == ("running" if initial == "active" else "stopped")
            for row in state.values()
        )
        assert all(
            row["status"] == ("enabled" if initial == "active" else "disabled")
            for row in state.values()
        )
        if initial != "absent":
            for name, content in prior.items():
                assert (credentials / name).read_text() == content
                assert (credentials / name).stat().st_mode & 0o777 == 0o600
            assert not (credentials / "silence-owner-operator-b-token").exists()
        else:
            assert not list(credentials.iterdir())
            assert not (
                root / "usr/local/libexec/observability-silence-gateway"
            ).exists()
        if initial == "active":
            assert request(old_token) == 200
            assert request(new_token) == 403
            (tmp_path / "fail-candidate").unlink()
            success = run()
            assert success.returncode == 0, success.stdout + success.stderr
            assert request(new_token) == 200
            assert request(old_token) == 403
            with urlopen(
                "http://127.0.0.1:" + str(ports["prometheus"]) + "/-/ready", timeout=2
            ) as response:
                assert response.status == 200
    finally:
        for name in ports:
            service(name, "stopped", "false")
