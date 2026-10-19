"""Keep fresh-node recovery output aligned with current controller prerequisites."""

from pathlib import Path
import os
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("path", ["a", "b"])
def test_recovery_plan_requires_admission_before_first_deploy(tmp_path, path):
    binary = tmp_path / "bin"
    binary.mkdir()
    marker = tmp_path / "side-effect"
    for name in ("make", "ssh", "terraform", "sops", "age", "restic"):
        stub = binary / name
        stub.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 77\n")
        stub.chmod(0o700)
    result = subprocess.run(["sh", str(ROOT / "scripts/restore.sh"), "--dry-run",
                             "--env", "prod", "--path-" + path],
        env=os.environ | {"PATH": str(binary) + os.pathsep + os.environ["PATH"]},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert not marker.exists()
    requirements = ["make init", "make plan", "make apply", "make inventory",
                    "Authenticate and pin public SSH identity", "make wait",
                    "make install-ssh-recovery", "make bootstrap-tailnet",
                    "TAILNET_HANDOFFS=", "DEPLOY_SSH_CONTEXTS_FILE",
                    "make migrate-ssh-ownership", "DEPLOY_PROMOTION_CONFIG_FILE",
                    "DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE", "make decrypt",
                    "make validate", "make dry-run", "make deploy"]
    offsets = [output.index(item) for item in requirements]
    assert offsets == sorted(offsets)
    assert "receipt sinks must be fresh and absent" in output
    assert "Do not fabricate contexts" in output
    for line in output.splitlines():
        if "make " in line:
            assert not re.search(r"make (?:init|plan|apply|inventory|wait|dry-run|deploy|verify) "
                                 r"(?:init|plan|apply|inventory|wait|dry-run|deploy|verify)(?: |$)", line)
    if path == "b":
        assert output.index("restore latest --target /") < output.index("Repeat required foundation")
        assert output.index("Repeat required foundation") < output.rindex("make dry-run")


def test_runbook_both_paths_require_shared_admission_and_exact_alias():
    text = (ROOT / "docs/RUNBOOK-restore.md").read_text()
    prerequisite = text.split("## Fresh-node prerequisites", 1)[1].split("## Path A", 1)[0]
    for item in ("install-ssh-recovery", "bootstrap-tailnet", "TAILNET_HANDOFFS",
                 "migrate-ssh-ownership", "DEPLOY_SSH_CONTEXTS_FILE",
                 "DEPLOY_PROMOTION_CONFIG_FILE", "DEPLOY_SSH_BASELINE_FAILURE_RECEIPTS_FILE"):
        assert item in prerequisite
    for path in ("## Path A", "## Path B"):
        section = text.split(path, 1)[1].split("\n## ", 1)[0]
        assert "Fresh-node\nprerequisites" in section or "Fresh-node prerequisites" in section
        assert 'ANSIBLE_LIMIT="$deploy_alias"' in section
    assert "A root restore can overwrite recovery files" in text


@pytest.mark.parametrize("environment", ["default", "../prod", "-prod"])
def test_recovery_plan_refuses_invalid_environment(environment):
    result = subprocess.run(["sh", str(ROOT / "scripts/restore.sh"), "--dry-run",
                             "--env", environment, "--path-a"],
        capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "invalid environment" in result.stderr
