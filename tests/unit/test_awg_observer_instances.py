"""Local Ansible verification and watchdog rendering use normalized AWG names."""

import copy
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("failed", ["", "awg2"])
def test_real_verify_tasks_check_every_named_instance(tmp_path, failed):
    source = yaml.safe_load((ROOT / "ansible/playbooks/verify.yml").read_text())[0]["tasks"]
    selected = [task for task in source if task["name"] in {
        "Normalize configured AmneziaWG instances for verification", "AmneziaWG interface up"
    }]
    binary = tmp_path / "awg"
    log = tmp_path / "calls"
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$AWG_LOG"\n[ "$2" != "$FAILED_AWG" ]\n')
    binary.chmod(0o755)
    # Preserve the production argv and replace only executable discovery.
    selected[-1]["ansible.builtin.command"]["argv"][0] = str(binary)
    from test_awg_device_binding import document
    awg = copy.deepcopy(document()["amneziawg_secrets"])
    for index, item in enumerate(awg["instances"], 1):
        item["name"] = f"awg{index}"
    play = [{
        "hosts": "localhost", "connection": "local", "gather_facts": False,
        "become": False,
        "vars": {"ansible_python_interpreter": sys.executable,
                 "vpn": {"enable_amneziawg": True},
                 "amneziawg_listen_port": 51820, "amneziawg_secrets": awg},
        "tasks": selected,
        "environment": {"AWG_LOG": str(log), "FAILED_AWG": failed},
    }]
    candidate = tmp_path / "play.yml"
    candidate.write_text(yaml.safe_dump(play))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    environment.update(
        ANSIBLE_CONFIG=str(config),
        ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"),
        ANSIBLE_ROLES_PATH=str(ROOT / "ansible/roles"),
        ANSIBLE_STDOUT_CALLBACK="default",
    )
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(candidate)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=40)
    assert (result.returncode == 0) == (not failed), result.stdout + result.stderr
    assert log.read_text().splitlines() == ["show awg1", "show awg2"]


def test_watchdog_names_follow_shared_normalization():
    tasks = yaml.safe_load((ROOT / "ansible/roles/watchdog/tasks/enable.yml").read_text())
    normalize = next(task for task in tasks if task["name"] == "Normalize configured AmneziaWG instances for watchdog probes")
    assert normalize["ansible.builtin.include_role"] == {"name": "amneziawg", "tasks_from": "instances"}
    variables = merge_render_vars()
    variables["watchdog_awg_interfaces"] = ["awg1", "awg2"]
    rendered = render_template(ROOT / "ansible/roles/watchdog/templates/vpn-watchdog.env.j2", variables)
    assert "AWG_INTERFACES=awg1,awg2" in rendered
    assert "AWG_INTERFACE=" not in rendered
