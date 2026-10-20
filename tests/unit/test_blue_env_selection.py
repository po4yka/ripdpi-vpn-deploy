"""The warm-spare and blue-green Make recipes pass the selected blue environment."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Each Make target and its extra required arguments.
TARGETS = (
    ("blue-green", ["GREEN_ENV=green"]),
    ("promote-spare", ["OTP=synthetic"]),
    ("watch-spare", []),
)
SCRIPTS = ("blue-green.sh", "promote-spare.sh", "warm-spare-watcher.sh")


def run_target(tmp_path, target, arguments, environment):
    """Run the real recipe in a directory whose scripts only report BLUE_ENV."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script in SCRIPTS:
        (scripts / script).write_text('#!/bin/sh\necho "BLUE_ENV=$BLUE_ENV"\n')
        (scripts / script).chmod(0o700)
    env = {key: value for key, value in os.environ.items()
           if key not in ("ENV", "BLUE_ENV", "MAKEFLAGS", "MAKEFILES", "MFLAGS", "GNUMAKEFLAGS")}
    return subprocess.run(["make", "-s", "-C", str(tmp_path), "-f", str(ROOT / "Makefile"), target, *arguments],
                          check=False, env={**env, **environment}, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize(("target", "extra"), TARGETS)
@pytest.mark.parametrize(("arguments", "environment", "selected"), [
    ([], {}, "prod"),
    (["ENV=staging"], {}, "staging"),
    (["BLUE_ENV=prod-b"], {}, "prod-b"),
    ([], {"BLUE_ENV": "prod-b"}, "prod-b"),
    (["ENV=prod-b", "BLUE_ENV=prod-b"], {}, "prod-b"),
])
def test_blue_env_wins_over_the_default_environment(tmp_path, target, extra, arguments, environment,
                                                    selected):
    result = run_target(tmp_path, target, [*extra, *arguments], environment)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"BLUE_ENV={selected}"


@pytest.mark.parametrize(("target", "extra"), TARGETS)
@pytest.mark.parametrize(("arguments", "environment"), [
    (["ENV=staging", "BLUE_ENV=prod-b"], {}),
    (["BLUE_ENV=prod-b"], {"ENV": "staging"}),
])
def test_conflicting_env_and_blue_env_refuse_before_the_script(tmp_path, target, extra, arguments,
                                                               environment):
    result = run_target(tmp_path, target, [*extra, *arguments], environment)
    assert result.returncode != 0
    assert "BLUE_ENV and ENV select different environments" in result.stderr
    assert "BLUE_ENV=" not in result.stdout
