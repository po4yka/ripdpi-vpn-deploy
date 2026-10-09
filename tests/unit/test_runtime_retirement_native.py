"""Actual systemd timer ownership, restoration and retirement preflight."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/runtime-release"
STATE = ROLE / "files/systemd-unit-state.py"
pytestmark = pytest.mark.native_runtime


def run(*arguments, input=None):
    result = subprocess.run(
        arguments, input=input, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return result


def test_timer_runtime_enablement_is_exact_and_foreign_authority_refuses_before_stop(
    tmp_path,
):
    assert sys.platform == "linux" and os.geteuid() == 0
    name = "p2-retire-runtime-fixture"
    service = Path(f"/etc/systemd/system/{name}.service")
    timer = Path(f"/etc/systemd/system/{name}.timer")
    assert not service.exists() and not timer.exists()
    service.write_text("[Service]\nType=oneshot\nExecStart=/usr/bin/true\n")
    timer.write_text(
        f"[Timer]\nOnActiveSec=1h\nUnit={name}.service\n[Install]\nWantedBy=timers.target\n"
    )
    names = [timer.name]
    owned = tmp_path / "foreign-authority"
    owned.write_text("foreign data must remain")
    os.chown(owned, 65534, 65534)

    def state():
        return json.loads(
            run(sys.executable, str(STATE), input=json.dumps(names)).stdout
        )

    try:
        run("systemctl", "daemon-reload")
        run("systemctl", "enable", "--runtime", timer.name)
        run("systemctl", "start", timer.name)
        previous = state()
        assert previous[timer.name] == {
            "exists": True,
            "active": True,
            "enabled": True,
            "unit_file_state": "enabled-runtime",
        }
        run("systemctl", "disable", timer.name)
        run("systemctl", "enable", timer.name)
        run("systemctl", "stop", timer.name)
        run(sys.executable, str(STATE), "restore", input=json.dumps(previous))
        assert state() == previous
        assert not os.path.lexists(
            Path("/etc/systemd/system/timers.target.wants") / timer.name
        )

        play = tmp_path / "retire.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "ansible_python_interpreter": sys.executable,
                            "runtime_retire_units": names,
                            "runtime_retire_paths": [str(owned)],
                        },
                        "tasks": [
                            {
                                "ansible.builtin.include_role": {
                                    "name": "runtime-release",
                                    "tasks_from": "retire",
                                }
                            }
                        ],
                    }
                ]
            )
        )
        environment = dict(os.environ, ANSIBLE_ROLES_PATH=str(ROOT / "ansible/roles"))
        rejected = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(play)],
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
        assert rejected.returncode != 0
        assert state() == previous
        assert owned.read_text() == "foreign data must remain"
        os.chown(owned, 0, 0)
        accepted = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(play)],
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr
        assert not owned.exists()
        assert not state()[timer.name]["active"] and not state()[timer.name]["enabled"]
    finally:
        subprocess.run(["systemctl", "stop", timer.name], capture_output=True)
        subprocess.run(["systemctl", "disable", timer.name], capture_output=True)
        for path in (timer, service):
            path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)


@pytest.mark.parametrize(
    "role,handler_name,is_timer",
    [
        ("watchdog", "Restart watchdog timer", True),
        ("backup", "Restart backup restore drill timer", True),
        ("snell", "Restart snell", False),
        ("policy-ratelimit", "Restart policy-ratelimit", False),
    ],
)
def test_queued_handler_cannot_restart_a_retired_runtime(
    tmp_path, role, handler_name, is_timer
):
    import copy

    name = "p2-queued-retirement-fixture"
    service = Path(f"/etc/systemd/system/{name}.service")
    timer = Path(f"/etc/systemd/system/{name}.timer")
    assert not service.exists() and not timer.exists()
    service.write_text(
        "[Service]\nExecStart=/usr/bin/sleep infinity\n[Install]\nWantedBy=multi-user.target\n"
    )
    timer.write_text(
        f"[Timer]\nOnActiveSec=1h\nUnit={name}.service\n[Install]\nWantedBy=timers.target\n"
    )
    unit = timer.name if is_timer else service.name
    original = yaml.safe_load(
        (ROOT / f"ansible/roles/{role}/handlers/main.yml").read_text()
    )
    handler = copy.deepcopy(
        next(row for row in original if row["name"] == handler_name)
    )
    # Only the real unit name is isolated; original handler conditions/actions remain.
    handler["ansible.builtin.systemd_service"]["name"] = unit
    variable = role.replace("-", "_") + "_role_enabled"
    play = tmp_path / "queued.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        variable: True,
                        "_watchdog_timer_preexisting": {"stat": {"exists": True}},
                        "_backup_restore_drill_timer_preexisting": {
                            "stat": {"exists": True}
                        },
                        "backup_restore_drill_enabled": True,
                    },
                    "tasks": [
                        {
                            "name": "Queue existing runtime handler",
                            "ansible.builtin.debug": {"msg": "queued"},
                            "changed_when": True,
                            "notify": handler_name,
                        },
                        {
                            "name": "Select disabled role intent",
                            "ansible.builtin.set_fact": {variable: False},
                        },
                        {
                            "name": "Retire fixture runtime before handler flush",
                            "ansible.builtin.systemd_service": {
                                "name": unit,
                                "state": "stopped",
                                "enabled": False,
                            },
                        },
                    ],
                    "handlers": [handler],
                }
            ]
        )
    )
    try:
        run("systemctl", "daemon-reload")
        run("systemctl", "start", unit)
        run("systemctl", "is-active", "--quiet", unit)
        result = run("ansible-playbook", "-i", "localhost,", str(play))
        assert "failed=0" in result.stdout
        assert (
            subprocess.run(
                ["systemctl", "is-active", "--quiet", unit], capture_output=True
            ).returncode
            != 0
        )
    finally:
        subprocess.run(
            ["systemctl", "stop", timer.name, service.name], capture_output=True
        )
        subprocess.run(
            ["systemctl", "disable", timer.name, service.name], capture_output=True
        )
        for path in (timer, service):
            path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)


def test_retirement_validation_refuses_foreign_descendants_and_preserves_unit_masks(
    tmp_path,
):
    helper = ROLE / "files/validate_retirement.py"
    directory = tmp_path / "owned-root"
    directory.mkdir()
    child = directory / "unrelated-child"
    child.write_text("foreign child")
    os.chown(child, 65534, 65534)
    rejected = subprocess.run(
        [sys.executable, str(helper)],
        input=json.dumps([str(directory)]),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert rejected.returncode == 2
    assert child.read_text() == "foreign child"
    mask = Path("/etc/systemd/system/p2-retire-mask-fixture.service")
    assert not os.path.lexists(mask)
    mask.symlink_to("/dev/null")
    try:
        accepted = run(sys.executable, str(helper), input=json.dumps([str(mask)]))
        assert json.loads(accepted.stdout)["paths"] == []
        assert mask.readlink() == Path("/dev/null")
    finally:
        mask.unlink()
