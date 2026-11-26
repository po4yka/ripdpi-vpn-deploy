"""Every infrastructure CLI install and root names one exact OpenTofu release."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_OPENTOFU = "opentofu/setup-opentofu@a1320f892987e89d278cc92dc5adc984fb93aca4"
SUPPORTED_VERSION = "1.13.10"
LINUX_AMD64_SHA256 = "c1f0d6b34d8328f963d3b1ad10896fae30a6c6890596190ffef477dab991090f"
INSTALLERS = (
    ".github/workflows/ci.yml",
    ".github/workflows/tf-policy.yml",
    ".github/actions/setup-disposable-ci/action.yml",
)


def setup_steps(path: str) -> list[dict]:
    document = yaml.safe_load((REPO_ROOT / path).read_text())
    jobs = document.get("jobs", {}).values() if "jobs" in document else [document["runs"]]
    return [step for job in jobs for step in job.get("steps", []) if "setup-" in step.get("uses", "")]


def test_every_installer_pins_one_checksummed_opentofu_release():
    pins = {}
    for path in INSTALLERS:
        steps = [step for step in setup_steps(path) if step["uses"].startswith("opentofu/setup-opentofu@")]
        assert steps, f"{path} must install OpenTofu"
        for step in steps:
            assert step["uses"] == SETUP_OPENTOFU, path
            assert step["with"]["tofu_wrapper"] is False, path
            assert step["with"]["checksums"] == LINUX_AMD64_SHA256, path
            pins[path] = step["with"]["tofu_version"]
    mise = re.search(r'^opentofu = "([^"]+)"$', (REPO_ROOT / "mise.toml").read_text(), re.MULTILINE)
    assert mise, "mise.toml must pin opentofu"
    pins["mise.toml"] = mise[1]
    assert set(pins.values()) == {SUPPORTED_VERSION}, pins


def test_no_installer_or_tool_pin_selects_terraform():
    for path in INSTALLERS:
        assert all("setup-terraform" not in step["uses"] for step in setup_steps(path)), path
    assert not re.search(r"^terraform\s*=", (REPO_ROOT / "mise.toml").read_text(), re.MULTILINE)


def test_every_root_requires_the_pinned_release():
    roots = sorted(REPO_ROOT.glob("terraform/**/versions.tf"))
    assert roots
    for versions in roots:
        assert f'required_version = "{SUPPORTED_VERSION}"' in versions.read_text(), versions


def test_ci_initializes_all_roots_with_frozen_provider_locks():
    for name in ("ci.yml", "tf-policy.yml"):
        jobs = yaml.safe_load((REPO_ROOT / ".github/workflows" / name).read_text())["jobs"]
        commands = [
            shlex.split(line)
            for job in jobs.values()
            for step in job.get("steps", [])
            for line in step.get("run", "").splitlines()
            if line.strip().startswith("tofu init ")
        ]
        assert commands
        assert all("-lockfile=readonly" in command for command in commands), name
