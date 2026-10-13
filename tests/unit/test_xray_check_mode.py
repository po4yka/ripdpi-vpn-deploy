"""A clean Xray dry-run plans its unit without starting an absent service."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_fresh_check_mode_requires_planned_unit_before_activation() -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/xray/tasks/enable.yml").read_text(encoding="utf-8")
    )
    by_name = {task["name"]: task for task in tasks}
    unit = by_name["Detect Xray unit change before guarded transaction"]
    staged = by_name["Stage complete Xray authority for guarded consumer acceptance"]
    service = by_name["Activate guarded standalone frontend generation"]
    assert unit["check_mode"] is True and unit["register"] == "_xray_unit_change"
    assert unit["ansible.builtin.template"]["dest"] == "/etc/systemd/system/xray.service"
    assert unit["ansible.builtin.template"]["mode"] == "0644"
    assert tasks.index(unit) < tasks.index(staged) < tasks.index(service)
    assert "not (transport_egress_fresh_check_mode" in staged["when"]
    plan = staged["ansible.builtin.set_fact"]["transport_runtime_candidates"]
    assert "'/etc/systemd/system/xray.service', 'mode': 420, 'gid': 0" in plan
    assert "xray.service.j2') | b64encode" in plan
    assert staged["no_log"] is True and staged["diff"] is False
    assert service["ansible.builtin.import_tasks"].endswith("transport-egress-activate.yml")
    activation = yaml.safe_load((ROOT / "ansible/roles/transport-egress/tasks/activate.yml").read_text())
    guarded = next(task for task in activation if any("ansible.builtin.systemd_service" in child for child in task.get("block", [])))
    assert guarded["when"] == "not ansible_check_mode"
    assert any("status" in child.get("ansible.builtin.command", {}).get("argv", []) for child in guarded["block"])
