"""Changed-file dependencies must never turn missing coverage into green CI."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "ci_selection", ROOT / "scripts/select-ci-checks.py"
)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)
JOBS = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]


@pytest.mark.parametrize(
    "path,selected,unselected",
    [
        (
            "docs/tasks/issues/example.md",
            {"vpnd-test", "vpnd-lint", "vpnd-sbom"},
            {"molecule", "tf-test", "go-helper"},
        ),
        (
            "vpnd/src/vpnd/__main__.py",
            {"vpnd-test", "vpnd-dependency", "vpnd-package"},
            {"ansible", "tf-policy"},
        ),
        (
            "ansible/roles/xray/tasks/enable.yml",
            {
                "ansible",
                "molecule",
                "molecule-full-stack",
                "molecule-failure-scenarios",
                "native-runtime",
                "transport-runtime-acceptance",
                "image-scan",
            },
            {"vpnd-test", "tf-test"},
        ),
        (
            "terraform/shared/cloud-init.yaml.tftpl",
            {"terraform", "tf-test", "tf-policy", "cloud-init", "native-runtime", "transport-runtime-acceptance"},
            {"molecule", "vpnd-test"},
        ),
        (
            "tools/probe-matrix-mtproto/main.go",
            {"go-helper"},
            {"molecule", "vpnd-test", "terraform"},
        ),
        (
            "contract/bundle-schema.json",
            {"contract-sync", "molecule", "vpnd-test"},
            {"terraform"},
        ),
        (
            "secrets/prod.secrets.example.yaml",
            {"reproducible-build", "molecule", "native-runtime", "transport-runtime-acceptance", "vpnd-test"},
            {"go-helper"},
        ),
        (
            "tests/unit/test_example.py",
            {"native-runtime", "transport-runtime-acceptance"},
            {"molecule", "vpnd-test", "tf-test"},
        ),
        ("tests/bats/example.bats", {"bats-test"}, {"molecule", "vpnd-test"}),
        (
            "images/debian13/Dockerfile",
            {"molecule", "image-scan"},
            {"vpnd-test", "terraform"},
        ),
        ("README.md", set(), {"molecule", "vpnd-test", "terraform", "go-helper"}),
    ],
)
def test_transitive_consumers_are_selected(path, selected, unselected):
    checks = selection.plan([path])["checks"]
    assert all(checks[name] for name in selected)
    assert all(not checks[name] for name in unselected)
    assert all(checks[name] for name in selection.ALWAYS)


@pytest.mark.parametrize(
    "path",
    [
        "scripts/decrypt-secrets.sh",
        "tests/fixtures/secrets-sample.yml",
        ".github/workflows/ci.yml",
        ".github/actions/setup-ci-python/action.yml",
        "Makefile",
        "requirements.txt",
        "requirements.yml",
        "mise.toml",
        "new-unmapped-component/source.py",
    ],
)
def test_shared_and_unknown_paths_force_every_check(path):
    assert all(selection.plan([path])["checks"].values())


@pytest.fixture(autouse=True)
def isolated_git_configuration(monkeypatch):
    # Only synthetic repositories in this module create commits or tags.
    for name in tuple(os.environ):
        if name.startswith("GIT_CONFIG_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def test_portable_unit_test_changes_skip_native_lanes_only_when_unreachable(tmp_path):
    units = tmp_path / "tests/unit"
    units.mkdir(parents=True)
    (tmp_path / "tests/native").mkdir()
    (tmp_path / "tests/native/runner.py").write_text("import test_runner_helper\n")
    (tmp_path / "Makefile").write_text("probe:\n\tpytest tests/unit/test_named_by_make.py\n")
    files = {
        "test_portable.py": "def test_ok():\n    pass\n",
        "test_marked.py": "import pytest\n@pytest.mark.native_runtime\ndef test_x():\n    pass\n",
        "test_lab_native.py": "from test_shared_helper import value\n",
        "test_shared_helper.py": "from test_transitive_helper import value\n",
        "test_transitive_helper.py": "value = 1\n",
        "test_runner_helper.py": "value = 2\n",
        "test_named_by_make.py": "def test_ok():\n    pass\n",
        "helper.py": "value = 3\n",
    }
    for name, text in files.items():
        (units / name).write_text(text)
    portable = selection.portable_unit_tests(tmp_path)
    assert portable == {"tests/unit/test_portable.py"}
    assert not selection.plan(["tests/unit/test_portable.py"], portable)["checks"]["native-runtime"]
    for name in [*files, "test_deleted.py", "fixtures/data.json"]:
        checks = selection.plan([f"tests/unit/{name}"], portable)["checks"]
        if name != "test_portable.py":
            assert checks["native-runtime"] and checks["transport-runtime-acceptance"], name
        assert checks["unit-tests"]
    # The live repository keeps Make-named and imported helpers native-reachable.
    live = selection.portable_unit_tests(ROOT)
    # Naming a module here would make it reachable through this file, so count instead.
    assert len(live) >= 100
    assert all("native_runtime" not in (ROOT / path).read_text() for path in live)
    assert "tests/unit/test_ci_dependency_selection.py" not in live  # It names the marker.
    assert "tests/unit/test_watchdog_templates.py" not in live
    assert "tests/unit/test_awg_device_binding.py" not in live


def test_pr_selection_skips_native_lanes_for_a_portable_test_edit(repo):
    (repo / "tests/unit").mkdir(parents=True)
    (repo / "tests/native").mkdir()
    (repo / "Makefile").write_text("all:\n")
    (repo / "tests/unit/test_portable.py").write_text("def test_ok():\n    pass\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "portable test")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "tests/unit/test_portable.py").write_text("def test_ok():\n    assert True\n")
    git(repo, "commit", "-qam", "edit portable test")
    result = selection.plan_from_git(repo, "pull_request", base)
    assert result["mode"] == "selected" and result["checks"]["unit-tests"]
    assert not result["checks"]["native-runtime"]


def test_an_unknown_path_after_300_files_cannot_be_truncated_away():
    paths = [f"docs/page-{i}.md" for i in range(350)] + ["unknown/input"]
    assert all(selection.plan(paths)["checks"].values())


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "CI test")
    (tmp_path / "ansible").mkdir()
    (tmp_path / "ansible/input.yml").write_text("original\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def test_git_range_covers_all_commits_renames_and_deleted_paths(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "vpnd").mkdir()
    git(repo, "mv", "ansible/input.yml", "vpnd/renamed file\nwith newline")
    git(repo, "commit", "-qm", "move between consumers")
    (repo / "README.md").write_text("second commit\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "docs")
    result = selection.plan_from_git(repo, "pull_request", base)
    assert result["changed_files"] == 3
    assert result["checks"]["molecule"] and result["checks"]["vpnd-test"]
    assert not result["checks"]["go-helper"]


@pytest.mark.parametrize(
    "event,base",
    [
        ("push", "HEAD"),
        ("workflow_dispatch", "HEAD"),
        ("pull_request", ""),
        ("pull_request", "0" * 40),
        ("pull_request", "f" * 40),
        ("pull_request", "--help"),
    ],
)
def test_full_run_when_event_or_history_cannot_authorize_selection(repo, event, base):
    assert all(selection.plan_from_git(repo, event, base)["checks"].values())


def test_empty_diff_and_nonancestor_base_force_full_run(repo):
    base = git(repo, "rev-parse", "HEAD")
    assert all(selection.plan_from_git(repo, "pull_request", base)["checks"].values())
    (repo / "README.md").write_text("other branch\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "other branch")
    unrelated = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "--detach", base)
    assert all(
        selection.plan_from_git(repo, "pull_request", unrelated)["checks"].values()
    )


def test_merge_checkout_compares_with_advanced_base_without_losing_pr_changes(repo):
    initial = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qb", "base")
    (repo / "terraform").mkdir()
    (repo / "terraform/base.tf").write_text("# base-only change\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "advance base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qb", "pr", initial)
    (repo / "docs").mkdir()
    (repo / "docs/guide.md").write_text("PR documentation\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "PR change")
    git(repo, "checkout", "base")
    git(repo, "merge", "--no-ff", "-qm", "test PR merge", "pr")
    result = selection.plan_from_git(repo, "pull_request", base)
    assert result["changed_files"] == 1
    assert result["checks"]["vpnd-test"]
    assert not result["checks"]["terraform"]


def needs_for(paths):
    checks = selection.plan(paths)["checks"]
    return {
        "selection": {"result": "success", "outputs": {"checks": json.dumps(checks)}},
        **{
            name: {"result": "success" if selected else "skipped"}
            for name, selected in checks.items()
        },
    }


def run_gate(needs):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-ci-results.py")],
        env={**os.environ, "NEEDS": json.dumps(needs)},
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "paths",
    [
        [".github/workflows/ci.yml"],
        ["docs/example.md"],
        ["ansible/roles/xray/tasks/enable.yml"],
    ],
)
def test_gate_accepts_success_and_only_planned_skips(paths):
    result = run_gate(needs_for(paths))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped"])
def test_any_selected_failure_cancellation_or_unexpected_skip_blocks_merge(outcome):
    for name in JOBS["required"]["needs"]:
        needs = needs_for([".github/workflows/ci.yml"])
        needs[name]["result"] = outcome
        assert run_gate(needs).returncode != 0, name


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-selector",
        "failed-selector",
        "invalid-json",
        "missing-plan-job",
        "extra-plan-job",
        "non-boolean",
        "missing-result",
        "unselected-failure",
        "unexpected-success",
    ],
)
def test_malformed_or_inconsistent_plan_never_passes(mutation):
    needs = needs_for(["docs/example.md"])
    checks = json.loads(needs["selection"]["outputs"]["checks"])
    if mutation == "missing-selector":
        del needs["selection"]
    elif mutation == "failed-selector":
        needs["selection"]["result"] = "failure"
    elif mutation == "invalid-json":
        needs["selection"]["outputs"]["checks"] = "{}garbage"
    elif mutation == "missing-plan-job":
        del checks["molecule"]
    elif mutation == "extra-plan-job":
        checks["ghost"] = False
    elif mutation == "non-boolean":
        checks["molecule"] = "false"
    elif mutation == "missing-result":
        del needs["molecule"]
    elif mutation == "unselected-failure":
        needs["molecule"]["result"] = "failure"
    elif mutation == "unexpected-success":
        needs["molecule"]["result"] = "success"
    if mutation in {"missing-plan-job", "extra-plan-job", "non-boolean"}:
        needs["selection"]["outputs"]["checks"] = json.dumps(checks)
    assert run_gate(needs).returncode != 0


def test_workflow_and_planner_cover_the_same_complete_graph():
    checks = selection.plan([".github/workflows/ci.yml"])["checks"]
    assert set(checks) == set(JOBS) - {"required", "selection"}
    assert set(JOBS["required"]["needs"]) == set(JOBS) - {"required"}
    for name in set(checks) - set(selection.ALWAYS):
        assert JOBS[name]["needs"] == "selection"
        assert (
            JOBS[name]["if"]
            == "${{ fromJSON(needs.selection.outputs.checks)['" + name + "'] }}"
        )
        assert "continue-on-error" not in JOBS[name]
    assert JOBS["required"]["if"] == "always()"
    gate = JOBS["required"]["steps"][-1]
    assert gate["env"]["NEEDS"] == "${{ toJSON(needs) }}"
    assert gate["run"] == "python3 scripts/check-ci-results.py"


def test_selector_cli_writes_machine_outputs_and_explains_the_plan(repo, tmp_path):
    output = tmp_path / "github-output"
    summary = tmp_path / "github-summary"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/select-ci-checks.py")],
        cwd=repo,
        env={
            **os.environ,
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    checks = json.loads(output.read_text().split("checks=", 1)[1])
    assert all(checks.values())
    assert "Full CI" in summary.read_text()


def merged_history(repo, shape="same"):
    """Create a PR head and the commit main received for it; return (pushed, head)."""
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qb", "pr")
    (repo / "pr.txt").write_text("pull request change\n")
    git(repo, "add", "pr.txt")
    git(repo, "commit", "-qm", "PR change")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "--detach", base)
    parent = base
    if shape == "stale":
        # Main advanced without the PR containing it: the run tested another tree.
        (repo / "main.txt").write_text("later main change\n")
        git(repo, "add", "main.txt")
        git(repo, "commit", "-qm", "advance main")
        parent = git(repo, "rev-parse", "HEAD")
    tree = git(repo, "rev-parse", f"{head}^{{tree}}")
    if shape == "tree":
        (repo / "pr.txt").write_text("different content\n")
        git(repo, "add", "pr.txt")
        tree = git(repo, "write-tree")
    pushed = git(repo, "commit-tree", tree, "-p", parent, "-m", "squash merge")
    return pushed, head


def fake_api(sha, head, pulls=None, pages=None, conclusion="success"):
    """Answer the GitHub REST reads with one merged PR and one full run by default."""
    default = {"total_count": 2, "jobs": [{"name": "a", "conclusion": "success"},
                                          {"name": "b", "conclusion": "success"}]}
    responses = {
        f"commits/{sha}/pulls": pulls if pulls is not None else [
            {"merged_at": "2026-10-24T00:00:00Z", "merge_commit_sha": sha,
             "base": {"ref": "main"}, "head": {"sha": head}}],
        f"actions/workflows/ci.yml/runs?event=pull_request&head_sha={head}&status=success&per_page=20":
            {"workflow_runs": [{"id": 7, "head_sha": head, "conclusion": conclusion}]},
    }
    for page, body in (pages or {1: default}).items():
        responses[f"actions/runs/7/jobs?filter=latest&per_page=100&page={page}"] = body
    return lambda path: responses[path]


def full_page(count, total):
    return {"total_count": total, "jobs": [{"name": f"job-{n}", "conclusion": "success"} for n in range(count)]}


@pytest.mark.parametrize("pages", [None, {1: full_page(100, 150), 2: full_page(50, 150)}])
def test_main_push_reuses_a_full_successful_run_of_the_identical_tree(repo, pages):
    sha, head = merged_history(repo)
    result = selection.plan_from_git(repo, "push", "", sha=sha, api=fake_api(sha, head, pages=pages))
    assert result["mode"] == "reused"
    assert {name for name, selected in result["checks"].items() if selected} == selection.ALWAYS
    assert run_gate({"selection": {"result": "success", "outputs": {"checks": json.dumps(result["checks"])}},
                     **{name: {"result": "success" if selected else "skipped"}
                        for name, selected in result["checks"].items()}}).returncode == 0


@pytest.mark.parametrize("case", ["tree", "stale", "no-pr", "two-prs", "unmerged", "other-base",
                                  "skipped-job", "failed-job", "partial-jobs", "no-run", "api-error",
                                  "http-error", "unknown-head", "bad-sha", "dispatch"])
def test_main_push_keeps_full_ci_when_reuse_is_uncertain(repo, case):
    import http.client
    shape = case if case in {"tree", "stale"} else "same"
    sha, head = merged_history(repo, shape)
    merged = {"merged_at": "2026-10-24T00:00:00Z", "merge_commit_sha": sha, "base": {"ref": "main"},
              "head": {"sha": head}}
    event, api = "push", fake_api(sha, head)
    if case == "no-pr":
        api = fake_api(sha, head, pulls=[])
    elif case == "two-prs":
        api = fake_api(sha, head, pulls=[merged, merged])
    elif case == "unmerged":
        api = fake_api(sha, head, pulls=[{**merged, "merged_at": None}])
    elif case == "other-base":
        api = fake_api(sha, head, pulls=[{**merged, "base": {"ref": "release"}}])
    elif case in {"skipped-job", "failed-job"}:
        outcome = "skipped" if case == "skipped-job" else "failure"
        api = fake_api(sha, head, pages={1: {"total_count": 2, "jobs": [
            {"name": "a", "conclusion": "success"}, {"name": "b", "conclusion": outcome}]}})
    elif case == "partial-jobs":
        api = fake_api(sha, head, pages={1: full_page(1, 120), 2: full_page(0, 120)})
    elif case == "no-run":
        api = fake_api(sha, head, conclusion="failure")
    elif case in {"api-error", "http-error"}:
        error = OSError("network unavailable") if case == "api-error" else http.client.IncompleteRead(b"")

        def api(path):
            raise error
    elif case == "unknown-head":
        # The PR head is neither local nor fetchable: this fixture has no origin remote.
        api = fake_api(sha, "f" * 40, pulls=[{**merged, "head": {"sha": "f" * 40}}])
    elif case == "bad-sha":
        sha = "HEAD"
    elif case == "dispatch":
        event = "workflow_dispatch"
    result = selection.plan_from_git(repo, event, "", sha=sha, api=api)
    assert result["mode"] == "full" and all(result["checks"].values())
