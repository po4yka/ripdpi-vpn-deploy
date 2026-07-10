"""Renovate may only manage pins that it can update safely and completely."""

import json
from pathlib import Path


def test_custom_managers_do_not_target_secret_backed_transport_pins():
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "renovate.json").read_text())
    managed_files = {
        file_match
        for manager in config["customManagers"]
        for file_match in manager["fileMatch"]
    }

    assert "^ansible/roles/xray/defaults/main\\.yml$" not in managed_files
    assert "^ansible/roles/amneziawg/defaults/main\\.yml$" not in managed_files
