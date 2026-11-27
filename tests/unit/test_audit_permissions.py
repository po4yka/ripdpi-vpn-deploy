"""audit-permissions finds plaintext where decrypt-secrets.sh actually writes it."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _audit(tmp_path: Path) -> subprocess.CompletedProcess:
    environment = {key: value for key, value in os.environ.items() if key != "VPN_RUNTIME_DIR"}
    environment.update(HOME=str(tmp_path / "home"), XDG_RUNTIME_DIR=str(tmp_path / "run"), TMPDIR=str(tmp_path / "tmp"))
    return subprocess.run(["bash", str(ROOT / "scripts/audit-permissions.sh")], env=environment,
                          capture_output=True, text=True, timeout=30, check=False)


def test_plaintext_left_in_the_runtime_directory_is_a_finding(tmp_path):
    runtime = tmp_path / "run"
    runtime.mkdir()
    (tmp_path / "tmp").mkdir()
    assert _audit(tmp_path).returncode == 0
    left = runtime / "vpn-prod.secrets.yaml"
    candidate = runtime / ".vpn-prod.secrets.Ab12Cd"  # an interrupted decrypt's private candidate
    for path in (left, candidate):
        path.write_text("synthetic: value\n")
    result = _audit(tmp_path)
    assert result.returncode == 1
    assert f"FAIL stray plaintext: {left}" in result.stdout
    assert f"FAIL stray plaintext: {candidate}" in result.stdout
