"""Exact native APT merge and procps optional/mandatory failure semantics."""

from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
import pytest

from template_render import render_template

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
        config = root / "apt.conf"
        config.write_text(f'Dir::Etc::parts "{parts}";\nDir::Etc::main "";\n')
        for enabled in (True, False):
            policy = render_template(
                ROOT
                / "ansible/roles/package_updates/templates/51ripdpi-unattended-upgrades.j2",
                dict(package_updates={"enabled": enabled, "security_only": True}),
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


def test_procps_optional_congestion_keys_do_not_hide_mandatory_failure():
    assert os.geteuid() == 0
    source = ROOT / "ansible/roles/baseline/files/baseline_sysctl.py"
    template = (
        ROOT / "ansible/roles/baseline/templates/sysctl-vpn.conf.j2"
    ).read_text()
    optional = (
        "\n".join(line for line in template.splitlines() if line.startswith("-")) + "\n"
    )
    # All kernel writes stay within a disposable network namespace. Use the
    # actual role's optional statements alongside a real mandatory setting.
    code = r"""
import json,pathlib,subprocess,sys,tempfile
source,optional=sys.argv[1:]
def run(*argv):return subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,text=True)
current=run('/usr/sbin/sysctl','-n','net.ipv4.ip_forward');assert current.returncode==0
with tempfile.TemporaryDirectory(prefix='vpn-p2-congestion-') as directory:
 policy=pathlib.Path(directory)/'policy.conf'
 mandatory='net.ipv4.ip_forward = '+current.stdout.strip()+'\n'
 policy.write_text(mandatory+optional)
 positive=run('/usr/bin/python3',source,str(policy));assert positive.returncode==0,positive.stderr
 assert run('/usr/sbin/sysctl','-n','net.ipv4.ip_forward').stdout==current.stdout
 unavailable=optional.replace(' = bbr',' = vpn-test-unavailable')
 policy.write_text(mandatory+unavailable)
 failed_optional=run('/usr/bin/python3',source,str(policy))
 assert failed_optional.returncode==0 and failed_optional.stderr=='optional sysctl setting unavailable\n'
 policy.write_text(mandatory+unavailable+'net.ipv4.vpn_test_missing_mandatory = 1\n')
 mixed=run('/usr/bin/python3',source,str(policy))
 assert mixed.returncode==1 and mixed.stderr=='mandatory sysctl policy failed\n'
 print(json.dumps({'actual_optional_policy_positive':True,'optional_failure_preserves_mandatory':True,'mixed_mandatory_failure_remains_fatal':True}))
"""
    result = subprocess.run(
        ["unshare", "--net", "/usr/bin/python3", "-c", code, str(source), optional],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
