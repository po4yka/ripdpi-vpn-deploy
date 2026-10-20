"""site.yml refuses host releases whose nftables lacks `destroy table`."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "ansible" / "playbooks" / "site.yml"
GUARD = "Refuse host operating systems older than Debian 13 or Ubuntu 24.04"


def _guard_task() -> dict:
    pre_tasks = yaml.safe_load(SITE.read_text(encoding="utf-8"))[0]["pre_tasks"]
    names = [task.get("name") for task in pre_tasks]
    # Every pre-task before the guard is an assertion or a read-only preflight.
    assert names.index(GUARD) < names.index("Validate reviewed network exposure policy before host changes")
    return pre_tasks[names.index(GUARD)]


@pytest.mark.parametrize(
    ("distribution", "major", "version", "accepted"),
    [
        ("Debian", "13", "13.1", True),
        ("Debian", "14", "14", True),
        ("Ubuntu", "24", "24.04", True),
        ("Ubuntu", "24", "24.10", True),
        ("Debian", "12", "12.11", False),
        ("Ubuntu", "22", "22.04", False),
        ("Rocky", "9", "9.4", False),
    ],
)
def test_site_admits_only_supported_host_releases(tmp_path, distribution, major, version, accepted):
    playbook = tmp_path / "play.yml"
    playbook.write_text(yaml.safe_dump([{
        "hosts": "localhost",
        "gather_facts": False,
        "become": False,
        # The repository config disables fact injection; only ansible_facts carries them.
        "vars": {"ansible_python_interpreter": sys.executable,
                 "ansible_facts": {"distribution": distribution, "distribution_major_version": major,
                                   "distribution_version": version}},
        "tasks": [_guard_task()],
    }]))
    env = {**os.environ, "ANSIBLE_CONFIG": str(REPO_ROOT / "ansible/ansible.cfg"), "ANSIBLE_HOME": str(tmp_path / "home"),
           "ANSIBLE_LOCAL_TEMP": str(tmp_path / "tmp")}
    result = subprocess.run(
        [shutil.which("ansible-playbook") or "ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
        check=False, capture_output=True, text=True, env=env, timeout=120,
    )
    assert (result.returncode == 0) is accepted, result.stdout[-2000:]
    if not accepted:
        assert "unsupported-host-os" in result.stdout
