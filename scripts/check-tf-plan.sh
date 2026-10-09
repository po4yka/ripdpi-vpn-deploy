#!/usr/bin/env bash
# Credential-free policy evaluation of an already-rendered Terraform plan.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "usage: check-tf-plan.sh <plan.json>" >&2
  exit 1
fi

exec python3 - "$REPO_ROOT" "$1" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

root, plan = map(Path, sys.argv[1:])
required = {
    "terraform.policy.admin_port",
    "terraform.policy.ssh_cidrs",
    "terraform.policy.secondary_ip",
    "terraform.policy.server_metadata",
    "terraform.policy.no_secrets_in_user_data",
}
try:
    result = subprocess.run(
        ["conftest", "test", "--rego-version", "v0", "--all-namespaces",
         "--output", "json", "-p", str(root / "terraform/policy"), str(plan)],
        capture_output=True, text=True, timeout=120,
    )
except (OSError, subprocess.TimeoutExpired):
    sys.exit("Terraform policy check: Conftest could not complete")
try:
    reports = json.loads(result.stdout)
    if not isinstance(reports, list):
        raise ValueError
    evaluated = set()
    total = 0
    problems = []
    for report in reports:
        successes = report["successes"]
        if type(successes) is not int or successes < 0:
            raise ValueError
        findings = []
        for key in ("failures", "warnings", "exceptions"):
            values = report.get(key, [])
            if not isinstance(values, list):
                raise ValueError
            findings.extend(values)
        count = successes + len(findings)
        if count:
            evaluated.add(report["namespace"])
        total += count
        for finding in findings:
            message = finding["msg"]
            if not isinstance(message, str):
                raise ValueError
            problems.append(f"{report['namespace']}: {message}")
except (KeyError, TypeError, ValueError):
    sys.exit("Terraform policy check: invalid or missing Conftest evaluation report")

if not total or not required.issubset(evaluated):
    sys.exit("Terraform policy check: incomplete policy evaluation")
if result.returncode or problems:
    for message in problems:
        print(message, file=sys.stderr)
    sys.exit("Terraform policy check: rejected")
print(f"Terraform policy check: {total} evaluations passed across {len(evaluated)} namespaces")
PY
