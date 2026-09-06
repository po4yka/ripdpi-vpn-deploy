#!/usr/bin/env python3
"""Select complete CI consumer groups; uncertain inputs always request full CI."""

import json
import os
from pathlib import Path
import re
import subprocess


# These checks inspect the whole repository, including executable documentation
# and test contracts. Do not infer individual pytest dependencies from filenames.
ALWAYS = {
    "gitleaks", "actionlint", "zizmor", "task-contract", "shellcheck",
    "python-validators", "unit-tests", "pytest-required",
}
CHECKS = {
    "ansible": {"ansible", "molecule", "molecule-full-stack", "molecule-failure-scenarios"},
    "terraform": {"terraform", "terraform-exception", "tf-test", "tf-policy", "cloud-init"},
    "rust": {"vpnd-test", "vpnd-clippy", "vpnd-msrv", "vpnd-deny", "vpnd-sbom"},
    "native": {"native-runtime"},
    "go": {"go-helper"},
    "shell": {"bats-test"},
    "images": {"image-scan"},
    "pins": {"reproducible-build"},
    "contract": {"contract-sync"},
}
# Edges name downstream consumers, not upstream prerequisites. Selecting Ansible
# includes every role and both full-stack scenarios: role cross-imports and
# shared inventory make narrower per-role selection unsafe without another graph.
CONSUMERS = {
    "ansible": {"native", "images"},
    "terraform": {"native"},
    "pins": {"ansible", "rust"},
    "contract": {"ansible", "rust"},
}
PATHS = (
    ("docs/", {"rust"}),  # vpnd/src/docs_bundle.rs embeds the entire directory.
    ("vpnd/", {"rust"}),
    ("ansible/", {"ansible"}),
    ("terraform/", {"terraform"}),
    ("secrets/", {"pins"}),
    ("contract/", {"contract"}),
    ("images/", {"ansible"}),
    ("tools/probe-matrix-mtproto/", {"go"}),
    ("tests/unit/", {"native"}),  # This directory also contains native tests.
    ("tests/bats/", {"shell"}),
    ("tests/snapshot/", {"ansible"}),
    ("tests/integration/", {"ansible", "native"}),
    ("scripts/tests/", set()),
    ("tools/tasking/", set()),
    ("openspec/", set()),
)
COMMON_ONLY = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE", "AGENTS.md", "CLAUDE.md"}
NATIVE_TEST_INPUTS = {"tests/conftest.py", "tests/pytest-durations.json.gz", "tests/CLAUDE.md", "tests/AGENTS.md"}
ALL_CHECKS = ALWAYS | set().union(*CHECKS.values())


def full_plan(reason, changed_files=None):
    return {
        "mode": "full", "reason": reason, "changed_files": changed_files,
        "components": sorted(CHECKS), "checks": dict.fromkeys(sorted(ALL_CHECKS), True),
    }


def plan(paths):
    """Map all changed paths, including deleted names, to transitive consumers."""
    if not paths:
        return full_plan("Empty diff cannot authorize selective checks", 0)
    components = set()
    for path in paths:
        if path in COMMON_ONLY:
            continue
        if path in NATIVE_TEST_INPUTS:
            components.add("native")
            continue
        for prefix, consumers in PATHS:
            if path.startswith(prefix):
                components.update(consumers)
                break
        else:
            # CI, Make/toolchain configuration, scripts and shared fixtures
            # intentionally have no narrow rule. New paths also fail closed.
            return full_plan("Shared or unmapped changed path", len(paths))
    pending = list(components)
    while pending:
        for consumer in CONSUMERS.get(pending.pop(), set()) - components:
            components.add(consumer)
            pending.append(consumer)
    selected = ALWAYS | set().union(*(CHECKS[component] for component in components))
    return {
        "mode": "selected", "reason": "Complete changed-file consumer groups",
        "changed_files": len(paths), "components": sorted(components),
        "checks": {name: name in selected for name in sorted(ALL_CHECKS)},
    }


def plan_from_git(repo, event, base):
    if event != "pull_request":
        return full_plan("Main pushes and manual runs execute full CI")
    if re.fullmatch(r"[0-9a-f]{40}", base) is None or base == "0" * 40:
        return full_plan("Missing or invalid PR base revision")
    try:
        # The checkout is GitHub's tested PR merge commit. Its base must be an
        # ancestor; otherwise selecting a subset could omit integration changes.
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=repo,
            check=True, capture_output=True, timeout=30,
        )
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "--no-renames", "-z", base, "HEAD", "--"],
            cwd=repo, stderr=subprocess.PIPE, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return full_plan("PR history unavailable or incompatible with the checkout")
    # NUL delimiters preserve whitespace/newlines. --no-renames includes both
    # old and new paths, so moving a file cannot lose its previous consumers.
    return plan([os.fsdecode(path) for path in changed.split(b"\0") if path])


def main():
    result = plan_from_git(Path.cwd(), os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("PR_BASE_SHA", ""))
    print(json.dumps(result, sort_keys=True))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("checks=" + json.dumps(result["checks"], separators=(",", ":")) + "\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            title = "Full CI" if result["mode"] == "full" else "CI dependency selection"
            count = result["changed_files"] if result["changed_files"] is not None else "not calculated"
            stream.write(f"## {title}\n\n{result['reason']}. Changed paths: {count}.\n\n")
            stream.write("| Check group | Decision |\n|---|---|\n")
            for name, selected in result["checks"].items():
                stream.write(f"| `{name}` | {'Run' if selected else 'Not affected'} |\n")


if __name__ == "__main__":
    main()
