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
spec = importlib.util.spec_from_file_location("ci_selection", ROOT / "scripts/select-ci-checks.py")
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)
JOBS = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]


@pytest.mark.parametrize("path,selected,unselected", [
    ("docs/tasks/issues/example.md", {"vpnd-test", "vpnd-clippy", "vpnd-sbom"}, {"molecule", "tf-test", "go-helper"}),
    ("vpnd/src/main.rs", {"vpnd-test", "vpnd-deny", "vpnd-msrv"}, {"ansible", "tf-policy"}),
    ("ansible/roles/xray/tasks/main.yml", {"ansible", "molecule", "molecule-full-stack", "molecule-failure-scenarios", "native-runtime", "image-scan"}, {"vpnd-test", "tf-test"}),
    ("terraform/shared/cloud-init.yaml.tftpl", {"terraform", "tf-test", "tf-policy", "cloud-init", "native-runtime"}, {"molecule", "vpnd-test"}),
    ("tools/probe-matrix-mtproto/main.go", {"go-helper"}, {"molecule", "vpnd-test", "terraform"}),
    ("contract/bundle-schema.json", {"contract-sync", "molecule", "vpnd-test"}, {"terraform"}),
    ("secrets/prod.secrets.example.yaml", {"reproducible-build", "molecule", "native-runtime", "vpnd-test"}, {"go-helper"}),
    ("tests/unit/test_example.py", {"native-runtime"}, {"molecule", "vpnd-test", "tf-test"}),
    ("tests/bats/example.bats", {"bats-test"}, {"molecule", "vpnd-test"}),
    ("images/debian13/Dockerfile", {"molecule", "image-scan"}, {"vpnd-test", "terraform"}),
    ("README.md", set(), {"molecule", "vpnd-test", "terraform", "go-helper"}),
])
def test_transitive_consumers_are_selected(path, selected, unselected):
    checks = selection.plan([path])["checks"]
    assert all(checks[name] for name in selected)
    assert all(not checks[name] for name in unselected)
    assert all(checks[name] for name in selection.ALWAYS)


@pytest.mark.parametrize("path", [
    "scripts/decrypt-secrets.sh", "tests/fixtures/secrets-sample.yml",
    ".github/workflows/ci.yml", ".github/actions/setup-ci-python/action.yml",
    "Makefile", "requirements.txt", "requirements.yml", "mise.toml",
    "new-unmapped-component/source.py",
])
def test_shared_and_unknown_paths_force_every_check(path):
    assert all(selection.plan([path])["checks"].values())


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


@pytest.mark.parametrize("event,base", [
    ("push", "HEAD"), ("workflow_dispatch", "HEAD"),
    ("pull_request", ""), ("pull_request", "0" * 40),
    ("pull_request", "f" * 40), ("pull_request", "--help"),
])
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
    assert all(selection.plan_from_git(repo, "pull_request", unrelated)["checks"].values())


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
        **{name: {"result": "success" if selected else "skipped"} for name, selected in checks.items()},
    }


def run_gate(needs):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-ci-results.py")],
        env={**os.environ, "NEEDS": json.dumps(needs)}, capture_output=True, text=True, timeout=10,
    )


@pytest.mark.parametrize("paths", [[".github/workflows/ci.yml"], ["docs/example.md"], ["ansible/roles/xray/tasks/main.yml"]])
def test_gate_accepts_success_and_only_planned_skips(paths):
    result = run_gate(needs_for(paths))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped"])
def test_any_selected_failure_cancellation_or_unexpected_skip_blocks_merge(outcome):
    for name in JOBS["required"]["needs"]:
        needs = needs_for([".github/workflows/ci.yml"])
        needs[name]["result"] = outcome
        assert run_gate(needs).returncode != 0, name


@pytest.mark.parametrize("mutation", [
    "missing-selector", "failed-selector", "invalid-json", "missing-plan-job",
    "extra-plan-job", "non-boolean", "missing-result", "unselected-failure", "unexpected-success",
])
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
        assert JOBS[name]["if"] == "${{ fromJSON(needs.selection.outputs.checks)['" + name + "'] }}"
        assert "continue-on-error" not in JOBS[name]
    assert JOBS["required"]["if"] == "always()"
    gate = JOBS["required"]["steps"][-1]
    assert gate["env"]["NEEDS"] == "${{ toJSON(needs) }}"
    assert gate["run"] == "python3 scripts/check-ci-results.py"


def test_selector_cli_writes_machine_outputs_and_explains_the_plan(repo, tmp_path):
    output = tmp_path / "github-output"
    summary = tmp_path / "github-summary"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/select-ci-checks.py")], cwd=repo,
        env={**os.environ, "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    checks = json.loads(output.read_text().split("checks=", 1)[1])
    assert all(checks.values())
    assert "Full CI" in summary.read_text()
