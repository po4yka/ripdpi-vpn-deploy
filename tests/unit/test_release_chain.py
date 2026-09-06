"""Exercise the automatic release handoff without publishing a release."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/release-please.yml").read_text())


def test_release_version_updates_include_the_locked_root_package():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    files = config["packages"]["."]["extra-files"]
    assert "vpnd/Cargo.toml" in files
    assert {
        "type": "toml", "path": "vpnd/Cargo.lock",
        "jsonpath": "$.package[?(@.name.value=='vpnd')].version",
    } in files


def test_release_automation_is_enabled_by_default_and_errors_are_fatal():
    release = workflow()["jobs"]["release"]
    assert release["if"] == "${{ github.ref == 'refs/heads/main' && vars.RELEASE_PLEASE_ENABLED != 'false' }}"
    action = next(step for step in release["steps"] if "release-please-action@" in step.get("uses", ""))
    assert not action.get("continue-on-error", False)
    assert not release.get("continue-on-error", False)
    for output in ("release_created", "tag_name", "sha"):
        assert release["outputs"][output] == "${{ steps.release.outputs." + output + " }}"
    assert action["id"] == "release"


def test_handoff_requires_a_new_root_release_and_narrow_dispatch_permissions():
    jobs = workflow()["jobs"]
    handoff = jobs["dispatch-binaries"]
    assert handoff["needs"] == "release"
    assert handoff["if"] == "${{ needs.release.outputs.release_created == 'true' }}"
    assert handoff["permissions"] == {"contents": "read", "actions": "write"}
    assert "actions" not in jobs["release"]["permissions"]
    checkout = next(step for step in handoff["steps"] if "actions/checkout@" in step.get("uses", ""))
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False
    dispatch = next(step for step in handoff["steps"] if "run" in step)
    assert dispatch["env"]["TAG"] == "${{ needs.release.outputs.tag_name }}"
    assert dispatch["env"]["RELEASE_SHA"] == "${{ needs.release.outputs.sha }}"
    assert dispatch["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert dispatch["env"]["GH_REPO"] == "${{ github.repository }}"


def test_release_pr_dispatches_all_required_workflows():
    jobs = workflow()["jobs"]
    checks = jobs["dispatch-checks"]
    assert checks["needs"] == "release"
    assert checks["if"] == "${{ needs.release.outputs.prs_created == 'true' }}"
    assert checks["permissions"] == {"contents": "read", "actions": "write"}
    assert jobs["release"]["outputs"]["pr"] == "${{ steps.release.outputs.pr }}"
    assert jobs["release"]["outputs"]["prs_created"] == "${{ steps.release.outputs.prs_created }}"
    for name in ("ci", "codeql"):
        parsed = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())
        assert "workflow_dispatch" in parsed[True]  # YAML 1.1 maps 'on' to True.


@pytest.mark.parametrize("case", ["created", "wrong-base", "wrong-head", "ci-error", "codeql-error"])
def test_release_pr_dispatch_command_and_error_propagation(tmp_path, case):
    step = workflow()["jobs"]["dispatch-checks"]["steps"][0]
    assert step["env"]["RELEASE_PR"] == "${{ needs.release.outputs.pr }}"
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert step["env"]["GH_REPO"] == "${{ github.repository }}"
    branch = "release-please--branches--main--components--vpnd"
    pr = {"baseBranchName": "main", "headBranchName": branch}
    if case == "wrong-base":
        pr["baseBranchName"] = "other"
    elif case == "wrong-head":
        pr["headBranchName"] = "main"
    gh = tmp_path / "gh"
    gh.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                  "with open(os.environ['CALL_LOG'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
                  "sys.exit(23 if sys.argv[3] == os.environ['FAIL_WORKFLOW'] else 0)\n")
    gh.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
               CALL_LOG=str(log), RELEASE_PR=json.dumps(pr),
               FAIL_WORKFLOW={"ci-error": "ci.yml", "codeql-error": "codeql.yml"}.get(case, ""))
    result = subprocess.run(["bash", "-c", step["run"]], cwd=tmp_path, env=env,
                            text=True, capture_output=True, check=False)
    if case.startswith("wrong-"):
        assert result.returncode != 0
        assert not log.exists()
    else:
        assert result.returncode == (0 if case == "created" else 23), result.stderr
        expected = [["workflow", "run", name, "--ref", branch] for name in ("ci.yml", "codeql.yml")]
        assert [json.loads(line) for line in log.read_text().splitlines()] == (
            expected[:1] if case == "ci-error" else expected
        )


@pytest.mark.parametrize("case", ["created", "mismatched", "missing", "invalid", "empty-sha", "dispatch-error"])
def test_handoff_validates_real_git_tag_before_dispatch(tmp_path, case):
    handoff = workflow()["jobs"]["dispatch-binaries"]
    command = next(step["run"] for step in handoff["steps"] if "run" in step)
    env = dict(os.environ, GIT_AUTHOR_NAME="release-test", GIT_COMMITTER_NAME="release-test",
               GIT_AUTHOR_EMAIL="release@example.invalid", GIT_COMMITTER_EMAIL="release@example.invalid")

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, env=env, text=True).strip()

    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "release")
    sha = git("rev-parse", "HEAD")
    git("tag", "vpnd-v1.2.3")
    git("commit", "-q", "--allow-empty", "-m", "main advanced")
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/validate-vpnd-release-tag.sh", tmp_path / "scripts")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                  "with open(os.environ['CALL_LOG'], 'w') as f: json.dump(sys.argv[1:], f)\n"
                  "sys.exit(int(os.environ['DISPATCH_EXIT']))\n")
    gh.chmod(0o755)
    log = tmp_path / "dispatch.json"
    env.update(PATH=f"{fake_bin}{os.pathsep}{env['PATH']}", CALL_LOG=str(log),
               TAG="vpnd-v1.2.3", RELEASE_SHA=sha, DISPATCH_EXIT="0")
    if case == "mismatched":
        env["RELEASE_SHA"] = git("rev-parse", "HEAD")
    elif case == "missing":
        env["TAG"] = "vpnd-v9.9.9"
    elif case == "invalid":
        env["TAG"] = "--help"
    elif case == "empty-sha":
        env["RELEASE_SHA"] = ""
    elif case == "dispatch-error":
        env["DISPATCH_EXIT"] = "23"
    result = subprocess.run(["bash", "-c", command], cwd=tmp_path, env=env,
                            text=True, capture_output=True, check=False)
    if case in ("created", "dispatch-error"):
        assert result.returncode == (0 if case == "created" else 23), result.stderr
        assert json.loads(log.read_text()) == [
            "workflow", "run", "release-vpnd.yml", "--ref", "vpnd-v1.2.3", "-f", "tag=vpnd-v1.2.3"
        ]
    else:
        assert result.returncode != 0
        assert not log.exists()
