from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ANSIBLE_CONFIG = REPO_ROOT / "ansible" / "ansible.cfg"


def test_hyphenated_inventory_groups_are_preserved_without_warning(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[vpn-p0-self-steal]\nexample ansible_connection=local\n")

    result = subprocess.run(
        ["ansible-inventory", "-i", str(inventory), "--graph"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "ANSIBLE_CONFIG": str(ANSIBLE_CONFIG)},
    )

    assert "@vpn-p0-self-steal:" in result.stdout
    assert "Invalid characters were found in group names" not in result.stderr
