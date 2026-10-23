"""Exercise CI package-source boundaries and failure propagation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["schema", "disposable"])
def installer(request):
    if request.param == "schema":
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
        steps = workflow["jobs"]["cloud-init"]["steps"]
        name = "Install cloud-init"
        install_args = ["install", "-y", "cloud-init"]
    else:
        action = yaml.safe_load(
            (ROOT / ".github/actions/setup-disposable-ci/action.yml").read_text()
        )
        steps = action["runs"]["steps"]
        name = "Install system dependencies"
        install_args = [
            "install", "-y", "--no-install-recommends", "age", "jq",
            "wireguard-tools", "uuid-runtime", "e2fsprogs", "openssh-server", "unzip",
        ]
    return next(step["run"] for step in steps if step.get("name") == name), install_args


@pytest.mark.parametrize("update_status, install_status", [(0, 0), (100, 0), (0, 100)])
def test_install_isolated_from_unrelated_runner_sources(
    tmp_path, installer, update_status, install_status,
):
    script, install_args = installer
    sources = tmp_path / "ubuntu.sources"
    sources.write_text("Types: deb\nURIs: https://archive.ubuntu.com/ubuntu\n")
    script = script.replace("/etc/apt/sources.list.d/ubuntu.sources", str(sources))
    calls = tmp_path / "calls.jsonl"
    apt = tmp_path / "apt-get"
    apt.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['APT_CALLS'], 'a') as out:\n"
        "    out.write(json.dumps(args) + '\\n')\n"
        "required = {'Dir::Etc::sourcelist=' + os.environ['UBUNTU_SOURCES'],\n"
        "            'Dir::Etc::sourceparts=-', 'APT::Update::Error-Mode=any'}\n"
        "options = {args[i + 1] for i, arg in enumerate(args[:-1]) if arg == '-o'}\n"
        "if not required <= options: sys.exit(43)  # unrelated source returns 403\n"
        "if 'update' in args: sys.exit(int(os.environ['UPDATE_STATUS']))\n"
        "sys.exit(int(os.environ['INSTALL_STATUS']))\n"
    )
    apt.chmod(0o755)
    mke2fs = tmp_path / "mke2fs"
    mke2fs.write_text('#!/bin/sh\nprintf "mke2fs 1.47.0\\n" >&2\n')
    mke2fs.chmod(0o755)
    sudo = tmp_path / "sudo"
    sudo.write_text('#!/bin/sh\nexec "$@"\n')
    sudo.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
             "APT_CALLS": str(calls), "UBUNTU_SOURCES": str(sources),
             "UPDATE_STATUS": str(update_status), "INSTALL_STATUS": str(install_status)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == (update_status or install_status), result.stderr
    invoked = [json.loads(line) for line in calls.read_text().splitlines()]
    assert len(invoked) == (2 if update_status == 0 else 1)
    assert invoked[0][-1] == "update"
    if update_status == 0:
        assert invoked[1][-len(install_args):] == install_args


def test_schema_validator_remains_enabled():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["cloud-init"]["steps"]
    validator = next(step["run"] for step in steps
                     if step.get("name") == "Validate with cloud-init schema")
    assert validator == "cloud-init schema --config-file /tmp/cloud-init.rendered.yaml"


def test_install_refuses_missing_ubuntu_sources(tmp_path, installer):
    script, _ = installer
    script = script.replace("/etc/apt/sources.list.d/ubuntu.sources", str(tmp_path / "absent"))
    sudo = tmp_path / "sudo"
    sudo.write_text('#!/bin/sh\necho unexpected-package-operation >&2\nexit 43\n')
    sudo.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True, check=False,
    )
    assert result.returncode == 1
    assert b"unexpected-package-operation" not in result.stderr
