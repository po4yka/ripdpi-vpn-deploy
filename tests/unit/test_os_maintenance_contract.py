"""Contracts for recurring and rolling operating-system maintenance."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_vpn_fleet_enables_unattended_security_updates() -> None:
    group_vars = yaml.safe_load((REPO_ROOT / "ansible/group_vars/all.yml").read_text())

    assert group_vars["security_controls"]["unattended_upgrades"] is True
    assert group_vars["security_controls"]["automatic_reboot"] is False
    assert group_vars["package_updates"]["security_only"] is True


def test_os_maintenance_is_rolling_and_closes_the_backlog() -> None:
    source = (REPO_ROOT / "ansible/playbooks/os-maintenance.yml").read_text()
    playbook = yaml.safe_load(source)
    play = playbook[0]
    tasks = play["tasks"]
    task_names = {task["name"]: task for task in tasks}

    assert play["hosts"] == "vpn"
    assert play["serial"] == 1
    assert play["any_errors_fatal"] is True
    assert task_names["Apply all pending OS package upgrades"]["ansible.builtin.apt"]["upgrade"] == "dist"
    assert task_names["Reboot after kernel or core-library updates"]["ansible.builtin.reboot"]
    assert task_names["Reject a residual package backlog"]["ansible.builtin.assert"]
    assert task_names["Reject a residual reboot requirement"]["ansible.builtin.assert"]
    assert task_names["Verify enabled transport services after maintenance"]["ansible.builtin.command"]
    assert "prometheus-node-exporter" in source
    assert "'node_exporter'" not in source
    assert "ansible_os_family" not in source


def test_make_exposes_verified_os_maintenance_target() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()

    assert "os-maintenance: require-clean-source require-inventory" in makefile
    assert "playbooks/os-maintenance.yml" in makefile
    assert "$(MAKE) verify" in makefile
    assert "$(MAKE) security-verify" in makefile
