"""Fail-closed coverage for live Ansible override files."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/validate-ansible-extra-vars.py"

spec = importlib.util.spec_from_file_location("validate_ansible_extra_vars", SCRIPT)
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def write_yaml(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "extra-vars.yml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_accepts_management_path_and_forwarding_overrides(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        {
            "ansible_host": "management.example.invalid",
            "ansible_port": 22,
            "firewall_forward_interface_contract": [
                {
                    "name": "real-vps-awg-evidence",
                    "input_interface": "awg-evidence0",
                    "output_interface": "eth0",
                }
            ],
        },
    )

    validator.validate(path)


@pytest.mark.parametrize(
    "key",
    [
        "vpn_service_address",
        "xray",
        "vpn",
        "xray_probe_client",
    ],
)
def test_rejects_data_plane_and_protocol_overrides(tmp_path: Path, key: str) -> None:
    path = write_yaml(tmp_path, {key: "untrusted.example.invalid"})

    with pytest.raises(ValueError, match="non-allowlisted"):
        validator.validate(path)


@pytest.mark.parametrize("document", [{}, [], None])
def test_rejects_empty_or_non_mapping_documents(
    tmp_path: Path, document: object
) -> None:
    path = write_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="non-empty mapping"):
        validator.validate(path)


@pytest.mark.parametrize(
    "entry",
    [
        {
            "name": "real-vps-awg-evidence",
            "input_interface": 'awg0"; flush ruleset #',
            "output_interface": "eth0",
        },
        {
            "name": "real-vps-awg-evidence\nflush ruleset",
            "input_interface": "awg0",
            "output_interface": "eth0",
        },
        {
            "name": "real-vps-awg-evidence",
            "input_interface": "awg0",
        },
        {
            "name": "real-vps-awg-evidence",
            "input_interface": "awg0",
            "output_interface": "eth0",
            "unexpected": "value",
        },
    ],
)
def test_rejects_unsafe_or_malformed_forwarding_entries(
    tmp_path: Path, entry: dict[str, str]
) -> None:
    path = write_yaml(tmp_path, {"firewall_forward_interface_contract": [entry]})

    with pytest.raises(ValueError):
        validator.validate(path)
