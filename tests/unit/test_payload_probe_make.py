"""Canonical Make probe rejects executable input before any network request."""
import os
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["HOST", "PORT", "SIZES", "ASN", "SOCKS_PORT", "UPLOAD", "CA_FILE", "SCHEME", "ECHO_PATH", "TIMEOUT", "NO_STATE"])
@pytest.mark.parametrize("value", ["$(shell touch injected)", "$(touch injected)", "1; touch injected", "1`touch injected`"])
def test_probe_make_preserves_literal_inputs(tmp_path, name, value):
    shutil.copy2(ROOT / "Makefile", tmp_path / "Makefile")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script in ["probe-payload-throttle.sh", "payload_probe_content.py"]:
        shutil.copy2(ROOT / "scripts" / script, scripts / script)
    arguments = {"HOST": "localhost", name: value}
    environment = {key: item for key, item in os.environ.items()
                   if not key.startswith("MAKE") and key not in {"MFLAGS", "GNUMAKEFLAGS"}}
    result = subprocess.run(["make", "probe-payload-throttle", *(f"{key}={item}" for key, item in arguments.items())],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    if name in {"UPLOAD", "NO_STATE"}:
        assert result.returncode != 0
    else:
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"verdict": "error", "rtt_ms": None, "error_kind": "probe-error"}
    assert not (tmp_path / "injected").exists()
