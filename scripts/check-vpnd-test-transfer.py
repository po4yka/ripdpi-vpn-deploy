#!/usr/bin/env python3
"""Reject missing, stale, skipped or failing baseline-to-Python test transfers."""

import argparse
import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNOTATION = re.compile(r"# Rust test: (vpnd/[^\s:]+\.rs::[A-Za-z0-9_]+)")


def test_destinations():
    result = {}
    for path in sorted((ROOT / "vpnd/tests").glob("test_*.py")):
        lines = path.read_text().splitlines()
        tree = ast.parse("\n".join(lines))
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) or not node.name.startswith("test_"):
                continue
            begin = min([node.lineno] + [dec.lineno for dec in node.decorator_list])
            comments = lines[begin-1:node.lineno-1]
            index = begin - 2
            while index >= 0 and (
                lines[index].strip().startswith("#") or not lines[index].strip()
            ):
                comments.append(lines[index])
                index -= 1
            for identity in ANNOTATION.findall("\n".join(comments)):
                relative = path.relative_to(ROOT).as_posix()
                result.setdefault(identity, []).append(relative + "::" + node.name)
    return result


def source_cases():
    inventory = ROOT / "vpnd/test-inventory.md"
    return {
        path + "::" + name
        for path, name in re.findall(
            r"^\| `(vpnd/[^`]+\.rs)` \| \d+ \| `([A-Za-z0-9_]+)` \|$",
            inventory.read_text(),
            re.MULTILINE,
        )
    }


def check(results):
    manifest = json.loads((ROOT / "vpnd/test-transfer.json").read_text())
    if set(manifest["cases"]) != source_cases():
        raise ValueError("baseline test inventory and transfer manifest differ")
    destinations = test_destinations()
    if manifest["cases"] != destinations:
        raise ValueError("transfer manifest and real annotated pytest functions differ")
    if not destinations:
        raise ValueError("empty transfer is not parity")
    evidence = json.loads(results.read_text())
    spec = importlib.util.spec_from_file_location(
        "vpnd_test_evidence", ROOT / "vpnd/tests/conftest.py"
    )
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    if evidence["fingerprint"] != plugin.fingerprint() or evidence["exitstatus"] != 0:
        raise ValueError("test evidence is stale or the complete suite failed")
    for identity, nodes in destinations.items():
        for node in nodes:
            cases = [
                phases
                for key, phases in evidence["cases"].items()
                if key == node or key.startswith(node + "[")
            ]
            if not cases or any(
                phases != {"setup": "passed", "call": "passed", "teardown": "passed"}
                for phases in cases
            ):
                raise ValueError("unexecuted, skipped or failing transfer: " + identity)
    print(
        f"Complete transfer: {len(destinations)} baseline functions, all mapped cases passed"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "vpnd/test-results.json")
    args = parser.parse_args()
    try:
        check(args.results)
    except (OSError, ValueError, KeyError) as error:
        print("Test transfer rejected: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
