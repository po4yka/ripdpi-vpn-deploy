"""AmneziaWG source-pin attestation must remain active in check mode."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_commit_resolution_is_normal_mode_attestation_only():
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/amneziawg/tasks/main.yml").read_text()
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
        (ROOT / "ansible/roles/amneziawg/tasks/main.yml").read_text()
    )
    clones = [task for task in tasks if task["name"].startswith("Clone amneziawg-")]

    assert len(clones) == 2
    assert all(task["ansible.builtin.git"]["update"] is False for task in clones)
    assert clones[0]["ansible.builtin.git"]["dest"].endswith(
        "-{{ amneziawg_go_commit }}"
    )
    assert clones[1]["ansible.builtin.git"]["dest"].endswith(
        "-{{ amneziawg_tools_commit }}"
    )


def test_build_receipts_make_check_mode_commit_aware_without_building():
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/amneziawg/tasks/main.yml").read_text()
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
            "path": "/usr/local/bin/amneziawg-go",
        },
    ]
    assert descriptors[1]["outputs"] == [
        {
            "name": "awg",
            "staged_path": "/var/lib/ripdpi/runtime-build-staging/amneziawg-tools/root/usr/bin/awg",
            "path": "/usr/bin/awg",
        },
        {
            "name": "awg-quick",
            "staged_path": "/var/lib/ripdpi/runtime-build-staging/amneziawg-tools/root/usr/bin/awg-quick",
            "path": "/usr/bin/awg-quick",
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

    source = (ROOT / "ansible/roles/amneziawg/tasks/main.yml").read_text()
    assert ".ripdpi-built-commit" not in source
    assert "_awg_go_rebuild_required" not in source
    assert "_awg_tools_rebuild_required" not in source
