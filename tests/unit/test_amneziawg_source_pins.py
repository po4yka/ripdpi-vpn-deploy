"""AWG-enabled secret producers must provide immutable source pins."""

import os
from pathlib import Path
import shutil
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AWG_GO_VERSION = "v0.2.12"
AWG_GO_COMMIT = "2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf"
AWG_TOOLS_VERSION = "v1.0.20241018"
AWG_TOOLS_COMMIT = "c0b400c6dfc046f5cae8f3051b14cb61686fcf55"


def test_awg_secret_examples_and_generators_include_immutable_source_pins():
    example = yaml.safe_load((REPO_ROOT / "secrets/prod.secrets.example.yaml").read_text())
    expected = {
        "amneziawg_go_version": AWG_GO_VERSION,
        "amneziawg_go_commit": AWG_GO_COMMIT,
        "amneziawg_tools_version": AWG_TOOLS_VERSION,
        "amneziawg_tools_commit": AWG_TOOLS_COMMIT,
    }
    assert {key: example[key] for key in expected} == expected

    bootstrap = (REPO_ROOT / "scripts/bootstrap-secrets.sh").read_text()
    for variable, value in (
        ("AWG_GO_VERSION", AWG_GO_VERSION),
        ("AWG_GO_COMMIT", AWG_GO_COMMIT),
        ("AWG_TOOLS_VERSION", AWG_TOOLS_VERSION),
        ("AWG_TOOLS_COMMIT", AWG_TOOLS_COMMIT),
    ):
        assert f'{variable}="{value}"' in bootstrap
    for key, variable in (
        ("amneziawg_go_version", "AWG_GO_VERSION"),
        ("amneziawg_go_commit", "AWG_GO_COMMIT"),
        ("amneziawg_tools_version", "AWG_TOOLS_VERSION"),
        ("amneziawg_tools_commit", "AWG_TOOLS_COMMIT"),
    ):
        assert f'{key}: "${{{variable}}}"' in bootstrap

    ci_bootstrap = (REPO_ROOT / "scripts/ci-bootstrap-secrets.sh").read_text()
    for key, value in expected.items():
        assert f'{key}: "{value}"' in ci_bootstrap


def test_amneziawg_molecule_vars_model_the_immutable_pin_contract():
    converge = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/amneziawg/molecule/default/converge.yml").read_text()
    )
    vars_ = converge[0]["vars"]
    # The real role checks the resolved local fixture commits. Do not label
    # synthetic source/build inputs with the unrelated upstream release pins.
    assert vars_["amneziawg_go_version"] == "molecule-fixture-v1"
    assert vars_["amneziawg_go_commit"] == "{{ molecule_awg_go_head.stdout | trim }}"
    assert vars_["amneziawg_tools_version"] == "molecule-fixture-v1"
    assert vars_["amneziawg_tools_commit"] == "{{ molecule_awg_tools_head.stdout | trim }}"
    assert converge[0]["environment"]["GIT_ALLOW_PROTOCOL"] == "file"
    assert converge[0]["environment"]["GIT_CONFIG_GLOBAL"] == "/opt/molecule-awg-fixture/gitconfig"


def test_amneziawg_molecule_requests_the_pinned_image_architecture():
    molecule = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/amneziawg/molecule/default/molecule.yml").read_text()
    )
    assert molecule["platforms"][0]["platform"] == "linux/amd64"


def test_amneziawg_molecule_verifies_the_exact_commit_keyed_checkouts():
    verify = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/amneziawg/molecule/default/verify.yml").read_text()
    )
    tasks = verify[0]["tasks"]
    clone = next(
        task
        for task in tasks
        if task["name"] == "Read the role-cloned source repository commits"
    )
    clone_path = " ".join(clone["ansible.builtin.command"]["argv"][2].split())
    inspect = next(
        task
        for task in tasks
        if task["name"] == "Inspect source build outputs and installed binaries"
    )
    paths = [" ".join(path.split()) for path in inspect["loop"]]

    assert clone["loop"] == [
        {"name": "amneziawg-go", "index": 0},
        {"name": "amneziawg-tools", "index": 1},
    ]
    assert clone_path == (
        "/opt/src/{{ item.name }}-{{ "
        "molecule_awg_fixture_heads.results[item.index].stdout | trim }}"
    )
    assert "/opt/src/amneziawg-go/amneziawg-go" not in paths
    assert "/opt/src/amneziawg-tools/src/wg" not in paths
    assert paths[0] == (
        "/opt/src/amneziawg-go-{{ "
        "molecule_awg_fixture_heads.results[0].stdout | trim "
        "}}/amneziawg-go"
    )
    assert paths[2] == (
        "/opt/src/amneziawg-tools-{{ "
        "molecule_awg_fixture_heads.results[1].stdout | trim "
        "}}/src/wg"
    )


def test_amneziawg_scenario_dispatches_real_role_tasks(tmp_path):
    """A role-task fault must reach the scenario's actual converge dispatch.

    This local sentinel checks dispatch only. Container preparation and the
    full build/config/service lifecycle belong to the actual Molecule run.
    """
    executable = shutil.which("ansible-playbook")
    assert executable, "Ansible is required for the real role-dispatch regression"
    role = REPO_ROOT / "ansible/roles/amneziawg"
    copied_role = tmp_path / "roles/amneziawg"
    shutil.copytree(role, copied_role)
    tasks_path = copied_role / "tasks/main.yml"
    tasks = yaml.safe_load(tasks_path.read_text())
    sentinel = "MOLECULE_AWG_ROLE_DISPATCH_SENTINEL"
    tasks_path.write_text(yaml.safe_dump([
        {"name": "Fail before any role mutation", "ansible.builtin.fail": {"msg": sentinel}},
        *tasks,
    ], sort_keys=False))
    converge = yaml.safe_load((role / "molecule/default/converge.yml").read_text())[0]
    playbook = tmp_path / "dispatch.yml"
    playbook.write_text(yaml.safe_dump([{
        "name": "Exercise the scenario role dispatch",
        "hosts": "localhost", "gather_facts": False, "become": False,
        "vars": converge.get("vars", {}), "tasks": converge.get("tasks", []),
    }], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
    environment.update(ANSIBLE_CONFIG=str(config), ANSIBLE_ROLES_PATH=str(tmp_path / "roles"),
                       ANSIBLE_BECOME="false", ANSIBLE_DEBUG="false", ANSIBLE_NOCOLOR="1")
    result = subprocess.run([executable, "-i", "localhost,", "-c", "local", str(playbook)],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, "converge never executed the failing role task"
    assert sentinel in result.stdout + result.stderr, result.stdout + result.stderr


def test_strict_awg_fixture_includes_immutable_source_pins():
    fixture = yaml.safe_load((REPO_ROOT / "tests/fixtures/secrets-sample.yml").read_text())
    assert fixture["amneziawg_go_version"] == AWG_GO_VERSION
    assert fixture["amneziawg_go_commit"] == AWG_GO_COMMIT
    assert fixture["amneziawg_tools_version"] == AWG_TOOLS_VERSION
    assert fixture["amneziawg_tools_commit"] == AWG_TOOLS_COMMIT
