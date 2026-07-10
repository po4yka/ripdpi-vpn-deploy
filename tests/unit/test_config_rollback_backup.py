"""Ensure idempotent convergence does not overwrite rollback configs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_xray_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/xray/tasks/main.yml").read_text()
    assert "register: _xray_config_change" in content
    assert "- _xray_config_change.changed" in content


def test_hysteria_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/hysteria/tasks/main.yml").read_text()
    assert "register: _hysteria_config_change" in content
    assert "- _hysteria_config_change.changed" in content
