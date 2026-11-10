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
    "gitleaks", "actionlint", "zizmor", "task-contract", "shellcheck",
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
    "engine": {"engine-interop"},
}
# Edges name downstream consumers, not upstream prerequisites. Selecting Ansible
# includes every role and both full-stack scenarios: role cross-imports and
# shared inventory make narrower per-role selection unsafe without another graph.
CONSUMERS = {
    "ansible": {"native", "images"},
    "terraform": {"native"},
    "pins": {"ansible", "python-vpnd", "engine"},
    "contract": {"ansible", "python-vpnd", "engine"},
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
    # Agent instructions and skills; the common pytest and task-contract checks read them.
    (".agents/", set()),
    (".claude/", set()),
    (".github/skills/", set()),
)
COMMON_ONLY = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE", "AGENTS.md", "CLAUDE.md"}
NATIVE_TEST_INPUTS = {"tests/conftest.py", "tests/pytest-durations.json.gz"}
# Folder notes are read only by the common pytest checks; docs/ notes ship with vpnd.
INSTRUCTION_NAMES = {"AGENTS.md", "CLAUDE.md"}
ALL_CHECKS = ALWAYS | set().union(*CHECKS.values())
# Job names of each selectable check as the Actions API reports them; a matrix or
# reusable workflow appends its own part. Used only to reuse a selective PR run.
JOB_NAMES = {
    "ansible": "ansible-lint + syntax-check", "molecule": "molecule (",
    "molecule-full-stack": "molecule full-stack (", "molecule-failure-scenarios": "molecule failure (",
    "terraform": "terraform fmt + validate (", "terraform-exception": "terraform inert exception root",
    "tf-test": "terraform test (", "tf-policy": "tf-policy / ", "cloud-init": "cloud-init schema",
    "vpnd-test": "vpnd-test / ", "vpnd-lint": "vpnd-lint / ", "vpnd-package": "vpnd-package / ",
    "vpnd-dependency": "vpnd-dependency / ", "vpnd-sbom": "vpnd release SBOM",
    "native-runtime": "native runtime integration (",
    "transport-runtime-acceptance": "native transport runtime acceptance (",
    "transport-native-acceptance": "native four-transport acceptance (",
    "go-helper": "MTProxy Go helper tests", "bats-test": "bats shell tests",
    "image-scan": "image-scan / ", "reproducible-build": "reproducible-build / ",
    "contract-sync": "contract-sync / ", "engine-interop": "engine-interop / ",
}


# Mentions in these paths are prose, data or stubs, never a CI consumer of a script.
MENTION_INERT = ("docs/", "openspec/", ".agents/", ".claude/", "tests/snapshot/", "tests/fixtures/", "tests/stubs/")
TOKEN = re.compile(r"[\w-]+(?:\.[\w-]+)*")
IMPORT = re.compile(r"\b(?:import|from)[ \t]+\.*([A-Za-z_][\w., \t]*)")
MAKE_CALL = re.compile(r"\bmake\b|\$\(MAKE\)")
MAKE_RULE = re.compile(r"^([A-Za-z0-9_.%-]+(?:[ \t]+[A-Za-z0-9_.%-]+)*)[ \t]*:(?!=)(.*)")
MAKE_VARIABLE = re.compile(r"^(?:(?:override|export)[ \t]+)*([A-Za-z0-9_.-]+)[ \t]*(?:[?:+]|::)?=")


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


def words(text):
    """Return every name-like token of text, and the dot-separated parts of each."""
    found = set()
    for token in TOKEN.findall(text):
        found.add(token)
        found.update(token.split("."))
    return found


def script_graph(repo):
    """Return consumers(path) for one scripts/ path of a pull request.

    consumers gives (components, checks) that run the script, or None when a
    consumer is unknown and full CI is required. A consumer is any tracked file
    that names the script's file name, or imports it as a Python module.
    Scripts, composite actions and reusable workflows pass the dependency on.
    A Makefile rule passes it to its dependents and to every
    line that runs make with its target; a Makefile variable passes it to the
    rules that use it. The always-run checks cover scripts/tests/ and portable
    unit tests. The match is textual, so a name that is built at run time is
    invisible: main pushes do not use this graph and run what a PR skipped.
    """
    root = Path(repo)
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=repo, check=True, capture_output=True,
                             text=True, timeout=60).stdout.split("\0")
    portable = portable_unit_tests(repo)
    files, jobs, targets, variables, make_global = {}, {}, {}, {}, set()

    def make_words(lines):
        # A comment that says "make" is prose, not a command.
        return words("\n".join(line for line in lines
                                if MAKE_CALL.search(line) and not line.lstrip().startswith("#")))

    for path in tracked:
        if not path or path.endswith(".md") or path.startswith(MENTION_INERT):
            continue
        # Root configuration and repository settings name scripts only in comments or local hooks.
        if path != "Makefile" and ("/" not in path or (
                path.startswith(".github/") and not path.startswith((".github/workflows/", ".github/actions/")))):
            continue
        try:
            lines = (root / path).read_text(errors="replace").split("\n")
        except OSError:
            continue  # deleted in the working tree, or a directory symlink
        if path == "Makefile":
            rules, define = [], False
            for line in lines:
                if define or line.startswith("define "):
                    define = not line.startswith("endef")
                    make_global.update(words(line))
                elif line.startswith("\t") and rules:
                    for rule in rules:
                        rule[0].update(words(line))
                        if MAKE_CALL.search(line):
                            rule[1].update(words(line))
                elif line.startswith("#"):
                    continue
                elif (found := MAKE_RULE.match(line)) and not line.startswith(".PHONY"):
                    rules = [targets.setdefault(name, (set(), set())) for name in found.group(1).split()]
                    for rule in rules:
                        # The rest of the line holds prerequisites, a target variable or an inline recipe.
                        rule[0].update(words(found.group(2)))
                        rule[1].update(words(found.group(2)))
                elif found := MAKE_VARIABLE.match(line):
                    rules = []  # a tab-indented continuation of this value is not a recipe
                    variables.setdefault(found.group(1), set()).update(words(line))
                else:
                    make_global.update(words(line))
        elif path == ".github/workflows/ci.yml":
            head, _, body = "\n".join(lines).partition("\njobs:\n")
            parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):[ \t]*(?:#.*)?\n", body)
            jobs[""] = (words(head + parts[0]), set())
            for name, chunk in zip(parts[1::2], parts[2::2]):
                jobs[name] = (words(chunk), make_words(chunk.split("\n")))
        else:
            text = "\n".join(lines)
            files[path] = (words(text), make_words(lines), words(" ".join(IMPORT.findall(text))))

    def consumers(changed):
        components, checks, pending, seen = set(), set(), [("file", changed)], set()

        def consume(job=None, path=None):
            """Record one consumer; False means it is unknown."""
            if job is not None:
                if job in ALL_CHECKS - ALWAYS:
                    checks.add(job)
                return job in ALL_CHECKS
            if path.startswith("scripts/tests/"):
                return True
            if path.startswith(("scripts/", ".github/")):
                pending.append(("file", path))
            elif path.startswith("tests/unit/"):
                if path not in portable:
                    components.add("native")
            elif path.startswith("tests/") and path.count("/") == 1:
                components.add("native")  # shared helpers that native suites import
            else:
                for prefix, found in PATHS:
                    if path.startswith(prefix):
                        components.update(found)
                        return True
                return False
            return True

        while pending:
            kind, item = entry = pending.pop()
            if entry in seen:
                continue
            seen.add(entry)
            if kind == "file":
                name = Path(item).parent.name if item.startswith(".github/actions/") else Path(item).name
                # Only an identifier can be imported; a package is imported by its directory name.
                module = Path(item).parent.name if name == "__init__.py" else (
                    Path(name).stem if re.fullmatch(r"[A-Za-z_]\w*\.py", name) else None)
                if name in make_global:
                    return None
                pending += [("variable", other) for other, found in variables.items() if name in found]
                pending += [("target", other) for other, (found, _) in targets.items() if name in found]
                for job, (found, _) in jobs.items():
                    if name in found and not consume(job=job):
                        return None
                for path, (found, _, imports) in files.items():
                    if path != item and (name in found or module in imports):
                        if not consume(path=path):
                            return None
            elif kind == "variable":
                if item in make_global:
                    return None
                pending += [("variable", other) for other, found in variables.items() if item in found]
                pending += [("target", other) for other, (found, _) in targets.items() if item in found]
            else:
                components.add("python-vpnd")  # vpnd runs Make targets by name
                pending += [("target", other) for other, (_, found) in targets.items() if item in found]
                for job, (_, found) in jobs.items():
                    if item in found and not consume(job=job):
                        return None
                for path, (_, found, _) in files.items():
                    if item in found and not path.startswith("vpnd/") and not consume(path=path):
                        return None
        return components, checks

    return consumers


def plan(paths, portable_tests=frozenset(), script_consumers=None):
    """Map all changed paths, including deleted names, to transitive consumers.

    portable_tests lists tests/unit modules that only the always-run portable
    pytest groups execute; every other tests/unit path selects native lanes.
    script_consumers is script_graph's result; without it a script needs full CI.
    """
    if not paths:
        return full_plan("Empty diff cannot authorize selective checks", 0)
    components, checks = set(), set()
    for path in paths:
        if path == 'tools/engine-interop.json':
            components.add('engine')
            continue
        if path in COMMON_ONLY or path in portable_tests:
            continue
        if Path(path).name in INSTRUCTION_NAMES and not path.startswith("docs/"):
            continue
        if path in NATIVE_TEST_INPUTS:
            components.add("native")
            continue
        if script_consumers and path.startswith("scripts/") and not path.startswith("scripts/tests/"):
            found = script_consumers(path)
            if found is None:
                return full_plan("A changed script has an unknown consumer", len(paths))
            components.update(found[0])
            checks.update(found[1])
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
    selected = ALWAYS | checks | set().union(*(CHECKS[component] for component in components))
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
    """Reuse a successful PR run when main received exactly its tested tree.

    The pushed tree must equal the PR head tree, and the previous main tip must
    be an ancestor of that head. A full run is reused as is. After a selective
    run the push repeats every check that its own diff selects, unless that
    check has jobs in the run and all of them succeeded. The push diff is
    planned without the script graph and with native lanes, so main runs what
    the PR skipped. Anything else returns None and keeps full CI.
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
        if not listed or total != len(listed):
            continue
        # A full plan runs every job; one skipped job means the PR used a selection.
        covered, missing = all(job.get("conclusion") == "success" for job in listed), set()
        if not covered and all(job.get("conclusion") in {"success", "skipped"} for job in listed):
            try:
                portable = portable_unit_tests(repo)
            except OSError:
                portable = frozenset()
            changed = git("diff", "--name-only", "--no-renames", "-z", f"{sha}^", sha, "--")
            needed = plan([path for path in changed.split("\0") if path], portable)["checks"]
            results = {name: {job.get("conclusion") for job in listed
                              if str(job.get("name", "")).startswith(prefix)}
                       for name, prefix in JOB_NAMES.items()}
            missing = {name for name, on in needed.items()
                       if on and name not in ALWAYS and results[name] != {"success"}}
            covered = missing != ALL_CHECKS - ALWAYS  # otherwise the run covered nothing
        if covered:
            return {
                "mode": "reused", "reason": f"Main tree matches successful PR CI run {run['id']}",
                "changed_files": None, "components": [],
                "checks": {name: name in ALWAYS | missing for name in sorted(ALL_CHECKS)},
            }
    return None


def plan_from_git(repo, event, base, sha="", api=None):
    result = event_plan(repo, event, base, sha, api)
    if event == "pull_request":
        # Native lanes run on main only: the push after the merge repeats them.
        result["checks"].update(dict.fromkeys(CHECKS["native"], False))
        result["reason"] += "; native lanes run on the main push"
    return result


def event_plan(repo, event, base, sha, api):
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
    paths = [os.fsdecode(path) for path in changed.split(b"\0") if path]
    consumers = None
    if any(path.startswith("scripts/") for path in paths):
        try:
            consumers = script_graph(repo)
        except (OSError, ValueError, subprocess.SubprocessError):
            consumers = None  # scripts then keep full CI
    return plan(paths, portable, consumers)


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
