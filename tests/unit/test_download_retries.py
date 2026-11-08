"""Pinned release downloads survive a short upstream slowdown."""
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CURL_POLICY = "--retry 4 --retry-delay 10 --retry-max-time 480"
# These hosts did not time out in CI; only GitHub release fetches share this policy.
OTHER_HOSTS = ("https://go.dev/", "https://pkgs.tailscale.com/", "https://pkg.cloudflareclient.com/")


def _tracked(*patterns: str) -> list[str]:
    return subprocess.run(["git", "ls-files", *patterns], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()


def _get_url_tasks(tasks: object):
    for task in tasks if isinstance(tasks, list) else []:
        if isinstance(task, dict):
            if isinstance(task.get("ansible.builtin.get_url"), dict):
                yield task
            for key in ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks"):
                yield from _get_url_tasks(task.get(key))


def test_ansible_release_downloads_retry_each_bounded_attempt() -> None:
    checked, bad = 0, []
    for rel in _tracked("ansible/*.yml"):
        for task in _get_url_tasks(yaml.safe_load((ROOT / rel).read_text())):
            module = task["ansible.builtin.get_url"]
            if str(module["url"]).startswith(OTHER_HOSTS):
                continue
            checked += 1
            until = f"{task.get('register')} is succeeded"
            if (module.get("timeout"), task.get("retries"), task.get("delay"), task.get("until")) != (60, 5, 10, until):
                bad.append(f"{rel}: {task['name']}")
    assert checked >= 8
    assert not bad, "\n".join(bad)


def test_ci_curl_downloads_retry_each_bounded_attempt() -> None:
    commands = [
        (rel, line.strip())
        for rel in _tracked(".github/workflows/*.yml", ".github/actions/*/action.yml")
        for line in (ROOT / rel).read_text().splitlines()
        if re.match(r"\s*curl -", line)
    ]
    assert commands
    bad = [f"{rel}: {line}" for rel, line in commands if CURL_POLICY not in line or "--max-time" not in line]
    assert not bad, "\n".join(bad)


def test_ci_retries_terraform_registry_requests() -> None:
    env = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["env"]
    assert (env["TF_REGISTRY_DISCOVERY_RETRY"], env["TF_REGISTRY_CLIENT_TIMEOUT"]) == ("5", "30")
