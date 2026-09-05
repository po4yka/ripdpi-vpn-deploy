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


@pytest.mark.parametrize("distro,template,secret_name", [
    ("debian13", "", "CI_UPCLOUD_TEMPLATE_UUID"),
    ("ubuntu2404", "", "CI_UPCLOUD_TEMPLATE_UUID_UBUNTU24"),
    ("debian13", "template-test-value", "CI_UPCLOUD_TEMPLATE_UUID"),
    ("ubuntu2404", "template-test-value", "CI_UPCLOUD_TEMPLATE_UUID_UBUNTU24"),
    ("unknown", "", None),
])
def test_template_preflight_fails_closed(tmp_path, distro, template, secret_name):
    gate = next(step for step in _job()["steps"] if step.get("id") == "gate")
    environment_file = tmp_path / "env"
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", gate["run"]],
        env={**os.environ, "MATRIX_DISTRO": distro,
             "CI_UPCLOUD_TEMPLATE_UUID_DEBIAN13": template if distro == "debian13" else "",
             "CI_UPCLOUD_TEMPLATE_UUID_UBUNTU24": template if distro == "ubuntu2404" else "",
             "GITHUB_ENV": str(environment_file), "GITHUB_OUTPUT": str(tmp_path / "output")},
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    if template:
        assert result.returncode == 0, result.stderr
        assert environment_file.read_text() == f"MATRIX_TEMPLATE_UUID={template}\n"
        assert template not in result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout
        assert "::error::" in result.stdout
        if secret_name:
            assert secret_name in result.stdout
        assert not environment_file.exists()


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
    steps = job["steps"]
    preflight = next(i for i, step in enumerate(steps) if step.get("id") == "gate")
    deploy = next(i for i, step in enumerate(steps) if step.get("name") == "Deploy")
    assert preflight < deploy
    for step in steps[preflight:]:
        assert "continue-on-error" not in step
        assert "outputs.skip" not in step.get("if", "")
    assert "if" not in steps[deploy]
    destroy = steps[-1]
    assert destroy["if"] == "always() && env.CI_ENV != ''"
    assert "make destroy DESTROY_ARGS=--non-interactive" in destroy["run"]
