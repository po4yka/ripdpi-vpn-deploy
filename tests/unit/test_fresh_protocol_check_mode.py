"""Fresh protocol dry-runs require a planned unit before deferring activation."""

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("role", "unit_task", "unit_path", "stat_task", "guard_task", "service_task", "plan_var", "stat_var"),
    [
        (
            "hysteria", "Install hysteria-server systemd unit",
            "/etc/systemd/system/hysteria-server.service",
            "Inspect Hysteria unit before check-mode activation",
            "Require planned Hysteria unit on a fresh check-mode host",
            "Ensure hysteria-server is enabled and started",
            "_hysteria_unit_plan", "_hysteria_unit_before",
        ),
        (
            "amneziawg", "Install awg-quick systemd unit (shared across instances)",
            "/etc/systemd/system/awg-quick@.service",
            "Inspect AmneziaWG unit before check-mode activation",
            "Require planned AmneziaWG unit on a fresh check-mode host",
            "Enable and start awg-quick@<iface> for every instance",
            "_awg_unit_plan", "_awg_unit_before",
        ),
    ],
)
def test_fresh_unit_is_planned_before_service_activation(
    role: str, unit_task: str, unit_path: str, stat_task: str, guard_task: str,
    service_task: str, plan_var: str, stat_var: str,
) -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles" / role / "tasks/main.yml").read_text(encoding="utf-8")
    )
    by_name = {task["name"]: task for task in tasks}
    unit, stat, guard, service = (by_name[name] for name in
                                  (unit_task, stat_task, guard_task, service_task))
    assert unit["register"] == plan_var
    assert stat["ansible.builtin.stat"]["path"] == unit_path
    assert guard["ansible.builtin.assert"]["that"] == [f"{plan_var}.changed"]
    assert tasks.index(unit) < tasks.index(stat) < tasks.index(guard) < tasks.index(service)
    assert f"{stat_var}.stat.exists" in service["when"]
