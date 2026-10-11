"""Consumer contract for Hysteria's shared runtime-release activation."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE_TASKS = ROOT / "ansible" / "roles" / "hysteria" / "tasks" / "enable.yml"
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
    assert activation_index < names.index("Validate Hysteria candidate before quiescing the accepted route")
    assert not any(task.get("notify") == "Restart hysteria" for task in tasks[:activation_index + 1])
    unit = (ROOT / "ansible/roles/hysteria/templates/hysteria-server.service.j2").read_text()
    assert "ExecStart={{ hysteria_install_root }}/releases/{{ hysteria.version }}/hysteria" in unit
    assert "ExecStart=/usr/local/bin" not in unit
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
    artifacts = {task['ansible.builtin.get_url']['dest']: task['ansible.builtin.get_url']
                 for task in converge['pre_tasks'] if 'ansible.builtin.get_url' in task}
    assert len(artifacts) == 4
    for architecture in ('amd64', 'arm64'):
        suffix = '-arm64' if architecture == 'arm64' else ''
        artifact = artifacts['/var/tmp/hysteria-molecule/hysteria-v2.8.2'+suffix]
        assert artifact['checksum'] == 'sha256:'+variables['hysteria']['linux_'+architecture+'_sha256']
        assert artifact['url'].endswith('/app/v2.8.2/hysteria-linux-'+architecture)
    upgraded = yaml.safe_load(VERIFY.read_text())[0]
    override = next(task['vars']['hysteria'] for task in upgraded['tasks']
                    if task['name'] == 'Upgrade Hysteria through runtime-release')
    assert override['version'] == 'v2.9.0'
    for architecture in ('amd64', 'arm64'):
        suffix = '-arm64' if architecture == 'arm64' else ''
        artifact = artifacts['/var/tmp/hysteria-molecule/hysteria-v2.9.0'+suffix]
        assert artifact['checksum'] == 'sha256:'+override['linux_'+architecture+'_sha256']
        assert artifact['url'].endswith('/app/v2.9.0/hysteria-linux-'+architecture)
    assert not any('content' in task.get('ansible.builtin.copy', {}) for task in converge['pre_tasks'])


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

    initial_assertion = next(
        task
        for task in verify["tasks"]
        if task["name"]
        == "Assert runtime-release current/public/previous links and receipt"
    )
    upgraded_assertion = next(
        task
        for task in verify["tasks"]
        if task["name"] == "Assert upgraded runtime-release links and receipts"
    )
    initial_clauses = initial_assertion["ansible.builtin.assert"]["that"]
    upgraded_clauses = upgraded_assertion["ansible.builtin.assert"]["that"]
    assert any(
        "results[1].stat.lnk_target == '/opt/hysteria/current/hysteria'" in clause
        for clause in initial_clauses
    )
    assert any(
        "results[2].stat.lnk_target == '/opt/hysteria/current/hysteria'" in clause
        for clause in upgraded_clauses
    )


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
    assert variables["hysteria"]["version"] == "v2.9.0"
    assert variables["hysteria_release_urls"]["amd64"].endswith("hysteria-v2.9.0")
    assert variables["hysteria_release_urls"]["arm64"].endswith("hysteria-v2.9.0-arm64")
    assert variables["hysteria"]["linux_amd64_sha256"] == (
        "8225c8380f1ae8122921d4986c2b70976e9c6e6f87a977e7d0498a813f4f3e37"
    )
    assert variables["hysteria"]["linux_arm64_sha256"] == (
        "a3ccc0a3e791b85710ef63d22304a6f7dea210259be71bcd70cf9a210a385454"
    )
    state_assertion = next(
        task
        for task in check_mode["tasks"]
        if task["name"]
        == "Assert global check mode predicted a release without writes or restart"
    )
    clauses = state_assertion["ansible.builtin.assert"]["that"]
    assert any("results[1].stat.exists ==" in clause for clause in clauses)
    assert any(
        "not check_mode_before_paths.results[1].stat.exists or" in clause
        for clause in clauses
    )
    converge = yaml.safe_load(CONVERGE.read_text(encoding="utf-8"))[0]
    artifacts = {task['ansible.builtin.get_url']['dest']: task['ansible.builtin.get_url']
                 for task in converge['pre_tasks'] if 'ansible.builtin.get_url' in task}
    for architecture in ('amd64', 'arm64'):
        suffix = '-arm64' if architecture == 'arm64' else ''
        assert artifacts['/var/tmp/hysteria-molecule/hysteria-v2.9.0'+suffix]['checksum'] == 'sha256:'+variables['hysteria']['linux_'+architecture+'_sha256']
