"""Tests for environment-scoped Terraform workspace selection."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "terraform-env.sh"


def _terraform_stub(tmp_path: Path) -> Path:
    stub = tmp_path / "tofu"
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'TF_DATA_DIR=%s %s\\n' "$TF_DATA_DIR" "$*" >> "$STUB_LOG"
while [[ "${1:-}" == -chdir=* ]]; do shift; done
case "${1:-}" in
  init|output) exit 0 ;;
  workspace)
    case "${2:-}" in
      select)
        [[ "${3:-}" == "${EXISTING_WORKSPACE:-default}" ]] && exit 0
        exit 1
        ;;
      new) exit 0 ;;
    esac
    ;;
esac
"""
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _run(
    tmp_path: Path,
    *,
    env_name: str,
    args: list[str],
    existing: str = "default",
    provider: str = "upcloud",
    backend_root: str | None = None,
) -> subprocess.CompletedProcess[str]:
    stub_dir = _terraform_stub(tmp_path).parent
    if backend_root is None:
        (tmp_path / "backend").mkdir(exist_ok=True)
        (tmp_path / "backend" / f"{provider}.s3.tfbackend").write_text('bucket = "fixture"\n')
        backend_root = str(tmp_path / "backend")
    env = {k: v for k, v in os.environ.items() if k != "TF_BACKEND_ROOT"} | {
        "TF_BACKEND_ROOT": backend_root,
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "STUB_LOG": str(tmp_path / "terraform.log"),
        "PROVIDER": provider,
        "ENV": env_name,
        "EXISTING_WORKSPACE": existing,
    }
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=REPO_ROOT, env=env, text=True, capture_output=True)


def test_prod_keeps_legacy_default_workspace(tmp_path: Path) -> None:
    result = _run(tmp_path, env_name="prod", args=["output", "-raw", "server_ipv4"])

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "terraform.log").read_text().splitlines() == [
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/upcloud/.terraform-env/default'} -chdir={REPO_ROOT / 'terraform/providers/upcloud'} workspace select default",
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/upcloud/.terraform-env/default'} -chdir={REPO_ROOT / 'terraform/providers/upcloud'} output -raw server_ipv4",
    ]


def test_init_creates_missing_nonprod_workspace(tmp_path: Path) -> None:
    result = _run(tmp_path, env_name="green-2026", args=["init", "-input=false"])

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "terraform.log").read_text().splitlines() == [
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/upcloud/.terraform-env/green-2026'} -chdir={REPO_ROOT / 'terraform/providers/upcloud'} init -input=false -backend-config={tmp_path / 'backend/upcloud.s3.tfbackend'}",
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/upcloud/.terraform-env/green-2026'} -chdir={REPO_ROOT / 'terraform/providers/upcloud'} workspace select green-2026",
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/upcloud/.terraform-env/green-2026'} -chdir={REPO_ROOT / 'terraform/providers/upcloud'} workspace new green-2026",
    ]


def test_non_init_refuses_to_create_missing_workspace(tmp_path: Path) -> None:
    result = _run(tmp_path, env_name="green-2026", args=["output", "-raw", "server_ipv4"])

    assert result.returncode != 0
    assert "run 'make PROVIDER=upcloud ENV=green-2026 init' first" in result.stderr
    assert (tmp_path / "terraform.log").read_text().splitlines() == [
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/upcloud/.terraform-env/green-2026'} -chdir={REPO_ROOT / 'terraform/providers/upcloud'} workspace select green-2026",
    ]


def test_scaleway_provider_root_is_accepted(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        env_name="prod",
        args=["output", "-raw", "server_ipv4"],
        provider="scaleway",
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "terraform.log").read_text().splitlines() == [
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/scaleway/.terraform-env/default'} -chdir={REPO_ROOT / 'terraform/providers/scaleway'} workspace select default",
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/scaleway/.terraform-env/default'} -chdir={REPO_ROOT / 'terraform/providers/scaleway'} output -raw server_ipv4",
    ]


def test_vultr_plan_runs_control_plane_preflight_first(tmp_path: Path) -> None:
    stub_dir = _terraform_stub(tmp_path).parent
    python = stub_dir / "python3"
    python.write_text("#!/usr/bin/env bash\nprintf 'preflight\\n' >> \"$STUB_LOG\"\n")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
    env = os.environ | {
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "STUB_LOG": str(tmp_path / "terraform.log"),
        "PROVIDER": "vultr",
        "ENV": "p2-vultr",
        "EXISTING_WORKSPACE": "p2-vultr",
        "TF_VAR_vultr_api_key": "test-key",
    }

    result = subprocess.run(
        ["bash", str(SCRIPT), "plan", "-refresh-only"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    lines = (tmp_path / "terraform.log").read_text().splitlines()
    assert lines[0].endswith("workspace select p2-vultr")
    assert lines[1] == "preflight"
    assert lines[2].endswith("plan -refresh-only")


def test_operator_scripts_pass_provider_and_environment_to_wrapper() -> None:
    for script in [REPO_ROOT / "scripts/destroy.sh", REPO_ROOT / "scripts/drift-since-tag.sh"]:
        source = script.read_text()
        assert 'env PROVIDER="$PROVIDER" ENV="$ENV" "${REPO_ROOT}/scripts/terraform-env.sh"' in source


def test_backup_rejects_unsafe_environment_before_reading_state() -> None:
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/backup-tf-state.sh")],
        cwd=REPO_ROOT,
        env=os.environ | {"ENV": "../escape", "PROVIDER": "upcloud"},
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "ENV must contain only letters, numbers, and hyphens" in result.stderr


def test_default_alias_refuses_before_terraform(tmp_path):
    result = _run(tmp_path, env_name="default", args=["init"])
    assert result.returncode == 2
    assert "reserved" in result.stderr
    assert not (tmp_path / "terraform.log").exists()


def test_reserved_alias_refuses_backup_restore_and_cohort_before_private_inputs():
    for script, arguments, settings in (
        ("backup-tf-state.sh", [], {"ENV": "default"}),
        ("restore-tf-state.sh", [], {"ENV": "default"}),
        ("new-cohort.sh", ["default"], {"SOURCE_ENV": "prod"}),
        ("new-cohort.sh", ["green"], {"SOURCE_ENV": "default"}),
    ):
        result = subprocess.run(["bash", str(REPO_ROOT / "scripts" / script), *arguments],
            env=os.environ | {"PROVIDER": "upcloud", **settings},
            capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
        assert "reserved" in result.stderr
        assert "missing" not in result.stderr


def _planned_var_file(tfvars_root: str) -> str:
    result = subprocess.run(
        ["make", "-n", "--no-print-directory", "plan", "PROVIDER=upcloud", "ENV=prod", f"TFVARS_ROOT={tfvars_root}"],
        cwd=REPO_ROOT, env={k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MAKEFILES")},
        text=True, capture_output=True, check=True,
    )
    return next(part for part in result.stdout.split() if part.startswith("-var-file="))


def test_plan_reads_tfvars_from_an_external_ops_checkout(tmp_path: Path) -> None:
    assert _planned_var_file(str(tmp_path / "ops/tfvars")) == f'-var-file="{tmp_path}/ops/tfvars/upcloud/prod.tfvars"'


def test_plan_keeps_the_provider_root_tfvars_by_default() -> None:
    assert _planned_var_file("") == f'-var-file="{REPO_ROOT}/terraform/providers/upcloud/environments/prod.tfvars"'


def test_relative_tfvars_root_is_refused() -> None:
    result = subprocess.run(["make", "-n", "--no-print-directory", "plan", "TFVARS_ROOT=config/tfvars"], cwd=REPO_ROOT,
                            env={k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MAKEFILES")},
                            text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "TFVARS_ROOT must be an absolute path" in result.stderr


@pytest.mark.parametrize("backend_root", ["", "relative/backend"])
def test_init_refuses_without_an_absolute_backend_root(tmp_path: Path, backend_root: str) -> None:
    result = _run(tmp_path, env_name="green-2026", args=["init"], backend_root=backend_root)
    assert result.returncode == 2
    assert "TF_BACKEND_ROOT must be the absolute directory of upcloud.s3.tfbackend" in result.stderr
    assert not (tmp_path / "terraform.log").exists()


def test_init_refuses_a_missing_backend_file(tmp_path: Path) -> None:
    result = _run(tmp_path, env_name="green-2026", args=["init"], backend_root=str(tmp_path))
    assert result.returncode == 2
    assert "missing backend file" in result.stderr
