"""Regression coverage for fail-closed CI destruction."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _test_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in ("destroy.sh", "terraform-env.sh"):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts / name)
    tf_dir = root / "terraform/providers/upcloud/environments"
    tf_dir.mkdir(parents=True)
    return root


def _terraform_stub(tmp_path: Path, *, fail_apply: bool = False) -> Path:
    stub = tmp_path / "terraform"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$STUB_LOG\"\n"
        "while [[ \"${1:-}\" == -chdir=* ]]; do shift; done\n"
        "if [[ \"${1:-}\" == apply && \"${FAIL_APPLY:-false}\" == true ]]; then exit 1; fi\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _run(root: Path, stub_dir: Path, env_name: str, *, fail_apply: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "PROVIDER": "upcloud",
        "ENV": env_name,
        "STUB_LOG": str(stub_dir / "terraform.log"),
        "FAIL_APPLY": str(fail_apply).lower(),
    }
    return subprocess.run(
        ["bash", str(root / "scripts/destroy.sh"), "--non-interactive"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )


def test_ci_destroy_skips_prompts_and_cleans_inventory_after_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-123-cleanup"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text('server_name = "vpn-ci.test"\n')
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\n")
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name)

    assert result.returncode == 0, result.stderr
    assert "CI destroy authorization accepted" in result.stdout
    assert not inventory.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert "plan -destroy" in (stub.parent / "terraform.log").read_text()
    assert "apply" in (stub.parent / "terraform.log").read_text()


def test_noninteractive_destroy_rejects_non_ci_environment(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    (root / "terraform/providers/upcloud/environments/prod.tfvars").write_text('server_name = "vpn-prod.test"\n')
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "prod")

    assert result.returncode == 2
    assert "restricted to validated ci-* environments" in result.stderr
    assert not (stub.parent / "terraform.log").exists()


def test_failed_ci_destroy_keeps_inventory_for_diagnosis(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-123-failure"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text('server_name = "vpn-ci.test"\n')
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\n")
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name, fail_apply=True)

    assert result.returncode != 0
    assert inventory.exists()


def test_ci_workflows_do_not_suppress_destroy_failure_or_cleanup_tfvars_early() -> None:
    for workflow in ("real-vps-deploy.yml", "transport-reachability-matrix.yml"):
        source = (REPO_ROOT / ".github/workflows" / workflow).read_text()
        assert "make destroy DESTROY_ARGS=--non-interactive" in source
        assert "make destroy || true" not in source
        assert "rm -f \"terraform/providers/upcloud/environments/${CI_ENV}.tfvars\"" in source
        assert "env.CI_ENV != ''" in source
