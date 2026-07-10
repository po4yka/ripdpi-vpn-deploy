"""Regression coverage for P2 maintenance hardening review fixes."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
GALAXY_CHECKER = REPO_ROOT / "scripts" / "check-ansible-galaxy-updates.py"

_spec = importlib.util.spec_from_file_location("check_ansible_galaxy_updates", GALAXY_CHECKER)
galaxy_checker = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = galaxy_checker
_spec.loader.exec_module(galaxy_checker)


def test_firewall_precedes_intrusion_prevention_in_site_playbook():
    site = (REPO_ROOT / "ansible" / "playbooks" / "site.yml").read_text(encoding="utf-8")
    assert site.index("    - role: firewall") < site.index("    - role: intrusion_prevention")


def test_firewall_applies_nftables_before_policy_ratelimit_preflight():
    site = (REPO_ROOT / "ansible" / "playbooks" / "site.yml").read_text(encoding="utf-8")
    tasks = (REPO_ROOT / "ansible" / "roles" / "firewall" / "tasks" / "main.yml").read_text(encoding="utf-8")
    policy_tasks = (REPO_ROOT / "ansible" / "roles" / "policy-ratelimit" / "tasks" / "main.yml").read_text(encoding="utf-8")
    molecule_converge = (REPO_ROOT / "ansible" / "roles" / "policy-ratelimit" / "molecule" / "default" / "converge.yml").read_text(encoding="utf-8")
    assert site.index("    - role: firewall") < site.index("    - role: policy-ratelimit")
    assert tasks.index("- name: Render nftables config") < tasks.index("- name: Reload nftables before dependent roles run")
    assert "ansible.builtin.meta: flush_handlers" not in tasks
    assert "policy_offenders" in policy_tasks
    assert "policy_offenders6" in policy_tasks
    assert molecule_converge.index("    - role: firewall") < molecule_converge.index("    - role: policy-ratelimit")


def test_hysteria_role_does_not_run_the_server_as_a_config_check():
    tasks = (REPO_ROOT / "ansible" / "roles" / "hysteria" / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "server -c {{ hysteria_config_dir }}/config.yaml check" not in tasks


def test_monitoring_preserves_honeypot_textfile_write_access():
    honeypot_tasks = (REPO_ROOT / "ansible" / "roles" / "honeypot" / "tasks" / "main.yml").read_text(encoding="utf-8")
    monitoring_tasks = (REPO_ROOT / "ansible" / "roles" / "monitoring" / "tasks" / "main.yml").read_text(encoding="utf-8")
    honeypot_defaults = (REPO_ROOT / "ansible" / "roles" / "honeypot" / "defaults" / "main.yml").read_text(encoding="utf-8")
    assert "node_exporter_textfile" in honeypot_defaults
    assert "node_exporter_textfile" in monitoring_tasks
    assert 'mode: "3775"' in honeypot_tasks
    assert 'mode: "3775"' in monitoring_tasks
    assert "notify: Restart honeypot" in honeypot_tasks
    assert "Ensure existing honeypot joins textfile writer group" in monitoring_tasks


def test_galaxy_resolution_failures_return_tooling_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check-ansible-galaxy-updates.py"])
    with patch.object(galaxy_checker.shutil, "which", return_value="/usr/bin/ansible-galaxy"), patch.object(
        galaxy_checker, "load_pins", return_value=[galaxy_checker.CollectionPin("community.general", "1.0.0")]
    ), patch.object(galaxy_checker, "resolve_latest_version", side_effect=RuntimeError("Galaxy unavailable")):
        assert galaxy_checker.main() == 2

    assert "error: Galaxy unavailable" in capsys.readouterr().err
