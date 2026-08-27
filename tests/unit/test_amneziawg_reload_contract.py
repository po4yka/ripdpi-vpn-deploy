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


def test_role_restart_applies_full_state_via_the_awg_quick_unit():
    """Config changes apply through a full unit restart: the reload verb
    cannot apply address/route changes and aborts on inactive instances,
    which silently skipped the rest of the handler loop."""
    content = HANDLER.read_text()

    assert 'name: "awg-quick@{{ item.name }}"' in content
    assert "state: restarted" in content
    assert "state: reloaded" not in content
    assert "awg syncconf" not in content


def test_config_render_notifies_the_installed_restart_handler():
    tasks = yaml.safe_load((ROLE_DIR / "tasks" / "main.yml").read_text())
    handlers = yaml.safe_load(HANDLER.read_text())
    render = next(task for task in tasks if task["name"] == "Render AmneziaWG interface configs")
    handler = next(handler for handler in handlers if handler["name"] == render["notify"])
    assert handler["ansible.builtin.systemd_service"]["state"] == "restarted"


def test_awg_quick_unit_strips_config_before_syncconf():
    """syncconf only accepts WireGuard directives, not awg-quick hooks."""
    content = UNIT_TEMPLATE.read_text()

    assert "awg syncconf %i" in content
    assert "awg-quick strip %i" in content


def test_rotation_uses_the_role_instance_normalization_for_every_instance():
    """Rotating credentials must not silently leave secondary peers stale."""
    content = ROTATION_PLAYBOOK.read_text()
    handler = content.split("    - name: Restart amneziawg", maxsplit=1)[1]

    assert "tasks_from: instances.yml" in content
    assert 'loop: "{{ _awg_instances }}"' in content
    assert 'dest: "{{ amneziawg_config_dir }}/{{ item.name }}.conf"' in content
    assert "ansible.builtin.systemd_service:" in handler
    assert 'name: "awg-quick@{{ item.name }}"' in handler
    assert "notify: Restart amneziawg" in content
    assert "state: restarted" in handler
    assert "state: reloaded" not in handler
    assert (
        "loop: \"{{ _awg_instances | default([{'name': amneziawg.interface}]) }}\""
        in handler
    )


def test_instance_normalization_remains_role_owned():
    """Deploy and rotation share one canonical multi-instance fallback."""
    content = INSTANCES.read_text()

    assert "amneziawg_secrets.instances" in content
    assert "'name': amneziawg.interface" in content
