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


def test_hysteria_role_does_not_run_the_server_as_a_config_check():
    tasks = (REPO_ROOT / "ansible" / "roles" / "hysteria" / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "server -c {{ hysteria_config_dir }}/config.yaml check" not in tasks


def test_galaxy_resolution_failures_return_tooling_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check-ansible-galaxy-updates.py"])
    with patch.object(galaxy_checker.shutil, "which", return_value="/usr/bin/ansible-galaxy"), patch.object(
        galaxy_checker, "load_pins", return_value=[galaxy_checker.CollectionPin("community.general", "1.0.0")]
    ), patch.object(galaxy_checker, "resolve_latest_version", side_effect=RuntimeError("Galaxy unavailable")):
        assert galaxy_checker.main() == 2

    assert "error: Galaxy unavailable" in capsys.readouterr().err
