"""AmneziaWG source-pin attestation must remain active in check mode."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_commit_resolution_runs_during_check_mode():
    tasks = yaml.safe_load((ROOT / "ansible/roles/amneziawg/tasks/main.yml").read_text())
    resolve_tasks = [task for task in tasks if task["name"].startswith("Resolve the amneziawg-")]

    assert len(resolve_tasks) == 2
    assert all(task.get("check_mode") is False for task in resolve_tasks)
    assert all(task.get("changed_when") is False for task in resolve_tasks)


def test_build_receipts_make_check_mode_commit_aware_without_building():
    tasks = yaml.safe_load((ROOT / "ansible/roles/amneziawg/tasks/main.yml").read_text())
    by_name = {task["name"]: task for task in tasks}

    for component, fact in (
        ("amneziawg-go", "_awg_go_rebuild_required"),
        ("amneziawg-tools", "_awg_tools_rebuild_required"),
    ):
        report = by_name[f"Report {component} build drift"]
        build = by_name[f"Build {component}"]
        receipt = by_name[f"Record {component} built commit"]

        assert report["when"] == "ansible_check_mode"
        assert report["changed_when"] == fact
        assert "not ansible_check_mode" in build["when"]
        assert fact in build["when"]
        assert "creates" not in build.get("args", {})
        assert "not ansible_check_mode" in receipt["when"]
        assert fact in receipt["when"]

    source = (ROOT / "ansible/roles/amneziawg/tasks/main.yml").read_text()
    assert "/opt/src/amneziawg-tools/src/wg" in source
    assert "/opt/src/amneziawg-tools/src/awg" not in source
