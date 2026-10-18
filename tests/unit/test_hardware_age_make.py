"""The hardware Make boundary passes selectors as literal data before access."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def target(tmp_path):
    shutil.copyfile(ROOT / "Makefile", tmp_path / "Makefile")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    helper = scripts / "setup-yubikey-age.sh"
    helper.write_text("#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nPath('called.json').write_text(json.dumps(sys.argv[1:]))\n")
    helper.chmod(0o700)
    return tmp_path


def run(target, *arguments):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("MAKE") and key not in {"MFLAGS", "GNUMAKEFLAGS"}}
    return subprocess.run(["make", "setup-yubikey", *arguments], cwd=target,
                          env=environment, capture_output=True, text=True, timeout=10, check=False)


def test_canonical_make_passes_explicit_generation_and_migration(target):
    result = run(target, "YUBIKEY_SERIAL=1234", "YUBIKEY_SLOT=2", "YUBIKEY_GENERATE=1", "REENCRYPT=1")
    assert result.returncode == 0, result.stderr
    assert json.loads((target / "called.json").read_text()) == ["--serial", "1234", "--slot", "2", "--generate", "--reencrypt"]


def test_canonical_make_resumes_without_generating(target):
    result = run(target, "YUBIKEY_SERIAL=1234", "YUBIKEY_SLOT=2")
    assert result.returncode == 0, result.stderr
    assert "--generate" not in json.loads((target / "called.json").read_text())


@pytest.mark.parametrize("name", ["YUBIKEY_SERIAL", "YUBIKEY_SLOT", "YUBIKEY_GENERATE", "REENCRYPT"])
@pytest.mark.parametrize("value", ["$(shell touch injected)", "$(touch injected)", "1; touch injected", "1`touch injected`"])
def test_make_and_shell_payloads_refuse_without_execution(target, name, value):
    arguments = {"YUBIKEY_SERIAL": "1234", "YUBIKEY_SLOT": "2"}
    arguments[name] = value
    result = run(target, *(key + "=" + item for key, item in arguments.items()))
    assert result.returncode != 0
    assert not (target / "injected").exists()
    assert not (target / "called.json").exists()


def test_hardware_target_refuses_multiple_goals_before_access(target):
    result = run(target, "YUBIKEY_SERIAL=1234", "YUBIKEY_SLOT=2", "workspace-status")
    assert result.returncode != 0
    assert not (target / "called.json").exists()
