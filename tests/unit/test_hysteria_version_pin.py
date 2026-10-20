"""Hysteria refuses non-stable runtime pins before acquisition."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "ansible" / "roles" / "hysteria" / "tasks" / "enable.yml"
PREFLIGHT = "Pre-flight — hysteria version must be an exact stable pin"


def _preflight_task() -> dict:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    names = [task.get("name") for task in tasks]
    acquisition = [
        index for index, task in enumerate(tasks)
        if "runtime_release_version" in str(task)
    ]
    assert acquisition and names.index(PREFLIGHT) < min(acquisition)
    return tasks[names.index(PREFLIGHT)]


@pytest.mark.parametrize(
    ("version", "accepted"),
    [
        ("v2.8.2", True),
        ("v2.13.0", True),
        ("", False),
        ("v2.9.0-rc1", False),
        ("2.8.2", False),
        ("v2.8", False),
    ],
)
def test_preflight_accepts_only_exact_stable_tags(tmp_path, version, accepted):
    playbook = tmp_path / "play.yml"
    playbook.write_text(yaml.safe_dump([{
        "hosts": "localhost",
        "gather_facts": False,
        "become": False,
        "vars": {"hysteria": {"version": version}},
        "tasks": [_preflight_task()],
    }], allow_unicode=True))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\n")
    env = {
        **os.environ,
        "ANSIBLE_CONFIG": str(config),
        "ANSIBLE_HOME": str(tmp_path / "home"),
        "ANSIBLE_LOCAL_TEMP": str(tmp_path / "tmp"),
    }
    result = subprocess.run(
        [shutil.which("ansible-playbook") or "ansible-playbook",
         "-i", "localhost,", "-c", "local", str(playbook)],
        check=False, capture_output=True, text=True, env=env, timeout=120,
    )
    assert (result.returncode == 0) is accepted, result.stdout[-2000:]
