"""Exercise the actual recovery budget reader/writer, including unsafe state."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "ansible/roles/watchdog/files/vpn-watchdog-state.py"
KEYS = (
    "consecutive_fails",
    "last_alert_epoch",
    "alerts_this_hour",
    "alerts_hour_started",
    "kicks_this_hour",
    "kicks_hour_started",
)


def invoke(action, path, content=None):
    return subprocess.run(
        [sys.executable, str(HELPER), action, str(path)],
        input=content,
        text=True,
        capture_output=True,
    )


def test_round_trip_and_mode(tmp_path):
    path = tmp_path / "state"
    assert invoke("read", path).stdout == ""
    content = "".join(f"{key}=7\n" for key in KEYS)
    assert invoke("write", path, content).returncode == 0
    assert invoke("read", path).stdout == content
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".watchdog-state-*"))
    before = path.read_bytes()
    assert invoke("write", path, "consecutive_fails=0\n").returncode == 2
    assert path.read_bytes() == before


def test_corrupt_existing_budget_cannot_reset(tmp_path):
    path = tmp_path / "state"
    path.write_text("kicks_this_hour=3\n")
    path.chmod(0o640)
    assert invoke("read", path).returncode == 2
    assert invoke("write", path, "".join(f"{key}=0\n" for key in KEYS)).returncode == 2
    assert path.read_text() == "kicks_this_hour=3\n"


def test_symlink_budget_cannot_overwrite_victim(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("private")
    path = tmp_path / "state"
    path.symlink_to(victim)
    result = invoke("write", path, "".join(f"{key}=0\n" for key in KEYS))
    assert result.returncode == 2 and "private" not in result.stderr
    assert victim.read_text() == "private"
