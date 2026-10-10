"""Run real policy task transitions and predictive Tailnet command probes."""

from __future__ import annotations

import grp
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLES = ROOT / "ansible/roles"


def run_play(tmp_path, play, *, check=False):
    path = tmp_path / "play.json"
    path.write_text(json.dumps(play))
    command = ["ansible-playbook", "-i", "localhost,", str(path)]
    if check:
        command.append("--check")
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env={
            **os.environ,
            "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
            "ANSIBLE_DEBUG": "false",
            "ANSIBLE_NOCOLOR": "1",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.parametrize(
    "role,task_name,parameter,field,enabled,disabled",
    [
        (
            "package_updates",
            "Configure unattended security updates",
            "package_updates",
            "enabled",
            'APT::Periodic::Unattended-Upgrade "1";',
            'APT::Periodic::Unattended-Upgrade "0";',
        ),
        (
            "intrusion_prevention",
            "Configure Fail2Ban sshd jail",
            "intrusion_prevention",
            "sshd",
            "enabled = true",
            "enabled = false",
        ),
    ],
)
def test_enabled_disabled_disabled_actual_policy_task_is_idempotent(
    tmp_path,
    role,
    task_name,
    parameter,
    field,
    enabled,
    disabled,
):
    role_path = ROLES / role
    template_task = next(
        task
        for task in yaml.safe_load(
            (
                role_path
                / (
                    "tasks/enable.yml"
                    if role == "intrusion_prevention"
                    else "tasks/main.yml"
                )
            ).read_text()
        )
        if task["name"] == task_name
    )
    action = template_task["ansible.builtin.template"]
    action.update(
        src=str(role_path / "templates" / action["src"]),
        dest=str(tmp_path / "policy"),
        owner=pwd.getpwuid(os.getuid()).pw_name,
        group=grp.getgrgid(os.getgid()).gr_name,
    )
    template_task["register"] = "policy"
    template_task.pop("notify", None)
    tasks = []
    for index, active in enumerate([True, False, False]):
        values = (
            {"enabled": active} if field == "enabled" else {"sshd": {"enabled": active}}
        )
        tasks.extend(
            [
                {"ansible.builtin.set_fact": {parameter: values}},
                template_task,
                {
                    "ansible.builtin.copy": {
                        "dest": str(tmp_path / f"result-{index}.json"),
                        "content": "{{ policy | to_json }}",
                    }
                },
                {
                    "ansible.builtin.copy": {
                        "src": str(tmp_path / "policy"),
                        "dest": str(tmp_path / f"policy-{index}"),
                        "remote_src": True,
                    }
                },
            ]
        )
    run_play(
        tmp_path,
        [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "become": False,
                "vars": {
                    "ansible_become": False,
                    "ansible_python_interpreter": sys.executable,
                },
                "tasks": tasks,
            }
        ],
    )
    assert enabled in (tmp_path / "policy-0").read_text()
    assert disabled in (tmp_path / "policy-1").read_text()
    assert (tmp_path / "policy-1").read_bytes() == (tmp_path / "policy-2").read_bytes()
    assert [
        json.loads((tmp_path / f"result-{index}.json").read_text())["changed"]
        for index in range(3)
    ] == [True, True, False]


@pytest.mark.parametrize("backend", ["Running", "NeedsLogin"])
def test_actual_bootstrap_readonly_json_probes_execute_in_check_mode(tmp_path, backend):
    tasks = yaml.safe_load(
        (ROLES / "tailnet-management/tasks/bootstrap.yml").read_text()
    )
    selected = [
        task
        for task in tasks
        if task["name"]
        in {
            "Read existing Tailnet state before package or controller writes",
            "Read existing running Tailnet preferences before host writes",
        }
    ]
    calls = tmp_path / "calls"
    cli = tmp_path / "tailscale"
    cli.write_text(f"""#!{sys.executable}
import json, pathlib, sys
with pathlib.Path({str(calls)!r}).open('a') as log: log.write(' '.join(sys.argv[1:])+'\\n')
if sys.argv[1:] == ['status', '--json']:
 print(json.dumps({{'BackendState': {backend!r}}}))
elif sys.argv[1:] == ['get', '--json', 'all']:
 print(json.dumps({{'accept-dns': False}}))
else: raise SystemExit('unexpected mutation command')
""")
    cli.chmod(0o700)
    output = tmp_path / "observed.json"
    selected.append(
        {
            "ansible.builtin.copy": {
                "dest": str(output),
                "content": "{{ {'status': _tailnet_existing_status, 'preferences': _tailnet_existing_preferences | default({})} | to_json }}",
            },
            "check_mode": False,
        }
    )
    run_play(
        tmp_path,
        [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "become": False,
                "vars": {
                    "ansible_become": False,
                    "ansible_python_interpreter": sys.executable,
                    "_tailnet_existing_cli_candidates": [str(cli)],
                },
                "tasks": selected,
            }
        ],
        check=True,
    )
    observed = json.loads(output.read_text())
    assert json.loads(observed["status"]["stdout"])["BackendState"] == backend
    expected = ["status --json"]
    if backend == "Running":
        expected.append("get --json all")
        assert json.loads(observed["preferences"]["stdout"]) == {"accept-dns": False}
    assert calls.read_text().splitlines() == expected
    assert observed["status"]["changed"] is False
