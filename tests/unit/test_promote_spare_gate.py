"""The OTP confirm gate on the warm-spare promotion path."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "promote-spare.sh"


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    state = tmp_path / "spare-state"
    state.mkdir()
    stubs = tmp_path / "bin"
    stubs.mkdir()
    blue_green = stubs / "blue-green.sh"
    blue_green.write_text("#!/usr/bin/env bash\nprintf 'blue-green ran\\n'\n")
    blue_green.chmod(blue_green.stat().st_mode | stat.S_IXUSR)
    return state, stubs


def _issue_otp(state: Path, otp: str, *, age_seconds: int = 0) -> None:
    import time

    otp_file = state / "pending-otp"
    mtime = int(time.time()) - age_seconds
    otp_file.write_text(f"{otp}\t{mtime}\n")


def _run(stubs: Path, state: Path, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{stubs}:{env['PATH']}",
            "VPN_SPARE_STATE_DIR": str(state),
            # Point the promotion at the stub so the gate is tested without a
            # real traffic swing.
            "BLUE_GREEN_SCRIPT": str(stubs / "blue-green.sh"),
        }
    )
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT), *args], text=True, capture_output=True, check=False, env=env,
    )


def test_missing_otp_argument_is_a_usage_error(tmp_path: Path) -> None:
    state, stubs = _setup(tmp_path)
    result = _run(stubs, state)
    assert result.returncode == 1
    assert "usage" in result.stderr


def test_no_pending_otp_refuses_before_anything_else(tmp_path: Path) -> None:
    state, stubs = _setup(tmp_path)
    result = _run(stubs, state, "123456")
    assert result.returncode == 1
    assert "no pending OTP" in result.stderr


def test_expired_otp_is_consumed_and_refused(tmp_path: Path) -> None:
    state, stubs = _setup(tmp_path)
    _issue_otp(state, "123456", age_seconds=7200)

    result = _run(stubs, state, "123456")

    assert result.returncode == 1
    assert "OTP expired" in result.stderr
    assert not (state / "pending-otp").exists()


def test_wrong_otp_refuses_and_stays_pending(tmp_path: Path) -> None:
    state, stubs = _setup(tmp_path)
    _issue_otp(state, "123456")

    result = _run(stubs, state, "999999")

    assert result.returncode == 1
    assert "does not match" in result.stderr
    # A wrong guess must not burn the pending OTP.
    assert (state / "pending-otp").exists()


def test_matching_otp_is_consumed_once_and_swing_runs(tmp_path: Path) -> None:
    state, stubs = _setup(tmp_path)
    _issue_otp(state, "123456")

    result = _run(stubs, state, "123456")

    assert result.returncode == 0, result.stderr
    assert "blue-green ran" in result.stdout
    assert not (state / "pending-otp").exists()

    replay = _run(stubs, state, "123456")
    assert replay.returncode == 1
    assert "no pending OTP" in replay.stderr


def test_diff_secrets_gates_fail_closed_without_network(tmp_path: Path) -> None:
    """diff-secrets must refuse before any SSH when its inputs are absent."""
    import stat

    script = REPO_ROOT / "scripts" / "diff-secrets.sh"
    stubs = tmp_path / "bin"
    stubs.mkdir()
    # CI runners and minimal workstations lack the full toolchain; stub the
    # tools the script probes so the test reaches the input gates.
    for tool in ("terraform", "ssh", "ansible", "ansible-playbook", "diff", "jq"):
        stub = stubs / tool
        stub.write_text("#!/usr/bin/env bash\nexit 0\n")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{stubs}:{env['PATH']}"
    # No ANSIBLE_SSH_PRIVATE_KEY_FILE at all.
    result = subprocess.run(
        ["bash", str(script)], text=True, capture_output=True, check=False,
        cwd=REPO_ROOT, env=env,
    )
    assert result.returncode == 1
    assert "ANSIBLE_SSH_PRIVATE_KEY_FILE is not set" in result.stderr

    key = tmp_path / "operator-key"
    key.write_text("dummy\n")
    env["ANSIBLE_SSH_PRIVATE_KEY_FILE"] = str(key)
    env["SECRETS_FILE"] = str(tmp_path / "absent.secrets.yaml")
    result = subprocess.run(
        ["bash", str(script)], text=True, capture_output=True, check=False,
        cwd=REPO_ROOT, env=env,
    )
    assert result.returncode == 1
    assert "make decrypt" in result.stderr
