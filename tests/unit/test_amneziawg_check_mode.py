"""AmneziaWG source-pin attestation must remain active in check mode."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "check_mode,helper_changed,refused",
    [(True, True, True), (True, False, False), (True, False, True), (False, True, False)],
    ids=["fresh-check", "installed-check", "installed-refusal", "ordinary-install"],
)
def test_retirement_uses_only_available_current_helpers(tmp_path, check_mode, helper_changed, refused):
    tasks = yaml.safe_load((ROOT / "ansible/roles/amneziawg/tasks/consumer-disable.yml").read_text())
    selected = [task for task in tasks if task["name"] in {
        "Select the complete accepted AWG retirement plan",
        "Predict fresh AmneziaWG consumer retirement",
        "Accept complete AWG retirement with retained runtime compensation",
    }]
    marker = tmp_path / "consumer-request.json"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    consumer = binaries / "python3"
    consumer.write_text(
        f"#!{sys.executable}\n"
        "import json,sys\nfrom pathlib import Path\n"
        "assert sys.argv[1:] == ['-Es', '/usr/local/libexec/ripdpi-consumer/amneziawg_consumer.py', 'apply']\n"
        f"Path({str(marker)!r}).write_text(json.dumps(json.load(sys.stdin)))\n"
        "print(json.dumps({'changed': False}))\n"
        f"raise SystemExit({65 if refused else 0})\n"
    )
    consumer.chmod(0o755)
    play = tmp_path / "retirement.yml"
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "environment": {"PATH": str(binaries) + ":" + os.environ["PATH"]},
        "vars": {"ansible_python_interpreter": sys.executable,
                 "_awg_consumer_install": {"changed": helper_changed}},
        "tasks": selected,
    }]))
    argv = ["ansible-playbook", "-i", "localhost,", str(play)]
    if check_mode:
        argv.append("--check")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30,
                            env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"),
                                 "ANSIBLE_NOCOLOR": "1", "ANSIBLE_STDOUT_CALLBACK": "default"})
    invoked = not (check_mode and helper_changed)
    assert (result.returncode == 0) == (not invoked or not refused), result.stdout + result.stderr
    assert marker.exists() == invoked
    if invoked:
        request = json.loads(marker.read_text())
        assert request["check"] is check_mode
        assert request["candidates"] == [
            {"path": "/etc/systemd/system/awg-quick@.service", "absent": True},
            {"path": "/etc/systemd/system/awg-quick.target", "absent": True},
            {"path": "/var/lib/ripdpi/amneziawg/instances.json", "absent": True},
        ]
    else:
        recap = re.search(r"localhost\s+:.*changed=(\d+)", result.stdout)
        assert recap and recap.group(1) == "1"


def test_commit_resolution_is_normal_mode_attestation_only():
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/amneziawg/tasks/enable.yml").read_text()
    )
    resolve_tasks = [
        task for task in tasks if task["name"].startswith("Resolve the amneziawg-")
    ]

    assert len(resolve_tasks) == 2
    assert all(task.get("check_mode") is False for task in resolve_tasks)
    assert all(task.get("when") == "not ansible_check_mode" for task in resolve_tasks)
    assert all(task.get("changed_when") is False for task in resolve_tasks)


def test_pinned_source_bumps_use_distinct_immutable_checkouts_before_attestation():
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/amneziawg/tasks/enable.yml").read_text()
    )
    clones = [task for task in tasks if task["name"].startswith("Clone amneziawg-")]

    assert len(clones) == 2
    assert all(task["ansible.builtin.git"]["update"] is False for task in clones)
    assert all(task.get("when") == "not ansible_check_mode" for task in clones)
    assert clones[0]["ansible.builtin.git"]["dest"] == "{{ _awg_go_source_dir }}"
    assert clones[1]["ansible.builtin.git"]["dest"].endswith(
        "-{{ amneziawg_tools_commit }}"
    )


def test_build_receipts_make_check_mode_commit_aware_without_building():
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/amneziawg/tasks/enable.yml").read_text()
    )
    by_name = {task["name"]: task for task in tasks}

    define = by_name["Define pinned AmneziaWG source-build descriptors"]
    converge = by_name["Converge pinned AmneziaWG source builds"]
    descriptors = define["ansible.builtin.set_fact"]["_amneziawg_build_descriptors"]

    assert [descriptor["name"] for descriptor in descriptors] == [
        "amneziawg-go",
        "amneziawg-tools",
    ]
    assert descriptors[0]["source"]["commit"] == "{{ amneziawg_go_commit }}"
    assert descriptors[1]["source"]["commit"] == "{{ amneziawg_tools_commit }}"
    assert descriptors[0]["outputs"] == [
        {
            "name": "installed",
            "staged_path": "/var/lib/ripdpi/runtime-build-staging/amneziawg-go/amneziawg-go",
            "path": "{{ _awg_go_release_dir }}/amneziawg-go",
        },
    ]
    assert descriptors[1]["outputs"] == [
        {
            "name": "awg",
            "staged_path": "/var/lib/ripdpi/runtime-build-staging/amneziawg-tools/root/usr/bin/awg",
            "path": "/opt/amneziawg/releases/tools-{{ amneziawg_tools_commit }}/awg",
        },
        {
            "name": "awg-quick",
            "staged_path": "/var/lib/ripdpi/runtime-build-staging/amneziawg-tools/root/usr/bin/awg-quick",
            "path": "/opt/amneziawg/releases/tools-{{ amneziawg_tools_commit }}/awg-quick",
        },
    ]
    assert "WITH_WGQUICK=yes" in descriptors[1]["steps"][1]["argv"]
    assert converge["ansible.builtin.include_role"] == {
        "name": "runtime-release",
        "tasks_from": "source-build",
        "defaults_from": "source-build",
    }
    assert converge["loop"] == "{{ _amneziawg_build_descriptors }}"
    assert converge["vars"] == {"runtime_build_descriptor": "{{ item }}"}

    source = (ROOT / "ansible/roles/amneziawg/tasks/enable.yml").read_text()
    assert ".ripdpi-built-commit" not in source
    assert "_awg_go_rebuild_required" not in source
    assert "_awg_tools_rebuild_required" not in source
