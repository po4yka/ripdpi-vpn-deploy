"""Verify that Terraform workflows use the supported pinned release."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SETUP_TERRAFORM = "hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e"
SUPPORTED_VERSION = "1.15.2"
WORKFLOWS = ("ci.yml", "real-vps-deploy.yml", "transport-reachability-matrix.yml")


def terraform_version(workflow: str) -> str:
    content = (WORKFLOW_DIR / workflow).read_text()
    assert SETUP_TERRAFORM in content
    match = re.search(r'terraform_version:\s*"([^"]+)"', content)
    assert match, f"{workflow} must declare terraform_version"
    return match.group(1)


def test_terraform_workflows_use_the_supported_pinned_release():
    """Reachability measurements must run against provider-supported Terraform."""
    versions = {workflow: terraform_version(workflow) for workflow in WORKFLOWS}

    assert set(versions.values()) == {SUPPORTED_VERSION}


def test_transport_workflow_does_not_override_setup_terraform():
    """The legacy manual download would replace the supported Terraform binary."""
    content = (WORKFLOW_DIR / "transport-reachability-matrix.yml").read_text()

    assert "releases.hashicorp.com/terraform/" not in content
    assert "terraform_1.9.5" not in content
