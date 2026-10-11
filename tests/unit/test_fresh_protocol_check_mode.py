"""Fresh protocol dry-runs require a planned unit before deferring activation."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    (
        "role",
        "unit_task",
        "unit_path",
        "stat_task",
        "guard_task",
        "service_task",
        "plan_var",
        "stat_var",
    ),
    [
        (
            "hysteria",
            "Install hysteria-server systemd unit",
            "/etc/systemd/system/hysteria-server.service",
            "Inspect Hysteria unit before check-mode activation",
            "Require planned Hysteria unit on a fresh check-mode host",
            "Activate guarded standalone frontend generation",
            "_hysteria_unit_plan",
            "_hysteria_unit_before",
        ),
        (
            "amneziawg",
            "Install awg-quick systemd unit (shared across instances)",
            "/etc/systemd/system/awg-quick@.service",
            "Inspect AmneziaWG unit before check-mode activation",
            "Require planned AmneziaWG unit on a fresh check-mode host",
            "Enable and start awg-quick@<iface> for every instance",
            "_awg_unit_plan",
            "_awg_unit_before",
        ),
    ],
)
def test_fresh_unit_is_planned_before_service_activation(
    role: str,
    unit_task: str,
    unit_path: str,
    stat_task: str,
    guard_task: str,
    service_task: str,
    plan_var: str,
    stat_var: str,
) -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles" / role / "tasks/enable.yml").read_text(encoding="utf-8")
    )
    by_name = {task["name"]: task for task in tasks}
    unit, stat, guard, service = (
        by_name[name] for name in (unit_task, stat_task, guard_task, service_task)
    )
    assert unit["register"] == plan_var
    assert stat["ansible.builtin.stat"]["path"] == unit_path
    assert guard["ansible.builtin.assert"]["that"] == [f"{plan_var}.changed"]
    assert (
        tasks.index(unit)
        < tasks.index(stat)
        < tasks.index(guard)
        < tasks.index(service)
    )
    if role == "hysteria":
        assert service["ansible.builtin.import_tasks"] == (
            "{{ role_path }}/../../playbooks/tasks/transport-egress-activate.yml"
        )
        shared = yaml.safe_load(
            (ROOT / "ansible/playbooks/tasks/transport-egress-activate.yml").read_text()
        )[0]["block"]
        generation = next(task for task in shared if task["name"] == "Activate guarded generation after frontend staging")
        assert generation["ansible.builtin.include_role"] == {
            "name": "transport-egress", "tasks_from": "activate",
        }
        assert generation["when"] == "transport_egress_role_enabled | default(false) | bool"
        activation = yaml.safe_load(
            (ROOT / "ansible/roles/transport-egress/tasks/activate.yml").read_text()
        )[0]
        assert activation["when"] == "not ansible_check_mode"
        assert activation["block"][0]["ansible.builtin.systemd_service"]["name"] == (
            "ripdpi-transport-generation.service"
        )
    else:
        assert f"{stat_var}.stat.exists" in service["when"]
