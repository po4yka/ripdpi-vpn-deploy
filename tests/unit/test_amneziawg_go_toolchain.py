"""AmneziaWG builds use one checksum-pinned Go release and never fetch another."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = REPO_ROOT / "ansible" / "roles" / "amneziawg"
TASKS = yaml.safe_load((ROLE / "tasks" / "enable.yml").read_text(encoding="utf-8"))
DEFAULTS = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
NAMES = [task.get("name") for task in TASKS]


def task(name: str) -> dict:
    return TASKS[NAMES.index(name)]


def test_pin_matches_the_repository_go_toolchain_and_its_verified_digests():
    mise = tomllib.loads((REPO_ROOT / "mise.toml").read_text(encoding="utf-8"))
    lab = json.loads((REPO_ROOT / "tests/integration/awg_source_candidate/sources.json").read_text())
    assert DEFAULTS["amneziawg_go_toolchain_version"] == mise["tools"]["go"] == lab["go_toolchain"]
    assert DEFAULTS["amneziawg_go_toolchain_sha256"] == lab["go_toolchain_sha256"]


def test_build_uses_only_the_verified_toolchain():
    packages = task("Install build dependencies for AmneziaWG userspace")["ansible.builtin.apt"]["name"]
    assert "golang" not in packages
    download = task("Download the checksum-pinned Go toolchain")["ansible.builtin.get_url"]
    assert download["checksum"] == "sha256:{{ amneziawg_go_toolchain_sha256[_awg_go_toolchain_arch] }}"
    extract = task("Extract the pinned Go toolchain")["ansible.builtin.unarchive"]
    marker = task("Record the completed Go toolchain extraction")["ansible.builtin.copy"]
    # Only a completed extraction writes the marker that lets a later run skip it.
    assert extract["creates"] == marker["dest"] == "{{ _awg_go_toolchain_root }}/.extracted"
    assert (NAMES.index("Extract the pinned Go toolchain") < NAMES.index("Record the completed Go toolchain extraction")
            < NAMES.index("Converge pinned AmneziaWG source builds"))
    descriptors = task("Define pinned AmneziaWG source-build descriptors")["ansible.builtin.set_fact"]
    go_steps = descriptors["_amneziawg_build_descriptors"][0]["steps"]
    build = next(step for step in go_steps if step["argv"][0] == "/usr/bin/make")
    assert build["environment"]["GOTOOLCHAIN"] == "local"
    assert build["environment"]["PATH"].startswith("{{ _awg_go_toolchain_root }}/go/bin:")


@pytest.mark.parametrize(("architecture", "accepted"),
                         [("x86_64", True), ("aarch64", True), ("riscv64", False), ("armv7l", False)])
def test_unpinned_architectures_refuse_before_download(tmp_path, architecture, accepted):
    playbook = tmp_path / "play.yml"
    playbook.write_text(yaml.safe_dump([{
        "hosts": "localhost",
        "gather_facts": False,
        "become": False,
        "vars": {**{key: DEFAULTS[key] for key in ("amneziawg_go_toolchain_version",
                                                   "amneziawg_go_toolchain_sha256")},
                 # The repository config disables fact injection; only ansible_facts carries them.
                 "ansible_python_interpreter": sys.executable,
                 "ansible_facts": {"architecture": architecture}},
        "tasks": [task("Select the pinned Go toolchain for this architecture"),
                  task("Refuse an AmneziaWG build without a pinned Go toolchain")],
    }]))
    env = {**os.environ, "ANSIBLE_CONFIG": str(REPO_ROOT / "ansible/ansible.cfg"), "ANSIBLE_HOME": str(tmp_path / "home"),
           "ANSIBLE_LOCAL_TEMP": str(tmp_path / "tmp")}
    result = subprocess.run(
        [shutil.which("ansible-playbook") or "ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
        check=False, capture_output=True, text=True, env=env, timeout=120,
    )
    assert (result.returncode == 0) is accepted, result.stdout[-2000:]
    if not accepted:
        assert "amneziawg-go-toolchain-unpinned" in result.stdout
