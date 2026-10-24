"""Execute the research role's profile admission before host mutation."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/real-vps-awg-nat"


@pytest.mark.parametrize(
    ("override", "accepted", "check_mode"),
    [
        ({}, True, False),
        ({"h1": "11", "s3": 0, "s4": 0}, True, True),
        ({"h1": "100-199"}, False, False),
        ({"i1": "<b 0xdeadbeef>"}, False, False),
        ({"i5": "<r 8>"}, False, True),
        ({"h1": "0"}, False, False),
        ({"h2": "1"}, False, False),
        ({"jmin": 71}, False, False),
        ({"s3": 1}, False, False),
        ({"s4": True}, False, False),
        ({"header_protection": True}, False, False),
        ({"wire_profile": "unsupported"}, False, False),
    ],
)
def test_profile_admission_before_mutation(tmp_path, override, accepted, check_mode):
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    profile = {**defaults["real_vps_awg_nat_obfuscation"], **override}
    playbook = tmp_path / "profile.yml"
    playbook.write_text(yaml.safe_dump([{
        "name": "Exercise actual evidence profile admission",
        "hosts": "localhost",
        "gather_facts": False,
        "become": False,
        "vars": {
            "ansible_facts": {"system": "Linux", "service_mgr": "systemd"},
            "real_vps_awg_nat_mode": "server",
            "provider": "example",
            "real_vps_awg_nat_expected_placement": {"server": {
                "inventory_hostname": "localhost", "ansible_host": "203.0.113.10",
                "provider": "example", "cohort_group": "vpn-p2-evidence",
            }},
            "real_vps_awg_nat_obfuscation": profile,
            # Candidate pins must not enable unqualified evidence semantics.
            "real_vps_awg_nat_awg_go_commit": "b5928efb6ca19f0153958460c3d141f04abc5c2e",
            "real_vps_awg_nat_awg_tools_commit": "ee0f0a9aa34ff0a0da4b3433b9512781cfe02843",
        },
        "roles": [{"role": "real-vps-awg-nat"}],
    }]))
    inventory = tmp_path / "inventory.ini"
    inventory.write_text(
        "[vpn-p2-evidence]\nlocalhost ansible_connection=local ansible_host=203.0.113.10\n"
    )
    args = ["ansible-playbook", "-i", str(inventory), str(playbook)]
    if accepted:
        args += ["--tags", "always"]
    if check_mode:
        args += ["--check"]
    result = subprocess.run(
        args, cwd=ROOT / "ansible", capture_output=True, text=True, check=False,
        env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
    )
    output = result.stdout + result.stderr
    assert (result.returncode == 0) is accepted, output
    assert "Require the supported AWG evidence profile" in output
    if accepted:
        assert "Bind placement to the provider-state address" in output
    else:
        assert "Refusing AWG evidence profile" in output
    assert "Create persistent firewall policy directories" not in output
