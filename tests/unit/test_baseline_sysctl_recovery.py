"""Baseline runtime sysctls must recover after an interrupted play."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_baseline_reconciles_sysctls_without_change_notifications():
    tasks = (ROOT / "ansible/roles/baseline/tasks/main.yml").read_text()
    handlers = (ROOT / "ansible/roles/baseline/handlers/main.yml").read_text()

    assert "name: Reconcile effective sysctl values on every converge" in tasks
    assert "cmd: sysctl -e --system" in tasks
    assert "notify: Apply sysctl" not in tasks
    assert "name: Apply sysctl" not in handlers
