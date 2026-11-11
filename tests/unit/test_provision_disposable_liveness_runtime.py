"""Offline boundaries of the disposable executor runtime provisioner; no VM or network."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import re
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load("provision_runtime", ROOT / "scripts/provision-disposable-liveness-runtime.py")


def test_inputs_come_from_the_sentinel_role_plus_a_new_enough_go(module):
    packages, commits = module.role_inputs()
    assert {"build-essential", "git", "iproute2", "nftables", "python3", "curl", "golang-1.24-go"} <= set(packages)
    assert commits == {"go": "2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf",
                       "tools": "c0b400c6dfc046f5cae8f3051b14cb61686fcf55"}


def test_engine_pins_match_the_ci_pins_of_the_same_releases(module):
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    environment = {key: str(value) for job in ci["jobs"].values() for step in job.get("steps", [])
                   for key, value in (step.get("env") or {}).items()}
    environment.update({key: str(value) for job in ci["jobs"].values() for key, value in (job.get("env") or {}).items()})
    sing_box = module.ENGINES["sing-box"]
    assert sing_box["version"] == environment["SING_BOX_CLIENT_VERSION"]
    assert sing_box["archives"]["amd64"][1] == environment["SING_BOX_CLIENT_LINUX_AMD64_SHA256"]
    action = yaml.safe_load((ROOT / ".github/actions/install-xray/action.yml").read_text())
    xray_env = action["runs"]["steps"][0]["env"]
    assert "v" + module.ENGINES["xray"]["version"] == xray_env["XRAY_VERSION"]
    assert module.ENGINES["xray"]["archives"]["amd64"][1] == xray_env["XRAY_SHA256"]
    # The local parser pins of the liveness installer must name the same versions.
    make = (ROOT / "Makefile").read_text()
    assert f"--sing-box-version {sing_box['version']} --xray-version {module.ENGINES['xray']['version']}" in make


@pytest.mark.parametrize("kind", ["tar", "zip"])
def test_engine_binary_reads_only_the_pinned_member(module, kind):
    name, archive_name = ("sing-box", "sing-box-1.14.3-linux-arm64.tar.gz") if kind == "tar" else ("xray", "Xray-linux-arm64-v8a.zip")
    member = "sing-box-1.14.3-linux-arm64/sing-box" if kind == "tar" else "xray"
    def archive_with(path: str) -> bytes:
        buffer = io.BytesIO()
        if kind == "tar":
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                info = tarfile.TarInfo(path)
                info.size = 6
                archive.addfile(info, io.BytesIO(b"engine"))
        else:
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(path, b"engine")
        return buffer.getvalue()

    assert module.engine_binary(name, archive_name, archive_with(member), "arm64") == b"engine"
    with pytest.raises(module.ProvisionError, match="archive-member"):
        module.engine_binary(name, archive_name, archive_with("README.md"), "arm64")


def test_vendor_archive_is_deterministic_and_accepted_by_the_offline_builder(module, tmp_path):
    installer = load("awg_installer", ROOT / "scripts/install-real-vps-awg-client-tools.py")
    source = tmp_path / "source"
    (source / "vendor/example.org/lib").mkdir(parents=True)
    (source / "vendor/modules.txt").write_text("# example.org/lib v1.0.0\n")
    (source / "vendor/example.org/lib/lib.go").write_text("package lib\n")
    (source / "go.mod").write_text("module example\n")
    first = module.vendor_archive(source, tmp_path / "one.tar")
    os.utime(source / "vendor/modules.txt", (1, 1))
    second = module.vendor_archive(source, tmp_path / "two.tar")
    assert first == second == hashlib.sha256((tmp_path / "one.tar").read_bytes()).hexdigest()
    with tarfile.open(tmp_path / "one.tar") as archive:
        members = archive.getmembers()
        installer.validate_vendor(members)
    assert {member.name for member in members} == {
        "vendor", "vendor/modules.txt", "vendor/example.org", "vendor/example.org/lib", "vendor/example.org/lib/lib.go"}


@pytest.mark.parametrize("fault", ["mode", "nonempty"])
def test_work_directory_must_be_private_and_empty(module, tmp_path, fault):
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    if fault == "mode":
        work.chmod(0o755)
    else:
        (work / "stale").write_text("")
    with pytest.raises(module.ProvisionError, match="^work-directory$"):
        module.private_work_directory(work)


def test_version_parser_reads_engine_and_awg_banners(module):
    assert module.version_of("sing-box version 1.14.3\n\nEnvironment: go1.24") == "1.14.3"
    assert module.version_of("Xray 26.10.31 (Xray, Penetrates Everything.)") == "26.10.31"
    assert re.fullmatch(r"\d+\.\d+\.\d+", module.version_of("awg v1.0.20241018 - https://amnezia.org"))
