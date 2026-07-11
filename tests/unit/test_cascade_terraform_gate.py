"""The isolated cascade Terraform surface is inert and attestation-gated."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TF_ROOT = ROOT / "terraform" / "exception" / "cascade-ingress"
PLAN = TF_ROOT / "plan.sh"
APPLY = TF_ROOT / "apply.sh"


def test_isolated_root_has_fixed_provider_neutral_output_contract() -> None:
    outputs = (TF_ROOT / "outputs.tf").read_text(encoding="utf-8")

    names = set(re.findall(r'^output "([^"]+)"', outputs, flags=re.MULTILINE))
    existing = set(
        re.findall(
            r'^output "([^"]+)"',
            (ROOT / "terraform/providers/upcloud/outputs.tf").read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )

    assert names == existing
    assert not any(part.name == "providers" for part in TF_ROOT.parents if part != ROOT)


def test_normal_terraform_router_cannot_reach_exception_root() -> None:
    router = (ROOT / "scripts" / "terraform-env.sh").read_text(encoding="utf-8")

    assert "terraform/exception" not in router
    assert "cascade-ingress" not in router


def test_missing_attestation_blocks_before_terraform_runs(tmp_path: Path) -> None:
    marker = tmp_path / "terraform-called"
    stub = tmp_path / "terraform"
    stub.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "CASCADE_ATTESTATION": str(tmp_path / "missing.json"),
        "CASCADE_EXCEPTION_CONFIRMATION": "I_ACKNOWLEDGE_RU_CASCADE_JURISDICTION_EXCEPTION",
    }

    result = subprocess.run([str(PLAN)], cwd=ROOT, env=env, text=True, capture_output=True)

    assert result.returncode != 0
    assert not marker.exists()
    assert "attestation" in result.stderr.lower()


def test_root_itself_invokes_attestation_checker() -> None:
    main = (TF_ROOT / "main.tf").read_text(encoding="utf-8")

    assert 'data "external" "attestation"' in main
    assert "check-cascade-attestation.py" in main
    assert 'result.status == "verified"' in main


def test_apply_boundary_blocks_after_attestation_check(tmp_path: Path) -> None:
    env = {**os.environ, "CASCADE_ATTESTATION": str(tmp_path / "missing.json")}

    result = subprocess.run([str(APPLY)], cwd=ROOT, env=env, text=True, capture_output=True)

    assert result.returncode != 0
    assert "attestation" in result.stderr.lower()


def test_cascade_secret_block_exists_with_empty_defaults() -> None:
    example = yaml.safe_load((ROOT / "secrets" / "prod.secrets.example.yaml").read_text(encoding="utf-8"))

    assert example["cascade_secrets"] == {
        "ingress_private_key": "",
        "ingress_public_key": "",
        "egress_private_key": "",
        "egress_public_key": "",
        "preshared_key": "",
        "classifier_proxy_password": "",
    }
