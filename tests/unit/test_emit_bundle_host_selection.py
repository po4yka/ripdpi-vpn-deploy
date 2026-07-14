"""Regression coverage for multi-host RIPDPI bundle endpoint selection."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_awg_uses_the_host_where_amneziawg_is_enabled(tmp_path: Path) -> None:
    for tool in ("jq", "python3"):
        if not shutil.which(tool):
            pytest.skip(f"required binary not found on PATH: {tool}")

    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    group_vars = repo / "ansible" / "group_vars"
    provider_roots = [
        repo / "terraform" / "providers" / "upcloud",
        repo / "terraform" / "providers" / "vultr",
    ]
    scripts.mkdir(parents=True)
    group_vars.mkdir(parents=True)
    for provider_root in provider_roots:
        provider_root.mkdir(parents=True)

    shutil.copy2(REPO_ROOT / "scripts" / "emit-bundle.sh", scripts / "emit-bundle.sh")
    shutil.copy2(
        REPO_ROOT / "scripts" / "ripdpi_cohort_fingerprint.py",
        scripts / "ripdpi_cohort_fingerprint.py",
    )
    (scripts / "emit-singbox.sh").write_text("#!/bin/sh\nprintf '{\"outbounds\":[]}'\n")
    (scripts / "terraform-env.sh").write_text(
        "#!/bin/sh\n"
        "if [ \"$PROVIDER\" = upcloud ]; then printf '192.0.2.10'; "
        "else printf '198.51.100.20'; fi\n"
    )
    for script in scripts.iterdir():
        script.chmod(0o700)

    (group_vars / "all.yml").write_text(yaml.safe_dump({"vpn": {}}))
    (group_vars / "vpn.yml").write_text(yaml.safe_dump({}))
    (group_vars / "vpn-p0.yml").write_text(
        yaml.safe_dump({"vpn": {"enable_amneziawg": False}})
    )
    (group_vars / "vpn-p2.yml").write_text(
        yaml.safe_dump({"vpn": {"enable_amneziawg": True}})
    )

    secrets = tmp_path / "secrets.json"
    secrets.write_text(
        json.dumps(
            {
                "amneziawg_secrets": {
                    "server_private_key": "server-private-fixture",
                    "listen_port": 51820,
                    "jc": 4,
                    "jmin": 40,
                    "jmax": 70,
                    "s1": 50,
                    "s2": 100,
                    "h1": 1,
                    "h2": 2,
                    "h3": 3,
                    "h4": 4,
                    "peers": [
                        {
                            "name": "android-ripdpi",
                            "public_key": "client-public-fixture",
                            "preshared_key": "client-psk-fixture",
                            "allowed_ips": "10.66.66.4/32",
                        }
                    ],
                }
            }
        )
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "sops").write_text("#!/bin/sh\ncat \"$SOPS_FILE\"\n")
    (fake_bin / "terraform").write_text("#!/bin/sh\nexit 0\n")
    (fake_bin / "wg").write_text("#!/bin/sh\nprintf 'server-public-fixture'\n")
    for stub in fake_bin.iterdir():
        stub.chmod(0o700)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "SOPS_FILE": str(secrets),
            "HOSTS": "upcloud:p0,vultr:p2",
            "COHORTS": "p0,p2",
        }
    )
    result = subprocess.run(
        ["bash", str(scripts / "emit-bundle.sh"), "android-ripdpi"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    bundle = json.loads(result.stdout)
    assert bundle["ripdpi"]["amneziawg"][0]["peer"]["endpoint"] == (
        "198.51.100.20:51820"
    )
