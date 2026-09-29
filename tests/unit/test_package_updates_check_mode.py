"""Check-mode contract for the unattended security updates role."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "ansible" / "roles" / "package_updates" / "tasks" / "main.yml"


def test_fresh_host_check_mode_defers_binary_validation_until_install() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    install = next(
        task for task in tasks if task["name"] == "Install unattended update packages"
    )
    validate = next(
        task
        for task in tasks
        if task["name"] == "Validate unattended-upgrades configuration"
    )

    assert install["register"] == "package_updates_packages"
    assert validate["when"] == [
        "package_updates.enabled | default(true)",
        "not ansible_check_mode or not (package_updates_packages.changed | default(false))",
    ]
