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
