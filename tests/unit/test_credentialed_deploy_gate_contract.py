"""Credentialed deploy workflows must gate on environment approval and env-indirect secrets."""

from pathlib import Path
import json
import re
import runpy
import subprocess

import pytest
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
            if re.search(r"\$\{\{\s*secrets[.\[]", json.dumps(job))
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
            assert not re.search(r"\$\{\{\s*secrets[.\[]", run), (
                f"{name} step #{index} ({step.get('name', 'unnamed')}) interpolates "
                "a secret into run: text; pass it through step-level env: instead"
            )


def test_fork_short_circuit_is_retained():
    for name, document in _workflow_documents():
        for job in document["jobs"].values():
            guard = next(step for step in job["steps"]
                         if step.get("name") == "Refuse to run on a fork PR")
            assert guard["if"] == (
                "github.event_name == 'pull_request' && "
                "github.event.pull_request.head.repo.full_name != github.repository"
            ), f"{name} must reject forks without rejecting dispatch/schedule events"
            assert "exit 1" in guard["run"]


@pytest.mark.parametrize("rules,expected", [
    ([], False),
    ([{"type": "wait_timer", "wait_timer": 5}], False),
    ([{"type": "required_reviewers", "reviewers": []}], False),
    ([{"type": "required_reviewers", "reviewers": [{"type": "User", "reviewer": {"id": 1}}]}], True),
])
def test_live_environment_contract_requires_a_real_reviewer(rules, expected):
    module = runpy.run_path(str(ROOT / "scripts/check-ci-deploy-gate.py"))
    assert module["has_required_reviewer"]({"protection_rules": rules}) is expected


@pytest.mark.parametrize("result", [
    subprocess.CompletedProcess([], 1, "", "private API diagnostics"),
    subprocess.CompletedProcess([], 0, "not-json", ""),
    subprocess.CompletedProcess([], 0, '{"protection_rules": []}', ""),
])
def test_live_environment_check_fails_closed_and_redacts_errors(monkeypatch, capsys, result):
    module = runpy.run_path(str(ROOT / "scripts/check-ci-deploy-gate.py"))
    monkeypatch.setattr(module["subprocess"], "run", lambda *args, **kwargs: result)
    assert module["main"]() != 0
    output = capsys.readouterr()
    assert "private API diagnostics" not in output.out + output.err


def test_live_environment_check_uses_read_only_bounded_api(monkeypatch):
    module = runpy.run_path(str(ROOT / "scripts/check-ci-deploy-gate.py"))

    def respond(argv, **kwargs):
        assert argv == ["gh", "api", "repos/po4yka/ripdpi-vpn-deploy/environments/ci-real-deploy"]
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(argv, 0, json.dumps({
            "protection_rules": [{"type": "required_reviewers", "reviewers": [
                {"type": "User", "reviewer": {"id": 1}},
            ]}],
        }), "")

    monkeypatch.setattr(module["subprocess"], "run", respond)
    assert module["main"]() == 0
