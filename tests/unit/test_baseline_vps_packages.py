"""VPS baseline must not run host-firmware services inside virtual guests."""

from pathlib import Path

import yaml


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
