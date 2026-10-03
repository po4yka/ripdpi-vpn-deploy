"""Checkout discovery must reflect real Git state without altering it."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/workspace-status.py"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, value):
    (repo / "tracked.txt").write_text(value)
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", value)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "checkout with spaces"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Regression")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "core.hooksPath", str(tmp_path / "empty-hooks"))
    git(path, "update-ref", "refs/remotes/origin/main", commit(path, "initial"))
    git(path, "remote", "add", "origin", "https://example.invalid/no-network")
    return path


def run(repo, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=repo, capture_output=True, text=True)


@pytest.mark.parametrize("relation,expected", [
    ("equal", (0, 0)), ("ahead", (1, 0)), ("behind", (0, 1)), ("diverged", (1, 1)),
])
def test_known_main_divergence(repo, relation, expected):
    initial = git(repo, "rev-parse", "HEAD")
    if relation == "ahead":
        commit(repo, "local")
    elif relation in {"behind", "diverged"}:
        git(repo, "switch", "-c", "other")
        git(repo, "update-ref", "refs/remotes/origin/main", commit(repo, "remote"))
        git(repo, "switch", "main")
        assert git(repo, "rev-parse", "HEAD") == initial
        if relation == "diverged":
            commit(repo, "local")
    before = hashlib.sha256((repo / ".git/index").read_bytes()).digest()
    result = run(repo, "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["head"] == git(repo, "rev-parse", "HEAD")
    assert report["branch"] == "main"
    assert (report["known_main"]["ahead"], report["known_main"]["behind"]) == expected
    assert report["changes"] == {"staged": 0, "unstaged": 0, "untracked": 0}
    assert hashlib.sha256((repo / ".git/index").read_bytes()).digest() == before


def test_dirty_counts_handle_rename_and_do_not_print_private_paths_or_contents(repo):
    git(repo, "mv", "tracked.txt", "renamed.txt")
    (repo / "renamed.txt").write_text("unstaged edit")
    (repo / "private\nname.txt").write_text("private content sentinel")
    result = run(repo, "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["changes"] == {"staged": 1, "unstaged": 1, "untracked": 1}
    assert "private content sentinel" not in result.stdout + result.stderr
    assert "name.txt" not in result.stdout + result.stderr


def test_configured_fsmonitor_cannot_mutate_checkout(repo, tmp_path):
    hook = tmp_path / "fsmonitor-hook.sh"
    hook.write_text("#!/bin/sh\n: > \"$PWD/fsmonitor-side-effect\"\nprintf 'token\\0/\\0'\n")
    hook.chmod(0o755)
    git(repo, "config", "core.fsmonitor", str(hook))
    marker = repo / "fsmonitor-side-effect"
    git(repo, "status", "--porcelain=v1")
    assert marker.exists(), "control query must exercise the configured hook"
    marker.unlink()
    before = hashlib.sha256((repo / ".git/index").read_bytes()).digest()
    result = run(repo, "--json")
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert json.loads(result.stdout)["changes"] == {"staged": 0, "unstaged": 0, "untracked": 0}
    assert hashlib.sha256((repo / ".git/index").read_bytes()).digest() == before


def test_detached_linked_worktree_and_nested_cwd(repo, tmp_path):
    linked = tmp_path / "linked checkout"
    git(repo, "worktree", "add", "--detach", str(linked), "HEAD")
    nested = linked / "nested"
    nested.mkdir()
    result = run(nested, "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["branch"] is None
    assert report["cwd"] == str(nested.resolve())
    assert report["worktree"] == str(linked.resolve())
    assert report["head"] == git(linked, "rev-parse", "HEAD")
    assert "(detached HEAD)" in run(nested).stdout


def test_inherited_git_overrides_cannot_redirect_checkout_or_index(repo, tmp_path, monkeypatch):
    linked = tmp_path / "selected checkout"
    git(repo, "worktree", "add", "--detach", str(linked), "HEAD")
    selected_head = commit(linked, "selected")
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_COMMON_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))
    monkeypatch.setenv("GIT_INDEX_FILE", str(repo / ".git/index"))
    result = run(linked, "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["worktree"] == str(linked.resolve())
    assert report["head"] == selected_head
    assert report["branch"] is None
    assert report["known_main"]["ahead"] == 1
    assert report["changes"] == {"staged": 0, "unstaged": 0, "untracked": 0}


def test_missing_known_main_is_explicit(repo):
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    report = json.loads(run(repo, "--json").stdout)
    assert report["known_main"] == {"ref": "origin/main", "revision": None, "ahead": None, "behind": None}
    assert "(unavailable) (local; no fetch)" in run(repo).stdout


def test_shallow_history_does_not_claim_exact_divergence(repo, tmp_path):
    commit(repo, "later")
    shallow = tmp_path / "shallow checkout"
    subprocess.run(["git", "clone", "--depth=1", repo.as_uri(), str(shallow)], check=True, capture_output=True)
    report = json.loads(run(shallow, "--json").stdout)
    assert report["shallow"] is True
    assert report["known_main"]["revision"] == git(repo, "rev-parse", "HEAD")
    assert report["known_main"]["ahead"] is None
    assert report["known_main"]["behind"] is None
    assert "divergence: unavailable (shallow history)" in run(shallow).stdout


def test_non_checkout_fails_without_raw_git_diagnostics(tmp_path):
    result = run(tmp_path, "--json")
    assert result.returncode == 2
    assert not result.stdout
    assert result.stderr == "workspace-status: checkout or selected task metadata unavailable\n"


def test_make_discovery_bypasses_fleet_configuration_and_provider_values(repo):
    shutil.copy(ROOT / "Makefile", repo / "Makefile")
    (repo / "scripts").mkdir()
    shutil.copy(SCRIPT, repo / "scripts/workspace-status.py")
    (repo / ".fleet.mk").write_text("$(error operator configuration must not be parsed)\n")
    marker = repo / "unexpected-provider-effect"
    result = subprocess.run(
        ["make", "workspace-status", f"PROVIDER=$(shell touch {marker})"], cwd=repo,
        capture_output=True, text=True, env={**os.environ, "PATH": os.environ["PATH"]},
    )
    assert result.returncode == 0, result.stderr
    assert "known main: origin/main" in result.stdout
    assert "(local; no fetch)" in result.stdout
    assert not marker.exists()


def test_task_pointers_use_real_taskctl(monkeypatch, repo):
    portfolio = json.loads(subprocess.run(
        [str(ROOT / "taskctl"), "list", "--json"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout)
    selected = next(task for task in portfolio["tasks"] if task["spec_mode"] == "required")
    expected = json.loads(subprocess.run(
        [str(ROOT / "taskctl"), "show", "--json", selected["id"]], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout)
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))
    result = run(ROOT, "--task", selected["id"], "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["task"] == {
        "id": selected["id"], "status": selected["status"], "portfolio": expected["path"],
        "execution": expected["execution"], "change": selected["openspec_change"],
    }


def test_bad_selected_task_fails_without_dumping_portfolio():
    result = run(ROOT, "--task", "missing-task", "--json")
    assert result.returncode == 2
    assert not result.stdout
    assert result.stderr == "workspace-status: checkout or selected task metadata unavailable\n"
