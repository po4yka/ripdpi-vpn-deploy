"""A clean Xray dry-run plans its unit without starting an absent service."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_fresh_check_mode_requires_planned_unit_before_activation() -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/xray/tasks/main.yml").read_text(encoding="utf-8")
    )
    by_name = {task["name"]: task for task in tasks}
    unit = by_name["Install xray systemd unit"]
    stat = by_name["Inspect xray unit before check-mode activation"]
    guard = by_name["Require planned xray unit on a fresh check-mode host"]
    service = by_name["Ensure xray is enabled and started"]
    assert unit["register"] == "_xray_unit_plan"
    assert stat["ansible.builtin.stat"]["path"] == unit["ansible.builtin.template"]["dest"]
    assert guard["ansible.builtin.assert"]["that"] == ["_xray_unit_plan.changed"]
    assert tasks.index(unit) < tasks.index(stat) < tasks.index(guard) < tasks.index(service)
    assert "_xray_unit_before.stat.exists" in service["when"]
