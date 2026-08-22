"""Credentialed deploy workflows must gate on environment approval and env-indirect secrets."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github/workflows"
WORKFLOWS = ("real-vps-deploy.yml", "transport-reachability-matrix.yml")
GATE_ENVIRONMENT = "ci-real-deploy"


def _workflow_documents():
    for name in WORKFLOWS:
        yield name, yaml.safe_load((WORKFLOW_DIR / name).read_text())


def test_credentialed_jobs_reference_the_protected_environment():
    for name, document in _workflow_documents():
        jobs = document["jobs"]
        credentialed = [
            job for job in jobs.values()
            if any(
                str(value).startswith("${{ secrets.")
                for value in (job.get("env") or {}).values()
            )
        ]
        assert credentialed, f"{name} has no credential-bearing job to gate"
        for job in credentialed:
            assert job.get("environment") == GATE_ENVIRONMENT


def test_no_secret_is_expanded_inside_run_blocks():
    for name, document in _workflow_documents():
        steps = [step for job in document["jobs"].values() for step in job.get("steps", [])]
        assert steps, f"{name} declares no steps"
        for index, step in enumerate(steps):
            run = step.get("run")
            if run is None:
                continue
            assert "${{ secrets." not in run, (
                f"{name} step #{index} ({step.get('name', 'unnamed')}) interpolates "
                "a secret into run: text; pass it through step-level env: instead"
            )


def test_fork_short_circuit_is_retained():
    for name in WORKFLOWS:
        source = (WORKFLOW_DIR / name).read_text()
        assert "Refuse to run on a fork PR" in source
