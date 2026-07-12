"""Playbooks must load the canonical profile variables before convergence."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_playbook_directory_exposes_canonical_group_vars(tmp_path):
    ansible_inventory = shutil.which("ansible-inventory")
    if ansible_inventory is None:
        pytest.skip("ansible-inventory is not installed")

    group_vars = ROOT / "ansible/playbooks/group_vars"
    assert group_vars.is_symlink()
    assert group_vars.resolve() == ROOT / "ansible/group_vars"

    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[vpn-p1-web]\np1-test\n")
    result = subprocess.run(
        [
            ansible_inventory,
            "-i",
            str(inventory),
            "--playbook-dir",
            str(ROOT / "ansible/playbooks"),
            "--host",
            "p1-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    profile = json.loads(result.stdout)["vpn"]
    assert profile["enable_xray_reality"] is False
    assert profile["enable_nginx_xhttp"] is True
    assert profile["enable_geodata"] is False
