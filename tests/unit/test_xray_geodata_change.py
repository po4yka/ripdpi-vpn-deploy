"""Execute real Ansible authority comparisons without publishing active files."""

from __future__ import annotations

import grp
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("active", ["same", "older", "missing", "mode", "receipt", "receipt-missing"])
def test_cached_geodata_is_compared_to_active_authority_without_publication(tmp_path, active):
    names = {
        "Detect selected geodata changes without publishing active assets",
        "Define selected geodata activation receipt",
        "Detect selected geodata receipt changes without publication",
    }
    tasks = [
        task for task in yaml.safe_load(
            (ROOT / "ansible/roles/xray/tasks/enable.yml").read_text()
        ) if task["name"] in names
    ]
    assert len(tasks) == len(names)
    for task in tasks:
        if "ansible.builtin.copy" in task:
            # Only ownership is isolated to the portable test user. Actual copy
            # modules, candidate selection and check mode remain production code.
            task["ansible.builtin.copy"].update(
                owner=pwd.getpwuid(os.getuid()).pw_name,
                group=grp.getgrgid(os.getgid()).gr_name,
            )
    candidate, installed = tmp_path / "candidate", tmp_path / "installed"
    candidate.mkdir()
    installed.mkdir()
    for name in ("geoip.dat", "geosite.dat"):
        source = candidate / name
        source.write_bytes(b"selected-" + name.encode())
        source.chmod(0o644)
        if active == "missing" and name == "geoip.dat":
            continue
        target = installed / name
        target.write_bytes(b"older" if active == "older" and name == "geoip.dat" else source.read_bytes())
        target.chmod(0o600 if active == "mode" and name == "geoip.dat" else 0o644)
    desired = {"geoip.dat": "a" * 64, "geosite.dat": "b" * 64}
    receipt = installed / ".geodata-activated.json"
    if active != "receipt-missing":
        receipt.write_text(json.dumps({
            "schema": 1, "desired": desired if active != "receipt" else {},
            "metadata": {"mode": 420, "uid": 0, "gid": 0},
        }, sort_keys=True, separators=(",", ":")))
        receipt.chmod(0o600)
    before = {
        path.name: (path.read_bytes(), path.stat().st_mode, path.stat().st_ino)
        for path in installed.iterdir()
    }
    play = [{
        "hosts": "localhost", "connection": "local", "gather_facts": False,
        "become": False,
        "vars": {
            "ansible_become": False, "ansible_python_interpreter": sys.executable,
            "transport_runtime_geodata_candidate_dir": str(candidate),
            "geodata": {"install_dir": str(installed),
                        "geoip_sha256": desired["geoip.dat"], "geosite_sha256": desired["geosite.dat"]},
            # A cached candidate reports no new staging, even before activation.
            "_geodata_pair": {"changed": False},
            "expected_asset_change": active in {"older", "missing", "mode"},
            "expected_receipt_change": active in {"receipt", "receipt-missing"},
        },
        "tasks": [*tasks, {
            "name": "Require actual active authority comparisons",
            "ansible.builtin.assert": {"that": [
                "_xray_geodata_change.changed == expected_asset_change",
                "_xray_geodata_receipt_change.changed == expected_receipt_change",
            ]},
        }],
    }]
    playbook = tmp_path / "play.json"
    playbook.write_text(json.dumps(play))
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(playbook)],
        check=False, cwd=tmp_path, capture_output=True, text=True, timeout=30,
        env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {
        path.name: (path.read_bytes(), path.stat().st_mode, path.stat().st_ino)
        for path in installed.iterdir()
    } == before
