"""VPS baseline must not run host-firmware services inside virtual guests."""

from pathlib import Path

import yaml
from jinja2 import Environment


REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "ansible" / "roles" / "baseline" / "tasks" / "main.yml"


def test_baseline_removes_fwupd_and_clears_obsolete_failed_units() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    removal = next(task for task in tasks if task["name"] == "Remove VPS firmware update tooling")
    package = removal["ansible.builtin.apt"]

    assert package["name"] == ["fwupd"]
    assert package["state"] == "absent"
    assert package["purge"] is True

    cleanup = next(task for task in tasks if task["name"] == "Clear obsolete fwupd failed units")
    assert cleanup["ansible.builtin.command"]["cmd"] == (
        "systemctl reset-failed fwupd.service fwupd-refresh.service"
    )
    assert cleanup["changed_when"] is False


def test_fresh_check_mode_requires_planned_timesync_package_before_activation() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    by_name = {task["name"]: task for task in tasks}
    package = by_name["Install baseline packages"]
    guard = by_name["Require planned timesync installation when check mode lacks the unit"]
    service = by_name["Ensure timesync is enabled"]
    assert "systemd-timesyncd" in package["ansible.builtin.apt"]["name"]
    assert package["register"] == "baseline_packages"
    assert tasks.index(package) < tasks.index(by_name["Collect service facts"]) < tasks.index(guard) < tasks.index(service)
    assert guard["ansible.builtin.assert"]["that"] == ["baseline_packages.changed"]
    environment = Environment()

    def selected(task: dict, *, check: bool, installed: bool) -> bool:
        conditions = task["when"]
        if isinstance(conditions, str):
            conditions = [conditions]
        variables = {"ansible_check_mode": check,
                     "ansible_facts": {"services": {"systemd-timesyncd.service": {}} if installed else {}}}
        return all(environment.compile_expression(condition)(**variables) for condition in conditions)

    assert selected(guard, check=True, installed=False)
    assert not selected(service, check=True, installed=False)
    assert not selected(guard, check=True, installed=True)
    assert selected(service, check=True, installed=True)
    assert not selected(guard, check=False, installed=False)
    assert selected(service, check=False, installed=False)
