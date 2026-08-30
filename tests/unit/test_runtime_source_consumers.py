"""Source-building roles must consume the shared typed receipt contract."""

import json
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

    restart = _task("naive", "Queue caddy-naive restart after source publication")
    assert restart["when"] == "naive.build_with_xcaddy | bool"
    assert restart["changed_when"] == "runtime_build_changed | bool"
    assert restart["notify"] == "Restart caddy-naive"


def test_xray_source_build_uses_resolved_commit_and_shared_receipt() -> None:
    select_digest = _task("xray-runtime", "Select pinned Xray source digest")
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
            "expected_sha256": "{{ xray_runtime_source_sha256 }}",
        }
    ]
    assert select_digest["ansible.builtin.set_fact"]["xray_runtime_source_sha256"] == (
        "{{ xray.source_linux_amd64_sha256 if "
        "ansible_facts['architecture'] == 'x86_64' else "
        "xray.source_linux_arm64_sha256 }}"
    )
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
    publish = _task("xray-runtime", "Publish Xray runtime change state")
    assert (
        "_xray_runtime_current.changed"
        in publish["ansible.builtin.set_fact"]["xray_runtime_changed"]
    )
    assert (
        "runtime_build_results | default({})"
        in publish["ansible.builtin.set_fact"]["xray_runtime_changed"]
    )
    assert (
        "xray_runtime_build_from_source"
        in publish["ansible.builtin.set_fact"]["xray_runtime_changed"]
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
        step["chdir"].startswith("/opt/src/amneziawg-go-{{ amneziawg_go_commit }}")
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
    assert xray_properties["source_linux_amd64_sha256"] == {
        "$ref": "#/$defs/sha256_hex"
    }
    assert xray_properties["source_linux_arm64_sha256"] == {
        "$ref": "#/$defs/sha256_hex"
    }
    assert "source_binary_sha256" not in xray_properties
    assert schema["properties"]["xray"]["dependentRequired"] == {
        "source_commit": [
            "source_linux_amd64_sha256",
            "source_linux_arm64_sha256",
        ],
        "source_linux_amd64_sha256": [
            "source_commit",
            "source_linux_arm64_sha256",
        ],
        "source_linux_arm64_sha256": [
            "source_commit",
            "source_linux_amd64_sha256",
        ],
    }
    assert example["xray"]["source_commit"].startswith("REPLACE_WITH_")
    assert example["xray"]["source_linux_amd64_sha256"].startswith("REPLACE_WITH_")
    assert example["xray"]["source_linux_arm64_sha256"].startswith("REPLACE_WITH_")

    for path in ("scripts/bootstrap-secrets.sh", "scripts/ci-bootstrap-secrets.sh"):
        bootstrap = (ROOT / path).read_text()
        assert "source_commit:" in bootstrap
        assert "source_linux_amd64_sha256:" in bootstrap
        assert "source_linux_arm64_sha256:" in bootstrap
        assert "source_binary_sha256:" not in bootstrap

    ci_bootstrap = (ROOT / "scripts/ci-bootstrap-secrets.sh").read_text()
    assert 'XRAY_SOURCE_COMMIT="${XRAY_SOURCE_COMMIT:-}"' in ci_bootstrap
    assert (
        'XRAY_SOURCE_LINUX_AMD64_SHA256="${XRAY_SOURCE_LINUX_AMD64_SHA256:-}"'
        in ci_bootstrap
    )
    assert (
        'XRAY_SOURCE_LINUX_ARM64_SHA256="${XRAY_SOURCE_LINUX_ARM64_SHA256:-}"'
        in ci_bootstrap
    )
    assert "^[0-9a-f]{40,64}$" in ci_bootstrap
    assert "^[0-9a-f]{64}$" in ci_bootstrap
    assert "example xray.source_commit" not in ci_bootstrap

    operator_docs = (ROOT / "docs/XRAY-RELEASE-LINE.md").read_text()
    assert "xray.source_commit" in operator_docs
    assert "xray.source_linux_amd64_sha256" in operator_docs
    assert "xray.source_linux_arm64_sha256" in operator_docs


def test_ci_bootstrap_refuses_partial_or_malformed_xray_source_pins(
    tmp_path: Path,
) -> None:
    script = ROOT / "scripts/ci-bootstrap-secrets.sh"
    base_environment = {
        "PATH": os.environ["PATH"],
        "OUT": str(tmp_path / "secrets.yaml"),
        "SERVER_NAME": "ci.example.test",
        "REALITY_TARGET": "origin.example.test:443",
        "REALITY_SERVER_NAME": "origin.example.test",
    }
    cases = [
        {"XRAY_SOURCE_COMMIT": "a" * 40},
        {
            "XRAY_SOURCE_LINUX_AMD64_SHA256": "b" * 64,
            "XRAY_SOURCE_LINUX_ARM64_SHA256": "c" * 64,
        },
        {
            "XRAY_SOURCE_COMMIT": "A" * 40,
            "XRAY_SOURCE_LINUX_AMD64_SHA256": "b" * 64,
            "XRAY_SOURCE_LINUX_ARM64_SHA256": "c" * 64,
        },
        {
            "XRAY_SOURCE_COMMIT": "a" * 40,
            "XRAY_SOURCE_LINUX_AMD64_SHA256": "b" * 64,
        },
        {
            "XRAY_SOURCE_COMMIT": "a" * 40,
            "XRAY_SOURCE_LINUX_ARM64_SHA256": "c" * 64,
        },
    ]

    for source_environment in cases:
        result = subprocess.run(
            ["bash", str(script)],
            env={**base_environment, **source_environment},
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 2
        assert result.stderr.startswith("ci-bootstrap-secrets: invalid XRAY_SOURCE_")
        assert not (tmp_path / "secrets.yaml").exists()


def test_source_build_role_uses_fixed_staging_and_fresh_check_prerequisites() -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/runtime-release/tasks/source-build.yml").read_text()
    )

    publish = next(
        task
        for task in tasks
        if task["name"] == "Publish runtime source-build change state"
    )
    results = publish["ansible.builtin.set_fact"]["runtime_build_results"]
    assert "cleanup_pending" in results
    assert ".cleanup_pending | default(false) | bool" in results

    cleanup_debt = next(
        task
        for task in tasks
        if task["name"] == "Report committed runtime source-build cleanup debt"
    )
    assert cleanup_debt["when"] == [
        "not ansible_check_mode",
        "(_runtime_build_convergence.stdout | from_json) .cleanup_pending | default(false) | bool",
    ]
    by_name = {task["name"]: task for task in tasks}
    validate = by_name[
        "Deep-validate runtime source-build descriptor on the controller"
    ]["ansible.builtin.command"]["argv"]
    inspect = by_name["Inspect runtime source-build receipt and outputs"]
    converge = by_name["Converge runtime source build under the project lock"]
    assert converge["changed_when"] == (
        "(_runtime_build_convergence.stdout | from_json).changed | bool"
    )
    assert "(_runtime_build_convergence.stdout | from_json).changed | bool" in (
        publish["ansible.builtin.set_fact"]["runtime_build_changed"]
    )
    assert "runtime_build_results | default({})" in (
        publish["ansible.builtin.set_fact"]["runtime_build_results"]
    )

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


def test_source_build_changed_state_latches_across_repeated_consumers(
    tmp_path: Path,
) -> None:
    executable = shutil.which("ansible-playbook")
    assert executable, "installed Ansible is required for the change-latch proof"
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/runtime-release/tasks/source-build.yml").read_text()
    )
    publish = next(
        task
        for task in tasks
        if task["name"] == "Publish runtime source-build change state"
    )
    tasks_path = tmp_path / "publish-change.yml"
    tasks_path.write_text(yaml.safe_dump([publish], sort_keys=False))
    playbook = tmp_path / "change-latch.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Exercise repeated source-build consumers",
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "runtime_build_descriptor": {"name": "xray-core"},
                        "_runtime_build_inspection_payload": {"rebuild_required": True},
                        "_runtime_build_convergence": {
                            "stdout": json.dumps(
                                {"changed": True, "cleanup_pending": True}
                            )
                        },
                    },
                    "tasks": [
                        {"ansible.builtin.include_tasks": str(tasks_path)},
                        {
                            "ansible.builtin.set_fact": {
                                "_runtime_build_convergence": {
                                    "stdout": json.dumps({"changed": False})
                                }
                            }
                        },
                        {"ansible.builtin.include_tasks": str(tasks_path)},
                        {
                            "ansible.builtin.set_fact": {
                                "runtime_build_descriptor": {"name": "caddy-naive"}
                            }
                        },
                        {"ansible.builtin.include_tasks": str(tasks_path)},
                        {
                            "ansible.builtin.assert": {
                                "that": [
                                    "not (runtime_build_changed | bool)",
                                    "runtime_build_results['xray-core'].changed | bool",
                                    "not (runtime_build_results['xray-core'].cleanup_pending | bool)",
                                    "not (runtime_build_results['caddy-naive'].changed | bool)",
                                ]
                            }
                        },
                    ],
                }
            ],
            sort_keys=False,
        )
    )
    environment = {
        key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ
    }
    environment.update(
        {
            "ANSIBLE_DEBUG": "false",
            "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
            "ANSIBLE_NOCOLOR": "1",
        }
    )

    result = subprocess.run(
        [executable, "-i", "localhost,", str(playbook)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr


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


def test_source_publication_changes_drive_service_restart_state(tmp_path: Path) -> None:
    executable = shutil.which("ansible-playbook")
    assert executable, "installed Ansible is required for the restart-state proof"
    naive_task = _task("naive", "Queue caddy-naive restart after source publication")
    xray_task = _task("xray-runtime", "Publish Xray runtime change state")
    cases = [
        ("source-changed", True, True, True, False, True),
        ("source-idempotent", True, False, True, False, False),
        ("prebuilt-stale-source-fact", False, True, False, False, False),
        ("prebuilt-link-changed", False, True, False, True, True),
    ]

    for (
        name,
        naive_source_enabled,
        runtime_build_changed,
        xray_source_enabled,
        xray_link_changed,
        expected_xray_changed,
    ) in cases:
        case_root = tmp_path / name
        case_root.mkdir()
        restart_marker = case_root / "naive-restarted"
        tasks_path = case_root / "source-publication-tasks.yml"
        tasks_path.write_text(yaml.safe_dump([naive_task, xray_task], sort_keys=False))
        playbook = case_root / "source-publication-playbook.yml"
        playbook.write_text(
            yaml.safe_dump(
                [
                    {
                        "name": "Exercise source publication restart propagation",
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars": {
                            "naive": {"build_with_xcaddy": naive_source_enabled},
                            "runtime_build_changed": runtime_build_changed,
                            "runtime_build_results": {
                                "xray-core": {"changed": runtime_build_changed}
                            },
                            "xray_runtime_build_from_source": xray_source_enabled,
                            "_xray_runtime_current": {"changed": xray_link_changed},
                            "expected_xray_changed": expected_xray_changed,
                        },
                        "handlers": [
                            {
                                "name": "Restart caddy-naive",
                                "ansible.builtin.copy": {
                                    "content": "restarted\n",
                                    "dest": str(restart_marker),
                                    "mode": "0600",
                                },
                            }
                        ],
                        "tasks": [
                            {"ansible.builtin.include_tasks": str(tasks_path)},
                            {"ansible.builtin.meta": "flush_handlers"},
                            {
                                "name": "Require Xray publication restart state",
                                "ansible.builtin.assert": {
                                    "that": [
                                        "(xray_runtime_changed | bool) == (expected_xray_changed | bool)"
                                    ]
                                },
                            },
                        ],
                    }
                ],
                sort_keys=False,
            )
        )
        config = case_root / "ansible.cfg"
        config.write_text("[defaults]\ninject_facts_as_vars=false\n")
        environment = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "LANG")
            if key in os.environ
        }
        environment.update(
            {
                "ANSIBLE_CONFIG": str(config),
                "ANSIBLE_DEBUG": "false",
                "ANSIBLE_HOME": str(case_root / "ansible-home"),
                "ANSIBLE_LOCAL_TEMP": str(case_root / "ansible-local"),
                "ANSIBLE_NOCOLOR": "1",
            }
        )

        result = subprocess.run(
            [executable, "-i", "localhost,", str(playbook)],
            cwd=case_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert restart_marker.exists() is (
            naive_source_enabled and runtime_build_changed
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
