"""Monitoring must give each nginx log to exactly one logrotate policy."""

from pathlib import Path

from scripts.template_render import merge_render_vars, render_fragment, render_template

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
    assert "rotate 7" in policy


def test_nginx_rotation_reopens_logs_without_reload_and_propagates_failure(tmp_path):
    import os
    import subprocess

    policy = render_template(ROLE / "templates/logrotate-nginx.j2", merge_render_vars())
    body = policy.split("postrotate", 1)[1].split("endscript", 1)[0]
    binary = tmp_path / "systemctl"
    log = tmp_path / "calls"
    binary.write_text("""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$CALLS"
if [[ "$1" == 'kill' ]]; then exit "${KILL_STATUS:-0}"; fi
if [[ "${INACTIVE:-0}" == 1 ]]; then exit 3; fi
""")
    binary.chmod(0o755)
    env = {**os.environ, "PATH": f'{tmp_path}:{os.environ["PATH"]}', "CALLS": str(log)}
    result = subprocess.run(["bash", "-c", body], env=env, capture_output=True)
    assert result.returncode == 0
    assert log.read_text().splitlines() == [
        "is-active --quiet nginx.service",
        "kill --signal=USR1 --kill-whom=main nginx.service",
    ]
    failed = subprocess.run(["bash", "-c", body], env={**env, "KILL_STATUS": "23"}, capture_output=True)
    assert failed.returncode == 23
    log.unlink()
    inactive = subprocess.run(["bash", "-c", body], env={**env, "INACTIVE": "1"}, capture_output=True)
    assert inactive.returncode == 0
    assert log.read_text().splitlines() == ["is-active --quiet nginx.service"]


def test_xray_rotation_never_restarts_or_signals_the_service():
    import yaml

    # Regression: a postrotate restart dropped every client session at each
    # daily rotation. Xray appends through a held descriptor, so the policy
    # truncates in place and runs no script on any profile.
    renders = {"defaults": merge_render_vars()}
    for profile in sorted((REPO_ROOT / "ansible" / "group_vars").glob("vpn-*.yml")):
        variables = merge_render_vars()
        variables.update(yaml.safe_load(profile.read_text(encoding="utf-8")) or {})
        renders[profile.name] = variables
    assert len(renders) > 1
    for name, variables in renders.items():
        policy = render_template(ROLE / "templates/logrotate-xray.j2", variables)
        directives = [line.split("#", 1)[0].split() for line in policy.splitlines()]
        words = {word for line in directives for word in line}
        assert "copytruncate" in words, name
        assert not words & {
            "postrotate", "prerotate", "firstaction", "lastaction", "preremove",
            "endscript", "create", "systemctl", "python3",
        }, name


def test_xhttp_only_retains_xray_logs_and_subscription_only_has_no_xray_policy():
    import yaml

    tasks = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    selector = next(task for task in tasks if task["name"] == "Resolve whether Xray diagnostics are enabled")["ansible.builtin.set_fact"]["_monitoring_xray_stats_enabled"]
    policy = next(task for task in tasks if task["name"] == "Drop logrotate config for xray")
    assert policy["when"] == "_monitoring_xray_stats_enabled | bool"
    variables = {"vpn": {"enable_xray_reality": False, "enable_nginx_xhttp": True}, "vpn_subscription_only": False}
    assert render_fragment("xray-diagnostics-selector.txt.j2", selector, variables).strip() == "True"
    variables["vpn_subscription_only"] = True
    assert render_fragment("xray-diagnostics-selector.txt.j2", selector, variables).strip() == "False"
