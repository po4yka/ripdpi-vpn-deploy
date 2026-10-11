"""Regression coverage for multi-host RIPDPI bundle endpoint selection."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("hosts", "cohorts"),
    (
        ("upcloud:p0,vultr:p2", "p0,p2"),
        ("vultr:p2,upcloud:p0", "p2,p0"),
    ),
)
def test_bundle_uses_feature_host_and_emits_ingress_topology(
    tmp_path: Path, hosts: str, cohorts: str
) -> None:
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
    shutil.copy2(REPO_ROOT / "scripts" / "transport_semantics.py", scripts / "transport_semantics.py")
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

    (group_vars / "all.yml").write_text(yaml.safe_dump({"vpn": {"enable_xray_reality": False}}))
    (group_vars / "vpn.yml").write_text(yaml.safe_dump({}))
    (group_vars / "vpn-p0.yml").write_text(
        yaml.safe_dump(
            {
                "vpn": {
                    "enable_amneziawg": False,
                    "enable_split_hop_ingress": True,
                }
            }
        )
    )
    (group_vars / "vpn-p2.yml").write_text(
        yaml.safe_dump({"vpn": {"enable_amneziawg": True}})
    )

    secrets = tmp_path / "secrets.json"
    secrets.write_text(
        json.dumps(
            {
                "amneziawg_secrets": {
                    "server_private_key": base64.b64encode(bytes([8]) * 32).decode(),
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
                            "public_key": "CQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk=",
                            "preshared_key": "CgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgo=",
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
    (fake_bin / "wg").write_text("#!/bin/sh\ncat >/dev/null\nprintf 'server-public-fixture'\n")
    for stub in fake_bin.iterdir():
        stub.chmod(0o700)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "SOPS_FILE": str(secrets),
            "HOSTS": hosts,
            "COHORTS": cohorts,
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
    assert bundle["ripdpi"]["topology"] == {
        "split_hop_egress": True,
        "hysteria_realm": None,
    }


@pytest.mark.parametrize("script", ["emit-bundle.sh", "emit-awg.sh", "new-client.sh"])
def test_actual_consumed_top_level_awg_view_cannot_hide_behind_valid_instance(tmp_path, script):
    """Exercise actual consumers with isolated IO; this is not tunnel proof."""
    import copy
    from transport_semantics import transport_errors

    test_bundle_uses_feature_host_and_emits_ingress_topology(tmp_path, "upcloud:p0,vultr:p2", "p0,p2")
    repo = tmp_path / "repo"
    secrets_path = tmp_path / "secrets.json"
    payload = json.loads(secrets_path.read_text())
    source = payload["amneziawg_secrets"]
    instance = copy.deepcopy(source)
    instance.update(name="awg-selected", listen_port=52999)
    source["instances"] = [instance]
    source["jmin"] = source["jmax"] + 1
    # The runtime-effective declaration remains valid; the existing consumer
    # actually reads the now-invalid top-level values and must check that view.
    assert not transport_errors(payload, sections=["awg"])
    secrets_path.write_text(json.dumps(payload))
    before = secrets_path.read_bytes()
    target = repo / "scripts" / script
    shutil.copyfile(REPO_ROOT / "scripts" / script, target)
    target.chmod(0o700)
    marker = tmp_path / "generation"
    (tmp_path / "bin" / "uuidgen").write_text('#!/bin/sh\ntouch "$GENERATION_MARKER"\nprintf "00000000-0000-4000-8000-000000000001"\n')
    (tmp_path / "bin" / "uuidgen").chmod(0o700)
    environment = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
                   "SOPS_FILE": str(secrets_path), "HOSTS": "vultr:p2", "COHORTS": "p2",
                   "PROVIDER": "vultr", "ENV": "p2", "GENERATION_MARKER": str(marker)}
    result = subprocess.run(["bash", str(target), "android-ripdpi"], cwd=repo,
                            env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "junk bounds must be ordered" in result.stderr
    assert not result.stdout
    assert secrets_path.read_bytes() == before and not marker.exists()
