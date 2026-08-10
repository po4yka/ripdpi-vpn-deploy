"""Repository checkout credentials must not remain available to later steps."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github/workflows"


def _workflow_documents():
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        yield path, yaml.safe_load(path.read_text()) or {}


def test_all_checkout_steps_disable_persisted_credentials():
    checkout_steps = []

    for path, workflow in _workflow_documents():
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    checkout_steps.append((path.name, job_name, step))

    assert checkout_steps
    for path_name, job_name, step in checkout_steps:
        assert step.get("with", {}).get("persist-credentials") is False, (
            f"{path_name}:{job_name} persists checkout credentials"
        )


def test_branch_protection_job_does_not_checkout_repository():
    source = (WORKFLOW_DIR / "branch-protection.yml").read_text()

    assert "actions/checkout@" not in source
