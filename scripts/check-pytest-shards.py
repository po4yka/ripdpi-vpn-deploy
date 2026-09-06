#!/usr/bin/env python3
"""Require four successful pytest groups covering the full portable suite once."""

import argparse
import json
import math
from pathlib import Path
import re


def unique_nodes(value):
    if not isinstance(value, list) or any(not isinstance(node, str) or not node for node in value):
        raise ValueError("invalid test node list")
    if len(value) != len(set(value)):
        raise ValueError("duplicate test nodes")
    return set(value)


def verify(reports):
    if len(reports) != 4 or any(not isinstance(report, dict) for report in reports):
        raise ValueError("exactly four group reports are required")
    if any(type(report.get("group")) is not int for report in reports):
        raise ValueError("invalid group identity")
    if {report["group"] for report in reports} != {1, 2, 3, 4}:
        raise ValueError("missing or duplicate group")
    expected = unique_nodes(reports[0].get("expected"))
    profile = reports[0].get("profile_sha256")
    if not expected or not isinstance(profile, str) or not re.fullmatch(r"[0-9a-f]{64}", profile):
        raise ValueError("missing collection or profile identity")
    merged = {}
    for report in reports:
        if type(report.get("exitstatus")) is not int or report["exitstatus"] != 0 or report.get("groups") != 4:
            raise ValueError("a group did not succeed")
        if report.get("profile_sha256") != profile or unique_nodes(report.get("expected")) != expected:
            raise ValueError("groups used different collections or duration profiles")
        selected = unique_nodes(report.get("selected"))
        if not selected or unique_nodes(report.get("finished")) != selected:
            raise ValueError("a group did not finish its selected tests")
        durations = report.get("durations")
        if not isinstance(durations, dict) or set(durations) != selected or any(
            type(value) not in (int, float) or not math.isfinite(value) or value < 0
            for value in durations.values()
        ):
            raise ValueError("incomplete or invalid execution durations")
        if merged.keys() & selected:
            raise ValueError("a test ran in more than one group")
        merged.update(durations)
    if set(merged) != expected:
        raise ValueError("group union does not match the full portable collection")
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path)
    parser.add_argument("--write-durations", type=Path, required=True)
    args = parser.parse_args()
    try:
        reports = [json.loads(path.read_text()) for path in sorted(args.reports.glob("*/report.json"))]
        durations = verify(reports)
    except (OSError, ValueError) as error:
        parser.exit(1, f"pytest group coverage failed: {error}\n")
    args.write_durations.parent.mkdir(parents=True, exist_ok=True)
    args.write_durations.write_text(json.dumps(durations, sort_keys=True, indent=2) + "\n")
    print(f"pytest group coverage: PASS ({len(durations)} tests, four disjoint groups)")
    for report in sorted(reports, key=lambda report: report["group"]):
        print(f"group {report['group']}: {len(report['selected'])} tests, "
              f"{sum(report['durations'].values()):.2f}s measured test time")


if __name__ == "__main__":
    main()
