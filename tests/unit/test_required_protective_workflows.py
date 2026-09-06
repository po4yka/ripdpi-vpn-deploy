"""Protective workflow outcomes must reach the branch-required CI aggregate."""

import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
PROTECTIVE = ("tf-policy", "image-scan", "contract-sync", "reproducible-build")


def _workflow(name):
    return yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text())


@pytest.mark.parametrize("workflow", PROTECTIVE)
def test_protective_workflow_is_selected_by_dependencies_and_required(workflow):
    ci = _workflow("ci")
    caller = ci["jobs"][workflow]
    assert caller["uses"] == f"./.github/workflows/{workflow}.yml"
    assert caller["needs"] == "selection"
    assert caller["if"] == "${{ fromJSON(needs.selection.outputs.checks)['" + workflow + "'] }}"
    assert "continue-on-error" not in caller
    assert "secrets" not in caller
    assert workflow in ci["jobs"]["required"]["needs"]
    # PyYAML treats the unquoted GitHub Actions `on` key as YAML 1.1 true.
    triggers = _workflow(workflow)[True]
    assert "workflow_call" in triggers
    assert "workflow_dispatch" in triggers
    assert "pull_request" not in triggers
    assert "push" not in triggers


@pytest.mark.parametrize("workflow", PROTECTIVE)
@pytest.mark.parametrize("outcome", ("failure", "cancelled", "skipped"))
def test_unsuccessful_protective_workflow_rejects_merge(workflow, outcome):
    gate = _workflow("ci")["jobs"]["required"]
    # Model the needs context emitted by Actions: only declared dependencies
    # reach the aggregate. An omitted protective result used to disappear here.
    outcomes = {name: "success" for name in gate["needs"]}
    outcomes[workflow] = outcome
    results = [outcomes[name] for name in gate["needs"]]
    assert _run_gate(gate, results).returncode != 0


def _run_gate(gate, results):
    step = gate["steps"][-1]
    assert step["env"]["NEEDS"] == "${{ toJSON(needs) }}"
    needs = {name: {"result": result} for name, result in zip(gate["needs"], results, strict=True)}
    needs["selection"]["outputs"] = {
        "checks": json.dumps({name: True for name in gate["needs"] if name != "selection"}),
    }
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=ROOT, env={**os.environ, "NEEDS": json.dumps(needs)},
        capture_output=True, text=True, timeout=10,
    )


@pytest.mark.parametrize("outcome", ("failure", "cancelled", "skipped"))
def test_unsuccessful_python_validators_reject_merge(outcome):
    gate = _workflow("ci")["jobs"]["required"]
    outcomes = {name: "success" for name in gate["needs"]}
    assert "python-validators" in outcomes
    outcomes["python-validators"] = outcome
    assert _run_gate(gate, list(outcomes.values())).returncode != 0


def test_successful_ci_emits_the_existing_branch_required_context():
    ci = _workflow("ci")
    gate = ci["jobs"]["required"]
    assert gate["if"] == "always()"
    assert gate["name"] == "required checks"
    assert '"required checks"' in (WORKFLOWS / "branch-protection.yml").read_text()
    assert set(gate["needs"]) == set(ci["jobs"]) - {"required"}
    assert _run_gate(gate, ["success"] * len(gate["needs"])).returncode == 0
    assert set(ci[True]) == {"push", "pull_request", "workflow_dispatch"}
    assert not ci[True]["pull_request"]  # No path filters can suppress the gate.


def test_security_events_write_is_scoped_to_the_image_scan_call():
    ci = _workflow("ci")
    assert ci["permissions"] == {"contents": "read"}
    assert ci["jobs"]["image-scan"]["permissions"] == {
        "contents": "read", "security-events": "write",
    }
    for name in set(PROTECTIVE) - {"image-scan"}:
        assert "permissions" not in ci["jobs"][name]
