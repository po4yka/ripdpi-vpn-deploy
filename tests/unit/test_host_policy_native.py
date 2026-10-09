"""Exact native APT merge and procps optional/mandatory failure semantics."""

from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import pytest
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_security_only_policy_replaces_broader_effective_apt_origin_lists():
    with tempfile.TemporaryDirectory(prefix="vpn-p2-apt-") as directory:
        root = Path(directory)
        parts = root / "parts"
        parts.mkdir()
        (parts / "50-broad").write_text(
            'Unattended-Upgrade::Origins-Pattern { "origin=Ubuntu,codename=noble,label=Ubuntu"; };\nUnattended-Upgrade::Allowed-Origins { "Ubuntu:noble"; };\n'
        )
        source = (
            ROOT
            / "ansible/roles/package_updates/templates/51ripdpi-unattended-upgrades.j2"
        ).read_text()
        config = root / "apt.conf"
        config.write_text(f'Dir::Etc::parts "{parts}";\nDir::Etc::main "";\n')
        for enabled in (True, False):
            policy = (
                Environment(undefined=StrictUndefined, autoescape=False)
                .from_string(source)
                .render(package_updates={"enabled": enabled, "security_only": True})
            )
            (parts / "51-policy").write_text(policy)
            result = subprocess.run(
                ["apt-config", "dump"],
                env={**os.environ, "APT_CONFIG": str(config)},
                capture_output=True,
                text=True,
                check=True,
            )
            origins = [
                line
                for line in result.stdout.splitlines()
                if line.startswith(
                    (
                        "Unattended-Upgrade::Origins-Pattern::",
                        "Unattended-Upgrade::Allowed-Origins::",
                    )
                )
            ]
            assert len(origins) == 3 and not any(
                "codename=noble,label=Ubuntu" in line or 'Ubuntu:noble"' in line
                for line in origins
            )
            assert (
                f'APT::Periodic::Unattended-Upgrade "{int(enabled)}";' in result.stdout
            )


def test_procps_bbr_only_failure_is_optional_but_later_mandatory_failure_is_fatal():
    assert os.geteuid() == 0
    source = ROOT / "ansible/roles/baseline/files/baseline_sysctl.py"
    with tempfile.TemporaryDirectory(prefix="vpn-p2-sysctl-") as directory:
        root = Path(directory)
        policy = root / "policy.conf"
        # Unsupported algorithm is deliberately synthetic. No kernel value changes.
        policy.write_text("-net.ipv4.tcp_congestion_control = vpn-test-unavailable\n")
        native = subprocess.run(
            ["/usr/sbin/sysctl", "-p", str(policy)], capture_output=True
        )
        assert (
            native.returncode != 0
        ), "supported procps returns failure even for a marked optional algorithm"
        optional = subprocess.run(
            ["/usr/bin/python3", str(source), str(policy)],
            capture_output=True,
            text=True,
        )
        assert (
            optional.returncode == 0
            and optional.stderr == "optional sysctl setting unavailable\n"
        )
        policy.write_text(
            policy.read_text() + "net.ipv4.vpn_test_missing_mandatory = 1\n"
        )
        mixed = subprocess.run(
            ["/usr/bin/python3", str(source), str(policy)],
            capture_output=True,
            text=True,
        )
        assert (
            mixed.returncode == 1 and mixed.stderr == "mandatory sysctl policy failed\n"
        )
