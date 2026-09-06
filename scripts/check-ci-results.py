#!/usr/bin/env python3
"""Reject failed selected checks and any outcome inconsistent with the CI plan."""

import json
import os
import sys


def validate(needs):
    if not isinstance(needs, dict) or needs.get("selection", {}).get("result") != "success":
        raise ValueError("CI dependency selection did not succeed")
    checks = json.loads(needs["selection"]["outputs"]["checks"])
    if not isinstance(checks, dict) or not checks or set(checks) != set(needs) - {"selection"}:
        raise ValueError("Dependency plan and required job graph differ")
    for name, selected in checks.items():
        if type(selected) is not bool:
            raise ValueError(f"Invalid selection for {name}")
        expected = "success" if selected else "skipped"
        actual = needs[name].get("result")
        if actual != expected:
            raise ValueError(f"{name}: expected {expected}, received {actual}")


def main():
    try:
        validate(json.loads(os.environ["NEEDS"]))
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        print(f"Required CI checks rejected: {error}", file=sys.stderr)
        return 1
    print("All selected checks succeeded; all skips were explicitly planned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
