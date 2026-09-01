"""Behavior tests for the fixed-command protocol-liveness sentinel."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import signal
import socket
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "vpn-protocol-liveness.py"


def _toolchain_fixture(tmp_path, bin_dir):
    spec = importlib.util.spec_from_file_location("awg_toolchain_fixture", REPO_ROOT / "scripts/install-real-vps-awg-client-tools.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    inputs = {"goBundleSha256": "a" * 64, "goCommit": "b" * 40,
              "toolsBundleSha256": "c" * 64, "toolsCommit": "d" * 40, "vendorSha256": "e" * 64}
    identity = hashlib.sha256(installer.canonical(inputs)).hexdigest()
    target = tmp_path / "toolchains" / identity
    (target / "bin").mkdir(parents=True, mode=0o700)
    binaries = {}
    for name in installer.BINARY_NAMES:
        path = target / "bin" / name
        shutil.copyfile(bin_dir / name, path)
        path.chmod(0o500)
        binaries[name] = installer.digest(path)
    (target / "bin").chmod(0o500)
    manifest = {"schemaVersion": 1, "inputs": inputs, "binaries": binaries,
                "treeSha256": installer.tree_digest(target)}
    (target / "manifest.json").write_bytes(installer.canonical(manifest))
    (target / "manifest.json").chmod(0o400)
    target.chmod(0o500)
    return identity


def _launch(config):
    # Library-only fixture overrides; production CLI has no path/owner escape.
    code = """
import importlib.util, os, pathlib, signal, socket, sys
spec = importlib.util.spec_from_file_location('fixture_sentinel', sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.AWG_TOOLCHAIN_BASE = pathlib.Path(sys.argv[2]).parent / 'toolchains'
module.AWG_TOOLCHAIN_UID = os.geteuid(); module.AWG_TOOLCHAIN_GID = os.getegid()
original_getaddrinfo = socket.getaddrinfo
module.socket.getaddrinfo = lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.20', 443))] if host == 'www.gstatic.com' else original_getaddrinfo(host, *a, **k)
sys.argv = [sys.argv[1], '--config', sys.argv[2]]
signal.signal(signal.SIGTERM, module.terminate_on_signal)
try: raise SystemExit(module.main())
except KeyboardInterrupt: raise SystemExit(130)
"""
    return [sys.executable, "-B", "-c", code, str(SCRIPT), str(config)]


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
    xray_parser_fails: bool = False,
    xray_log_auth: bool = False,
    control_curl_fails: bool = False,
    awg_start_delay_seconds: float = 0,
) -> tuple[Path, dict[str, str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "calls.log"
    _write_executable(
        bin_dir / "curl",
        f"""#!/usr/bin/env python3
import os, pathlib, sys, time
args = " ".join(sys.argv[1:])
with pathlib.Path(os.environ["CALL_LOG"]).open("a") as log:
    log.write(f"curl {{args}}\\n")
    if "--socks5-hostname" in args:
        log.write(f"curl-start {{time.monotonic_ns()}} {{args}}\\n")
blocked = {tuple(f"--socks5-hostname 127.0.0.1:{port}" for port in blocked_ports)!r}
if any(marker in args for marker in blocked):
    time.sleep({blocked_delay_seconds!r})
    raise SystemExit(28)
if "--socks5-hostname" in args and {sing_curl_sleeps!r}:
    time.sleep(30)
if "--socks5-hostname" in args and {sing_auth_fails!r}:
    print("authentication rejected", file=sys.stderr)
    raise SystemExit(22)
if "--socks5-hostname" not in args and os.environ.get("IN_AWG_NETNS") != "1" and {control_curl_fails!r}:
    raise SystemExit(28)
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
        bin_dir / "xray",
        f"""#!/usr/bin/env python3
import os, sys
if sys.argv[1:] == ["version"]:
    with open(os.environ["CALL_LOG"], "a", encoding="utf-8") as log:
        log.write("xray version\\n")
    print("Xray 26.3.27 (Xray, Penetrates Everything.)")
    raise SystemExit(0)
import json, pathlib, signal, socket
with pathlib.Path(os.environ["CALL_LOG"]).open("a") as log:
    log.write("xray " + " ".join(sys.argv[1:]) + "\\n")
if "-test" in sys.argv:
    if {xray_parser_fails!r}:
        print("invalid profile DO_NOT_LEAK", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0)
config = json.loads(pathlib.Path(sys.argv[sys.argv.index("-config") + 1]).read_text())
pathlib.Path(os.environ["XRAY_PID_FILE"]).write_text(str(os.getpid()))
listeners = []
for inbound in config["inbounds"]:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((inbound["listen"], inbound["port"]))
    listener.listen()
    listeners.append(listener)
if {xray_log_auth!r}:
    print("authentication rejected DO_NOT_LEAK", file=sys.stderr, flush=True)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
signal.pause()
""",
    )
    _write_executable(
        bin_dir / "ip",
        """#!/usr/bin/env bash
printf 'ip %s\n' "$*" >> "$CALL_LOG"
if [[ "${1:-} ${2:-}" == 'link show' ]]; then
  if [[ "${EXISTING_AWG_INTERFACE:-}" == 1 || -f "$AWG_PID_FILE" ]]; then exit 0; else exit 1; fi
fi
if [[ "${1:-} ${2:-}" == 'link set' && "${FAIL_AWG_MOVE:-}" == 1 ]]; then exit 1; fi
if [[ "$*" == *'link delete awglive'* && "${FAIL_LINK_DELETE:-}" == 1 ]]; then exit 2; fi
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
if [[ "${1:-}" == --version ]]; then
  echo 'amneziawg-tools v1.0.0'
elif [[ "${1:-}" == setconf ]]; then
  [[ "${3:-}" == /dev/stdin ]] || exit 1
  [[ "$(cat)" == *DO_NOT_LEAK_PRIVATE_KEY* ]] || exit 1
else
  printf 'fixture-peer %s\n' "$(date +%s)"
fi
""",
    )
    _write_executable(
        bin_dir / "awg-quick",
        """#!/usr/bin/env bash
printf 'awg-quick %s\n' "$*" >> "$CALL_LOG"
cat "$2"
""",
    )
    _write_executable(
        bin_dir / "amneziawg-go",
        f"""#!/usr/bin/env python3
import os, pathlib, signal, sys
import time
log_path = pathlib.Path(os.environ["CALL_LOG"])
time.sleep({awg_start_delay_seconds!r})
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
    awg.chmod(0o600)
    toolchain_id = _toolchain_fixture(tmp_path, bin_dir)
    sing_profiles = {}
    profile_config = tmp_path / "sing-box.json"
    profile_config.write_text("{}")
    for index, profile in enumerate(
        ("p0-reality", "p2-hysteria2"), start=1
    ):
        sing_profiles[profile] = [18080 + index]
    xray_config = tmp_path / "xray.json"
    xray_config.write_text(json.dumps(_xray_document([18181])))
    xray_config.chmod(0o600)
    config.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "sentinel": "tls-freeze-a",
                "provenance": {"controller_revision": "a" * 40, "runner_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                               "client_generation_id": str(uuid4()), "public_profile_digest": "b" * 64, "vantage": "external"},
                "target_identity": {
                    "inventory_alias": "vpn-p2-fixture",
                    "public_service_address_sha256": "c" * 64,
                    "deployable_digest": "d" * 64,
                    "applied_at": int(time.time()) - 10,
                    "required_profiles": ["p0-reality", "p1-xhttp", "p2-amneziawg", "p2-hysteria2"],
                    "source_revision": "a" * 40,
                    "runner_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                    "public_profile_digest": "b" * 64,
                },
                "probe_url": "https://www.gstatic.com/generate_204",
                "expected_status": 204,
                "timeout_seconds": 15,
                "degraded_after_ms": 3000,
                "expected_runtime": {"sing_box": "1.14.0", "xray": "26.3.27", "awg": "1.0.0", "awg_toolchain": toolchain_id},
                "sing_box": {"config": str(profile_config), "profiles": sing_profiles},
                "xray": {"config": str(xray_config), "profiles": {"p1-xhttp": [18181]}},
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
            "VPN_LIVENESS_LOCK": str(tmp_path / "probe.lock"),
            "AWG_PID_FILE": str(tmp_path / "awg.pid"),
            "SING_PID_FILE": str(tmp_path / "sing.pid"),
            "XRAY_PID_FILE": str(tmp_path / "xray.pid"),
        }
    )
    return config, env


def _xray_document(ports: list[int]) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks",
                      "tag": f"probe-{index}", "settings": {"udp": False}}
                     for index, port in enumerate(ports)],
        "outbounds": [{"protocol": "vless", "tag": "p1-xhttp",
                       "settings": {"vnext": [{"address": "192.0.2.1", "port": 443,
                         "users": [{"id": "00000000-0000-4000-8000-000000000001", "encryption": "none"}]}]},
                       "streamSettings": {"network": "xhttp", "security": "tls",
                         "tlsSettings": {"serverName": "probe.example", "allowInsecure": False},
                         "xhttpSettings": {"path": "/probe", "host": "probe.example"}}}],
        "routing": {"rules": [{"type": "field", "inboundTag": [f"probe-{index}" for index in range(len(ports))],
                               "outboundTag": "p1-xhttp"}]},
    }


def _run(config: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _launch(config),
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )


def test_sentinel_reports_authenticated_data_plane_success_without_secrets(
    tmp_path: Path,
) -> None:
    config, env = _setup(tmp_path)
    for name in ("amneziawg-go", "awg", "awg-quick"):
        (tmp_path / "bin" / name).write_text("#!/bin/sh\nexit 93\n")

    result = _run(config, env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 2
    assert payload["target_identity"] == json.loads(config.read_text())["target_identity"]
    assert payload["provenance"] == json.loads(config.read_text())["provenance"]
    for profile in payload["profiles"]:
        assert profile["payload_transport"] == "tcp-https"
        assert profile["dns_through_tunnel"] is True
        assert profile["authenticated_handshake"] is True
        if profile["profile"] == "p2-amneziawg":
            assert profile["target_address_family"] == "ipv4"
            assert profile["fresh_handshake"] is True
        else:
            assert profile["target_address_family"] == "unknown"
            assert "fresh_handshake" not in profile
    assert payload["control"]["verdict"] == "ok"
    assert {item["profile"]: item["verdict"] for item in payload["profiles"]} == {
        "p0-reality": "ok",
        "p1-xhttp": "ok",
        "p2-hysteria2": "ok",
        "p2-amneziawg": "ok",
    }
    assert "DO_NOT_LEAK" not in result.stdout + result.stderr
    calls = (tmp_path / "calls.log").read_text()
    assert "--resolve" not in calls
    assert calls.count("sing-box run") == 1
    assert payload["runtime"]["xray"] == "26.3.27"
    assert payload["runtime"]["awg_toolchain"] == json.loads(config.read_text())["expected_runtime"]["awg_toolchain"]
    assert calls.index("xray run -test -config") < calls.index("xray run -config")
    assert subprocess.run(["ps", "-p", (tmp_path / "xray.pid").read_text().strip()], capture_output=True).returncode != 0
    assert "netns delete vpn-live-" in calls
    interface = next(line.split()[-1] for line in calls.splitlines() if line.startswith("ip link show "))
    assert len(interface) <= 15
    awg_pid = (tmp_path / "awg.pid").read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


@pytest.mark.parametrize("code,stdout,stderr", [(1, "sing-box version 1.13.16", ""), (0, "", "amneziawg-tools v1.0.0")])
def test_runtime_version_requires_successful_stdout(monkeypatch, code, stdout, stderr):
    spec = importlib.util.spec_from_file_location("sentinel_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], code, stdout, stderr))
    assert module.command_version(["fixture", "version"]) == "unknown"


@pytest.mark.parametrize(
    ("responses", "expected", "calls"),
    [
        ([OSError("transient launch failure"), subprocess.CompletedProcess(["xray", "version"], 0, "Xray 26.3.27\n", "")], "26.3.27", 2),
        ([subprocess.TimeoutExpired(["xray", "version"], 5), subprocess.CompletedProcess(["xray", "version"], 0, "Xray 26.3.27\n", "")], "26.3.27", 2),
        ([OSError("first launch failure"), subprocess.TimeoutExpired(["xray", "version"], 5)], "missing", 2),
        ([subprocess.CompletedProcess(["xray", "version"], 0, "unrelated 26.3.27\n", "")], "unknown", 1),
        ([subprocess.CompletedProcess(["xray", "version"], 1, "Xray 26.3.27\n", "")], "unknown", 1),
    ],
)
def test_xray_version_retries_only_transient_launch_failures(monkeypatch, responses, expected, calls):
    spec = importlib.util.spec_from_file_location("sentinel_xray_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    remaining = iter(responses)
    observed = []

    def run(*args, **kwargs):
        observed.append((args, kwargs))
        response = next(remaining)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    assert module.xray_version() == expected
    assert len(observed) == calls
    assert all(call[0][0] == ["xray", "version"] and call[1]["timeout"] == 5 for call in observed)


def test_existing_loopback_listener_cannot_supply_runtime_success(monkeypatch):
    spec = importlib.util.spec_from_file_location("sentinel_listener", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        monkeypatch.setattr(module.subprocess, "Popen", lambda *_a, **_k: pytest.fail("must reject occupied port before starting runtime"))
        result = module.probe_runtime_profiles("sing-box", {"config": "/fixture", "profiles": {"p0-reality": [port]}}, {}, True)
        assert result[0]["verdict"] == "error"
        assert result[0]["error_kind"] == "listener_in_use"
        assert result[0]["payload_transport"] == "unknown"
        assert result[0]["target_address_family"] == "unknown"


def test_awg_probe_command_keeps_hostname_resolution_inside_namespace():
    spec = importlib.util.spec_from_file_location("sentinel_dns", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    command = module.curl_command(
        {"probe_url": "https://fixture.example/", "timeout_seconds": 1},
        [],
        ["ip", "netns", "exec", "vpn-live-fixture"],
    )
    assert command[:4] == ["ip", "netns", "exec", "vpn-live-fixture"]
    assert "--resolve" not in command
    assert command[-1] == "https://fixture.example/"


def test_awg_namespace_curl_forces_ipv4_and_resolves_hostname_inside_namespace(
    tmp_path: Path,
) -> None:
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    document["probe_url"] = "https://dual-stack.fixture/"
    config.write_text(json.dumps(document))

    result = _run(config, env)

    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls.log").read_text().splitlines()
    awg_curl = next(
        line
        for line in calls
        if line.startswith("ip netns exec vpn-live-") and " curl " in line
    )
    awg_arguments = awg_curl.split()
    assert "--ipv4" in awg_arguments
    assert "--resolve" not in awg_arguments
    assert awg_arguments[-1] == "https://dual-stack.fixture/"
    awg = next(
        item for item in json.loads(result.stdout)["profiles"] if item["profile"] == "p2-amneziawg"
    )
    assert awg["target_address_family"] == "ipv4"
    assert awg["dns_through_tunnel"] is True


def test_legacy_sing_box_xhttp_requires_explicit_migration(tmp_path):
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    document["sing_box"]["profiles"]["p1-xhttp"] = [18083]
    config.write_text(json.dumps(document))
    result = _run(config, env)
    assert result.returncode == 2
    assert "p1-xhttp requires xray" in result.stderr
    assert not (tmp_path / "calls.log").exists()


@pytest.mark.parametrize(
    "invalid",
    ["not-an-object", {"config": "relative.json", "profiles": {}}, {"config": "/tmp/sing-box.json", "profiles": []}],
)
def test_malformed_sing_box_config_is_rejected_without_probe_or_traceback(tmp_path, invalid):
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    document["sing_box"] = invalid
    config.write_text(json.dumps(document))

    result = _run(config, env)

    assert result.returncode == 2
    assert result.stderr.strip() == "vpn-protocol-liveness: invalid sing-box profiles"
    assert not (tmp_path / "calls.log").exists()


@pytest.mark.parametrize("invalid", ["missing-pin", "bad-id", "modified-binary", "symlink", "writable-tree", "writable-parent", "input-mismatch"])
def test_awg_toolchain_is_verified_before_any_network_or_namespace(tmp_path, invalid):
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    target = tmp_path / "toolchains" / document["expected_runtime"]["awg_toolchain"]
    if invalid == "missing-pin":
        del document["expected_runtime"]["awg_toolchain"]
    elif invalid == "bad-id":
        document["expected_runtime"]["awg_toolchain"] = "../outside"
    elif invalid == "modified-binary":
        binary = target / "bin/awg"
        binary.chmod(0o700)
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o500)
    elif invalid == "symlink":
        (target / "bin").chmod(0o700)
        (target / "bin/awg").unlink()
        (target / "bin/awg").symlink_to(tmp_path / "bin/awg")
        (target / "bin").chmod(0o500)
    elif invalid == "writable-tree":
        target.chmod(0o700)
    elif invalid == "writable-parent":
        target.parent.chmod(0o777)
    else:
        path = target / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["inputs"]["goCommit"] = "f" * 40
        path.chmod(0o600)
        path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        path.chmod(0o400)
    config.write_text(json.dumps(document))
    result = _run(config, env)
    assert result.returncode == 2
    assert "invalid AWG toolchain" in result.stderr
    assert not (tmp_path / "calls.log").exists()


@pytest.mark.parametrize("url", ["http://probe.example/", "https://probe.example:8443/", "https://[::1]/", "https://user:pass@probe.example/", "https://probe.example/#fragment"])
def test_awg_url_boundary_is_checked_before_any_network(tmp_path, url):
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    document["probe_url"] = url
    config.write_text(json.dumps(document))
    result = _run(config, env)
    assert result.returncode == 2
    assert not (tmp_path / "calls.log").exists()


def test_awg_existing_interface_is_never_adopted_or_deleted(tmp_path):
    config, env = _setup(tmp_path)
    env["EXISTING_AWG_INTERFACE"] = "1"
    result = _run(config, env)
    awg = next(p for p in json.loads(result.stdout)["profiles"] if p["profile"] == "p2-amneziawg")
    assert awg["verdict"] == "error"
    calls = (tmp_path / "calls.log").read_text()
    assert "link show awglive" in calls
    assert "amneziawg-go " not in calls
    assert "link delete awglive" not in calls
    assert "netns add" not in calls


def test_awg_move_failure_removes_only_its_host_interface(tmp_path):
    config, env = _setup(tmp_path)
    env["FAIL_AWG_MOVE"] = "1"
    result = _run(config, env)
    awg = next(p for p in json.loads(result.stdout)["profiles"] if p["profile"] == "p2-amneziawg")
    assert awg["verdict"] == "error"
    calls = (tmp_path / "calls.log").read_text()
    assert "ip link delete awglive" in calls
    assert "amneziawg-go -f awglive" in calls
    assert "netns delete vpn-live-" in calls


def test_absent_awg_config_needs_no_awg_toolchain_or_runtime(tmp_path):
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    del document["amneziawg"]
    del document["expected_runtime"]["awg"]
    del document["expected_runtime"]["awg_toolchain"]
    document["target_identity"]["required_profiles"].remove("p2-amneziawg")
    config.write_text(json.dumps(document))
    result = _run(config, env)
    payload = json.loads(result.stdout)
    assert payload["runtime"] == document["expected_runtime"]
    assert all(p["verdict"] == "ok" for p in payload["profiles"])
    assert "awg " not in (tmp_path / "calls.log").read_text()


@pytest.mark.parametrize("invalid", ["missing-pin", "relative-path", "wrong-profile", "empty-ports", "duplicate-port", "boolean-port"])
def test_invalid_xray_profile_is_rejected_before_any_probe(tmp_path, invalid):
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    if invalid == "missing-pin":
        del document["expected_runtime"]["xray"]
    elif invalid == "relative-path":
        document["xray"]["config"] = "xray.json"
    elif invalid == "wrong-profile":
        document["xray"]["profiles"] = {"p0-reality": [18181]}
    else:
        document["xray"]["profiles"]["p1-xhttp"] = {
            "empty-ports": [], "duplicate-port": [18181, 18181], "boolean-port": [True],
        }[invalid]
    config.write_text(json.dumps(document))
    result = _run(config, env)
    assert result.returncode == 2
    assert "invalid xray profile" in result.stderr
    assert not (tmp_path / "calls.log").exists()


@pytest.mark.parametrize("pin,banner,code", [
    ("26.3.2", "Xray 26.3.27", 0),
    ("26.3.27", "unrelated 26.3.27", 0),
    ("26.3.27", "Xray 26.3.27", 1),
])
def test_xray_version_requires_exact_successful_product_banner(tmp_path, pin, banner, code):
    config, env = _setup(tmp_path)
    document = json.loads(config.read_text())
    document["expected_runtime"]["xray"] = pin
    config.write_text(json.dumps(document))
    _write_executable(tmp_path / "bin" / "xray", f"#!/usr/bin/env python3\nprint({banner!r})\nraise SystemExit({code})\n")
    payload = json.loads(_run(config, env).stdout)
    assert all(p["verdict"] == "error" and p["error_kind"] == "runtime_mismatch" for p in payload["profiles"])


def test_xray_parser_failure_is_redacted_and_never_starts_runtime(tmp_path):
    config, env = _setup(tmp_path, xray_parser_fails=True)
    result = _run(config, env)
    p1 = next(p for p in json.loads(result.stdout)["profiles"] if p["profile"] == "p1-xhttp")
    assert p1["error_kind"] == "runtime_config"
    assert p1["verdict"] == "error"
    assert "DO_NOT_LEAK" not in result.stdout + result.stderr
    assert not (tmp_path / "xray.pid").exists()


@pytest.mark.parametrize("blocked,control_fails,expected", [
    ((18181,), False, "ok"),
    ((18181, 18182), False, "blocked"),
    ((18181, 18182), True, "unknown"),
])
def test_xray_endpoint_variants_require_healthy_control_for_blocking(tmp_path, blocked, control_fails, expected):
    config, env = _setup(tmp_path, blocked_ports=blocked, control_curl_fails=control_fails)
    document = json.loads(config.read_text())
    document["xray"]["profiles"]["p1-xhttp"] = [18181, 18182]
    Path(document["xray"]["config"]).write_text(json.dumps(_xray_document([18181, 18182])))
    config.write_text(json.dumps(document))
    payload = json.loads(_run(config, env).stdout)
    p1 = next(p for p in payload["profiles"] if p["profile"] == "p1-xhttp")
    assert payload["runtime"] == document["expected_runtime"]
    assert p1["verdict"] == expected
    assert len(p1["variants"]) == 2
    assert [v["variant"] for v in p1["variants"]] == [1, 2]


def test_xray_auth_failure_is_never_blocking_evidence(tmp_path):
    config, env = _setup(tmp_path, blocked_ports=(18181,), xray_log_auth=True)
    result = _run(config, env)
    p1 = next(p for p in json.loads(result.stdout)["profiles"] if p["profile"] == "p1-xhttp")
    assert p1["verdict"] == "error"
    assert p1["error_kind"] == "authentication"
    assert p1["variants"][0]["error_kind"] == "authentication"
    assert "DO_NOT_LEAK" not in result.stdout + result.stderr


def test_awg_startup_tolerates_slow_userspace_interface_creation(
    tmp_path: Path,
) -> None:
    config, env = _setup(tmp_path, awg_start_delay_seconds=2.2)

    result = _run(config, env)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    awg = next(
        item for item in payload["profiles"] if item["profile"] == "p2-amneziawg"
    )
    assert awg["verdict"] == "ok"


def test_transport_timeout_is_blocked_only_when_direct_control_succeeds(
    tmp_path: Path,
) -> None:
    config, env = _setup(
        tmp_path,
        blocked_ports=(18081, 18084),
        blocked_delay_seconds=3,
    )
    document = json.loads(config.read_text())
    document["timeout_seconds"] = 3
    document["sing_box"]["profiles"]["p0-reality"] = [18081, 18084]
    config.write_text(json.dumps(document))

    result = _run(config, env)

    payload = json.loads(result.stdout)
    profiles = {item["profile"]: item for item in payload["profiles"]}
    assert payload["control"]["verdict"] == "ok"
    assert profiles["p0-reality"]["verdict"] == "blocked"
    assert [item["verdict"] for item in profiles["p0-reality"]["variants"]] == [
        "blocked",
        "blocked",
    ]
    starts = {}
    for line in (tmp_path / "calls.log").read_text().splitlines():
        if not line.startswith("curl-start "):
            continue
        _, timestamp, arguments = line.split(" ", 2)
        for port in (18081, 18084):
            if f"127.0.0.1:{port}" in arguments:
                starts[port] = int(timestamp)
    assert set(starts) == {18081, 18084}
    assert abs(starts[18081] - starts[18084]) < 2_000_000_000


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
    awg = next(
        item for item in payload["profiles"] if item["profile"] == "p2-amneziawg"
    )
    calls = (tmp_path / "calls.log").read_text()
    assert awg["verdict"] == "blocked", awg
    assert awg["dns_through_tunnel"] is False
    assert awg["authenticated_handshake"] is False
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
    awg = next(
        item for item in payload["profiles"] if item["profile"] == "p2-amneziawg"
    )
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
    sing_verdicts = [
        item["verdict"]
        for item in payload["profiles"]
        if item["profile"] in {"p0-reality", "p2-hysteria2", "p1-xhttp"}
    ]
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


def test_awg_cleanup_failure_is_error_and_still_stops_userspace_process(
    tmp_path: Path,
) -> None:
    config, env = _setup(tmp_path)
    env["FAIL_NETNS_DELETE"] = "1"

    result = _run(config, env)

    payload = json.loads(result.stdout)
    awg = next(
        item for item in payload["profiles"] if item["profile"] == "p2-amneziawg"
    )
    calls = (tmp_path / "calls.log").read_text()
    assert awg["verdict"] == "error"
    assert "-n vpn-live-" in calls and "link delete awglive" in calls
    awg_pid = (tmp_path / "awg.pid").read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


def test_awg_link_cleanup_failure_is_not_treated_as_absence(tmp_path):
    config, env = _setup(tmp_path)
    env["FAIL_LINK_DELETE"] = "1"
    result = _run(config, env)
    awg = next(p for p in json.loads(result.stdout)["profiles"] if p["profile"] == "p2-amneziawg")
    assert awg["verdict"] == "error"
    assert awg["error_kind"] == "cleanup"
    assert "netns delete vpn-live-" in (tmp_path / "calls.log").read_text()


def test_awg_namespace_and_process_are_removed_on_signal(tmp_path: Path) -> None:
    config, env = _setup(tmp_path, awg_curl_sleeps=True)
    process = subprocess.Popen(
        _launch(config),
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
        raise AssertionError(
            f"AWG probe did not start: stdout={stdout!r}, stderr={stderr!r}"
        )

    process.send_signal(signal.SIGTERM)
    process.communicate(timeout=8)

    calls = (tmp_path / "calls.log").read_text()
    assert process.returncode == 130
    assert "netns delete vpn-live-" in calls
    awg_pid = pid_file.read_text().strip()
    assert subprocess.run(["ps", "-p", awg_pid], capture_output=True).returncode != 0


@pytest.mark.parametrize("runtime", ["sing", "xray"])
def test_socks_runtime_process_is_removed_on_signal(tmp_path: Path, runtime: str) -> None:
    config, env = _setup(tmp_path, sing_curl_sleeps=runtime == "sing",
                         blocked_ports=(18181,) if runtime == "xray" else (),
                         blocked_delay_seconds=30 if runtime == "xray" else 0)
    process = subprocess.Popen(
        _launch(config),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    pid_file = tmp_path / f"{runtime}.pid"
    marker = "--socks5-hostname 127.0.0.1:" + ("18081" if runtime == "sing" else "18181")
    for _ in range(200):
        if (
            pid_file.exists()
            and marker in (tmp_path / "calls.log").read_text()
        ):
            break
        time.sleep(0.05)
    else:
        process.kill()
        stdout, stderr = process.communicate()
        raise AssertionError(
            f"{runtime} probe did not start: stdout={stdout!r}, stderr={stderr!r}"
        )

    process.send_signal(signal.SIGTERM)
    process.communicate(timeout=8)

    assert process.returncode == 130
    sing_pid = pid_file.read_text().strip()
    assert subprocess.run(["ps", "-p", sing_pid], capture_output=True).returncode != 0


@pytest.mark.parametrize("failure", ["timeout", "signal", "collision"])
def test_namespace_partial_creation_is_reconciled_without_deleting_collision(monkeypatch, failure):
    spec = importlib.util.spec_from_file_location("sentinel_namespace", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    present = failure == "collision"
    calls = []
    monkeypatch.setattr(module, "namespace_exists", lambda _name: present, raising=False)
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.9", 443))])
    def run(command, **_kwargs):
        nonlocal present
        calls.append(command)
        if command[:3] == ["ip", "link", "show"]:
            return subprocess.CompletedProcess(command, 1, b"", b"")
        if command[:3] == ["ip", "netns", "add"]:
            if failure == "collision":
                raise AssertionError("pre-existing namespace must not be changed")
            present = True
            if failure == "signal":
                raise KeyboardInterrupt
            raise subprocess.TimeoutExpired(command, 5)
        if command[:3] == ["ip", "netns", "delete"]:
            assert present and failure != "collision"
            present = False
            return subprocess.CompletedProcess(command, 0, b"", b"")
        raise AssertionError("unexpected namespace fixture command")
    monkeypatch.setattr(module.subprocess, "run", run)
    config = {"probe_url": "https://probe.example/", "amneziawg": {"config": "/fixture", "address": "10.66.66.2/32"}}
    if failure == "signal":
        with pytest.raises(KeyboardInterrupt):
            module.probe_awg(config, True, {})
    else:
        assert module.probe_awg(config, True, {})["verdict"] == "error"
    assert present == (failure == "collision")
    assert any(c[:3] == ["ip", "netns", "delete"] for c in calls) == (failure != "collision")


def test_awg_validation_call_is_retained_without_an_unused_result():
    tree = ast.parse(SCRIPT.read_text())
    probe = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "probe_awg"
    )
    direct_calls = [
        node
        for node in ast.walk(probe)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "awg_probe_url"
    ]
    assert len(direct_calls) == 1


def test_awg_validation_failure_precedes_namespace_mutation(monkeypatch):
    spec = importlib.util.spec_from_file_location("sentinel_awg_validation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "awg_probe_url", lambda _config: (_ for _ in ()).throw(ValueError())
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("validation must precede namespace mutation")
        ),
    )

    result = module.probe_awg(
        {"amneziawg": {"config": "/fixture"}}, True, {}
    )

    assert result["verdict"] == "error"
    assert result["duration_ms"] is None
    assert result["error_kind"] == "valueerror"


def test_unstarted_curl_does_not_claim_attempted_payload(monkeypatch):
    spec = importlib.util.spec_from_file_location("sentinel_curl_failure", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError()))
    variants = module.parallel_curl_probes({"timeout_seconds": 1, "probe_url": "https://fixture/"}, [["--socks5-hostname", "127.0.0.1:18081"]])
    result = module.aggregate_variants("p0-reality", variants)
    assert result["payload_transport"] == "unknown"
    assert result["target_address_family"] == "unknown"
