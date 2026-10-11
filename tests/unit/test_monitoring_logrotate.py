"""Monitoring must give each nginx log to exactly one logrotate policy."""

from pathlib import Path

from scripts.template_render import merge_render_vars, render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = REPO_ROOT / "ansible" / "roles" / "monitoring"


def test_nginx_logrotate_policy_replaces_the_overlapping_legacy_dropin():
    tasks = (ROLE / "tasks" / "enable.yml").read_text(encoding="utf-8")
    policy = render_template(
        ROLE / "templates" / "logrotate-nginx.j2", merge_render_vars()
    )

    assert "dest: /etc/logrotate.d/nginx" in tasks
    assert "path: /etc/logrotate.d/nginx-vpn" in tasks
    assert "state: absent" in tasks
    assert "cmd: logrotate --debug /etc/logrotate.conf" in tasks
    assert policy.startswith("/var/log/nginx/*.log {")
    assert "/var/log/nginx/vpn-*.log" not in policy
    assert "rotate 14" in policy


def test_xray_rotation_restarts_active_service_and_propagates_failure(tmp_path):
    import os
    import subprocess

    variables = merge_render_vars()
    variables["vpn"]["enable_transport_egress"] = False
    policy = render_template(ROLE / "templates/logrotate-xray.j2", variables)
    body = policy.split("postrotate", 1)[1].split("endscript", 1)[0]
    assert "HUP" not in body
    binary = tmp_path / "systemctl"
    log = tmp_path / "calls"
    binary.write_text("""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$CALLS"
if [[ "$1" == 'restart' ]]; then exit "${RESTART_STATUS:-0}"; fi
if [[ "${INACTIVE:-0}" == 1 ]]; then exit 3; fi
""")
    binary.chmod(0o755)
    env = {**os.environ, "PATH": f'{tmp_path}:{os.environ["PATH"]}', "CALLS": str(log)}
    result = subprocess.run(["bash", "-c", body], env=env, capture_output=True)
    assert result.returncode == 0
    assert log.read_text().splitlines() == [
        "is-active --quiet xray.service",
        "restart xray.service",
        "is-active --quiet xray.service",
    ]
    failed = subprocess.run(
        ["bash", "-c", body], env={**env, "RESTART_STATUS": "23"}, capture_output=True
    )
    assert failed.returncode == 23
    log.unlink()
    inactive = subprocess.run(
        ["bash", "-c", body], env={**env, "INACTIVE": "1"}, capture_output=True
    )
    assert inactive.returncode == 0
    assert log.read_text().splitlines() == ["is-active --quiet xray.service"]


def test_guarded_xray_rotation_uses_admitted_recovery_without_direct_restart(tmp_path):
    import os
    import subprocess

    variables = merge_render_vars()
    variables["vpn"]["enable_transport_egress"] = True
    policy = render_template(ROLE / "templates/logrotate-xray.j2", variables)
    body = policy.split("postrotate", 1)[1].split("endscript", 1)[0]
    calls = tmp_path / "calls"
    systemctl = tmp_path / "systemctl"
    systemctl.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\nexit \"${INACTIVE:-0}\"\n")
    systemctl.chmod(0o755)
    python = tmp_path / "python3"
    python.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\nexit \"${RECOVERY_STATUS:-0}\"\n")
    python.chmod(0o755)
    environment = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "CALLS": str(calls)}
    result = subprocess.run(["bash", "-c", body], env=environment, capture_output=True)
    assert result.returncode == 0
    assert calls.read_text().splitlines() == [
        "is-active --quiet xray.service",
        "-Es /usr/local/libexec/ripdpi-transport-egress/generation.py recover --config /etc/ripdpi/transport-egress/generation.json --normalizer-config /etc/ripdpi/transport-egress/normalizer.json --unit xray.service",
    ]
    failed = subprocess.run(["bash", "-c", body], env={**environment, "RECOVERY_STATUS": "23"}, capture_output=True)
    assert failed.returncode == 23
    assert "restart" not in calls.read_text()
    calls.unlink()
    inactive = subprocess.run(["bash", "-c", body], env={**environment, "INACTIVE": "3"}, capture_output=True)
    assert inactive.returncode == 0
    assert calls.read_text().splitlines() == ["is-active --quiet xray.service"]


def test_xhttp_only_retains_xray_logs_and_subscription_only_has_no_xray_policy():
    import yaml
    from jinja2 import Environment

    tasks = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    selector = next(task for task in tasks if task["name"] == "Resolve whether Xray diagnostics are enabled")["ansible.builtin.set_fact"]["_monitoring_xray_stats_enabled"]
    policy = next(task for task in tasks if task["name"] == "Drop logrotate config for xray")
    assert policy["when"] == "_monitoring_xray_stats_enabled | bool"
    variables = {"vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": True}, "vpn_subscription_only": False}
    environment = Environment()
    environment.filters["bool"] = bool
    assert environment.from_string(selector).render(variables).strip() == "True"
    variables["vpn_subscription_only"] = True
    assert environment.from_string(selector).render(variables).strip() == "False"
