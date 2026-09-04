"""Make must refuse or preserve Tailnet promotion inputs before expansion."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

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


def test_promotion_refuses_multiple_goals_before_expanding_inputs(
    tmp_path: Path,
) -> None:
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


@pytest.mark.parametrize(
    "name",
    ["ENV", "PROVIDER", "HOME", "DEPLOY_SOURCE_REVISION", "DEPLOYABLE_SOURCE_DIGEST"],
)
def test_promotion_rejects_non_config_command_line_input_before_expansion(
    tmp_path: Path, name: str
) -> None:
    marker = tmp_path / f"{name.lower()}-expanded"
    result = subprocess.run(
        [
            "make",
            "-n",
            "tailnet-network-promote",
            "TAILNET_NETWORK_CONFIG=/private/config.json",
            f"{name}=$(shell touch {marker})",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert (
        "accepts command-line values only for TAILNET_NETWORK_CONFIG" in result.stderr
    )
    assert not marker.exists()


@pytest.mark.parametrize(
    "name",
    ["ENV", "PROVIDER", "HOME", "DEPLOY_SOURCE_REVISION", "DEPLOYABLE_SOURCE_DIGEST"],
)
def test_promotion_neutralizes_ambient_eager_input_before_expansion(
    tmp_path: Path, name: str
) -> None:
    marker = tmp_path / f"ambient-{name.lower()}-expanded"
    environment = {**os.environ, name: f"$(shell touch {marker})"}
    result = subprocess.run(
        [
            "make",
            "-n",
            "tailnet-network-promote",
            "TAILNET_NETWORK_CONFIG=/private/config.json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "inputs must be literal values" in result.stderr
    assert not marker.exists()


def test_promotion_passes_ambient_provider_token_without_command_line_origin(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    observed = tmp_path / "observed-token"
    wrapper = bin_dir / "python3"
    wrapper.write_text(
        "#!/bin/sh\n" 'printf \'%s\' "$UPCLOUD_TOKEN" > "$TOKEN_OBSERVED"\n'
    )
    wrapper.chmod(0o700)
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "UPCLOUD_TOKEN": "ambient-provider-capability",
        "TOKEN_OBSERVED": str(observed),
    }
    result = subprocess.run(
        [
            "make",
            "tailnet-network-promote",
            "TAILNET_NETWORK_CONFIG=/private/config.json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert observed.read_text() == "ambient-provider-capability"
