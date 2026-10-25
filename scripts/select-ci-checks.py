#!/usr/bin/env python3
"""Select complete CI consumer groups; uncertain inputs always request full CI."""

import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request


# These checks inspect the whole repository, including executable documentation
# and test contracts. Do not infer individual pytest dependencies from filenames.
ALWAYS = {
    "pr-title", "gitleaks", "actionlint", "zizmor", "task-contract", "shellcheck",
    "python-validators", "unit-tests", "pytest-required",
}
CHECKS = {
    "ansible": {"ansible", "molecule", "molecule-full-stack", "molecule-failure-scenarios"},
    "terraform": {"terraform", "terraform-exception", "tf-test", "tf-policy", "cloud-init"},
    "python-vpnd": {"vpnd-test", "vpnd-lint", "vpnd-package", "vpnd-dependency", "vpnd-sbom"},
    "native": {"native-runtime", "transport-runtime-acceptance", "transport-native-acceptance"},
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
    "pins": {"ansible", "python-vpnd"},
    "contract": {"ansible", "python-vpnd"},
}
PATHS = (
    ("docs/", {"python-vpnd"}),  # vpnd packages the entire tracked Markdown directory.
    ("vpnd/", {"python-vpnd"}),
    ("ansible/", {"ansible"}),
    ("terraform/", {"terraform"}),
    ("secrets/", {"pins"}),
    ("contract/", {"contract"}),
    ("images/", {"ansible"}),
    ("tools/probe-matrix-mtproto/", {"go"}),
    ("tests/unit/", {"native"}),  # This directory also contains native tests.
    ("tests/bats/", {"shell"}),
    ("tests/snapshot/", {"ansible"}),
    ("tests/native/", {"native"}),
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


def portable_unit_tests(repo):
    """Return top-level tests/unit modules that no native lane selects, names or imports.

    A module is native-reachable when its name contains "native", it mentions
    the native_runtime marker, the Makefile names it, or its module name appears
    in another native-reachable test file, a native or integration helper, a
    script or a CI definition. The closure is textual and deliberately broad: a
    false positive only selects more CI. Native collection still imports every
    tests/unit module before deselection, so a portable module must not change
    process state at import time; its import errors fail the portable groups.
    """
    root = Path(repo)
    units = {path.relative_to(root).as_posix(): path.read_text(errors="replace")
             for path in sorted((root / "tests/unit").glob("*.py"))}
    makefile = (root / "Makefile").read_text(errors="replace")
    # Only test_*.py modules can be portable; conftest or package files load for every test.
    reachable = {path for path, text in units.items()
                 if not Path(path).name.startswith("test_") or "native" in Path(path).name
                 or "native_runtime" in text or Path(path).name in makefile}
    texts = [units[path] for path in reachable]
    # Other consumers that can name a test module: native suites, integration
    # helpers, scripts and CI definitions.
    for directory in ("tests/native", "tests/integration", "scripts", ".github"):
        texts += [path.read_text(errors="replace") for path in sorted((root / directory).rglob("*"))
                  if path.is_file() and path.suffix in {".py", ".sh", ".yml", ".yaml", ".json", ".j2"}]
    while texts:
        text = texts.pop()
        for path in set(units) - reachable:
            if re.search(rf"\b{re.escape(Path(path).stem)}\b", text):
                reachable.add(path)
                texts.append(units[path])
    return frozenset(set(units) - reachable)


def plan(paths, portable_tests=frozenset()):
    """Map all changed paths, including deleted names, to transitive consumers.

    portable_tests lists tests/unit modules that only the always-run portable
    pytest groups execute; every other tests/unit path selects native lanes.
    """
    if not paths:
        return full_plan("Empty diff cannot authorize selective checks", 0)
    components = set()
    for path in paths:
        if path in COMMON_ONLY or path in portable_tests:
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


def github_api(path):
    """GET one GitHub REST resource of this repository with the job token."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def reused_plan(repo, sha, api):
    """Reuse a full successful PR run when main received exactly its tested tree.

    The pushed tree must equal the PR head tree, and the previous main tip must
    be an ancestor of that head. Anything else returns None and keeps full CI.
    """
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        return None
    pulls = [pull for pull in api(f"commits/{sha}/pulls")
             if pull.get("merged_at") and pull.get("merge_commit_sha") == sha
             and pull.get("base", {}).get("ref") == "main"]
    if len(pulls) != 1:
        return None
    head = pulls[0]["head"]["sha"]
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        return None

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                              text=True, timeout=60).stdout.strip()

    if subprocess.run(["git", "cat-file", "-e", f"{head}^{{commit}}"], cwd=repo,
                      capture_output=True, timeout=30).returncode != 0:
        git("fetch", "--no-tags", "--quiet", "origin", head)
    # The PR run tested head merged with the main of its time. When the previous
    # main tip is already in head, every such merge has head's tree, whatever the
    # branch protection settings are.
    git("merge-base", "--is-ancestor", f"{sha}^", head)
    if git("rev-parse", f"{head}^{{tree}}") != git("rev-parse", f"{sha}^{{tree}}"):
        return None
    runs = api(f"actions/workflows/ci.yml/runs?event=pull_request&head_sha={head}&status=success&per_page=20")
    for run in runs.get("workflow_runs", []):
        if run.get("head_sha") != head or run.get("conclusion") != "success":
            continue
        listed, total = [], None
        for page in range(1, 6):
            jobs = api(f"actions/runs/{run['id']}/jobs?filter=latest&per_page=100&page={page}")
            total = jobs.get("total_count")
            listed += jobs.get("jobs", [])
            if not jobs.get("jobs") or len(listed) >= (total or 0):
                break
        # A full plan runs every job; one skipped job means the PR used a selection.
        if listed and total == len(listed) and all(
                job.get("conclusion") == "success" for job in listed):
            return {
                "mode": "reused", "reason": f"Main tree matches full successful PR CI run {run['id']}",
                "changed_files": None, "components": [],
                "checks": {name: name in ALWAYS for name in sorted(ALL_CHECKS)},
            }
    return None


def plan_from_git(repo, event, base, sha="", api=None):
    if event == "push" and api is not None:
        try:
            reused = reused_plan(repo, sha, api)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException,
                subprocess.SubprocessError):
            reused = None  # An API, network or history failure keeps full CI.
        if reused:
            return reused
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
    try:
        # The working tree is the tested merge commit; a deleted path is absent
        # from it and therefore keeps its native consumers.
        portable = portable_unit_tests(repo)
    except OSError:
        portable = frozenset()
    # NUL delimiters preserve whitespace/newlines. --no-renames includes both
    # old and new paths, so moving a file cannot lose its previous consumers.
    return plan([os.fsdecode(path) for path in changed.split(b"\0") if path], portable)


def main():
    api = github_api if os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY") else None
    result = plan_from_git(Path.cwd(), os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("PR_BASE_SHA", ""),
                           os.environ.get("GITHUB_SHA", ""), api)
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
