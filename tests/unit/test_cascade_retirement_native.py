"""Historical cascade state remains outside inert-scaffold retirement ownership."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize("role", ["cascade-ingress", "cascade-egress"])
def test_active_historical_interface_refuses_before_recovery_input_deletion(
    tmp_path, role
):
    assert sys.platform == "linux" and os.geteuid() == 0
    interface = "p2cascade0"
    policy = tmp_path / "policy.nft"
    config = tmp_path / "recovery.conf"
    policy.write_text("prior historical policy")
    config.write_text("prior historical recovery input")
    values = {
        role.replace("-", "_"): {
            "wg_interface": interface,
            "routing_table": 203,
            "policy_path": str(policy),
        },
        "ansible_python_interpreter": sys.executable,
    }
    play = tmp_path / "retire.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": values,
                    "tasks": [
                        {
                            "ansible.builtin.import_tasks": str(
                                ROOT / f"ansible/roles/{role}/tasks/disable.yml"
                            )
                        }
                    ],
                }
            ]
        )
    )
    driver = tmp_path / "namespace.py"
    driver.write_text("""import json, os, pathlib, subprocess, sys
subprocess.run(['ip','link','add',sys.argv[1],'type','dummy'],check=True)
result = subprocess.run(['ansible-playbook','-i','localhost,',sys.argv[2]],capture_output=True,text=True,timeout=30)
assert result.returncode != 0
assert 'Historical' in result.stdout or 'historical' in result.stdout
assert pathlib.Path(sys.argv[3]).read_text() == 'prior historical policy'
assert pathlib.Path(sys.argv[4]).read_text() == 'prior historical recovery input'
subprocess.run(['ip','link','show','dev',sys.argv[1]],check=True,stdout=subprocess.DEVNULL)
print('historical cascade authority preserved')
""")
    environment = dict(os.environ, ANSIBLE_ROLES_PATH=str(ROOT / "ansible/roles"))
    result = subprocess.run(
        [
            "unshare",
            "--net",
            sys.executable,
            str(driver),
            interface,
            str(play),
            str(policy),
            str(config),
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "historical cascade authority preserved" in result.stdout
