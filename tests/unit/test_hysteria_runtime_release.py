"""Consumer contract for Hysteria's shared runtime-release activation."""

from hashlib import sha256
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE_TASKS = ROOT / "ansible" / "roles" / "hysteria" / "tasks" / "main.yml"
CONVERGE = (
    ROOT / "ansible" / "roles" / "hysteria" / "molecule" / "default" / "converge.yml"
)
VERIFY = ROOT / "ansible" / "roles" / "hysteria" / "molecule" / "default" / "verify.yml"
CHECK_MODE = (
    ROOT / "ansible" / "roles" / "hysteria" / "molecule" / "default" / "check-mode.yml"
)
SIDE_EFFECT = (
    ROOT / "ansible" / "roles" / "hysteria" / "molecule" / "default" / "side_effect.yml"
)
MOLECULE = (
    ROOT / "ansible" / "roles" / "hysteria" / "molecule" / "default" / "molecule.yml"
)


def test_hysteria_delegates_pinned_binary_activation_to_runtime_release() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    runtime_task = next(
        task
        for task in tasks
        if task.get("ansible.builtin.include_role", {}).get("name") == "runtime-release"
    )

    contract = runtime_task["vars"]
    assert contract["runtime_release_install_root"] == "{{ hysteria_install_root }}"
    assert contract["runtime_release_binary_name"] == "hysteria"
    assert contract["runtime_release_public_link"] == "/usr/local/bin/hysteria"
    assert contract["runtime_release_artifact_type"] == "binary"
    assert (
        contract["runtime_release_urls"]["amd64"] == "{{ hysteria_release_urls.amd64 }}"
    )
    assert (
        contract["runtime_release_urls"]["arm64"] == "{{ hysteria_release_urls.arm64 }}"
    )

    names = [task["name"] for task in tasks]
    activation_index = names.index(
        "Install pinned Hysteria release through runtime-release"
    )
    notification_index = names.index(
        "Notify Hysteria restart after runtime release activation"
    )
    assert activation_index < notification_index
    assert tasks[notification_index]["notify"] == "Restart hysteria"
    assert "runtime_release_changed" in tasks[notification_index]["changed_when"]
    assert tasks[notification_index]["when"] == "not ansible_check_mode"
    assert "ansible.builtin.get_url" not in ROLE_TASKS.read_text(encoding="utf-8")


def test_hysteria_molecule_uses_verified_local_artifacts() -> None:
    converge = yaml.safe_load(CONVERGE.read_text(encoding="utf-8"))[0]
    variables = converge["vars"]

    assert variables["hysteria_release_urls"]["amd64"].startswith("file://")
    assert variables["hysteria_release_urls"]["arm64"].startswith("file://")
    assert (
        variables["hysteria_release_urls"]["amd64"]
        != variables["hysteria_release_urls"]["arm64"]
    )
    fixture_artifacts = {
        task["ansible.builtin.copy"]["dest"]: task["ansible.builtin.copy"]["content"]
        for task in converge["pre_tasks"]
        if task["name"].startswith("Write deterministic Hysteria")
    }
    assert (
        sha256(
            fixture_artifacts["/var/tmp/hysteria-molecule/hysteria-v2.8.2"].encode()
        ).hexdigest()
        == variables["hysteria"]["linux_amd64_sha256"]
    )
    assert (
        sha256(
            fixture_artifacts[
                "/var/tmp/hysteria-molecule/hysteria-v2.8.2-arm64"
            ].encode()
        ).hexdigest()
        == variables["hysteria"]["linux_arm64_sha256"]
    )
    assert (
        sha256(
            fixture_artifacts["/var/tmp/hysteria-molecule/hysteria-v2.8.3"].encode()
        ).hexdigest()
        == "f61dc01abae6cb72404aae6582b86e0958bb0bc3119012c606772351d6c37fbd"
    )
    assert (
        sha256(
            fixture_artifacts[
                "/var/tmp/hysteria-molecule/hysteria-v2.8.3-arm64"
            ].encode()
        ).hexdigest()
        == "29fa1c48937c356daf098f17a7512e8df2af29015ca7188f0cd0d9124fd24276"
    )
    assert not any(
        "Stub hysteria binary" in task["name"] for task in converge["pre_tasks"]
    )


def test_hysteria_molecule_verifies_runtime_release_upgrade_and_rollback_links() -> (
    None
):
    verify = yaml.safe_load(VERIFY.read_text(encoding="utf-8"))[0]
    task_names = [task["name"] for task in verify["tasks"]]

    assert (
        "Assert runtime-release current/public/previous links and receipt" in task_names
    )
    assert "Upgrade Hysteria through runtime-release" in task_names
    assert "Flush upgraded Hysteria runtime-release handler" in task_names
    assert "Assert upgraded fixture version and active Hysteria service" in task_names
    assert "Assert upgraded runtime-release links and receipts" in task_names


def test_hysteria_molecule_runs_check_mode_in_a_global_ansible_process() -> None:
    molecule = yaml.safe_load(MOLECULE.read_text(encoding="utf-8"))
    sequence = molecule["scenario"]["test_sequence"]
    assert (
        sequence.index("idempotence")
        < sequence.index("side_effect")
        < sequence.index("verify")
    )

    side_effect = yaml.safe_load(SIDE_EFFECT.read_text(encoding="utf-8"))[0]
    command = side_effect["tasks"][0]["ansible.builtin.command"]["argv"]
    assert "--check" in command
    assert "{{ lookup('env', 'MOLECULE_INVENTORY_FILE') }}" in command
    assert command[-1].endswith("/check-mode.yml")

    check_mode = yaml.safe_load(CHECK_MODE.read_text(encoding="utf-8"))[0]
    include = next(
        task
        for task in check_mode["tasks"]
        if task.get("ansible.builtin.include_role", {}).get("name") == "hysteria"
    )
    assert include["ansible.builtin.include_role"]["name"] == "hysteria"
    variables = check_mode["vars"]
    assert variables["hysteria"]["version"] == "v2.8.4"
    assert variables["hysteria_release_urls"]["amd64"].endswith("hysteria-v2.8.4")
    assert variables["hysteria_release_urls"]["arm64"].endswith("hysteria-v2.8.4-arm64")
    assert variables["hysteria"]["linux_amd64_sha256"] == (
        "a94b3a4cbb14183ae933de5c5e2478da95b1d000d1c7d0d50102dba0882eee46"
    )
    assert variables["hysteria"]["linux_arm64_sha256"] == (
        "398f21663faa504a8e00518b298b4a4fd418a3ba61d5e33a4d87a25b05a4d2a0"
    )
    state_assertion = next(
        task
        for task in check_mode["tasks"]
        if task["name"]
        == "Assert global check mode predicted a release without writes or restart"
    )
    clauses = state_assertion["ansible.builtin.assert"]["that"]
    assert any(
        "results[1].stat.exists ==" in clause
        for clause in clauses
    )
    assert any(
        "not check_mode_before_paths.results[1].stat.exists or" in clause
        for clause in clauses
    )
    converge = yaml.safe_load(CONVERGE.read_text(encoding="utf-8"))[0]
    artifacts = {
        task["ansible.builtin.copy"]["dest"]: task["ansible.builtin.copy"]["content"]
        for task in converge["pre_tasks"]
        if task["name"].startswith("Write deterministic Hysteria")
    }
    assert (
        sha256(
            artifacts["/var/tmp/hysteria-molecule/hysteria-v2.8.4"].encode()
        ).hexdigest()
        == variables["hysteria"]["linux_amd64_sha256"]
    )
    assert (
        sha256(
            artifacts["/var/tmp/hysteria-molecule/hysteria-v2.8.4-arm64"].encode()
        ).hexdigest()
        == variables["hysteria"]["linux_arm64_sha256"]
    )
    assert "Assert global check mode predicted a release without writes or restart" in {
        task["name"] for task in check_mode["tasks"]
    }
