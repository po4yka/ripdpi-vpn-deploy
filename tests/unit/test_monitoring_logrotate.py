"""Monitoring must give each nginx log to exactly one logrotate policy."""

from pathlib import Path

from scripts.template_render import merge_render_vars, render_template


REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = REPO_ROOT / "ansible" / "roles" / "monitoring"


def test_nginx_logrotate_policy_replaces_the_overlapping_legacy_dropin():
    tasks = (ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
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
