"""The honeypot connection log must have an actively scheduled size bound."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
ROLE = REPO_ROOT / "ansible" / "roles" / "honeypot"
TASKS = ROLE / "tasks" / "main.yml"
LOGROTATE_TEMPLATE = ROLE / "templates" / "logrotate-honeypot.j2"
SERVICE_TEMPLATE = ROLE / "templates" / "honeypot-logrotate.service.j2"
TIMER_TEMPLATE = ROLE / "templates" / "honeypot-logrotate.timer.j2"

spec = importlib.util.spec_from_file_location("honeypot_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = renderer
spec.loader.exec_module(renderer)


def test_honeypot_log_is_size_rotated_on_a_five_minute_schedule() -> None:
    tasks = TASKS.read_text(encoding="utf-8")

    for template in (LOGROTATE_TEMPLATE, SERVICE_TEMPLATE, TIMER_TEMPLATE):
        assert template.exists()
    for destination in (
        "/etc/honeypot-logrotate.conf",
        "/etc/systemd/system/honeypot-logrotate.service",
        "/etc/systemd/system/honeypot-logrotate.timer",
    ):
        assert destination in tasks
    assert "name: honeypot-logrotate.timer" in tasks
    assert "enabled: true" in tasks
    assert "state: started" in tasks

    variables = renderer.merge_render_vars()
    policy = renderer.render_template(LOGROTATE_TEMPLATE, variables)
    service = renderer.render_template(SERVICE_TEMPLATE, variables)
    timer = renderer.render_template(TIMER_TEMPLATE, variables)

    assert "/var/log/honeypot/connections.log" in policy
    assert "size 10M" in policy
    assert "rotate 7" in policy
    assert "create 0640 honeypot honeypot" in policy
    assert "compress" in policy
    assert "copytruncate" not in policy
    assert "--state /var/lib/honeypot/logrotate.status" in service
    assert "/etc/honeypot-logrotate.conf" in service
    assert "OnUnitActiveSec=5m" in timer
    assert "Persistent=true" in timer
