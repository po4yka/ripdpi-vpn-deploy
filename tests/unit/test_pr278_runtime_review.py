"""Exercise read-only verification and standalone forwarding review regressions."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"


def load(path):
    return yaml.safe_load((ANSIBLE / path).read_text())


def execute(tmp_path, selected, variables, *, environment=None, check=False):
    directory = tmp_path / "playbooks"
    directory.mkdir(exist_ok=True)
    play = directory / "review.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Exercise runtime review boundary",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "become": False,
                    "vars": {"ansible_python_interpreter": sys.executable, **variables},
                    "tasks": selected,
                }
            ]
        )
    )
    return subprocess.run(
        [
            "ansible-playbook",
            "-i",
            "localhost,",
            "-c",
            "local",
            *(["--check"] if check else []),
            str(play),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "ANSIBLE_ROLES_PATH": str(tmp_path / "roles"),
            **(environment or {}),
        },
    )


def executable(path, content):
    path.write_text(content)
    path.chmod(0o755)
    return path


@pytest.mark.parametrize(
    "unit_environment,success",
    [
        ('OTHER=synthetic-private "XRAY_LOCATION_ASSET=/assets with spaces"', True),
        ("OTHER=synthetic-private", False),
        ("XRAY_LOCATION_ASSET=/one XRAY_LOCATION_ASSET=/two", False),
    ],
)
@pytest.mark.parametrize("check_mode", [False, True])
def test_verify_executes_canonical_source_without_installed_helper(
    tmp_path, unit_environment, success, check_mode
):
    helper = tmp_path / "roles/xray/files/xray_validate.py"
    helper.parent.mkdir(parents=True)
    helper.write_bytes((ANSIBLE / "roles/xray/files/xray_validate.py").read_bytes())
    marker = tmp_path / "validation.json"
    binary = executable(
        tmp_path / "xray",
        f"""#!{sys.executable}
import json, os, pathlib, sys
pathlib.Path({str(marker)!r}).write_text(json.dumps({{"argv":sys.argv[1:], "asset":os.environ["XRAY_LOCATION_ASSET"]}}))
print("synthetic-private-validator-output")
""",
    )
    executable(tmp_path / "systemctl", '#!/bin/sh\nprintf "%s\\n" "$TEST_UNIT_ENV"\n')
    configuration = tmp_path / "config.json"
    configuration.write_text('{"synthetic":true}\n')
    original = configuration.read_bytes()
    task = copy.deepcopy(
        next(
            item
            for item in load("playbooks/verify.yml")[0]["tasks"]
            if item["name"] == "Xray config valid"
        )
    )
    command = task["ansible.builtin.command"]
    assert command["argv"] == [
        "/usr/bin/python3",
        "-",
        "--config",
        "/etc/xray/config.json",
    ]
    assert task["no_log"] is True and task["changed_when"] is False
    command["argv"][0] = sys.executable
    command["argv"][-1] = str(configuration)
    command["argv"].extend(["--binary", str(binary)])
    result = execute(
        tmp_path,
        [task],
        {"vpn": {"enable_xray_reality": True}},
        environment={
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "TEST_UNIT_ENV": unit_environment,
        },
        check=check_mode,
    )
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    assert configuration.read_bytes() == original
    assert "synthetic-private" not in result.stdout + result.stderr
    assert marker.exists() is success
    if success:
        assert json.loads(marker.read_text()) == {
            "argv": ["run", "-test", "-config", str(configuration)],
            "asset": "/assets with spaces",
        }
        assert "changed=0" in result.stdout


@pytest.mark.parametrize("awg", [None, False, True])
def test_active_split_hop_requests_forwarding_when_site_toggle_is_false(tmp_path, awg):
    directory = tmp_path / "sysctl.d"
    directory.mkdir()
    (directory / "90-vpn.conf").write_text(
        "net.ipv4.ip_forward = 0\nnet.ipv6.conf.all.forwarding = 0\n"
    )
    (directory / "60-split-hop-egress.conf").write_text("net.ipv4.ip_forward = 1\n")
    forwarding = load("roles/baseline/tasks/forwarding.yml")
    for task in forwarding:
        for module in ("ansible.builtin.copy", "ansible.builtin.file"):
            if module in task:
                values = task[module]
                values.pop("owner", None)
                values.pop("group", None)
                for key in ("path", "dest"):
                    if key in values:
                        values[key] = values[key].replace(
                            "/etc/sysctl.d/", str(directory) + "/"
                        )
                        values[key] = values[key].replace(
                            "/usr/local/libexec", str(tmp_path / "libexec")
                        )
    helper_install = next(
        task
        for task in forwarding
        if task["name"] == "Install ordered mandatory sysctl policy helper"
    )
    helper_install["ansible.builtin.copy"]["src"] = str(
        ANSIBLE / "roles/baseline/files/baseline_sysctl.py"
    )
    # Only the privileged kernel boundary is replaced; real role inclusion,
    # expression evaluation, file publication/removal and ordering all execute.
    forwarding[-1]["ansible.builtin.command"] = {"argv": [sys.executable, "-c", "pass"]}
    role = tmp_path / "roles/baseline/tasks"
    role.mkdir(parents=True)
    (role / "forwarding.yml").write_text(yaml.safe_dump(forwarding))
    invocation = next(
        item
        for item in load("roles/split-hop-egress/tasks/enable.yml")
        if item["name"] == "Reconcile the baseline-owned forwarding policy"
    )
    variables = (
        {}
        if awg is None
        else {"vpn": {"enable_amneziawg": awg, "enable_split_hop_egress": False}}
    )
    result = execute(tmp_path, [invocation], variables)
    assert result.returncode == 0, result.stdout + result.stderr
    override = directory / "91-vpn-forward.conf"
    assert override.read_text() == (
        "net.ipv4.ip_forward = 1\n" f"net.ipv6.conf.all.forwarding = {int(bool(awg))}\n"
    )
    assert not (directory / "60-split-hop-egress.conf").exists()
    again = execute(tmp_path, [invocation], variables)
    assert again.returncode == 0 and "changed=0" in again.stdout, (
        again.stdout + again.stderr
    )
    # Without the active split-hop caller, baseline retains only other workloads.
    result = execute(
        tmp_path,
        [
            {
                "ansible.builtin.include_role": {
                    "name": "baseline",
                    "tasks_from": "forwarding",
                }
            }
        ],
        variables,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert override.exists() is bool(awg)
