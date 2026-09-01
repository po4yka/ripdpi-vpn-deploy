"""Make must refuse or preserve Tailnet promotion inputs before expansion."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_promotion_rejects_command_line_provider_token_before_expansion(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "provider-token-expanded"
    result = subprocess.run(
        [
            "make",
            "-n",
            "tailnet-network-promote",
            "TAILNET_NETWORK_CONFIG=/private/config.json",
            f"UPCLOUD_TOKEN=$(shell touch {marker})",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "provider credentials must come from the environment" in result.stderr
    assert not marker.exists()


def test_promotion_preserves_config_as_literal_data_before_recipe_expansion(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "config-expanded"
    literal = f"$(shell touch {marker})"
    environment = {**os.environ}
    environment.pop("UPCLOUD_TOKEN", None)
    result = subprocess.run(
        ["make", "-n", "tailnet-network-promote", f"TAILNET_NETWORK_CONFIG={literal}"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert '"$TAILNET_NETWORK_CONFIG"' in result.stdout


def test_promotion_refuses_multiple_goals_before_expanding_inputs(tmp_path: Path) -> None:
    marker = tmp_path / "multi-goal-expanded"
    result = subprocess.run(
        [
            "make",
            "-n",
            "tailnet-network-promote",
            "help",
            f"TAILNET_NETWORK_CONFIG=$(shell touch {marker})",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "requires exactly one Make goal" in result.stderr
    assert not marker.exists()
