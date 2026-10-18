"""Provider return-port authority refuses malformed direct role inputs."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("role", ["firewall", "split-hop-egress"])
@pytest.mark.parametrize("value,ssh_port,valid", [
    ("32768-60999", 22, True),
    ("40000-45000", 2222, True),
    ("40000-40000", 22, True),
    (True, 22, False),
    (32768, 22, False),
    (None, 22, False),
    ("", 22, True),
    ("032768-60999", 22, False),
    ("1023-60999", 22, False),
    ("32768-65536", 22, False),
    ("60999-32768", 22, False),
    ("32768-60999", 40000, False),
    ("32768-60999 extra=unsafe", 22, False),
])
def test_role_refuses_unsafe_source_range_before_mutation(tmp_path, role, value, ssh_port, valid):
    filename = "enable.yml" if role == "split-hop-egress" else "main.yml"
    task = yaml.safe_load((ROOT / f"ansible/roles/{role}/tasks/{filename}").read_text())[0]
    assert task["name"] == "Validate provider NAT source-port range before mutation"
    play = [{"hosts": "localhost", "gather_facts": False, "vars": {
        "terraform_nat_source_port_range": value, "ansible_port": ssh_port,
    }, "tasks": [task]}]
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run([shutil.which("ansible-playbook"), "-i", "localhost,", "-c", "local", str(path)],
        text=True, capture_output=True, timeout=25,
        env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"), "ANSIBLE_NOCOLOR": "1"})
    assert (result.returncode == 0) is valid, result.stdout + result.stderr
    if not valid:
        assert "provider-nat-source-port-range-invalid" in result.stdout
