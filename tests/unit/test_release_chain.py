"""Exercise the automatic release handoff without publishing a release."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolated_git_configuration(monkeypatch):
    # Only synthetic repositories in this module create commits or tags.
    for name in tuple(os.environ):
        if name.startswith("GIT_CONFIG_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/release-please.yml").read_text())


def test_release_version_updates_include_the_locked_root_package():
    config = json.loads((ROOT / ".github/release-please-config.json").read_text())
    assert config["draft"] is True
    assert config["force-tag-creation"] is True
    files = config["packages"]["."]["extra-files"]
    assert {
        "type": "toml",
        "path": "vpnd/pyproject.toml",
        "jsonpath": "$.project.version",
    } in files
    assert not any("Cargo" in str(entry) for entry in files)
    import tomllib

    project = tomllib.loads((ROOT / "vpnd/pyproject.toml").read_text())["project"]
    manifest = json.loads((ROOT / ".github/release-please-manifest.json").read_text())
    assert project["version"] == manifest["."]


def test_release_automation_is_enabled_by_default_and_errors_are_fatal():
    release = workflow()["jobs"]["release"]
    assert release["if"] == "${{ github.ref == 'refs/heads/main' && vars.RELEASE_PLEASE_ENABLED != 'false' }}"
    action = next(step for step in release["steps"] if "release-please-action@" in step.get("uses", ""))
    assert not action.get("continue-on-error", False)
    assert not release.get("continue-on-error", False)
    for output in ("release_created", "tag_name", "sha"):
        assert release["outputs"][output] == "${{ steps.release.outputs." + output + " }}"
    assert action["id"] == "release"
    notice = next(step for step in release["steps"] if "GITHUB_STEP_SUMMARY" in step.get("run", ""))
    assert notice["if"] == "${{ steps.release.outputs.prs_created == 'true' }}"
    assert "Approve workflows to run" in notice["run"]
    assert "dispatch-checks" not in workflow()["jobs"]


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


def test_every_release_job_has_a_timeout():
    workflow = yaml.safe_load((ROOT / ".github/workflows/release-vpnd.yml").read_text())
    missing = [name for name, job in workflow["jobs"].items() if not isinstance(job.get("timeout-minutes"), int)]
    assert missing == []


def _release_step(name):
    workflow = yaml.safe_load((ROOT / ".github/workflows/release-vpnd.yml").read_text())
    return next(step for step in workflow["jobs"]["release"]["steps"] if step.get("name") == name)


@pytest.mark.parametrize("wheel_bytes,accepted", [(["same"] * 4, True), (["same"] * 3 + ["other"], False)])
def test_release_publishes_packages_only_when_every_runner_built_the_same_bytes(tmp_path, wheel_bytes, accepted):
    for target, wheel in zip(("x86_64-linux", "aarch64-linux", "x86_64-darwin", "aarch64-darwin"), wheel_bytes):
        runner = tmp_path / "runners" / f"vpnd-{target}"
        runner.mkdir(parents=True)
        (runner / f"vpnd-{target}.tar.gz").write_text(target)
        (runner / "vpnd-1.2.3-py3-none-any.whl").write_text(wheel)
        (runner / "vpnd-1.2.3.tar.gz").write_text("sdist")
    step = _release_step("Require identical Python packages from every runner")
    result = subprocess.run(["bash", "-c", step["run"]], cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    published = sorted(path.name for path in (tmp_path / "dist").glob("*")) if accepted else []
    assert published == ([
        "vpnd-1.2.3-py3-none-any.whl", "vpnd-1.2.3.tar.gz", "vpnd-aarch64-darwin.tar.gz",
        "vpnd-aarch64-linux.tar.gz", "vpnd-x86_64-darwin.tar.gz", "vpnd-x86_64-linux.tar.gz",
    ] if accepted else [])


def test_every_published_release_asset_carries_build_provenance():
    workflow = yaml.safe_load((ROOT / ".github/workflows/release-vpnd.yml").read_text())
    build = next(step for step in workflow["jobs"]["build"]["steps"] if step.get("name") == "Attest build provenance")
    assert build["with"]["subject-path"].split() == ["dist/vpnd-*.tar.gz", "dist/vpnd-*.whl"]
    steps = workflow["jobs"]["release"]["steps"]
    names = [step.get("name") for step in steps]
    attest = steps[names.index("Attest SBOM and checksum provenance")]
    assert attest["with"]["subject-path"].split() == ["dist/sbom.json", "dist/SHA256SUMS"]
    assert names.index("Generate SHA256SUMS") < names.index("Attest SBOM and checksum provenance") < names.index("Publish GitHub release")
    assert {"id-token": "write", "attestations": "write"}.items() <= workflow["jobs"]["release"]["permissions"].items()
    # merge-multiple would let one runner's package silently replace another's.
    download = next(step for step in steps if step.get("uses", "").startswith("actions/download-artifact@"))
    assert "merge-multiple" not in download["with"]
