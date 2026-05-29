"""Verify that the Xray-core version pin is consistent across the repo.

Cross-checks:
  docs/XRAY-RELEASE-LINE.md  — the heading marked "(current Latest"
  secrets/prod.secrets.example.yaml → xray.version  — the canonical pin

Both must agree. A mismatch means either the doc was updated after a release
bump without also bumping the example schema, or vice-versa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check-xray-version-pin.py"


def test_xray_version_pin_consistent():
    """check-xray-version-pin.py exits 0 when doc and pin agree."""
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Xray-core version pin mismatch between docs/XRAY-RELEASE-LINE.md "
        "and secrets/prod.secrets.example.yaml.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
