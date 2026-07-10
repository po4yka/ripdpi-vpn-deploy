"""Regression checks for AmneziaWG reload and credential rotation."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE_DIR = REPO_ROOT / "ansible" / "roles" / "amneziawg"
HANDLER = ROLE_DIR / "handlers" / "main.yml"
INSTANCES = ROLE_DIR / "tasks" / "instances.yml"
UNIT_TEMPLATE = ROLE_DIR / "templates" / "awg-quick@.service.j2"
ROTATION_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rotate-credentials.yml"


def test_role_reload_uses_the_awg_quick_systemd_unit():
    """The unit strips awg-quick-only directives before syncconf runs."""
    content = HANDLER.read_text()

    assert 'name: "awg-quick@{{ item.name }}"' in content
    assert "state: reloaded" in content
    assert "awg syncconf" not in content


def test_awg_quick_unit_strips_config_before_syncconf():
    """syncconf only accepts WireGuard directives, not awg-quick hooks."""
    content = UNIT_TEMPLATE.read_text()

    assert "awg syncconf %i" in content
    assert "awg-quick strip %i" in content


def test_rotation_uses_the_role_instance_normalization_for_every_instance():
    """Rotating credentials must not silently leave secondary peers stale."""
    content = ROTATION_PLAYBOOK.read_text()
    handler = content.split("    - name: Reload amneziawg", maxsplit=1)[1]

    assert "tasks_from: instances.yml" in content
    assert 'loop: "{{ _awg_instances }}"' in content
    assert 'dest: "{{ amneziawg_config_dir }}/{{ item.name }}.conf"' in content
    assert "ansible.builtin.systemd_service:" in handler
    assert 'name: "awg-quick@{{ item.name }}"' in handler
    assert "state: reloaded" in handler
    assert 'loop: "{{ _awg_instances | default([{\'name\': amneziawg.interface}]) }}"' in handler


def test_instance_normalization_remains_role_owned():
    """Deploy and rotation share one canonical multi-instance fallback."""
    content = INSTANCES.read_text()

    assert "amneziawg_secrets.instances" in content
    assert "'name': amneziawg.interface" in content
