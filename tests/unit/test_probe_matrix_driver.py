"""Behavior tests for the probe-matrix control and cell driver interface."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import yaml
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "probe-matrix-driver.py"


def _executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _setup(tmp_path: Path) -> tuple[Path, dict[str, str], str]:
    secret = "DO_NOT_LEAK_MATRIX_SECRET"
    profile = tmp_path / "target.json"
    profile.write_text(json.dumps({
        "schema_version": 1,
        "target_id": "generic-dual",
        "endpoint": "203.0.113.9",
        "expected_xray_version": "v26.3.27",
        "expected_mtg_version": "v2.2.8",
        "expected_mtproto_helper_version": "gotd-v0.160.0",
        "protocols": {
            "mtproto": {"port": 10443, "secret": secret},
            "xhttp-vless": {"port": 11443, "server_name": "probe.example", "path": "/vless", "uuid": "00000000-0000-4000-8000-000000000001"},
            "xhttp-trojan": {"port": 12443, "server_name": "probe.example", "path": "/trojan", "password": secret},
            "tcp-trojan": {"port": 13443, "server_name": "probe.example", "password": secret},
            "tls-non-443": {"port": 14443, "server_name": "probe.example"},
        },
    }))
    profile.chmod(0o600)
    config = tmp_path / "matrix.yaml"
    config.write_text(yaml.safe_dump({
        "schema_version": 2,
        "vantage": "filtered-path-a",
        "poll_interval_seconds": 300,
        "control": {"url": "https://control.example/probe", "expected_status": 204, "timeout_seconds": 2, "degraded_after_ms": 3000},
        "protocols": ["mtproto", "xhttp-vless", "xhttp-trojan", "tcp-trojan", "tls-non-443"],
        "targets": [{"id": "generic-dual", "comparison_set": "generic-pair", "destination_class": "neutral-pattern", "topology": "single-ip-dual-role", "profile_file": str(profile)}],
    }))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "curl", "#!/bin/sh\nprintf '204 0.042000'\n")
    _executable(bin_dir / "openssl", "#!/bin/sh\nexit 0\n")
    _executable(bin_dir / "xray", """#!/usr/bin/env python3
import json, socket, sys
if sys.argv[1:2] == ["version"]:
    print("Xray 26.3.27 (Xray, Penetrates Everything.) d2758a0 (go1.26.1 darwin/arm64)")
    raise SystemExit(0)
if "-test" in sys.argv:
    raise SystemExit(0)
path = sys.argv[sys.argv.index("-config") + 1]
port = json.load(open(path))["inbounds"][0]["port"]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", port))
s.listen()
while True:
    conn, _ = s.accept()
    conn.close()
""")
    mtproto = bin_dir / "probe-matrix-mtproto"
    _executable(mtproto, """#!/usr/bin/env python3
import json, sys
if sys.argv[1:] == ["--version"]:
    print("gotd-v0.160.0")
    raise SystemExit(0)
request = json.load(sys.stdin)
assert "secret" in request
print(json.dumps({"ok": True}))
""")
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PROBE_MATRIX_MTPROTO_BIN"] = str(mtproto)
    return config, env, secret


def _run(config: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", str(DRIVER), *args, "--config", str(config)], cwd=REPO_ROOT, env=env, text=True, capture_output=True, timeout=10, check=False)


def test_direct_control_success_uses_shared_verdict_contract(tmp_path: Path) -> None:
    config, env, _ = _setup(tmp_path)
    result = _run(config, env, "control")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"verdict": "ok", "rtt_ms": 42}


def test_all_five_protocol_adapters_succeed_without_leaking_secrets(tmp_path: Path) -> None:
    config, env, secret = _setup(tmp_path)
    for protocol in ("mtproto", "xhttp-vless", "xhttp-trojan", "tcp-trojan", "tls-non-443"):
        result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", protocol, "--control-verdict", "ok")
        assert result.returncode == 0, f"{protocol}: {result.stderr}"
        assert json.loads(result.stdout)["verdict"] == "ok"
        assert secret not in result.stdout + result.stderr


def test_unsafe_profile_permissions_fail_closed_without_secret_leak(tmp_path: Path) -> None:
    config, env, secret = _setup(tmp_path)
    profile = Path(yaml.safe_load(config.read_text())["targets"][0]["profile_file"])
    profile.chmod(0o644)
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "mtproto", "--control-verdict", "ok")
    assert json.loads(result.stdout) == {"verdict": "error", "rtt_ms": None, "error_kind": "profile-permissions"}
    assert secret not in result.stdout + result.stderr


def test_network_failure_is_unknown_when_direct_control_is_unavailable(tmp_path: Path) -> None:
    config, env, _ = _setup(tmp_path)
    curl = Path(env["PATH"].split(":", 1)[0]) / "curl"
    _executable(curl, "#!/bin/sh\nexit 28\n")
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "xhttp-vless", "--control-verdict", "error")
    assert json.loads(result.stdout)["verdict"] == "unknown"


def test_slow_authenticated_request_is_throttled(tmp_path: Path) -> None:
    config, env, _ = _setup(tmp_path)
    document = yaml.safe_load(config.read_text())
    document["control"]["degraded_after_ms"] = 10
    config.write_text(yaml.safe_dump(document))
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "xhttp-vless", "--control-verdict", "ok")
    assert json.loads(result.stdout)["verdict"] == "throttled"


def test_network_failure_is_blocked_only_with_healthy_same_tick_control(tmp_path: Path) -> None:
    config, env, _ = _setup(tmp_path)
    curl = Path(env["PATH"].split(":", 1)[0]) / "curl"
    _executable(curl, "#!/bin/sh\nexit 28\n")
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "xhttp-vless", "--control-verdict", "ok")
    assert json.loads(result.stdout)["verdict"] == "blocked"


def test_xray_version_mismatch_is_dependency_error(tmp_path: Path) -> None:
    config, env, secret = _setup(tmp_path)
    xray = Path(env["PATH"].split(":", 1)[0]) / "xray"
    _executable(xray, "#!/bin/sh\nprintf 'Xray v0.0.0\\n'\n")
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "tcp-trojan", "--control-verdict", "ok")
    assert json.loads(result.stdout)["error_kind"] == "version-mismatch"
    assert secret not in result.stdout + result.stderr


@pytest.mark.parametrize("pin,banner,returncode", [
    ("v26.3.2", "Xray 26.3.27", 0),
    ("v26.3.27", "unrelated v26.3.27", 0),
    ("v26.3.27", "Xray 26.3.27", 1),
])
def test_xray_pin_requires_exact_successful_version_banner(tmp_path, pin, banner, returncode):
    config, env, _ = _setup(tmp_path)
    profile = tmp_path / "target.json"
    document = json.loads(profile.read_text())
    document["expected_xray_version"] = pin
    profile.write_text(json.dumps(document))
    xray = Path(env["PATH"].split(":", 1)[0]) / "xray"
    _executable(xray, f"#!/usr/bin/env python3\nprint({banner!r})\nraise SystemExit({returncode})\n")
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "tcp-trojan", "--control-verdict", "ok")
    assert json.loads(result.stdout)["error_kind"] == "version-mismatch"


def test_xray_authentication_rejection_never_becomes_filtering_claim(tmp_path: Path) -> None:
    config, env, _ = _setup(tmp_path)
    bin_dir = Path(env["PATH"].split(":", 1)[0])
    _executable(bin_dir / "curl", "#!/bin/sh\nexit 28\n")
    _executable(bin_dir / "xray", """#!/usr/bin/env python3
import json, pathlib, socket, sys
if sys.argv[1:2] == ["version"]:
    print("Xray 26.3.27")
    raise SystemExit(0)
if "-test" in sys.argv:
    raise SystemExit(0)
config = json.load(open(sys.argv[sys.argv.index("-config") + 1]))
pathlib.Path(config["log"]["error"]).write_text("authentication rejected")
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(("127.0.0.1", config["inbounds"][0]["port"]))
listener.listen()
while True:
    connection, _ = listener.accept()
    connection.close()
""")
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "xhttp-vless", "--control-verdict", "ok")
    assert json.loads(result.stdout)["error_kind"] == "authentication"


def test_mtproto_authentication_rejection_is_error_and_request_is_stdin_only(tmp_path: Path) -> None:
    config, env, secret = _setup(tmp_path)
    bin_dir = Path(env["PATH"].split(":", 1)[0])
    argv_log = tmp_path / "argv.log"
    helper = bin_dir / "probe-matrix-mtproto"
    _executable(helper, f"""#!/usr/bin/env python3
import json, pathlib, sys
if sys.argv[1:] == ["--version"]:
    print("gotd-v0.160.0")
    raise SystemExit(0)
pathlib.Path({str(argv_log)!r}).write_text(repr(sys.argv))
json.load(sys.stdin)
print(json.dumps({{"error_kind": "authentication"}}))
raise SystemExit(1)
""")
    result = _run(config, env, "cell", "--target-id", "generic-dual", "--protocol", "mtproto", "--control-verdict", "ok")
    assert json.loads(result.stdout)["error_kind"] == "authentication"
    assert secret not in result.stdout + result.stderr + argv_log.read_text()


def test_make_interfaces_emit_one_json_line_for_invalid_requests() -> None:
    for target in ("probe-matrix-control", "probe-matrix-cell"):
        result = subprocess.run(["make", target], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        lines = result.stdout.splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["error_kind"] == "request-invalid"
