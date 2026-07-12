"""Cloud-init must publish its completion marker only after SSH reload succeeds."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "terraform" / "shared" / "cloud-init.yaml.tftpl"
RENDERER = REPO_ROOT / "scripts" / "render-cloud-init-ci.py"
MARKER = "/var/lib/cloud-init-vpn-bootstrap.done"


def test_bootstrap_marker_depends_on_validated_successful_ssh_reload(
    tmp_path: Path,
) -> None:
    rendered = subprocess.run(
        [sys.executable, str(RENDERER)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rendered_config = yaml.safe_load(rendered)
    assert rendered_config["users"][1]["name"] == "deploy"
    assert "${" not in rendered

    cloud_config = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    commands = cloud_config["runcmd"]

    assert len(commands) == 1
    assert commands[0][:2] == ["sh", "-c"]
    command = commands[0][2]
    assert command.index("install -d -m 0755 /run/sshd") < command.index("sshd -t")
    assert command.index("sshd -t") < command.index("systemctl reload ssh")
    assert command.index("systemctl reload ssh") < command.index(f"touch {MARKER}")

    sshd = tmp_path / "sshd"
    sshd.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sshd.chmod(0o755)
    systemctl = tmp_path / "systemctl"
    systemctl.write_text('#!/bin/sh\nexit "${SYSTEMCTL_RC:?}"\n', encoding="utf-8")
    systemctl.chmod(0o755)
    marker = tmp_path / "bootstrap.done"
    executable = (
        command.replace("install -d -m 0755 /run/sshd && ", "")
        .replace("/usr/sbin/sshd", str(sshd))
        .replace("systemctl", str(systemctl))
        .replace(MARKER, str(marker))
    )

    failed = subprocess.run(
        ["sh", "-c", executable],
        env={**os.environ, "SYSTEMCTL_RC": "1"},
        check=False,
    )
    assert failed.returncode != 0
    assert not marker.exists()

    succeeded = subprocess.run(
        ["sh", "-c", executable],
        env={**os.environ, "SYSTEMCTL_RC": "0"},
        check=False,
    )
    assert succeeded.returncode == 0
    assert marker.exists()

    already_completed = subprocess.run(
        ["sh", "-c", executable],
        env={**os.environ, "SYSTEMCTL_RC": "1"},
        check=False,
    )
    assert already_completed.returncode == 0
    assert marker.exists()
