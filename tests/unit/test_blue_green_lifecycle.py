"""Execute blue-green with real Make scheduling and synthetic infrastructure."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def executable(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    path.chmod(0o700)


# Answers in prompt order: plan review, SSH pin, SSH ownership, dry-run review, traffic swing.
APPROVE_ALL = "yes\n\n\nyes\nyes\n"


def migration_inputs(tmp_path, root, source, provider="upcloud", blue="prod", green="green", blue_alias="node-prod", green_alias="node-green"):
    if not source.exists():
        source.write_text("synthetic source authority\n")
    source.chmod(0o600)
    target = tmp_path / "target.sops.yaml"
    target.write_text("synthetic independent target authority\n")
    target.chmod(0o600)
    (root / "ansible/inventory").mkdir(parents=True, exist_ok=True)
    plan = tmp_path / "migration.json"
    plan.write_text(json.dumps({
        "schema_version": 1, "id": "11111111-2222-4333-8444-555555555555",
        "inventory": str(root / "ansible/inventory/generated.ini"), "known_hosts": str(tmp_path / "known_hosts"),
        "source": {"host": provider + ":" + blue, "alias": blue_alias, "cohort": "fullstack", "secrets_file": str(source)},
        "target": {"host": provider + ":" + green, "alias": green_alias, "cohort": "device-full-tailnet",
                   "secrets_file": str(target), "awg_instances": {}},
        "publication": {"source_alias": "publisher", "target_alias": "publisher", "directory": "/var/lib/vpn-subscription",
                        "origin": "https://subscription.example.test"}}))
    plan.chmod(0o600)
    return {"GREEN_SOPS_FILE": str(target), "DEVICE_MIGRATION_PLAN": str(plan), "DEVICE_MIGRATION_APPROVAL": "a" * 64}


def run_blue_green(tmp_path, failed_phase=None, answers=APPROVE_ALL, provider="upcloud", tfvars=None, extra_environment=None):
    root, binary = tmp_path / "repo", tmp_path / "bin"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/blue-green.sh", scripts / "blue-green.sh")
    (scripts / "device_migration_inventory.py").write_text("import sys\nassert sys.argv[1] in ('check', 'render')\n")
    environments = root / f"terraform/providers/{provider}/environments"
    environments.mkdir(parents=True)
    for name, text in (tfvars or {"green": "# synthetic input\n"}).items():
        (environments / f"{name}.tfvars").write_text(text)
    phases = ("init", "plan", "apply", "wait", "dry-run", "deploy", "verify", "smoke-test")
    (root / "Makefile").write_text(
        ".PHONY: " + " ".join(phases) + "\n" + "".join(
            f"{phase}:\n\t@python3 scripts/phase.py {phase}\n" for phase in phases
        )
    )
    (scripts / "phase.py").write_text("""
import json, os, pathlib, sys, time
phase, environment = sys.argv[1], os.environ['ENV']
root = pathlib.Path.cwd()
with (root / 'calls').open('a') as stream:
    stream.write(json.dumps([environment, phase]) + '\\n')
if environment == 'green':
    previous = {'plan': 'init', 'apply': 'plan', 'dry-run': 'apply',
                'deploy': 'dry-run', 'verify': 'deploy', 'smoke-test': 'verify'}.get(phase)
    if previous and not (root / (previous + '.complete')).exists():
        sys.exit('dependent phase started before ' + previous)
    if phase in ('dry-run', 'deploy', 'verify', 'smoke-test'):
        assert (root / 'migration-prepare.complete').exists()
        assert pathlib.Path(os.environ['SECRETS_FILE']).read_text() == 'prepared target credentials'
        assert os.environ['SOPS_FILE'] == os.environ['GREEN_SOPS_FILE']
    if phase == 'init':
        time.sleep(0.15)
    if phase == os.environ.get('FAILED_PHASE'):
        sys.exit(23)
    (root / (phase + '.complete')).touch()
""")
    (scripts / "device-migration.py").write_text("""
import json, os, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
action = sys.argv[1]
with (root / 'calls').open('a') as stream:
    stream.write(json.dumps(['green', 'migration-' + action]) + '\\n')
if 'migration-' + action == os.environ.get('FAILED_PHASE'):
    sys.exit(23)
if action == 'prepare':
    if sys.argv[-2:] != ['--approve', 'a' * 64]: sys.exit(25)
    assert (root / 'apply.complete').exists()
    pathlib.Path(os.environ['GREEN_SOPS_FILE']).write_text('prepared target credentials')
if action == 'publish': assert (root / 'smoke-test.complete').exists()
if action == 'ready': assert (root / 'migration-publish.complete').exists()
(root / ('migration-' + action + '.complete')).touch()
""")
    executable(scripts / "terraform-env.sh", """#!/bin/sh
case "$*" in
  *server_hostname*) printf 'node-%s\n' "$ENV" ;;
  *server_ipv4*) echo 192.0.2.7 ;;
  *ssh_port*) echo 2222 ;;
  *) exit 1 ;;
esac
""")
    executable(scripts / "render-inventory.sh", "#!/bin/sh\nexit 0\n")
    executable(binary / "sops", "#!/bin/sh\ncat \"$2\"\n")
    executable(binary / "ssh-keygen", "#!/bin/sh\nexit 0\n")
    executable(binary / "ansible-inventory", "#!/bin/sh\n"
               "echo '{\"vpn\":{\"hosts\":[\"node-prod\",\"node-green\"]}}'\n")
    encrypted = tmp_path / "synthetic.sops.yaml"
    encrypted.write_text("synthetic encrypted input\n")
    environment = {**os.environ, "PATH": os.pathsep.join((str(binary), str(Path(sys.executable).parent), os.environ["PATH"])),
                   "BLUE_ENV": "prod", "GREEN_ENV": "green", "PROVIDER": provider,
                   "SOPS_FILE": str(encrypted), "ANSIBLE_SSH_PRIVATE_KEY_FILE": str(tmp_path / "key"),
                   "GREEN_TAILNET_HANDOFF": str(tmp_path / "handoff"),
                   "DEPLOY_SSH_CONTEXTS_FILE": str(tmp_path / "contexts"),
                   "MAKEFLAGS": "-j4", "FAILED_PHASE": failed_phase or ""}
    environment.update(migration_inputs(tmp_path, root, encrypted, provider))
    environment.update(extra_environment or {})
    result = subprocess.run(["bash", str(scripts / "blue-green.sh")], cwd=root, env=environment,
                            input=answers, capture_output=True, text=True, timeout=15)
    calls = root / "calls"
    return result, [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []


def key_tfvars(key):
    return f'server_name = "node"\nadmin_ssh_public_key = "{key}"\n'


@pytest.mark.parametrize("green_key", ["ssh-ed25519 AAAABLUEKEY operator@laptop", "ssh-ed25519 AAAABLUEKEY other@host"])
def test_hetzner_green_with_the_blue_key_refuses_before_plan(tmp_path, green_key):
    tfvars = {"prod": key_tfvars("ssh-ed25519 AAAABLUEKEY operator@laptop"), "green": key_tfvars(green_key)}
    result, calls = run_blue_green(tmp_path, provider="hetzner", tfvars=tfvars)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "one SSH key per fingerprint" in result.stderr
    assert calls == [["prod", "verify"]]


def test_hetzner_green_with_its_own_key_provisions(tmp_path):
    tfvars = {"prod": key_tfvars("ssh-ed25519 AAAABLUEKEY operator@laptop"),
              "green": key_tfvars("ssh-ed25519 AAAAGREENKEY operator@laptop")}
    result, calls = run_blue_green(tmp_path, provider="hetzner", tfvars=tfvars)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[-1] == ["green", "migration-ready"]


@pytest.mark.parametrize("failed_phase", [None, "plan", "dry-run", "verify", "migration-prepare", "migration-publish", "migration-ready"])
def test_phases_are_serial_and_failures_stop_dependents(tmp_path, failed_phase):
    result, calls = run_blue_green(tmp_path, failed_phase)
    expected = ["init", "plan", "apply", "wait", "migration-plan", "migration-prepare", "dry-run", "deploy", "verify", "smoke-test", "migration-publish", "migration-ready"]
    if failed_phase:
        expected = expected[:expected.index(failed_phase) + 1]
    assert result.returncode == (23 if failed_phase and failed_phase.startswith('migration-') else 2 if failed_phase else 0), result.stdout + result.stderr
    assert calls == [["prod", "verify"], *[["green", phase] for phase in expected]]


@pytest.mark.parametrize(("answers", "last_phase", "message"), [
    ("\n", "plan", "Aborting before apply"),
    ("no\n", "plan", "Aborting before apply"),
    ("yes\n\n\n\n", "dry-run", "Aborting before deploy"),
    ("yes\n\n\nno\n", "dry-run", "Aborting before deploy"),
])
def test_green_apply_and_deploy_wait_for_a_typed_review(tmp_path, answers, last_phase, message):
    result, calls = run_blue_green(tmp_path, answers=answers)
    phases = ["init", "plan", "apply", "wait", "migration-plan", "migration-prepare", "dry-run"]
    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stderr
    assert calls == [["prod", "verify"], *[["green", phase] for phase in phases[:phases.index(last_phase) + 1]]]


def test_child_make_does_not_load_inherited_makefiles(tmp_path):
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/blue-green.sh", scripts / "blue-green.sh")
    binary = tmp_path / "bin"
    executable(binary / "sops", "#!/bin/sh\nprintf 'synthetic: true\\n'\n")
    executable(binary / "ansible-inventory", "#!/bin/sh\n"
               "echo '{\"vpn\":{\"hosts\":[\"node-prod\"]}}'\n")
    executable(scripts / "terraform-env.sh", "#!/bin/sh\necho node-prod\n")
    (root / "Makefile").write_text("verify:\n\t@exit 23\n")
    injected = tmp_path / "inherited.mk"
    injected.write_text("$(error inherited Makefile was parsed)\n")
    encrypted = tmp_path / "synthetic.sops.yaml"
    encrypted.touch()
    result = subprocess.run(["bash", str(scripts / "blue-green.sh")], cwd=root,
        env={**os.environ, "PATH": os.pathsep.join((str(binary), str(Path(sys.executable).parent), os.environ["PATH"])),
             "BLUE_ENV": "prod", "GREEN_ENV": "green", "SOPS_FILE": str(encrypted),
             "ANSIBLE_SSH_PRIVATE_KEY_FILE": str(tmp_path / "key"), "MAKEFILES": str(injected),
             **migration_inputs(tmp_path, root, encrypted)},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "inherited Makefile was parsed" not in result.stderr
    assert "Error 23" in result.stderr


@pytest.mark.parametrize("blue,green", [("prod", "default"), ("default", "prod"),
                                       ("default", "green"), ("prod", "../prod")])
@pytest.mark.parametrize("dry_run", [False, True])
def test_state_alias_collision_refuses_before_private_inputs(blue, green, dry_run):
    result = subprocess.run(["bash", str(ROOT / "scripts/blue-green.sh"),
                             *(["--dry-run"] if dry_run else [])],
        env={**os.environ, "BLUE_ENV": blue, "GREEN_ENV": green,
             "SOPS_FILE": "/absent-private-source", "ANSIBLE_SSH_PRIVATE_KEY_FILE": ""},
        capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "default is reserved" in result.stderr
    assert "missing" not in result.stderr and "must be set" not in result.stderr


@pytest.mark.parametrize('field,value', [('GREEN_SOPS_FILE', ''), ('DEVICE_MIGRATION_PLAN', ''),
                                         ('DEVICE_MIGRATION_APPROVAL', 'not-reviewed')])
def test_missing_migration_inputs_refuse_before_provider_or_secret_calls(tmp_path, field, value):
    result, calls = run_blue_green(tmp_path, extra_environment={field: value})
    assert result.returncode != 0 and calls == []


def test_stale_preapproval_never_deploys_or_publishes(tmp_path):
    result, calls = run_blue_green(tmp_path, extra_environment={'DEVICE_MIGRATION_APPROVAL': 'b' * 64})
    assert result.returncode == 25
    assert calls[-1] == ['green', 'migration-prepare']
    assert all(phase not in {'deploy', 'migration-publish', 'migration-ready'} for _, phase in calls)


def test_operator_can_approve_fresh_review_after_inventory_render(tmp_path):
    result, calls = run_blue_green(tmp_path, answers='yes\n\n\n' + 'a' * 64 + '\nyes\nyes\n',
                                   extra_environment={'DEVICE_MIGRATION_APPROVAL': ''})
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.index(['green', 'migration-plan']) < calls.index(['green', 'migration-prepare']) < calls.index(['green', 'deploy'])


def test_incomplete_device_evidence_never_prints_retirement_guidance(tmp_path):
    result, calls = run_blue_green(tmp_path, failed_phase='migration-ready')
    assert result.returncode == 23 and calls[-1] == ['green', 'migration-ready']
    assert 'When ready to destroy blue' not in result.stdout
    assert 'Blue-green orchestration done' not in result.stdout


def test_declined_handover_preserves_both_possible_device_paths(tmp_path):
    result, calls = run_blue_green(tmp_path, answers='yes\n\n\nyes\nno\n')
    assert result.returncode == 1 and calls[-1] == ['green', 'migration-publish']
    assert 'Retain both blue and green' in result.stdout
    assert 'device-migration rollback' in result.stdout
    assert 'make destroy' not in result.stdout
    assert 'Blue-green orchestration done' not in result.stdout


def test_completed_handover_keeps_migrated_environment_identity(tmp_path):
    result, calls = run_blue_green(tmp_path)
    assert result.returncode == 0 and calls[-1] == ['green', 'migration-ready']
    assert 'Keep operating under PROVIDER=upcloud ENV=green' in result.stdout
    assert 'separately reviewed migration' in result.stdout
    assert 'rename green.tfvars' not in result.stdout


def test_plan_selection_conflict_refuses_before_provider_mutation(tmp_path):
    result, calls = run_blue_green(tmp_path, extra_environment={'BLUE_COHORT': 'p0-minimal'})
    assert result.returncode != 0 and calls == []
    assert 'migration plan must match' in result.stderr
