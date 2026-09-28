"""Exercise the schema job's package-source boundary and failure propagation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("update_status", [0, 100])
def test_schema_install_isolated_from_unrelated_runner_sources(tmp_path, update_status):
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["cloud-init"]["steps"]
    script = next(step["run"] for step in steps if step.get("name") == "Install cloud-init")
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
    )
    apt.chmod(0o755)
    sudo = tmp_path / "sudo"
    sudo.write_text('#!/bin/sh\nexec "$@"\n')
    sudo.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-c", script],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
             "APT_CALLS": str(calls), "UBUNTU_SOURCES": str(sources),
             "UPDATE_STATUS": str(update_status)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == update_status, result.stderr
    invoked = [json.loads(line) for line in calls.read_text().splitlines()]
    assert len(invoked) == (2 if update_status == 0 else 1)
    assert invoked[0][-1] == "update"
    if update_status == 0:
        assert invoked[1][-3:] == ["install", "-y", "cloud-init"]
    validator = next(step["run"] for step in steps
                     if step.get("name") == "Validate with cloud-init schema")
    assert validator == "cloud-init schema --config-file /tmp/cloud-init.rendered.yaml"


def test_schema_install_refuses_missing_ubuntu_sources(tmp_path):
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    script = next(step["run"] for step in workflow["jobs"]["cloud-init"]["steps"]
                  if step.get("name") == "Install cloud-init")
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
