"""Behavior tests for the watchdog's authenticated REALITY probe orchestration."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ansible" / "roles" / "watchdog" / "templates" / "vpn-watchdog.sh.j2"


def _executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + body)
    path.chmod(0o755)


def _run_watchdog(
    tmp_path: Path,
    *,
    canary_status: str = "204",
    socks_ready: bool = True,
    xray_client_exits: bool = False,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    state_file = tmp_path / "state"
    config_file = tmp_path / "reality.json"
    config_file.write_text("{}")
    term_marker = tmp_path / "xray-terminated"

    _executable(
        bin_dir / "systemctl",
        "printf '%s\\n' \"$*\" >> \"${SYSTEMCTL_LOG}\"\n"
        "exit 0\n",
    )
    _executable(bin_dir / "timeout", "exit 0\n")
    _executable(
        bin_dir / "ss",
        "printf '%s\\n' 'LISTEN 0 4096 0.0.0.0:443 0.0.0.0:*'\n"
        + (
            "printf '%s\\n' 'LISTEN 0 4096 127.0.0.1:31082 0.0.0.0:*'\n"
            if socks_ready
            else ""
        ),
    )
    _executable(
        bin_dir / "df",
        "printf '%s\\n' 'Use%' '10%'\n",
    )
    _executable(
        bin_dir / "curl",
        "if printf '%s\\n' \"$@\" | grep -q -- '--proxy'; then\n"
        "  printf '%s' \"${CANARY_STATUS}\"\n"
        "fi\n",
    )
    _executable(
        bin_dir / "xray",
        "if printf '%s\\n' \"$@\" | grep -q -- '-test'; then exit 0; fi\n"
        + ("exit 23\n" if xray_client_exits else "")
        + "trap 'touch \"${XRAY_TERM_MARKER}\"; exit 0' TERM INT\n"
        "while :; do read -r -t 1 _ || true; done\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ENABLE_XRAY": "true",
            "ENABLE_NGINX_XHTTP": "false",
            "ENABLE_HYSTERIA": "false",
            "ENABLE_AMNEZIAWG": "false",
            "XRAY_BIN": str(bin_dir / "xray"),
            "XRAY_PORT": "443",
            "XRAY_REALITY_CONFIG": str(config_file),
            "XRAY_REALITY_PROBES": "443:31082",
            "XRAY_REALITY_PROBE_URL": "https://canary.example.test/healthz",
            "XRAY_REALITY_PROBE_TIMEOUT": "1",
            "CANARY_STATUS": canary_status,
            "XRAY_TERM_MARKER": str(term_marker),
            "STATE_FILE": str(state_file),
            "FAIL_THRESHOLD": "1",
            "KICKS_PER_HOUR_MAX": "1",
            "SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
            "WATCHDOG_PROVIDER": "ntfy",
            "NTFY_URL": "https://notify.example.test",
            "NTFY_TOPIC": "test-topic",
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )


def test_authenticated_reality_round_trip_reports_success_and_cleans_up(tmp_path):
    result = _run_watchdog(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "OK    xray REALITY TCP/443 round-trip" in result.stdout
    assert (tmp_path / "xray-terminated").exists()
    assert "consecutive_fails=0" in (tmp_path / "state").read_text()


def test_wrong_canary_status_is_a_probe_failure_and_cleans_up(tmp_path):
    result = _run_watchdog(tmp_path, canary_status="200")

    assert result.returncode != 0, result.stderr
    assert "FAIL  xray REALITY TCP/443 round-trip" in result.stdout
    assert (tmp_path / "xray-terminated").exists()
    assert "consecutive_fails=1" in (tmp_path / "state").read_text()
    assert "restart xray.service" in (tmp_path / "systemctl.log").read_text()


def test_recovery_kicks_are_bounded_per_hour(tmp_path):
    first = _run_watchdog(tmp_path, canary_status="200")
    second = _run_watchdog(tmp_path, canary_status="200")

    assert first.returncode != 0, first.stderr
    assert second.returncode != 0, second.stderr
    calls = (tmp_path / "systemctl.log").read_text().splitlines()
    assert calls.count("restart xray.service") == 1
    assert "kicks_this_hour=1" in (tmp_path / "state").read_text()


def test_socks_startup_timeout_is_a_probe_failure_and_cleans_up(tmp_path):
    result = _run_watchdog(tmp_path, socks_ready=False)

    assert result.returncode != 0, result.stderr
    assert "FAIL  xray REALITY TCP/443 round-trip" in result.stdout
    assert (tmp_path / "xray-terminated").exists()
    assert "consecutive_fails=1" in (tmp_path / "state").read_text()


def test_xray_client_early_exit_is_a_probe_failure(tmp_path):
    result = _run_watchdog(tmp_path, xray_client_exits=True)

    assert result.returncode != 0, result.stderr
    assert "FAIL  xray REALITY TCP/443 round-trip" in result.stdout
    assert "consecutive_fails=1" in (tmp_path / "state").read_text()
