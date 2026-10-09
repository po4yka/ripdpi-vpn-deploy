#!/usr/bin/env python3
"""Evaluate all plan policies, rejecting empty or invalid evaluation results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


POLICY = Path(__file__).resolve().parents[1] / "terraform/policy"


def evaluate(plan: Path) -> int:
    try:
        result = subprocess.run(
            ["conftest", "test", "--rego-version", "v0", "--all-namespaces",
             "--output=json", "-p", str(POLICY), str(plan)],
            capture_output=True, text=True, timeout=120,
        )
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty evaluation")
        checks = 0
        rejected = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid result row")
            namespace = row.get("namespace")
            successes = row.get("successes", 0)
            if (not isinstance(namespace, str)
                    or not namespace.startswith("terraform.policy.")
                    or type(successes) is not int or successes < 0):
                raise ValueError("invalid result summary")
            checks += successes
            for key in ("failures", "warnings", "exceptions"):
                entries = row.get(key, [])
                if not isinstance(entries, list) or any(
                    not isinstance(entry, dict) or not isinstance(entry.get("msg"), str)
                    for entry in entries
                ):
                    raise ValueError("invalid diagnostic summary")
                checks += len(entries)
                if entries and key != "warnings":
                    rejected.add(namespace)
        if checks == 0:
            raise ValueError("zero policy checks")
        if result.returncode or rejected:
            print("Terraform plan policy: REJECT" +
                  (" (" + ", ".join(sorted(rejected)) + ")" if rejected else ""),
                  file=sys.stderr)
            return 1
        print(f"Terraform plan policy: PASS ({checks} checks)")
        return 0
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        # Conftest parser errors can include input text. Keep plan data private.
        print("Terraform plan policy: evaluation failed or checked no rules", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_json", type=Path)
    args = parser.parse_args()
    return evaluate(args.plan_json)


if __name__ == "__main__":
    raise SystemExit(main())
