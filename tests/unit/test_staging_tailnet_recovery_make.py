"""Make seam for destructive staging Tailnet recovery exercises."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
TARGETS = (
    "staging-tailnet-controller-loss-test",
    "staging-tailnet-reboot-recovery-test",
)


@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize(
    "field", ("ANSIBLE_LIMIT", "TAILNET_RECOVERY_CONFIG", "TAILSCALE_AUTH_KEY")
)
def test_recovery_make_inputs_are_never_expanded(tmp_path, target, field):
    marker = tmp_path / "expanded"
    result = subprocess.run(
        ["make", target, f"{field}=$(shell touch {marker})"],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert not marker.exists()


@pytest.mark.parametrize("target", TARGETS)
def test_recovery_make_accepts_only_one_goal(tmp_path, target):
    result = subprocess.run(
        ["make", target, "help"],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "requires exactly one Make goal" in result.stderr


@pytest.mark.parametrize("target", TARGETS)
def test_recovery_scenario_cannot_be_selected_by_caller(tmp_path, target):
    result = subprocess.run(
        ["make", target, "TAILNET_RECOVERY_SCENARIO=controller-loss"],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "accepts only ANSIBLE_LIMIT and TAILNET_RECOVERY_CONFIG" in result.stderr
