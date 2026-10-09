"""Real systemd retirement of recorded membership using inert fixture units.

The fixture units exercise role ownership and systemd activation only; they do
not claim AmneziaWG tunnel or upstream source-build acceptance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/amneziawg"
pytestmark = pytest.mark.native_runtime


def test_recorded_two_to_one_rename_and_repeated_disable_preserve_foreign_unit(
    tmp_path,
):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires owned root Linux systemd fixture host")
    if not shutil.which("ansible-playbook") or not Path("/run/systemd/system").exists():
        pytest.skip("requires active systemd and pinned Ansible")
    record = Path("/var/lib/ripdpi/amneziawg/instances.json")
    assert not record.exists(), "native fixture must not displace prior AWG ownership"
    prefix = "p2" + uuid.uuid4().hex[:7]
    members = [prefix + suffix for suffix in "abcf"]
    units = ["awg-quick@" + name + ".service" for name in members]
    configs = tmp_path / "configs"
    configs.mkdir()
    owned_dir_existed = record.parent.exists()
    record.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    selections = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    select = next(
        task
        for task in selections
        if task["name"] == "Select obsolete recorded AmneziaWG instances"
    )
    publish = next(
        task
        for task in selections
        if task["name"] == "Record the converged AmneziaWG instance ownership set"
    )

    def ctl(*argv, check=True):
        return subprocess.run(
            ["systemctl", *argv],
            capture_output=True,
            text=True,
            check=check,
            timeout=10,
        )

    def converge(previous, current):
        record.write_text(
            json.dumps({"schema": 1, "config_dir": str(configs), "instances": previous})
        )
        record.chmod(0o600)
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "ansible_become": False,
                    "ansible_python_interpreter": sys.executable,
                    "amneziawg_config_dir": str(configs),
                    "_awg_instances": [{"name": name} for name in current],
                },
                "tasks": [
                    {"ansible.builtin.import_tasks": str(ROLE / "tasks/ownership.yml")},
                    select,
                    {
                        "ansible.builtin.import_tasks": str(
                            ROLE / "tasks/retire-instances.yml"
                        )
                    },
                    publish,
                ],
            }
        ]
        path = tmp_path / "reconcile.yml"
        path.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            env={
                **os.environ,
                "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(record.read_text())["instances"] == current
        return result.stdout

    try:
        for name, unit in zip(members, units):
            Path("/etc/systemd/system", unit).write_text(
                "[Unit]\nDescription=Owned P2 AWG lifecycle fixture\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/true\nExecStop=/bin/true\n[Install]\nWantedBy=multi-user.target\n"
            )
            (configs / (name + ".conf")).write_text(
                "synthetic lifecycle ownership fixture\n"
            )
        ctl("daemon-reload")
        for unit in units:
            ctl("enable", "--now", unit)
        a, b, c, foreign = members
        output = converge([a, b], [a])
        assert ctl("is-active", units[0]).stdout.strip() == "active"
        assert ctl("is-active", units[1], check=False).returncode != 0
        assert ctl("is-enabled", units[1], check=False).stdout.strip() == "disabled"
        assert not (configs / (b + ".conf")).exists(), output
        converge([a], [c])
        assert ctl("is-active", units[0], check=False).returncode != 0
        assert not (configs / (a + ".conf")).exists()
        assert ctl("is-active", units[2]).stdout.strip() == "active"
        converge([c], [])
        assert ctl("is-active", units[2], check=False).returncode != 0
        output = converge([], [])
        assert "changed=0" in output, "repeated empty membership must be a no-op"
        target = Path("/etc/systemd/system/awg-quick.target")
        assert (
            not target.exists()
        ), "fixture must not replace prior AWG target authority"
        target.write_text(
            "[Unit]\nDescription=Owned AWG target lifecycle fixture\n[Install]\nWantedBy=multi-user.target\n"
        )
        ctl("daemon-reload")
        ctl("enable", "--now", target.name)
        foreign_path = Path("/etc/systemd/system", units[3])
        foreign_before = foreign_path.read_bytes()
        foreign_path.write_text(
            foreign_path.read_text().replace(
                "[Unit]\n", "[Unit]\nPartOf=awg-quick.target\n", 1
            )
        )
        ctl("daemon-reload")
        disabled_play = tmp_path / "disable-role.yml"
        disabled_play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "ansible_python_interpreter": sys.executable,
                            "amneziawg_config_dir": str(configs),
                            "amneziawg_role_enabled": False,
                        },
                        "roles": [{"role": "amneziawg"}],
                    }
                ]
            )
        )
        environment = {**os.environ, "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")}
        refused = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(disabled_play)],
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
        )
        assert refused.returncode != 0
        assert ctl("is-active", units[3]).stdout.strip() == "active"
        assert ctl("is-active", target.name).stdout.strip() == "active"
        assert target.exists() and record.exists()
        # The fixture owner removes its unrelated coupling explicitly; retirement never does.
        foreign_path.write_bytes(foreign_before)
        ctl("daemon-reload")
        for attempt in range(2):
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", str(disabled_play)],
                capture_output=True,
                text=True,
                env=environment,
                timeout=30,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            if attempt:
                assert "changed=0" in result.stdout
        assert ctl("is-active", target.name, check=False).returncode != 0
        assert not os.path.lexists(
            Path("/etc/systemd/system/multi-user.target.wants") / target.name
        )
        assert not target.exists()
        assert ctl("is-active", units[3]).stdout.strip() == "active"
        assert ctl("is-enabled", units[3]).stdout.strip() == "enabled"
        assert (configs / (foreign + ".conf")).exists()
    finally:
        ctl("disable", "--now", "awg-quick.target", check=False)
        Path("/etc/systemd/system/awg-quick.target").unlink(missing_ok=True)
        for unit in units:
            ctl("disable", "--now", unit, check=False)
            Path("/etc/systemd/system", unit).unlink(missing_ok=True)
        ctl("daemon-reload", check=False)
        record.unlink(missing_ok=True)
        if not owned_dir_existed:
            record.parent.rmdir()


def test_unrecorded_historical_shared_unit_requires_explicit_owner_adoption(tmp_path):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires owned root Linux fixture host")
    if not shutil.which("ansible-playbook"):
        pytest.skip("requires pinned Ansible")
    shared = Path("/etc/systemd/system/awg-quick@.service")
    record = Path("/var/lib/ripdpi/amneziawg/instances.json")
    assert (
        not shared.exists() and not record.exists()
    ), "test must not displace prior AWG authority"
    marker = tmp_path / "mutation"
    fixture = "[Unit]\nDescription=Historical P2 ownership fixture\n"
    shared.write_text(fixture)
    try:
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "ansible_become": False,
                    "ansible_python_interpreter": sys.executable,
                    "amneziawg_config_dir": str(tmp_path),
                },
                "tasks": [
                    {"ansible.builtin.import_tasks": str(ROLE / "tasks/ownership.yml")},
                    {
                        "ansible.builtin.copy": {
                            "dest": str(marker),
                            "content": "mutated",
                        }
                    },
                ],
            }
        ]
        file = tmp_path / "historical.yml"
        file.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(file)],
            text=True,
            capture_output=True,
            timeout=20,
            env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
        )
        assert result.returncode != 0
        assert "explicitly adopt" in result.stdout
        assert shared.read_text() == fixture and not marker.exists()
    finally:
        shared.unlink()
