"""Tests for environment-scoped Terraform workspace selection."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "terraform-env.sh"


def _terraform_stub(tmp_path: Path) -> Path:
    stub = tmp_path / "terraform"
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
) -> subprocess.CompletedProcess[str]:
    stub_dir = _terraform_stub(tmp_path).parent
    env = os.environ | {
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
    result = _run(tmp_path, env_name="green-2026", args=["init", "-backend=false"])

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "terraform.log").read_text().splitlines() == [
        f"TF_DATA_DIR={REPO_ROOT / 'terraform/providers/upcloud/.terraform-env/green-2026'} -chdir={REPO_ROOT / 'terraform/providers/upcloud'} init -backend=false",
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
