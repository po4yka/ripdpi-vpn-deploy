"""Credential-free OpenTofu identity transitions of the provider roots."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Thread
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ("hetzner", "vultr", "scaleway")
SERVERS = {
    "hetzner": "hcloud_server.vpn",
    "vultr": "vultr_instance.vpn",
    "scaleway": "scaleway_instance_server.vpn",
}
pytestmark = pytest.mark.native_runtime


def execute(directory, *arguments, backend_scope="test-workspace"):
    # Only copied configurations, generated mock state and synthetic inputs enter
    # this process. Do not inherit provider credentials or OpenTofu CLI switches.
    environment = {
        key: value for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "TF_PLUGIN_CACHE_DIR"}
    }
    environment.update(TF_IN_AUTOMATION="1", CHECKPOINT_DISABLE="1",
                       TF_VAR_state_passphrase="tf-test-passphrase-not-a-secret",
                       TF_VAR_plan_backend_scope=backend_scope)
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
    if configuration[0] != "hetzner":
        assert all(change["actions"] == ["no-op"] for change in plan_for(result, "edited_comment_keeps_identity").values())


@pytest.mark.parametrize("run", ("single_key_list_keeps_node", "second_key_keeps_node"))
def test_admin_key_list_edits_keep_the_node_and_key_resources(configuration, run):
    provider, directory, _ = configuration
    result = execute(directory, "test", "-json", "-verbose", "-filter=tests/lifecycle.tftest.hcl")
    assert result.returncode == 0, result.stderr
    changes = plan_for(result, run)
    assert changes[SERVERS[provider]]["actions"] == ["no-op"]
    key_resource = "hcloud_ssh_key.admin" if provider == "hetzner" else "terraform_data.admin_ssh_public_key"
    assert changes[key_resource]["actions"] == ["no-op"]


def test_identity_edits_are_blocked_by_exact_server_lifecycle(configuration):
    provider, directory, setup = configuration
    edits = {"admin_user": '"replacement-admin"', "ssh_port": "2222"}
    edits["admin_ssh_public_keys"] = '["ssh-ed25519 AAAACHANGEDKEY test@harness"]'
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
    public_key = json.dumps(["ssh-ed25519 AAAATESTKEY test@harness\n"])
    initial = setup[:setup.index('run "unchanged_identity"')]
    # file() retains the final newline in a conventional public-key file.
    fresh = initial.replace(
        'run "create_node" {\n  command = apply',
        f'run "create_node" {{\n  command = apply\n  variables {{ admin_ssh_public_keys = {public_key} }}',
    )
    (directory / "tests" / "key-newline-fresh.tftest.hcl").write_text(fresh)
    result = execute(directory, "test", "-json", "-filter=tests/key-newline-fresh.tftest.hcl")
    assert result.returncode == 0, "A fresh node must accept a newline-terminated public key"

    transition = initial + f'''run "key_newline" {{
  command = plan
  variables {{ admin_ssh_public_keys = {public_key} }}
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


@pytest.mark.parametrize("state_config", sorted(ROOT.glob("terraform/**/state.tf")),
                         ids=lambda path: path.parent.name)
def test_encryption_passphrase_stays_out_of_plan_json(tmp_path, state_config):
    shutil.copyfile(state_config, tmp_path / "state.tf")
    (tmp_path / "test_backend_override.tf").write_text('terraform {\n  backend "local" {}\n}\n')
    (tmp_path / "main.tf").write_text('resource "terraform_data" "test" { input = "value" }\n')
    (tmp_path / "test-provider-installation.tfrc").write_text("")
    for args in (("init", "-input=false"), ("plan", "-input=false", "-out=reviewed.plan"),
                 ("show", "-json", "reviewed.plan"), ("apply", "-input=false", "reviewed.plan")):
        result = execute(tmp_path, *args)
        assert result.returncode == 0, result.stderr
        if args[0] == "show":
            if state_config.parent.name != "cascade-ingress":
                foreign = execute(tmp_path, "apply", "-input=false", "reviewed.plan", backend_scope="other-workspace")
                assert foreign.returncode != 0 and not (tmp_path / "terraform.tfstate").exists()
            assert "tf-test-passphrase-not-a-secret" not in result.stdout
            assert json.loads(result.stdout)["resource_changes"][0]["change"]["actions"] == ["create"]
    assert "encrypted_data" in json.loads((tmp_path / "terraform.tfstate").read_text())


def test_adopt_pre_guard_snapshot_in_isolated_backend(configuration, tmp_path):
    recover_snapshot(configuration, tmp_path / "pre-guard", old_digest=False)
    if configuration[0] != "hetzner":
        recover_snapshot(configuration, tmp_path / "old-digest", old_digest=True)


def recover_snapshot(configuration, tmp_path, old_digest):
    provider, source, setup = configuration
    root = tmp_path / "terraform/providers" / provider
    root.mkdir(parents=True)
    for path in [*source.glob("*.tf"), source / ".terraform.lock.hcl", source / "test-provider-installation.tfrc"]:
        shutil.copy2(path, root / path.name)
    shutil.copytree(source.parents[1] / "shared", root.parents[1] / "shared")
    legacy = ROOT / "tests/fixtures/provider-bootstrap-lifecycle" / provider
    shutil.copy2(legacy.parent / "cloud-init.yaml.tftpl", root / "legacy-cloud-init.tftpl")
    if old_digest:
        entry = root / "main.tf"
        previous = entry.read_text().replace("sha256(local.bootstrap_key)", "sha256(trimspace(var.admin_ssh_public_keys[0]))")
        entry.write_text(previous.replace("ssh_key = local.bootstrap_key", "ssh_key = var.admin_ssh_public_keys[0]"))
    else:
        for path in legacy.glob("*.tf.fixture"):
            shutil.copy2(path, root / path.stem)
    (root / "scratch_override.tf").write_text('terraform {\n backend "local" {}\n}\n')

    mock, variables = setup.split("variables {\n", 1)
    uuid = str(uuid4())
    if provider == "scaleway":
        mock = mock.replace('mock_provider "scaleway" {}', f'''mock_provider "scaleway" {{
  mock_resource "scaleway_instance_server" {{ defaults = {{ id = "pl-waw-1/{uuid}" }} }}
}}''')
    values = variables.split("\n}", 1)[0]
    tfvars = root / "identity.tfvars"
    tfvars.write_text(values)
    (root / "legacy.tftest.hcl").write_text(mock + "variables {\n" + values + '\n}\nrun "seed" { command = apply }\n')
    assert execute(root, "init", "-input=false", "-lockfile=readonly").returncode == 0
    seed = execute(root, "test", "-json", "-filter=legacy.tftest.hcl")
    assert seed.returncode == 0 and any(e.get("test_run", {}).get("status") == "pass" for e in events(seed))
    # The legacy server's prevent_destroy retains the mock deployment at test teardown.
    assert (root / "errored_test.tfstate").is_file()
    for path in source.glob("*.tf"):
        shutil.copy2(path, root / path.name)

    class VolumeRead(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != f"/instance/v1/zones/pl-waw-1/servers/{uuid}":
                self.send_error(404)
                return
            body = json.dumps({"server": {"id": uuid, "zone": "pl-waw-1", "volumes": {
                "0": {"id": "00000000-0000-4000-8000-000000000100", "size": 20_000_000_000,
                      "volume_type": "sbs_volume"}}}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with HTTPServer(("127.0.0.1", 0), VolumeRead) as api:
        server = Thread(target=api.serve_forever, daemon=True)
        server.start()
        # Only synthetic credentials and this loopback endpoint are available to the real plugins.
        environment = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "CHECKPOINT_DISABLE": "1",
                       "TF_CLI_CONFIG_FILE": str(root / "test-provider-installation.tfrc"),
                       "TF_VAR_state_passphrase": "tf-test-passphrase-not-a-secret",
                       "TF_VAR_plan_backend_scope": "test-workspace",
                       "HCLOUD_TOKEN": "0" * 64, "VULTR_API_KEY": "fixture", "SCW_ACCESS_KEY": "SCW" + "0" * 17,
                       "SCW_SECRET_KEY": uuid, "SCW_DEFAULT_PROJECT_ID": uuid,
                       "SCW_API_URL": f"http://127.0.0.1:{api.server_port}",
                       "HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1"}

        def tofu(*args, check=True):
            return subprocess.run(["tofu", *args], cwd=root, env=environment, capture_output=True,
                                  text=True, timeout=120, check=check)

        def verify(plan):
            command = [sys.executable, str(ROOT / "scripts/check-bootstrap-guard-plan.py"), provider]
            if old_digest:
                command.append("--upgrade-digest")
            return subprocess.run(command,
                                  input=tofu("show", "-json", plan).stdout, capture_output=True, text=True)

        try:
            tofu("state", "push", "errored_test.tfstate")
            plan = ["plan", "-refresh=false", "-input=false", "-no-color", "-var-file=identity.tfvars"]
            targets = ["-target=terraform_data.admin_user"]
            if provider != "hetzner":
                targets.append("-target=terraform_data.admin_ssh_public_key")
            mismatches = ["admin_user=other", 'admin_ssh_public_keys=["ssh-ed25519 AAAADIFFERENT fixture"]', "ssh_port=2222"]
            if old_digest:
                targets = ["-target=terraform_data.admin_ssh_public_key"]
                tfvars.write_text(values.replace("test@harness", "new annotation"))
            else:
                mismatches.append('admin_ssh_public_keys=["ssh-ed25519 AAAATESTKEY test@harness","ssh-ed25519 AAAAEXTRA extra"]')
            for mismatch in mismatches:
                tofu(*plan, *targets, "-var", mismatch, "-out=wrong.plan")
                assert verify("wrong.plan").returncode != 0
            tofu(*plan, *targets, "-out=guard.plan")
            assert verify("guard.plan").returncode == 0
            tofu("apply", "-input=false", "guard.plan")

            # A full plan on the recovered copy must retain every managed server. The historical
            # Scaleway resource had no explicit root volume and its volume transition is refused.
            full = tofu(*plan, "-var=build_env=next", "-out=qualified.plan", check=False)
            if provider == "scaleway" and not old_digest:
                assert full.returncode != 0
                assert "Resource instance scaleway_instance_server.vpn has prevent_destroy set" in full.stderr
            else:
                assert full.returncode == 0, full.stderr
                changes = {row["address"]: row["change"]
                           for row in json.loads(tofu("show", "-json", "qualified.plan").stdout)["resource_changes"]}
                assert all("delete" not in change["actions"] and "create" not in change["actions"]
                           for change in changes.values())
                machine = changes[SERVERS[provider]]
                assert machine["before"]["id"] == machine["after"]["id"]
                assert machine["before"]["user_data"] == machine["after"]["user_data"]
                if old_digest and provider == "vultr":
                    assert changes["vultr_ssh_key.admin"]["actions"] == ["update"]
                    assert changes["vultr_ssh_key.admin"]["before"]["id"] == changes["vultr_ssh_key.admin"]["after"]["id"]
                if provider == "hetzner":
                    assert changes["hcloud_firewall_attachment.vpn"]["actions"] == ["forget"]
                    assert machine["after"]["firewall_ids"] == [2001]
        finally:
            api.shutdown()
            server.join()
