"""Least-privilege contracts for repository-owned Molecule image publishing."""

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOWS = (
    "publish-molecule-debian13.yml",
    "publish-molecule-ubuntu2404.yml",
)


@pytest.mark.parametrize("workflow_name", WORKFLOWS)
def test_publish_job_owns_only_required_write_permissions(workflow_name):
    workflow = yaml.safe_load((WORKFLOW_DIR / workflow_name).read_text())

    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"publish"}
    assert workflow["jobs"]["publish"]["permissions"] == {
        "contents": "read",
        "packages": "write",
        "security-events": "write",
    }
