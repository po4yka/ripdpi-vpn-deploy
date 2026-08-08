"""Behavior tests for the fixed-command protocol-liveness sentinel."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "vpn-protocol-liveness.py"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _setup(
    tmp_path: Path,
    *,
    blocked_ports: tuple[int, ...] = (),
    blocked_delay_seconds: float = 0,
    awg_curl_fails: bool = False,
    awg_curl_sleeps: bool = False,
    sing_curl_sleeps: bool = False,
    sing_auth_fails: bool = False,
    sing_log_auth: bool = False,
) -> tuple[Path, dict[str, str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "calls.log"
    now_file = tmp_path / "now"
    now_file.write_text("9999999999")

    _write_executable(
        bin_dir / "curl",
        f"""#!/usr/bin/env python3
import os, pathlib, sys, time
args = " ".join(sys.argv[1:])
with pathlib.Path(os.environ["CALL_LOG"]).open("a") as log:
    log.write(f"curl {{args}}\\n")
blocked = {tuple(f"--socks5-hostname 127.0.0.1:{port}" for port in blocked_ports)!r}
if any(marker in args for marker in blocked):
    time.sleep({blocked_delay_seconds!r})
    raise SystemExit(28)
if "--socks5-hostname" in args and {sing_curl_sleeps!r}:
    time.sleep(30)
if "--socks5-hostname" in args and {sing_auth_fails!r}:
    print("authentication rejected", file=sys.stderr)
    raise SystemExit(22)
if os.environ.get("IN_AWG_NETNS") == "1":
    if {awg_curl_sleeps!r}:
        time.sleep(30)
    if {awg_curl_fails!r}:
        raise SystemExit(28)
print("204 0.040000", end="")
""",
    )
    _write_executable(
        bin_dir / "sing-box",
        f"""#!/usr/bin/env python3
import os, pathlib, signal, socket, sys
with pathlib.Path(os.environ["CALL_LOG"]).open("a") as log:
    log.write("sing-box " + " ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["version"]:
    print("sing-box version 1.14.0")
    raise SystemExit(0)
if {sing_log_auth!r}:
    print("authentication rejected", file=sys.stderr)
pathlib.Path(os.environ["SING_PID_FILE"]).write_text(str(os.getpid()))
listeners = []
for port in (18081, 18082, 18083, 18084):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen()
    listeners.append(listener)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
signal.pause()
""",
    )
    _write_executable(
        bin_dir / "ip",
        """#!/usr/bin/env bash
printf 'ip %s\n' "$*" >> "$CALL_LOG"
if [[ "${1:-} ${2:-}" == 'link show' && ! -f "$AWG_PID_FILE" ]]; then exit 1; fi
if [[ "${1:-} ${2:-} ${3:-}" == 'netns delete vpn-live-'* && "${FAIL_NETNS_DELETE:-}" == 1 ]]; then exit 42; fi
if [[ "${1:-} ${2:-} ${3:-}" == 'netns exec vpn-live-'* ]]; then
  shift 3
  IN_AWG_NETNS=1 exec "$@"
fi
exit 0
""",
    )
    _write_executable(
        bin_dir / "awg",
        """#!/usr/bin/env bash
printf 'awg %s\n' "$*" >> "$CALL_LOG"
if [[ "${1:-}" == --version ]]; then echo 'amneziawg-tools v1.0.0'; else cat "$NOW_FILE"; fi
""",
    )
    _write_executable(
        bin_dir / "awg-quick",
        """#!/usr/bin/env bash
printf 'awg-quick %s\n' "$*" >> "$CALL_LOG"
exit 0
""",
    )
    _write_executable(
        bin_dir / "amneziawg-go",
        """#!/usr/bin/env python3
import os, pathlib, signal, sys
log_path = pathlib.Path(os.environ["CALL_LOG"])
with log_path.open("a") as log:
    log.write("amneziawg-go " + " ".join(sys.argv[1:]) + "\\n")
pathlib.Path(os.environ["AWG_PID_FILE"]).write_text(str(os.getpid()))
def stop(*_args):
    with log_path.open("a") as log:
        log.write("amneziawg-go stopped\\n")
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
signal.pause()
""",
    )

    config = tmp_path / "sentinel.json"
    secret = "DO_NOT_LEAK_PRIVATE_KEY"
    awg = tmp_path / "awg.conf"
    awg.write_text(f"[Interface]\nPrivateKey = {secret}\n")
    sing_profiles = {}
    profile_config = tmp_path / "sing-box.json"
    profile_config.write_text("{}")
    for index, profile in enumerate(("p0-reality", "p1-xhttp", "p2-hysteria2"), start=1):
        sing_profiles[profile] = [18080 + index]
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sentinel": "tls-freeze-a",
                "probe_url": "https://www.gstatic.com/generate_204",
                "expected_status": 204,
                "timeout_seconds": 15,
                "degraded_after_ms": 3000,
                "expected_runtime": {"sing_box": "1.14.0", "awg": "1.0.0"},
                "sing_box": {"config": str(profile_config), "profiles": sing_profiles},
                "amneziawg": {"config": str(awg), "address": "10.66.66.2/32"},
            }
        )
    )
    config.chmod(0o600)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALL_LOG": str(call_log),
            "NOW_FILE": str(now_file),
            "VPN_LIVENESS_LOCK": str(tmp_path / "probe.lock"),
            "AWG_PID_FILE": str(tmp_path / "awg.pid"),
            "SING_PID_FILE": str(tmp_path / "sing.pid"),
        }
    )
    return config, env


def _run(config: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--config", str(config)],
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )


def test_sentinel_reports_authenticated_data_plane_success_without_secrets(tmp_path: Path) -> None:
    config, env = _setup(tmp_path)

    result = _run(config, env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["control"]["verdict"] == "ok"
    assert {item["profile"]: item["verdict"] for item in payload["profiles"]} == {
        "p0-reality": "ok",
        "p1-xhttp": "ok",
        "p2-hysteria2": "ok",
        "p2-amneziawg": "ok",
    }
    assert "DO_NOT_LEAK" not in result.stdout + result.stderr
    calls = (tmp_path / "calls.log").read_text()
    assert calls.count("sing-box run") == 1
    assert "netns delete vpn-live-" in calls
    awg_pid = (tmp_path / "awg.pid").read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


def test_transport_timeout_is_blocked_only_when_direct_control_succeeds(tmp_path: Path) -> None:
    config, env = _setup(
        tmp_path,
        blocked_ports=(18081, 18084),
        blocked_delay_seconds=3,
    )
    document = json.loads(config.read_text())
    document["timeout_seconds"] = 3
    document["sing_box"]["profiles"]["p0-reality"] = [18081, 18084]
    config.write_text(json.dumps(document))

    started = time.monotonic()
    result = _run(config, env)
    elapsed = time.monotonic() - started

    payload = json.loads(result.stdout)
    profiles = {item["profile"]: item for item in payload["profiles"]}
    assert payload["control"]["verdict"] == "ok"
    assert profiles["p0-reality"]["verdict"] == "blocked"
    assert [item["verdict"] for item in profiles["p0-reality"]["variants"]] == [
        "blocked",
        "blocked",
    ]
    assert elapsed < 6.5


def test_profile_stays_alive_when_one_endpoint_variant_succeeds(tmp_path: Path) -> None:
    config, env = _setup(tmp_path, blocked_ports=(18081,))
    document = json.loads(config.read_text())
    document["sing_box"]["profiles"]["p0-reality"] = [18081, 18084]
    config.write_text(json.dumps(document))

    result = _run(config, env)

    payload = json.loads(result.stdout)
    p0 = next(item for item in payload["profiles"] if item["profile"] == "p0-reality")
    assert p0["verdict"] == "ok"
    assert [item["verdict"] for item in p0["variants"]] == ["blocked", "ok"]
    calls = (tmp_path / "calls.log").read_text()
    assert "127.0.0.1:18081" in calls
    assert "127.0.0.1:18084" in calls


def test_awg_namespace_is_removed_after_probe_failure(tmp_path: Path) -> None:
    config, env = _setup(tmp_path, awg_curl_fails=True)

    result = _run(config, env)

    payload = json.loads(result.stdout)
    awg = next(item for item in payload["profiles"] if item["profile"] == "p2-amneziawg")
    calls = (tmp_path / "calls.log").read_text()
    assert awg["verdict"] == "blocked"
    assert "netns delete vpn-live-" in calls
    awg_pid = (tmp_path / "awg.pid").read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


def test_awg_namespace_is_removed_after_probe_timeout(tmp_path: Path) -> None:
    config, env = _setup(tmp_path, awg_curl_sleeps=True)
    document = json.loads(config.read_text())
    document["timeout_seconds"] = 1
    config.write_text(json.dumps(document))

    result = _run(config, env)

    payload = json.loads(result.stdout)
    awg = next(item for item in payload["profiles"] if item["profile"] == "p2-amneziawg")
    calls = (tmp_path / "calls.log").read_text()
    assert awg["verdict"] == "error"
    assert "netns delete vpn-live-" in calls
    awg_pid = (tmp_path / "awg.pid").read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


def test_runtime_mismatch_is_error_not_blocked(tmp_path: Path) -> None:
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    document["expected_runtime"]["sing_box"] = "9.9.9"
    config.write_text(json.dumps(document))

    result = _run(config, env)

    payload = json.loads(result.stdout)
    assert all(item["verdict"] == "error" for item in payload["profiles"])
    assert payload["control"]["verdict"] == "ok"


def test_authentication_failure_is_error_not_blocked(tmp_path: Path) -> None:
    direct = tmp_path / "direct"
    direct.mkdir()
    config, env = _setup(direct, sing_auth_fails=True)

    result = _run(config, env)

    payload = json.loads(result.stdout)
    sing_verdicts = [item["verdict"] for item in payload["profiles"] if item["profile"] != "p2-amneziawg"]
    assert sing_verdicts == ["error", "error", "error"]

    logged = tmp_path / "logged"
    logged.mkdir()
    config, env = _setup(logged, blocked_ports=(18081,), sing_log_auth=True)

    result = _run(config, env)

    payload = json.loads(result.stdout)
    p0 = next(item for item in payload["profiles"] if item["profile"] == "p0-reality")
    assert p0["verdict"] == "error"
    assert p0["error_kind"] == "authentication"
    assert [item["verdict"] for item in p0["variants"]] == ["error"]
    assert p0["variants"][0]["error_kind"] == "authentication"


def test_awg_cleanup_failure_is_error_and_still_stops_userspace_process(tmp_path: Path) -> None:
    config, env = _setup(tmp_path)
    env["FAIL_NETNS_DELETE"] = "1"

    result = _run(config, env)

    payload = json.loads(result.stdout)
    awg = next(item for item in payload["profiles"] if item["profile"] == "p2-amneziawg")
    calls = (tmp_path / "calls.log").read_text()
    assert awg["verdict"] == "error"
    assert "-n vpn-live-" in calls and "link delete awglive" in calls
    awg_pid = (tmp_path / "awg.pid").read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


def test_awg_namespace_and_process_are_removed_on_signal(tmp_path: Path) -> None:
    config, env = _setup(tmp_path, awg_curl_sleeps=True)
    process = subprocess.Popen(
        ["python3", str(SCRIPT), "--config", str(config)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    pid_file = tmp_path / "awg.pid"
    for _ in range(200):
        if pid_file.exists():
            break
        time.sleep(0.05)
    else:
        process.kill()
        stdout, stderr = process.communicate()
        raise AssertionError(f"AWG probe did not start: stdout={stdout!r}, stderr={stderr!r}")

    process.send_signal(signal.SIGTERM)
    process.communicate(timeout=8)

    calls = (tmp_path / "calls.log").read_text()
    assert process.returncode == 130
    assert "netns delete vpn-live-" in calls
    awg_pid = pid_file.read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


def test_sing_box_process_is_removed_on_signal(tmp_path: Path) -> None:
    config, env = _setup(tmp_path, sing_curl_sleeps=True)
    process = subprocess.Popen(
        ["python3", str(SCRIPT), "--config", str(config)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    pid_file = tmp_path / "sing.pid"
    for _ in range(200):
        if pid_file.exists() and "--socks5-hostname" in (tmp_path / "calls.log").read_text():
            break
        time.sleep(0.05)
    else:
        process.kill()
        stdout, stderr = process.communicate()
        raise AssertionError(f"sing-box probe did not start: stdout={stdout!r}, stderr={stderr!r}")

    process.send_signal(signal.SIGTERM)
    process.communicate(timeout=8)

    assert process.returncode == 130
    sing_pid = pid_file.read_text().strip()
    assert subprocess.run(["ps", "-p", sing_pid], capture_output=True).returncode != 0
