"""Regression coverage for version-aware Xray geodata activation."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from template_render import merge_render_vars, render_template


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    REPO_ROOT
    / "ansible"
    / "roles"
    / "geodata"
    / "templates"
    / "vpn-xray-geodata-activate.sh.j2"
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_activation(tmp_path: Path, xray_version: str) -> list[str]:
    script = tmp_path / "activate.sh"
    script.write_text(
        render_template(TEMPLATE, merge_render_vars()),
        encoding="utf-8",
    )
    script.chmod(0o755)

    log = tmp_path / "systemctl.log"
    xray = tmp_path / "xray"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        xray,
        f"#!/usr/bin/env bash\nprintf 'Xray {xray_version} test-build\\n'\n",
    )
    _write_executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
exit 0
""",
    )

    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SYSTEMCTL_LOG": str(log),
        "XRAY_BIN": str(xray),
    }
    subprocess.run(["bash", str(script)], env=env, check=True)
    return log.read_text(encoding="utf-8").splitlines()


def test_pre_hot_reload_xray_is_restarted_instead_of_killed(tmp_path: Path) -> None:
    calls = _run_activation(tmp_path, "26.3.27")

    assert "restart xray.service" in calls
    assert "kill --signal=HUP xray.service" not in calls
    assert calls[-1] == "is-active --quiet xray.service"


def test_hot_reload_capable_xray_receives_hup(tmp_path: Path) -> None:
    calls = _run_activation(tmp_path, "26.4.0")

    assert "kill --signal=HUP xray.service" in calls
    assert "restart xray.service" not in calls
    assert calls[-1] == "is-active --quiet xray.service"
