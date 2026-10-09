"""Selected real-VPS jobs must fail before provisioning if configuration is absent."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/real-vps-deploy.yml"


def _job():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["deploy"]


@pytest.mark.parametrize("fork,missing,success", [
    ("true", None, False), ("false", "UPCLOUD_TOKEN", False),
    ("false", "CI_TAILSCALE_OAUTH_CLIENT_SECRET", False), ("false", None, True),
])
def test_protected_preflight_fails_before_tools(tmp_path, fork, missing, success):
    job = yaml.safe_load((ROOT / ".github/workflows/ci-disposable-deploy.yml").read_text())["jobs"]["deploy"]
    guard = job["steps"][1]
    environment = {**os.environ, "FORK": fork}
    for name in guard["env"]:
        if name != "FORK":
            environment[name] = "synthetic-value" if name != missing else ""
    result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", guard["run"]],
                            env=environment, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) is success
    assert "synthetic-value" not in result.stdout + result.stderr


def test_optional_ubuntu_is_selected_before_jobs_start():
    # Repository variables are available during matrix expansion; secrets are not.
    assert _job()["strategy"]["matrix"] == {
        "distro": "${{ fromJSON(vars.CI_REAL_DEPLOY_UBUNTU24 == 'true' && "
                  "'[\"debian13\",\"ubuntu2404\"]' || '[\"debian13\"]') }}",
    }


def test_selected_deploy_cannot_be_short_circuited_into_success():
    job = _job()
    assert "continue-on-error" not in job
    assert "github.event_name == 'schedule'" in job["if"]
    assert job["uses"] == "./.github/workflows/ci-disposable-deploy.yml"
    shared = yaml.safe_load((ROOT / ".github/workflows/ci-disposable-deploy.yml").read_text())["jobs"]["deploy"]
    steps = shared["steps"]
    deploy = next(step for step in steps if "scripts/ci-real-deploy.py" in step.get("run", ""))
    assert "if" not in deploy
    for step in steps:
        assert "continue-on-error" not in step
        assert "outputs.skip" not in step.get("if", "")
    assert steps[-1]["if"] == "always()"
    assert steps[-1]["with"]["if-no-files-found"] == "error"
