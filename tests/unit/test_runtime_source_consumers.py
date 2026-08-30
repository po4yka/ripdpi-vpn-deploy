"""Source-building roles must consume the shared typed receipt contract."""

import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _tasks(role: str) -> list[dict]:
    return yaml.safe_load((ROOT / f"ansible/roles/{role}/tasks/main.yml").read_text())


def _task(role: str, name: str) -> dict:
    return next(task for task in _tasks(role) if task["name"] == name)


def test_naive_build_uses_compound_identity_and_pinned_output_receipt() -> None:
    wrapper = _task("naive", "Converge pinned caddy-naive source build")
    task = wrapper
    descriptor = task["vars"]["runtime_build_descriptor"]

    assert task["ansible.builtin.include_role"] == {
        "name": "runtime-release",
        "tasks_from": "source-build",
        "defaults_from": "source-build",
    }
    assert descriptor["name"] == "caddy-naive"
    assert descriptor["source"] == {
        "xcaddy_version": "{{ naive.xcaddy_version }}",
        "caddy_version": "{{ naive.caddy_version }}",
        "forwardproxy_module": "{{ naive.forwardproxy_module }}",
    }
    assert descriptor["outputs"] == [
        {
            "name": "installed",
            "staged_path": "/var/lib/ripdpi/runtime-build-staging/caddy-naive/installed",
            "path": "/usr/local/bin/caddy-naive",
            "expected_sha256": "{{ naive.xcaddy_sha256 }}",
        }
    ]

    source = (ROOT / "ansible/roles/naive/tasks/main.yml").read_text()
    assert "Check whether caddy-naive binary already exists" not in source
    assert "Verify caddy-naive binary sha256" not in source
    assert "_caddy_naive_stat.stat.checksum" not in source
    assert "/root/.cache/go-build" not in source
    assert all(
        step["environment"]["GOCACHE"].startswith(
            "/var/lib/ripdpi/runtime-build-staging/caddy-naive/"
        )
        for step in descriptor["steps"]
    )
    assert all(
        "/usr/local/bin/caddy-naive" not in argument
        for step in descriptor["steps"]
        for argument in step["argv"]
    )


def test_xray_source_build_uses_resolved_commit_and_shared_receipt() -> None:
    resolve = _task("xray-runtime", "Resolve pinned Xray source commit")
    converge = _task("xray-runtime", "Converge pinned Xray source build")
    descriptor = converge["vars"]["runtime_build_descriptor"]

    assert resolve["check_mode"] is False
    assert resolve["when"] == [
        "xray_runtime_build_from_source | bool",
        "not ansible_check_mode",
    ]
    assert resolve["changed_when"] is False
    assert descriptor["name"] == "xray-core"
    assert descriptor["source"] == {
        "repository": "https://github.com/XTLS/Xray-core",
        "version": "{{ xray.version }}",
        "commit": "{{ xray.source_commit }}",
    }
    assert descriptor["outputs"] == [
        {
            "name": "installed",
            "staged_path": "/var/lib/ripdpi/runtime-build-staging/xray-core/xray",
            "path": "{{ xray_install_dir }}/releases/{{ xray.version }}/xray",
            "expected_sha256": "{{ xray.source_binary_sha256 }}",
        }
    ]
    assert converge["ansible.builtin.include_role"] == {
        "name": "runtime-release",
        "tasks_from": "source-build",
        "defaults_from": "source-build",
    }
    assert converge["when"] == "xray_runtime_build_from_source | bool"

    defaults = yaml.safe_load(
        (ROOT / "ansible/roles/xray-runtime/defaults/main.yml").read_text()
    )
    assert defaults["xray_runtime_build_from_source"] == (
        "{{ vpn.build_xray_from_source | default(false) }}"
    )
    source = (ROOT / "ansible/roles/xray-runtime/tasks/main.yml").read_text()
    assert "Build pinned Xray source" not in source
    assert "Inspect source-built Xray checksum" not in source
    clone = _task("xray-runtime", "Clone pinned Xray source")
    assert clone["ansible.builtin.git"]["version"] == "{{ xray.source_commit }}"
    assert clone["ansible.builtin.git"]["dest"] == (
        "/opt/src/xray-core-{{ xray.source_commit }}"
    )
    assert clone["ansible.builtin.git"]["update"] is False
    assert all(
        step["chdir"] == "/opt/src/xray-core-{{ xray.source_commit }}"
        for step in descriptor["steps"]
    )
    assert all(
        "{{ xray_install_dir }}" not in argument
        for step in descriptor["steps"]
        for argument in step["argv"]
    )


def test_amneziawg_checkouts_are_immutable_per_exact_commit() -> None:
    tasks = _tasks("amneziawg")
    by_name = {task["name"]: task for task in tasks}
    go_clone = by_name["Clone amneziawg-go"]["ansible.builtin.git"]
    tools_clone = by_name["Clone amneziawg-tools"]["ansible.builtin.git"]
    descriptors = by_name["Define pinned AmneziaWG source-build descriptors"][
        "ansible.builtin.set_fact"
    ]["_amneziawg_build_descriptors"]

    assert go_clone["dest"] == "/opt/src/amneziawg-go-{{ amneziawg_go_commit }}"
    assert tools_clone["dest"] == (
        "/opt/src/amneziawg-tools-{{ amneziawg_tools_commit }}"
    )
    assert go_clone["update"] is False
    assert tools_clone["update"] is False
    assert all(
        step["chdir"].startswith(
            "/opt/src/amneziawg-go-{{ amneziawg_go_commit }}"
        )
        for step in descriptors[0]["steps"]
    )
    assert all(
        step["chdir"].startswith(
            "/opt/src/amneziawg-tools-{{ amneziawg_tools_commit }}"
        )
        for step in descriptors[1]["steps"]
    )


def test_xray_source_pins_are_separate_optional_secret_fields() -> None:
    schema = yaml.safe_load((ROOT / "secrets/schema.json").read_text())
    example = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    xray_properties = schema["properties"]["xray"]["properties"]

    assert xray_properties["source_commit"]["pattern"] == (
        "^([0-9a-f]{40,64}|REPLACE_WITH_[A-Z0-9_]+)$"
    )
    assert xray_properties["source_binary_sha256"] == {"$ref": "#/$defs/sha256_hex"}
    assert example["xray"]["source_commit"].startswith("REPLACE_WITH_")
    assert example["xray"]["source_binary_sha256"].startswith("REPLACE_WITH_")


def test_source_build_role_uses_fixed_staging_and_fresh_check_prerequisites() -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/runtime-release/tasks/source-build.yml").read_text()
    )
    by_name = {task["name"]: task for task in tasks}
    validate = by_name[
        "Deep-validate runtime source-build descriptor on the controller"
    ]["ansible.builtin.command"]["argv"]
    inspect = by_name["Inspect runtime source-build receipt and outputs"]
    converge = by_name["Converge runtime source build under the project lock"]

    assert validate[-2:] == ["--stage-root", "{{ runtime_build_stage_root }}"]
    assert inspect["ansible.builtin.command"]["argv"][-2:] == [
        "--stage-root",
        "{{ runtime_build_stage_root }}",
    ]
    assert converge["ansible.builtin.command"]["argv"][-2:] == [
        "--stage-root",
        "{{ runtime_build_stage_root }}",
    ]
    assert "_runtime_build_stage_directory.changed" in inspect["when"]


def test_source_build_controller_validation_uses_running_ansible_python() -> None:
    task = next(
        item
        for item in yaml.safe_load(
            (ROOT / "ansible/roles/runtime-release/tasks/source-build.yml").read_text()
        )
        if item["name"]
        == "Deep-validate runtime source-build descriptor on the controller"
    )

    assert task["ansible.builtin.command"]["argv"][0] == (
        "{{ ansible_playbook_python }}"
    )


def test_fresh_source_build_check_predicts_change_without_running_recipe(
    tmp_path: Path,
) -> None:
    executable = shutil.which("ansible-playbook")
    assert executable, "installed Ansible is required for the check-mode proof"
    marker = tmp_path / "recipe-ran"
    output = tmp_path / "runtime"
    descriptor = {
        "schema_version": 1,
        "name": "check-fixture",
        "source": {"revision": "a" * 40},
        "steps": [
            {
                "argv": ["/usr/bin/touch", str(marker)],
                "chdir": str(tmp_path),
                "environment": {},
                "timeout_seconds": 30,
            }
        ],
        "outputs": [
            {
                "name": "installed",
                "staged_path": (
                    "/var/lib/ripdpi/runtime-build-staging/check-fixture/runtime"
                ),
                "path": str(output),
            }
        ],
    }
    playbook = tmp_path / "source-build-check.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Exercise fresh source-build check mode",
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "tasks": [
                        {
                            "name": "Check source-build role",
                            "ansible.builtin.include_role": {
                                "name": "runtime-release",
                                "tasks_from": "source-build",
                                "defaults_from": "source-build",
                            },
                            "vars": {"runtime_build_descriptor": descriptor},
                        },
                        {
                            "name": "Require predicted source-build drift",
                            "ansible.builtin.assert": {
                                "that": ["runtime_build_changed | bool"]
                            },
                        },
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\ninject_facts_as_vars=false\n")
    environment = {
        key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ
    }
    environment.update(
        {
            "ANSIBLE_CONFIG": str(config),
            "ANSIBLE_DEBUG": "false",
            "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
            "ANSIBLE_ROLES_PATH": str(ROOT / "ansible" / "roles"),
            "ANSIBLE_NOCOLOR": "1",
        }
    )

    result = subprocess.run(
        [executable, "-i", "localhost,", str(playbook), "--check"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert not output.exists()
