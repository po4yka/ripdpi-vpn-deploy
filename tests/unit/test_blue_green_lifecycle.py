"""Execute blue-green with real Make scheduling and synthetic infrastructure."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def executable(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    path.chmod(0o700)


# Answers in prompt order: plan review, SSH pin, SSH ownership, dry-run review, traffic swing.
APPROVE_ALL = "yes\n\n\nyes\nyes\n"


def run_blue_green(tmp_path, failed_phase=None, answers=APPROVE_ALL, provider="upcloud", tfvars=None):
    root, binary = tmp_path / "repo", tmp_path / "bin"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/blue-green.sh", scripts / "blue-green.sh")
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
    if phase == 'init':
        time.sleep(0.15)
    if phase == os.environ.get('FAILED_PHASE'):
        sys.exit(23)
    (root / (phase + '.complete')).touch()
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
    executable(binary / "sops", "#!/bin/sh\nprintf 'synthetic: true\\n'\n")
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
    assert calls[-1] == ["green", "smoke-test"]


@pytest.mark.parametrize("failed_phase", [None, "plan", "dry-run", "verify"])
def test_phases_are_serial_and_failures_stop_dependents(tmp_path, failed_phase):
    result, calls = run_blue_green(tmp_path, failed_phase)
    expected = ["init", "plan", "apply", "wait", "dry-run", "deploy", "verify", "smoke-test"]
    if failed_phase:
        expected = expected[:expected.index(failed_phase) + 1]
    assert result.returncode == (2 if failed_phase else 0), result.stdout + result.stderr
    assert calls == [["prod", "verify"], *[["green", phase] for phase in expected]]


@pytest.mark.parametrize(("answers", "last_phase", "message"), [
    ("\n", "plan", "Aborting before apply"),
    ("no\n", "plan", "Aborting before apply"),
    ("yes\n\n\n\n", "dry-run", "Aborting before deploy"),
    ("yes\n\n\nno\n", "dry-run", "Aborting before deploy"),
])
def test_green_apply_and_deploy_wait_for_a_typed_review(tmp_path, answers, last_phase, message):
    result, calls = run_blue_green(tmp_path, answers=answers)
    phases = ["init", "plan", "apply", "wait", "dry-run"]
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
             "ANSIBLE_SSH_PRIVATE_KEY_FILE": str(tmp_path / "key"), "MAKEFILES": str(injected)},
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
