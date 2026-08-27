#!/usr/bin/env python3
"""Read-only verification of the hosted credentialed-deploy approval gate."""

import json
import subprocess
import sys


def has_required_reviewer(document: object) -> bool:
    if not isinstance(document, dict):
        return False
    rules = document.get("protection_rules")
    if not isinstance(rules, list):
        return False
    return any(
        isinstance(rule, dict)
        and rule.get("type") == "required_reviewers"
        and isinstance(rule.get("reviewers"), list)
        and any(
            isinstance(entry, dict)
            and entry.get("type") in {"User", "Team"}
            and isinstance(entry.get("reviewer"), dict)
            and isinstance(entry["reviewer"].get("id"), int)
            and entry["reviewer"]["id"] > 0
            for entry in rule["reviewers"]
        )
        for rule in rules
    )


def main() -> int:
    try:
        result = subprocess.run(
            ["gh", "api", "repos/po4yka/ripdpi-vpn-deploy/environments/ci-real-deploy"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("CI deploy gate: GitHub API unavailable; approval is unverified", file=sys.stderr)
        return 2
    if result.returncode != 0:
        print("CI deploy gate: cannot read environment; approval is unverified", file=sys.stderr)
        return 2
    try:
        document = json.loads(result.stdout)
    except (ValueError, TypeError):
        print("CI deploy gate: invalid API response", file=sys.stderr)
        return 2
    if not has_required_reviewer(document):
        print("CI deploy gate: required-reviewer protection is missing", file=sys.stderr)
        return 1
    print("CI deploy gate: required-reviewer protection verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
