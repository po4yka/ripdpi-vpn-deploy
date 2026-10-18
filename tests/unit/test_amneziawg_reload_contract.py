"""Regression checks for AmneziaWG reload and credential rotation."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE_DIR = REPO_ROOT / "ansible" / "roles" / "amneziawg"
HANDLER = ROLE_DIR / "handlers" / "main.yml"
INSTANCES = ROLE_DIR / "tasks" / "instances.yml"
UNIT_TEMPLATE = ROLE_DIR / "templates" / "awg-quick@.service.j2"
ROTATION_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rotate-credentials.yml"


def test_acquisition_has_no_restart_handler_outside_consumer_acceptance():
    assert yaml.safe_load(HANDLER.read_text()) == []
    tasks = yaml.safe_load((ROLE_DIR / "tasks/enable.yml").read_text())
    assert all("notify" not in task for task in tasks)


def test_all_private_configs_enter_one_complete_retained_consumer():
    tasks = yaml.safe_load((ROLE_DIR / "tasks/configure.yml").read_text())
    render = next(task for task in tasks if task["name"] == "Stage every complete private AmneziaWG configuration")
    assert render["loop"] == "{{ _awg_instances }}"
    assert render["no_log"] is True
    accept = next(task for task in tasks if task["name"] == "Accept complete AmneziaWG runtime and firewall together")
    assert accept["ansible.builtin.command"]["argv"][-1] == "apply"
    assert "'candidates': _awg_consumer_candidates" in accept["ansible.builtin.command"]["stdin"]
    assert "'firewall': _firewall_consumer_candidate" in accept["ansible.builtin.command"]["stdin"]


def test_awg_quick_unit_strips_config_before_syncconf():
    """syncconf only accepts WireGuard directives, not awg-quick hooks."""
    content = UNIT_TEMPLATE.read_text()

    assert "awg syncconf %i" in content
    assert "awg-quick strip {{ amneziawg_config_dir }}/%i.conf" in content


def test_rotation_uses_the_role_instance_normalization_for_every_instance():
    """Rotating credentials must not silently leave secondary peers stale."""
    content = ROTATION_PLAYBOOK.read_text()
    enable = yaml.safe_load((ROLE_DIR / "tasks/enable.yml").read_text())
    assert any(task.get("ansible.builtin.import_tasks") == "instances.yml" for task in enable)
    rotation = yaml.safe_load((REPO_ROOT / "ansible/playbooks/tasks/awg-rotate.yml").read_text())[0]
    assert [task["ansible.builtin.include_role"]["name"] for task in rotation["block"]] == ["firewall", "amneziawg"]
    assert rotation["block"][1]["ansible.builtin.include_role"] == {"name": "amneziawg"}
    assert rotation["rescue"][0]["ansible.builtin.include_role"] == {"name": "firewall", "tasks_from": "awg-restore.yml"}
    assert rotation["rescue"][-1]["ansible.builtin.fail"]["msg"] == "awg-rotation-activation-failed"
    play = yaml.safe_load(content)[0]
    admission = next(task for task in play["tasks"] if task.get("ansible.builtin.import_tasks") == "tasks/public-listener-preflight.yml")
    activation = next(task for task in play["tasks"] if task.get("ansible.builtin.import_tasks") == "tasks/awg-rotate.yml")
    assert admission["when"] == activation["when"]
    assert 0 < play["tasks"].index(admission) < play["tasks"].index(activation)
    assert "Re-render AmneziaWG peers" not in content
    assert "Restart amneziawg" not in content
    staging = rotation["block"][0]
    assert staging["vars"]["firewall_stage_candidate"] is True
    assert staging["vars"]["firewall_site_transaction"] is False


def test_instance_normalization_remains_role_owned():
    """Deploy and rotation share one admitted instance resolver."""
    content = INSTANCES.read_text()

    tasks = yaml.safe_load(content)
    resolver = next(task for task in tasks if "ansible.builtin.command" in task)
    assert resolver["ansible.builtin.command"]["argv"][-2].endswith("scripts/awg_device_binding.py")
    assert resolver["no_log"] is True and resolver["check_mode"] is False
    assert "amneziawg_secrets" in resolver["ansible.builtin.command"]["stdin"]
