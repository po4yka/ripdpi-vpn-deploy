"""Actual Ansible disabled entrypoints need no enabled-role inputs or package writes."""

from __future__ import annotations
import os
from pathlib import Path
import re
import subprocess
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_absent_host_web_roles_check_and_repeated_retirement_preserve_shared_nginx():
    assert os.geteuid() == 0
    units = [
        "vpn-sub-mirror.timer",
        "vpn-sub-mirror.service",
        "vpn-bootstrap.service",
        "cdn-front-prefix-refresh.timer",
        "cdn-front-prefix-refresh.service",
        "vpn-geodata-refresh.timer",
        "vpn-geodata-refresh.service",
    ]
    for unit in units:
        result = subprocess.run(
            ["systemctl", "show", unit, "--property=LoadState", "--value"],
            capture_output=True,
            text=True,
        )
        assert (
            result.stdout.strip() == "not-found"
        ), "requires no preexisting canonical owned runtime"
    nginx_before = subprocess.run(
        ["systemctl", "show", "nginx.service", "--property=ActiveState,UnitFileState"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    apt_before = Path("/var/lib/dpkg/status").read_bytes()
    template = """- hosts: localhost
  connection: local
  become: false
  gather_facts: false
  roles:
    - role: nginx-xhttp
      nginx_xhttp_role_enabled: false
    - role: cdn-front
      cdn_front_role_enabled: false
    - role: subscription-host
      subscription_host_role_enabled: false
    - role: geodata
      geodata_role_enabled: false
    - role: intrusion_prevention
      intrusion_prevention_role_enabled: false
"""
    with tempfile.TemporaryDirectory(prefix="vpn-p2-disable-") as directory:
        play = Path(directory) / "play.yml"
        play.write_text(template)
        environment = {
            **os.environ,
            "ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles"),
            "ANSIBLE_STDOUT_CALLBACK": "default",
            "ANSIBLE_NOCOLOR": "1",
        }
        for flags in (["--check"], [], []):
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", str(play), *flags],
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=90,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            final = result.stdout[result.stdout.index("PLAY RECAP") :]
            assert re.search(r"failed=0", final)
            if flags == [] and not (Path(directory) / "first").exists():
                (Path(directory) / "first").touch()
            elif not flags:
                assert re.search(r"changed=0", final), final
    assert Path("/var/lib/dpkg/status").read_bytes() == apt_before
    assert (
        subprocess.run(
            [
                "systemctl",
                "show",
                "nginx.service",
                "--property=ActiveState,UnitFileState",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        == nginx_before
    )
