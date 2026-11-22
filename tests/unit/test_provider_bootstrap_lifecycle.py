"""Credential-free OpenTofu identity transitions of the provider roots."""

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
    # this process. Do not inherit provider credentials or OpenTofu CLI switches.
    environment = {
        key: value for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "TF_PLUGIN_CACHE_DIR"}
    }
    environment.update(TF_IN_AUTOMATION="1", CHECKPOINT_DISABLE="1")
    environment["TF_CLI_CONFIG_FILE"] = str(directory / "test-provider-installation.tfrc")
    return subprocess.run(
        ["tofu", *arguments], cwd=directory, env=environment,
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
    tests = directory / "tests"
    tests.mkdir()
    setup = (ROOT / "terraform" / "providers" / provider / "tests" / "lifecycle.tftest.hcl").read_text()
    (tests / "lifecycle.tftest.hcl").write_text(setup)
    # make tf-test has already installed the pinned provider. Reuse only those
    # dependency binaries, with copied lock hashes still enforced, rather than
    # downloading them again. Never load ambient CLI credentials/configuration.
    mirror = ROOT / "terraform" / "providers" / provider / ".terraform-env" / ".validation" / "providers"
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
    assert len(matches) == 1, "Expected one actual OpenTofu plan event"
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
            diagnostic["summary"] == "Resource instance cannot be destroyed"
            and diagnostic["detail"].startswith(f"Resource instance {SERVERS[provider]} has prevent_destroy set,")
            for diagnostic in diagnostics
        ), f"{input_name} must fail at the protected server lifecycle"
        assert any(event.get("test_run", {}).get("status") == "pass" and event.get("@testrun") == "create_node"
                   for event in events(result)), "Initial positive mock apply must succeed"


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
            event.get("diagnostic", {}).get("summary") == "Resource instance cannot be destroyed"
            and event["diagnostic"]["detail"].startswith(f"Resource instance {SERVERS[provider]} has prevent_destroy set,")
            for event in events(result)
        )
    else:
        assert result.returncode == 0, "Public-key file whitespace must not replace the node"
        changes = plan_for(result, "key_newline")
        assert changes[SERVERS[provider]]["actions"] == ["no-op"]
        assert changes["terraform_data.admin_ssh_public_key"]["actions"] == ["no-op"]
