"""Actual systemd PID/context activation from the production unit-change signals.

Inert sleep processes prove lifecycle delivery only, not Xray/MTProto protocols.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/probe-matrix-target"
pytestmark = pytest.mark.native_runtime


def test_changed_probe_unit_restarts_affected_pid_and_applies_new_context(tmp_path):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires owned root Linux systemd fixture host")
    if not shutil.which("ansible-playbook") or not Path("/run/systemd/system").exists():
        pytest.skip("requires systemd and pinned Ansible")
    names = ["probe-matrix-xray", "probe-matrix-mtg"]
    units = [Path("/etc/systemd/system", name + ".service") for name in names]
    assert not any(
        path.exists() for path in units
    ), "test must not displace prior probe authority"
    tasks = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    signals = [
        task for task in tasks if task["name"].startswith("Apply changed probe matrix")
    ]
    handlers = yaml.safe_load((ROLE / "handlers/main.yml").read_text())
    handlers = [task for task in handlers if task["name"] != "Reload nginx"]

    def ctl(*argv, check=True):
        return subprocess.run(
            ["systemctl", *argv],
            text=True,
            capture_output=True,
            timeout=10,
            check=check,
        ).stdout.strip()

    def pid(name):
        return int(ctl("show", name, "--property=MainPID", "--value"))

    script = tmp_path / "observe-context.py"
    script.write_text(
        "import os,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(os.environ['P2_PROBE_CONTEXT'])\nos.execl('/usr/bin/sleep','sleep','infinity')\n"
    )

    def unit(path, revision):
        command = (
            "/usr/bin/python3 "
            + str(script)
            + " "
            + str(tmp_path / (path.stem + ".context"))
        )
        path.write_text(
            "[Unit]\nDescription=Owned P2 probe activation fixture\n[Service]\nExecStart="
            + command
            + "\nEnvironment=P2_PROBE_CONTEXT="
            + revision
            + "\n[Install]\nWantedBy=multi-user.target\n"
        )

    try:
        for path in units:
            unit(path, "first")
        ctl("daemon-reload")
        for name in names:
            ctl("start", name)
        for changed in [names[0], names[1], None]:
            before = {name: pid(name) for name in names}
            assert all(before.values())
            if changed:
                unit(units[names.index(changed)], "second")
            play = [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "ansible_become": False,
                        "ansible_python_interpreter": sys.executable,
                        "probe_matrix_target_role_enabled": True,
                        "probe_matrix_target": {"manage_services": True},
                        "_probe_matrix_service_units": {
                            "results": [
                                {"item": name, "changed": name == changed}
                                for name in names
                            ]
                        },
                    },
                    "tasks": [
                        {
                            "ansible.builtin.debug": {
                                "msg": "Unit file publication changed"
                            },
                            "changed_when": changed is not None,
                            "notify": "Reload probe matrix systemd",
                        },
                        *signals,
                    ],
                    "handlers": handlers,
                }
            ]
            path = tmp_path / "activate.yml"
            path.write_text(yaml.safe_dump(play, sort_keys=False))
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", str(path)],
                text=True,
                capture_output=True,
                timeout=20,
                env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
            )
            assert result.returncode == 0, result.stdout + result.stderr
            for name in names:
                current = pid(name)
                assert (current != before[name]) == (name == changed)
                if name == changed:
                    assert (tmp_path / (name + ".context")).read_text() == "second"
            if changed is None:
                assert "changed=0" in result.stdout
    finally:
        for name, path in zip(names, units):
            ctl("stop", name, check=False)
            path.unlink(missing_ok=True)
        ctl("daemon-reload", check=False)
