"""Fresh-host geodata dry-runs must retain the planned publication checks."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_fresh_check_mode_checks_sources_and_defers_unavailable_paths() -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/geodata/tasks/main.yml").read_text(encoding="utf-8")
    )
    by_name = {task["name"]: task for task in tasks}
    directory = by_name["Ensure geodata install directory"]
    directory_guard = by_name[
        "Require a planned geodata directory on a fresh check-mode host"
    ]
    source_check = by_name[
        "Check pinned geodata URLs without writing on a fresh check-mode host"
    ]
    assert directory["register"] == "_geodata_directory_plan"
    assert directory_guard["ansible.builtin.assert"]["that"] == [
        "_geodata_directory_plan.changed"
    ]
    assert tasks.index(directory) < tasks.index(directory_guard) < tasks.index(source_check)
    assert source_check["check_mode"] is False
    assert source_check["ansible.builtin.uri"]["method"] == "HEAD"
    assert source_check["ansible.builtin.uri"]["status_code"] == 200
    for artifact in ("Download geosite.dat", "Download geoip.dat"):
        assert "_geodata_directory_before.stat.isdir" in by_name[artifact]["when"]

    timer_guard = by_name[
        "Require a planned geodata timer on a fresh check-mode host"
    ]
    assert timer_guard["ansible.builtin.assert"]["that"] == [
        "_geodata_timer_plan.changed"
    ]
    assert tasks.index(by_name["Drop refresh systemd timer"]) < tasks.index(
        timer_guard
    ) < tasks.index(by_name["Enable refresh timer"])
