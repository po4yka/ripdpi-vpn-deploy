"""The saved-plan gate must evaluate every policy family and fail closed."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check-tf-plan.sh"
NAMESPACES = (
    "admin_port", "ssh_cidrs", "secondary_ip", "server_metadata",
    "no_secrets_in_user_data",
)


def run_gate(tmp_path: Path, reports, *, status: int = 0):
    plan = tmp_path / "plan with spaces.json"
    plan.write_text("{}")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "conftest"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['AUDIT_ARGV']).write_text(json.dumps(sys.argv[1:]))\n"
        f"print({json.dumps(json.dumps(reports))})\n"
        f"sys.exit({status})\n"
    )
    stub.chmod(0o755)
    argv = tmp_path / "argv.json"
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "AUDIT_ARGV": str(argv)}
    result = subprocess.run([str(CHECK), str(plan)], env=env, capture_output=True, text=True)
    return result, json.loads(argv.read_text()), plan


def successful_reports():
    return [{"namespace": f"terraform.policy.{name}", "successes": 1} for name in NAMESPACES]


def test_success_evaluates_all_namespaces_and_the_exact_json_path(tmp_path):
    result, argv, plan = run_gate(tmp_path, successful_reports())
    assert result.returncode == 0, result.stderr
    assert "5 evaluations passed across 5 namespaces" in result.stdout
    assert argv == [
        "test", "--rego-version", "v0", "--all-namespaces", "--output", "json",
        "-p", str(ROOT / "terraform/policy"), str(plan),
    ]


@pytest.mark.parametrize("reports", [[], [{"namespace": "main", "successes": 0}], successful_reports()[:-1]])
def test_zero_or_incomplete_evaluation_cannot_succeed(tmp_path, reports):
    result, _, _ = run_gate(tmp_path, reports)
    assert result.returncode != 0
    assert "incomplete policy evaluation" in result.stderr


@pytest.mark.parametrize("key", ["failures", "warnings", "exceptions"])
def test_reported_violation_fails_even_if_tool_exit_is_zero(tmp_path, key):
    reports = successful_reports()
    reports[0][key] = [{"msg": "management port opened"}]
    result, _, _ = run_gate(tmp_path, reports)
    assert result.returncode != 0
    assert "terraform.policy.admin_port" in result.stderr
    assert "management port opened" not in result.stderr


def test_tool_failure_cannot_succeed_with_a_success_shaped_report(tmp_path):
    result, _, _ = run_gate(tmp_path, successful_reports(), status=2)
    assert result.returncode != 0


@pytest.mark.parametrize("reports", [{}, [None], [{"namespace": "main", "successes": True}], [{"namespace": "main", "successes": -1}]])
def test_malformed_report_is_rejected(tmp_path, reports):
    result, _, _ = run_gate(tmp_path, reports)
    assert result.returncode != 0
    assert "invalid or missing" in result.stderr


def test_operator_plan_uses_the_shared_saved_plan_gate():
    source = (ROOT / "scripts/tf-policy-test.sh").read_text()
    assert '"${REPO_ROOT}/scripts/check-tf-plan.sh" "$PLAN_JSON"' in source
    assert "\nconftest test" not in source
