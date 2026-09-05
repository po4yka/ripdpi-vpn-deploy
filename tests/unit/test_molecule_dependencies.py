"""Fail-closed checks for Molecule's offline dependencies and scenario inputs."""

import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from template_render import render_template


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_role_molecule_requirements_file_exists_from_role_cwd() -> None:
    configs = sorted(
        (REPO_ROOT / "ansible" / "roles").glob("*/molecule/*/molecule.yml")
    )
    assert configs

    for config_path in configs:
        config = yaml.safe_load(config_path.read_text())
        options = (config.get("dependency") or {}).get("options", {})
        for option in ("requirements-file", "role-file"):
            requirements = options.get(option)
            assert requirements, f"{config_path}: missing dependency option {option}"
            role_working_directory = config_path.parents[2]
            resolved = (role_working_directory / requirements).resolve()
            assert resolved.is_file(), f"{config_path}: missing {resolved}"


def test_molecule_driver_collection_is_pinned_before_scenarios_run() -> None:
    requirements = yaml.safe_load((REPO_ROOT / "requirements.yml").read_text())
    collections = {
        item["name"]: item["version"] for item in requirements["collections"]
    }

    assert collections["community.docker"] == "5.2.0"


def _published_scenario() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "ansible/molecule/full-stack-published/molecule.yml").read_text()
    )


def _full_stack_scenario() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "ansible/molecule/full-stack/molecule.yml").read_text()
    )


def _published_variables() -> dict:
    inventory = _published_scenario()["provisioner"]["inventory"]
    groups = inventory["group_vars"]
    hosts = inventory["hosts"]["vpn"]["hosts"]
    return {
        **groups["all"], **groups["vpn"],
        **hosts["vpn-fullstack-debian13-published"],
        **yaml.safe_load(
            (REPO_ROOT / "ansible/molecule/full-stack/test-secrets.yaml").read_text()
        ),
    }


def test_full_stack_inventories_mirror_listener_defaults() -> None:
    canonical = yaml.safe_load(
        (REPO_ROOT / "ansible/group_vars/all.yml").read_text()
    )
    names = {
        "xray_port",
        "xray_fallback_port",
        "nginx_xhttp_public_port",
        "nginx_xhttp_fallback_port",
        "hysteria_port",
        "amneziawg_listen_port",
        "subscription_port",
        "honeypot_port",
        "dns_morph_bridge_listen_port",
        "hysteria_realm_listen_port",
        "cdn_front_port",
        "naive_bind_port",
        "split_hop_ingress_listen_port",
    }
    expected = {name: canonical[name] for name in names}

    for scenario in (_full_stack_scenario(), _published_scenario()):
        variables = scenario["provisioner"]["inventory"]["group_vars"]["all"]
        assert {name: variables.get(name) for name in names} == expected


def test_full_stack_scenarios_repeat_convergence_before_verification() -> None:
    expected = [
        "dependency", "syntax", "create", "prepare", "converge",
        "idempotence", "verify", "destroy",
    ]

    for scenario in (_full_stack_scenario(), _published_scenario()):
        sequence = scenario["scenario"]["test_sequence"]
        assert sequence == expected


def test_hosted_full_stack_job_runs_both_idempotence_scenarios() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["molecule-full-stack"]["steps"]
    run = next(step["run"] for step in steps
               if step.get("name") == "molecule full-stack test")

    assert run.count("molecule -c molecule/full-stack/molecule.yml test -s full-stack") == 1
    assert run.count(
        "molecule -c molecule/full-stack-published/molecule.yml "
        "test -s full-stack-published"
    ) == 1


def test_published_requirements_resolve_to_current_checkout_from_documented_cwd() -> None:
    requirements = _published_scenario()["dependency"]["options"]["requirements-file"]
    resolved = (REPO_ROOT / "ansible" / requirements).resolve()
    # Checking only existence can accidentally accept a different checkout's
    # requirements when this repository is itself inside a worktree directory.
    assert resolved == (REPO_ROOT / "requirements.yml").resolve()
    assert resolved.is_file()


def test_published_scenario_explicitly_disables_unpublished_xray_fallback() -> None:
    canonical = yaml.safe_load(
        (REPO_ROOT / "ansible/group_vars/all.yml").read_text()
    )
    inventory = _published_scenario()["provisioner"]["inventory"]
    groups = inventory["group_vars"]
    hosts = inventory["hosts"]["vpn"]["hosts"]

    assert groups["all"]["xray_fallback_port"] == canonical["xray_fallback_port"] == 2053
    assert "xray_fallback_port" not in groups["vpn"]
    assert hosts["vpn-fullstack-debian13-published"]["xray_fallback_port"] == 0


def test_standalone_p0_molecule_fixtures_declare_required_canonical_inputs() -> None:
    """Standalone role scenarios must not depend on parent group-vars discovery."""
    canonical = yaml.safe_load(
        (REPO_ROOT / "ansible/group_vars/all.yml").read_text()
    )
    xray = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/xray/molecule/default/converge.yml").read_text()
    )[0]["vars"]
    watchdog = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/watchdog/molecule/default/converge.yml").read_text()
    )[0]["vars"]

    assert xray["p0_reality_shapes"] == canonical["p0_reality_shapes"]
    assert watchdog["xray_fallback_port"] == canonical["xray_fallback_port"]


def test_published_host_override_beats_repository_all_group_default(tmp_path) -> None:
    """Prove the scenario override with the same canonical group-vars discovery."""
    executable = shutil.which("ansible-inventory")
    assert executable, "installed Ansible is required for inventory precedence proof"
    scenario = _published_scenario()["provisioner"]["inventory"]
    host = "vpn-fullstack-debian13-published"
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(yaml.safe_dump({"all": {"children": {"vpn": {"hosts": {
        host: scenario["hosts"]["vpn"]["hosts"][host],
    }}}}}))

    result = subprocess.run(
        [executable, "-i", str(inventory), "--playbook-dir",
         str(REPO_ROOT / "ansible/playbooks"), "--host", host],
        check=True, capture_output=True, text=True, timeout=15,
    )

    assert json.loads(result.stdout)["xray_fallback_port"] == 0


def test_published_listener_contract_matches_declared_runtime_inputs(tmp_path) -> None:
    """Exercise the real renderer/validator, not role execution or live ports."""
    variables = _published_variables()
    # Do not use merge_render_vars(): its unrelated group_vars/all.yml inputs
    # can hide missing variables in Molecule's isolated inventory.
    assert "terraform_public_listeners_b64" in variables
    encoded_template = tmp_path / "provider-contract.j2"
    encoded_template.write_text(variables["terraform_public_listeners_b64"])
    expected = json.loads(base64.b64decode(
        render_template(encoded_template, variables).strip(), validate=True,
    ))
    assert expected
    template = REPO_ROOT / "ansible/templates/listener-manifest.json.j2"
    actual = json.loads(render_template(template, variables))
    spec = importlib.util.spec_from_file_location(
        "molecule_listener_contract", REPO_ROOT / "scripts/check-listener-contract.py",
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    assert validator.check({"expected": expected, "actual": actual}) == []

    # A stale contract must not accept a changed scenario listener.
    variables["nginx_xhttp_public_port"] += 1
    changed = json.loads(render_template(template, variables))
    assert validator.check({"expected": expected, "actual": changed})


def test_published_enabled_roles_have_public_service_address() -> None:
    variables = _published_variables()
    assert variables["vpn"]["enable_nginx_xhttp"] is True
    assert variables["vpn"]["enable_watchdog"] is True
    assert variables["vpn_service_address"] == "203.0.113.10"


def test_full_stack_scenarios_exercise_controller_owned_convergence_only() -> None:
    """Molecule cannot prove the out-of-container SSH transaction."""
    site = yaml.safe_load((REPO_ROOT / "ansible/playbooks/site.yml").read_text())
    transaction = site[1]
    assert transaction["tags"] == ["ssh-transaction"]

    adapter = yaml.safe_load(
        (REPO_ROOT / "ansible/molecule/controller-converge-adapter.yml").read_text()
    )[0]
    serialized = yaml.safe_dump(adapter)
    assertions = adapter["tasks"][0]["ansible.builtin.assert"]["that"]
    assert "ansible_play_hosts_all | length == 1" in assertions
    assert "ansible_connection == 'community.docker.docker'" in assertions
    assert "MOLECULE_SCENARIO_DIRECTORY" in serialized
    assert adapter["tasks"][1]["ansible.builtin.set_fact"] == {
        "ssh_transaction_controller_managed": True,
    }

    for slug, scenario in (("full-stack", _full_stack_scenario()),
                           ("full-stack-published", _published_scenario())):
        environment = scenario["provisioner"]["env"]
        variables = scenario["provisioner"]["inventory"]["group_vars"]["vpn"]
        assert environment["ANSIBLE_SKIP_TAGS"] == "ssh-transaction"
        assert "ssh_transaction_controller_managed" not in variables
        converge = yaml.safe_load(
            (REPO_ROOT / f"ansible/molecule/{slug}/converge.yml").read_text()
        )
        assert [item["ansible.builtin.import_playbook"] for item in converge] == [
            "../controller-converge-adapter.yml", "../../playbooks/site.yml",
        ]


def test_baseline_role_scenario_does_not_claim_transactional_ssh_publication() -> None:
    verify = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/baseline/molecule/default/verify.yml").read_text()
    )[0]
    serialized = yaml.safe_dump(verify)
    assert "20-ansible-hardening.conf" not in serialized
    algorithm_reads = [
        task for task in verify["tasks"]
        if task["name"] == "Read effective SSH algorithm compatibility"
    ]
    assert len(algorithm_reads) == 1
    assert algorithm_reads[0]["ansible.builtin.command"] == {"cmd": "sshd -T"}
    assert algorithm_reads[0]["changed_when"] is False
    assert "sshd -T -C" not in serialized


def test_published_static_role_defaults_match_declared_manifest(tmp_path) -> None:
    """Load actual static defaults, but never execute roles or contact hosts."""
    executable = shutil.which("ansible-playbook")
    assert executable, "installed Ansible is required for static role-default proof"
    source = yaml.safe_load((REPO_ROOT / "ansible/playbooks/site.yml").read_text())[0]
    manifest_tasks = [task for task in source["pre_tasks"]
                      if task["name"] == "Build effective public listener manifest"]
    assert len(manifest_tasks) == 1
    roles = [{**role, "when": False} for role in source["roles"]]
    assert roles and all(role["when"] is False for role in roles)
    playbooks = tmp_path / "ansible/playbooks"
    playbooks.mkdir(parents=True)
    templates = playbooks.parent / "templates"
    templates.mkdir()
    shutil.copyfile(REPO_ROOT / "ansible/templates/listener-manifest.json.j2",
                    templates / "listener-manifest.json.j2")
    scenario_inventory = _published_scenario()["provisioner"]["inventory"]
    groups = scenario_inventory["group_vars"]
    published_host = scenario_inventory["hosts"]["vpn"]["hosts"][
        "vpn-fullstack-debian13-published"
    ]
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(yaml.safe_dump({"all": {
        "vars": groups["all"], "children": {"vpn": {
            "vars": groups["vpn"], "hosts": {"localhost": {**published_host,
                "ansible_connection": "local", "ansible_become": False,
                "ansible_python_interpreter": sys.executable,
            }},
        }},
    }}))
    play = {
        "name": "Observe published inputs without role execution",
        "hosts": "localhost", "gather_facts": False, "become": False,
        "vars_files": [str(REPO_ROOT / "ansible/molecule/full-stack/test-secrets.yaml")],
        "pre_tasks": manifest_tasks, "roles": roles,
        "tasks": [{"name": "Observe static role defaults", "tags": ["published-inputs"],
                   "ansible.builtin.debug": {"msg": "{{ {'fallback_defined': "
                       "xray_fallback_port is defined, 'fallback_port': "
                       "xray_fallback_port | default(0) | int, "
                       "'manifest': public_listener_manifest} }}"}}],
    }
    # The only executable source task is the manifest set_fact. Every static
    # role has a literal false condition; no fixture handler or notify exists.
    assert set(play) == {"name", "hosts", "gather_facts", "become", "vars_files",
                         "pre_tasks", "roles", "tasks"}
    playbook = playbooks / "inputs.yml"
    playbook.write_text(yaml.safe_dump([play], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nfact_caching=memory\ncallback_result_format=json\n")
    collections = tmp_path / "collections"
    collections.mkdir()
    env = {name: os.environ[name] for name in ("PATH", "HOME", "LANG") if name in os.environ}
    env.update({
        "ANSIBLE_CONFIG": str(config), "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
        "ANSIBLE_ROLES_PATH": str(REPO_ROOT / "ansible/roles"),
        "ANSIBLE_COLLECTIONS_PATH": str(collections),
        "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
        "ANSIBLE_NOCOLOR": "1", "ANSIBLE_BECOME": "false",
        "ANSIBLE_LOAD_CALLBACK_PLUGINS": "false", "ANSIBLE_STDOUT_CALLBACK": "default",
    })
    result = subprocess.run(
        [executable, "-i", str(inventory), str(playbook), "--tags", "published-inputs"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert re.search(r"localhost\s+: ok=2\s+changed=0\s+unreachable=0\s+failed=0", output), output
    observations = []
    for match in re.finditer(r"ok: \[localhost\] => (\{)", result.stdout):
        value, _ = json.JSONDecoder().raw_decode(result.stdout[match.start(1):])
        if isinstance(value.get("msg"), dict) and "fallback_defined" in value["msg"]:
            observations.append(value["msg"])
    assert len(observations) == 1, output
    variables = _published_variables()
    observed = observations[0]
    assert observed["fallback_defined"] is ("xray_fallback_port" in variables)
    assert observed["fallback_port"] == variables.get("xray_fallback_port", 0)
    expected = json.loads(render_template(
        REPO_ROOT / "ansible/templates/listener-manifest.json.j2", variables,
    ))
    # The production validator compares enabled listeners. Static defaults may
    # add disabled records (for example Snell variants) without exposing ports.
    assert [item for item in observed["manifest"] if item["enabled"]] == [
        item for item in expected if item["enabled"]
    ]
