"""Execute the CI installer with real ZIP/hash tools and a local download fixture."""

import hashlib
import os
from pathlib import Path
import subprocess
import zipfile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github/actions/install-xray/action.yml"


def installer():
    return yaml.safe_load(ACTION.read_text())["runs"]["steps"][0]


def test_ci_xray_consumers_share_one_reviewed_pin():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for job in ("templates-render", "unit-tests"):
        steps = workflow["jobs"][job]["steps"]
        installs = [s for s in steps if s.get("uses") == "./.github/actions/install-xray"]
        assert len(installs) == 1
        assert "with" not in installs[0]
    assert "Xray-linux-64.zip" not in (ROOT / ".github/workflows/ci.yml").read_text()
    pin = installer()["env"]
    example = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    assert pin["XRAY_VERSION"] == example["xray"]["version"]
    assert len(pin["XRAY_SHA256"]) == 64
    assert set(pin["XRAY_SHA256"]) <= set("0123456789abcdef")


@pytest.mark.parametrize("case", ["valid", "corrupt", "download-error", "version-drift", "runtime-error"])
def test_installer_never_executes_or_installs_unverified_bytes(tmp_path, case):
    step = installer()
    repo = tmp_path / "repo"
    (repo / "secrets").mkdir(parents=True)
    version = "v0.0.0" if case == "version-drift" else step["env"]["XRAY_VERSION"]
    (repo / "secrets/prod.secrets.example.yaml").write_text(
        yaml.safe_dump({"xray": {"version": version}})
    )
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as fixture:
        fixture.writestr("xray", '#!/bin/sh\necho executed >> "$EXEC_LOG"\nexit ' +
                         ("7" if case == "runtime-error" else "0") + "\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if case == "corrupt":
        with archive.open("ab") as stream:
            stream.write(b"tampered")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/usr/bin/env python3\nimport os, pathlib, shutil, sys\n'
        'pathlib.Path(os.environ["DOWNLOAD_LOG"]).write_text("called")\n'
        'if os.environ["DOWNLOAD_ERROR"] == "true": sys.exit(22)\n'
        'args = sys.argv[1:]\n'
        'assert "https://github.com/XTLS/Xray-core/releases/download/" + '
        'os.environ["XRAY_VERSION"] + "/Xray-linux-64.zip" in args\n'
        'shutil.copyfile(os.environ["FIXTURE"], args[args.index("-o") + 1])\n'
    )
    curl.chmod(0o755)
    sudo = bin_dir / "sudo"
    sudo.write_text(
        '#!/usr/bin/env python3\nimport os, shutil, sys\n'
        'assert sys.argv[1:4] == ["install", "-m", "0755"]\n'
        'assert sys.argv[5:] == ["/usr/local/bin/xray"]\n'
        'shutil.copyfile(sys.argv[4], os.environ["INSTALLED"])\n'
    )
    sudo.chmod(0o755)
    runner_temp = tmp_path / "runner temp"
    runner_temp.mkdir()
    installed = tmp_path / "installed-xray"
    installed.write_text("existing runtime")
    env = dict(os.environ, **step["env"])
    env.update(XRAY_SHA256=digest, PATH=f"{bin_dir}:{os.environ['PATH']}",
               RUNNER_TEMP=str(runner_temp), INSTALLED=str(installed),
               FIXTURE=str(archive), EXEC_LOG=str(tmp_path / "executed"),
               DOWNLOAD_LOG=str(tmp_path / "downloaded"),
               DOWNLOAD_ERROR=str(case == "download-error").lower())
    result = subprocess.run(["bash", "-c", step["run"]], cwd=repo, env=env,
                            capture_output=True, text=True, timeout=15)
    assert (result.returncode == 0) == (case == "valid"), result.stderr
    assert (tmp_path / "executed").exists() == (case in {"valid", "runtime-error"})
    if case == "valid":
        with zipfile.ZipFile(archive) as fixture:
            assert installed.read_bytes() == fixture.read("xray")
    else:
        assert installed.read_text() == "existing runtime"
    if case in {"corrupt", "download-error"}:
        assert not list(runner_temp.rglob("xray"))
    if case == "version-drift":
        assert not (tmp_path / "downloaded").exists()
