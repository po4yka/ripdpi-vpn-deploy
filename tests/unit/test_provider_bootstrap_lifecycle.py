"""Credential-free Terraform transitions, including pre-guard state migration."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ("hetzner", "vultr", "scaleway")
SERVERS = {
    "hetzner": "hcloud_server.vpn",
    "vultr": "vultr_instance.vpn",
    "scaleway": "scaleway_instance_server.vpn",
}
pytestmark = pytest.mark.native_runtime


def execute(directory, *arguments):
    # Only copied configurations, generated mock state and synthetic inputs enter
    # this process. Do not inherit provider credentials or Terraform CLI switches.
    environment = {
        key: value for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "TF_PLUGIN_CACHE_DIR"}
    }
    environment.update(TF_IN_AUTOMATION="1", CHECKPOINT_DISABLE="1")
    environment["TF_CLI_CONFIG_FILE"] = str(directory / "test-provider-installation.tfrc")
    return subprocess.run(
        ["terraform", *arguments], cwd=directory, env=environment,
        capture_output=True, text=True, timeout=180,
    )


@pytest.fixture(scope="module", params=PROVIDERS)
def configuration(request, tmp_path_factory):
    provider = request.param
    temporary = tmp_path_factory.mktemp(f"bootstrap-{provider}")
    directory = temporary / "terraform" / "providers" / provider
    directory.mkdir(parents=True)
    # No checkout-wide copy: private state, auto.tfvars, .terraform, and operator
    # configuration must never enter the harness.
    tracked = subprocess.check_output(
        ["git", "ls-files", f"terraform/providers/{provider}"], cwd=ROOT, text=True,
    ).splitlines()
    for relative in tracked:
        source = ROOT / relative
        if source.is_symlink() or source.name != ".terraform.lock.hcl" and source.suffix != ".tf":
            continue
        shutil.copyfile(source, directory / source.name)
    shared = temporary / "terraform" / "shared"
    shared.mkdir()
    for name in ("cloud-init.yaml.tftpl", "bootstrap-sshd-ownership.py"):
        shutil.copyfile(ROOT / "terraform" / "shared" / name, shared / name)
    legacy = directory.parent / f"legacy_{provider}"
    legacy.mkdir()
    for source in directory.glob("*.tf"):
        shutil.copyfile(source, legacy / source.name)
    for source in (ROOT / "tests" / "fixtures" / "provider-bootstrap-lifecycle" / provider).glob("*.tf.fixture"):
        shutil.copyfile(source, legacy / source.name.removesuffix(".fixture"))
    tests = directory / "tests"
    tests.mkdir()
    setup = (ROOT / "terraform" / "providers" / provider / "tests" / "lifecycle.tftest.hcl").read_text()
    (tests / "lifecycle.tftest.hcl").write_text(setup)
    # Migration switches module configurations while retaining the same resource
    # addresses and in-memory state. Outputs prove stable provider identities.
    identity = f'output "test_server_id" {{ value = {SERVERS[provider]}.id }}\n'
    if provider == "hetzner":
        identity += 'output "test_firewall_id" { value = hcloud_firewall.vpn.id }\n'
    for destination in (directory, legacy):
        (destination / "identity.tf").write_text(identity)
    migration = setup[:setup.index('run "')]
    migration += f'''run "legacy_node" {{
  command = apply
  state_key = "migration"
  module {{ source = "../legacy_{provider}" }}
}}
run "migrate_plan" {{
  command = plan
  state_key = "migration"
}}
run "migrate_apply" {{
  command = apply
  state_key = "migration"
  assert {{
    condition = output.test_server_id == run.legacy_node.test_server_id
    error_message = "Migration must retain the original server identity."
  }}
'''
    if provider == "hetzner":
        migration += '''  assert {
    condition = output.test_firewall_id == run.legacy_node.test_firewall_id
    error_message = "Migration must retain the original firewall identity."
  }
'''
    migration += '''}
run "after_migration" {
  command = plan
  state_key = "migration"
}
'''
    for name in ("migration", "first-adoption", "bootstrap-drift"):
        (tests / f"{name}.tftest.hcl").write_text(migration)
    # make tf-test has already installed the pinned provider. Reuse only those
    # dependency binaries, with copied lock hashes still enforced, rather than
    # downloading them again. Never load ambient CLI credentials/configuration.
    mirror = ROOT / "terraform" / "providers" / provider / ".terraform" / "providers"
    if mirror.is_dir():
        configuration_text = f'''provider_installation {{
  filesystem_mirror {{ path = {json.dumps(str(mirror))} }}
}}'''
    else:
        configuration_text = "provider_installation { direct {} }"
    (directory / "test-provider-installation.tfrc").write_text(configuration_text)
    initialized = execute(directory, "init", "-backend=false", "-input=false", "-no-color")
    assert initialized.returncode == 0, initialized.stderr
    return provider, directory, setup


def events(result):
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]


def plan_for(result, run):
    matches = [event["test_plan"] for event in events(result)
               if event.get("type") == "test_plan" and event.get("@testrun") == run]
    assert len(matches) == 1, "Expected one actual Terraform plan event"
    return {change["address"]: change["change"] for change in matches[0]["resource_changes"]}


def test_unchanged_identity_has_no_resource_changes(configuration):
    _, directory, _ = configuration
    result = execute(directory, "test", "-json", "-verbose", "-filter=tests/lifecycle.tftest.hcl")
    assert result.returncode == 0, result.stderr
    assert all(change["actions"] == ["no-op"] for change in plan_for(result, "unchanged_identity").values())


def test_identity_edits_are_blocked_by_exact_server_lifecycle(configuration):
    provider, directory, setup = configuration
    edits = {"admin_user": '"replacement-admin"', "ssh_port": "2222"}
    edits["admin_ssh_public_key"] = '"ssh-ed25519 AAAACHANGEDKEY test@harness"'
    for input_name, new_value in edits.items():
        test = setup[:setup.index('run "unchanged_identity"')]
        test += f'''run "changed_identity" {{
  command = plan
  variables {{ {input_name} = {new_value} }}
}}
'''
        (directory / "tests" / "negative.tftest.hcl").write_text(test)
        result = execute(directory, "test", "-json", "-filter=tests/negative.tftest.hcl")
        assert result.returncode != 0, input_name
        diagnostics = [event["diagnostic"] for event in events(result) if "diagnostic" in event]
        assert any(
            diagnostic["summary"] == "Instance cannot be destroyed"
            and diagnostic["detail"].startswith(f"Resource {SERVERS[provider]} has lifecycle.prevent_destroy set,")
            and "lifecycle.prevent_destroy" in diagnostic["detail"]
            for diagnostic in diagnostics
        ), f"{input_name} must fail at the protected server lifecycle"
        assert any(event.get("test_run", {}).get("status") == "pass" and event.get("@testrun") == "create_node"
                   for event in events(result)), "Initial positive mock apply must succeed"


def test_legacy_state_migration_preserves_nodes_and_forgets_attachment(configuration):
    provider, directory, _ = configuration
    result = execute(directory, "test", "-json", "-verbose", "-filter=tests/migration.tftest.hcl")
    assert result.returncode == 0, result.stderr
    migration = plan_for(result, "migrate_plan")
    assert migration[SERVERS[provider]]["actions"] in (["no-op"], ["update"])
    assert all("delete" not in change["actions"] for change in migration.values())
    assert migration["terraform_data.admin_user"]["actions"] == ["create"]
    if provider != "hetzner":
        assert migration["terraform_data.admin_ssh_public_key"]["actions"] == ["create"]
    else:
        assert migration["hcloud_firewall.vpn"]["actions"] == ["no-op"]
        assert migration["hcloud_firewall_attachment.vpn"]["actions"] == ["forget"]
        assert migration[SERVERS[provider]]["after"]["firewall_ids"] == [2001]
    assert all(change["actions"] == ["no-op"] for change in plan_for(result, "after_migration").values())


def test_first_adoption_rejects_changed_bootstrap_identity(configuration):
    provider, directory, _ = configuration
    migration = (directory / "tests" / "migration.tftest.hcl").read_text()
    setup = migration[:migration.index('run "migrate_plan"')]
    edits = {"admin_user": '"replacement-admin"'}
    if provider == "hetzner":
        edits["server_name"] = '"replacement-node"'
    edits["admin_ssh_public_key"] = '"ssh-ed25519 AAAACHANGEDKEY test@harness"'
    for name, value in edits.items():
        test = setup + f'''run "first_adoption" {{
  command = plan
  state_key = "migration"
  variables {{ {name} = {value} }}
}}
'''
        (directory / "tests" / "first-adoption.tftest.hcl").write_text(test)
        result = execute(directory, "test", "-json", "-filter=tests/first-adoption.tftest.hcl")
        assert result.returncode != 0, name
        diagnostics = [event["diagnostic"] for event in events(result) if "diagnostic" in event]
        if provider == "hetzner":
            assert any(
                diagnostic["summary"] == "Instance cannot be destroyed"
                and diagnostic["detail"].startswith(f"Resource {SERVERS[provider]} has lifecycle.prevent_destroy set,")
                for diagnostic in diagnostics
            ), "Existing Hetzner key attributes must protect identity during first adoption"
        else:
            assert any(
                diagnostic["summary"] == "Resource postcondition failed"
                and "Bootstrap administrator identity differs" in diagnostic["detail"]
                for diagnostic in diagnostics
            ), f"{provider} {name} must refuse divergent first-adoption identity during plan"
        assert any(event.get("test_run", {}).get("status") == "pass" and event.get("@testrun") == "legacy_node"
                   for event in events(result)), "The legacy node must exist before testing adoption"


def test_unrelated_bootstrap_drift_stays_ignored(configuration):
    provider, directory, _ = configuration
    migration = (directory / "tests" / "migration.tftest.hcl").read_text()
    setup = migration[:migration.index('run "migrate_plan"')]
    test = setup + '''run "unrelated_bootstrap_drift" {
  command = plan
  state_key = "migration"
  variables { build_env = "next" }
}
'''
    (directory / "tests" / "bootstrap-drift.tftest.hcl").write_text(test)
    result = execute(directory, "test", "-json", "-verbose", "-filter=tests/bootstrap-drift.tftest.hcl")
    assert result.returncode == 0, result.stderr
    change = plan_for(result, "unrelated_bootstrap_drift")[SERVERS[provider]]
    assert change["actions"] in (["no-op"], ["update"])
    assert change["before"]["user_data"] == change["after"]["user_data"]


def test_public_key_newline_respects_provider_identity_contract(configuration):
    provider, directory, setup = configuration
    public_key = json.dumps("ssh-ed25519 AAAATESTKEY test@harness\n")
    initial = setup[:setup.index('run "unchanged_identity"')]
    # file() retains the final newline in a conventional public-key file.
    fresh = initial.replace(
        'run "create_node" {\n  command = apply',
        f'run "create_node" {{\n  command = apply\n  variables {{ admin_ssh_public_key = {public_key} }}',
    )
    (directory / "tests" / "key-newline-fresh.tftest.hcl").write_text(fresh)
    result = execute(directory, "test", "-json", "-filter=tests/key-newline-fresh.tftest.hcl")
    assert result.returncode == 0, "A fresh node must accept a newline-terminated public key"

    transition = initial + f'''run "key_newline" {{
  command = plan
  variables {{ admin_ssh_public_key = {public_key} }}
}}
'''
    (directory / "tests" / "key-newline-transition.tftest.hcl").write_text(transition)
    result = execute(directory, "test", "-json", "-verbose", "-filter=tests/key-newline-transition.tftest.hcl")
    if provider == "hetzner":
        # Hetzner retains its existing exact provider-key contract.
        assert result.returncode != 0
        assert any(
            event.get("diagnostic", {}).get("summary") == "Instance cannot be destroyed"
            and event["diagnostic"]["detail"].startswith(f"Resource {SERVERS[provider]} has lifecycle.prevent_destroy set,")
            for event in events(result)
        )
    else:
        assert result.returncode == 0, "Public-key file whitespace must not replace the node"
        changes = plan_for(result, "key_newline")
        assert changes[SERVERS[provider]]["actions"] == ["no-op"]
        assert changes["terraform_data.admin_ssh_public_key"]["actions"] == ["no-op"]
