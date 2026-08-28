"""Behavior tests for the probe-matrix control and cell driver interface."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import ssl
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "probe-matrix-driver.py"


@pytest.fixture
def https_control(tmp_path: Path, monkeypatch):
    """Real loopback TLS/curl path checks, not VPN protocol acceptance."""
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
        "-nodes", "-days", "1", "-subj", "/CN=127.0.0.1",
        "-addext", "subjectAltName=IP:127.0.0.1", "-keyout", str(key), "-out", str(cert),
    ], check=True, capture_output=True, timeout=10)
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib callback name
            requests.append(self.path)
            self.send_response(204)
            self.end_headers()

        def log_message(self, _format, *_args):
            return

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Bind without listening: the failed SOCKS endpoint cannot be stolen by
    # another test between port discovery and curl's connection attempt.
    with socket.socket() as refused:
        refused.bind(("127.0.0.1", 0))
        monkeypatch.setenv("CURL_CA_BUNDLE", str(cert))
        monkeypatch.setenv("CURL_HOME", str(tmp_path))
        try:
            yield {
                "url": f"https://127.0.0.1:{server.server_port}/probe",
                "expected_status": 204, "timeout_seconds": 2, "degraded_after_ms": 3000,
            }, refused.getsockname()[1], requests
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


@pytest.fixture(params=["matrix", "sentinel", "sentinel-parallel"])
def real_curl_probe(request):
    name = request.param
    path = DRIVER if name == "matrix" else REPO_ROOT / "scripts" / "vpn-protocol-liveness.py"
    spec = importlib.util.spec_from_file_location("loopback_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def run(control, port=None):
        if name == "matrix":
            return module.curl_probe({"control": control}, proxy_port=port)
        config = {**control, "probe_url": control["url"]}
        extra = ["--socks5-hostname", f"127.0.0.1:{port}"] if port is not None else []
        if name == "sentinel-parallel":
            return module.parallel_curl_probes(config, [extra])[0]
        return module.curl_probe(config, extra)

    return run


@pytest.mark.parametrize("ambient", ["curlrc", "uppercase-proxy", "lowercase-proxy"])
def test_real_curl_direct_control_ignores_ambient_proxy(
    tmp_path, monkeypatch, https_control, real_curl_probe, ambient,
):
    control, port, requests = https_control
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            monkeypatch.delenv(name)
    proxy = f"http://127.0.0.1:{port}"
    if ambient == "curlrc":
        (tmp_path / ".curlrc").write_text(f'proxy = "{proxy}"\n')
    else:
        for name in ("https_proxy", "all_proxy"):
            monkeypatch.setenv(name.upper() if ambient == "uppercase-proxy" else name, proxy)
    assert real_curl_probe(control)["verdict"] == "ok"
    assert requests == ["/probe"]


@pytest.mark.parametrize("ambient", ["curlrc", "NO_PROXY", "no_proxy"])
def test_real_curl_dead_socks_cannot_bypass_tunnel(
    tmp_path, monkeypatch, https_control, real_curl_probe, ambient,
):
    control, port, requests = https_control
    if ambient == "curlrc":
        (tmp_path / ".curlrc").write_text('noproxy = "*"\n')
    else:
        monkeypatch.setenv(ambient, "*")
    assert real_curl_probe(control)["verdict"] == "ok"
    result = real_curl_probe(control, port)
    assert result["verdict"] not in {"ok", "throttled"}
    assert result["error_kind"] == "network"
    assert requests == ["/probe"]


def test_real_curl_curlrc_cannot_disable_tls_validation(
    tmp_path, monkeypatch, https_control, real_curl_probe,
):
    control, _, requests = https_control
    monkeypatch.delenv("CURL_CA_BUNDLE")
    (tmp_path / ".curlrc").write_text("insecure\n")
    result = real_curl_probe(control)
    assert result["verdict"] == "error"
    assert result["error_kind"].replace("_", "-") == "unexpected-response"
    assert requests == []


def test_real_curl_expected_https_status_is_required(https_control, real_curl_probe):
    control, _, requests = https_control
    result = real_curl_probe({**control, "expected_status": 200})
    assert result["verdict"] == "error"
    assert result["error_kind"].replace("_", "-") == "unexpected-response"
    assert requests == ["/probe"]


def test_real_curl_subprocess_has_explicit_path_and_no_proxy_environment(
    monkeypatch, https_control, real_curl_probe,
):
    control, port, _ = https_control
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                 "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.setenv(name, "ambient-value")
    actual_popen = subprocess.Popen
    calls = []

    def observed_popen(command, *args, **kwargs):
        calls.append((command, kwargs.get("env")))
        return actual_popen(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", observed_popen)
    assert real_curl_probe(control)["verdict"] == "ok"
    assert real_curl_probe(control, port)["verdict"] not in {"ok", "throttled"}
    assert len(calls) == 2
    for index, (command, environment) in enumerate(calls):
        assert command[:2] == ["curl", "--disable"]
        assert environment is not None
        assert not any(name.lower().endswith("_proxy") for name in environment)
        assert environment["PATH"] == os.environ["PATH"]
        assert command[command.index("--noproxy") + 1] == ("" if index else "*")
    assert calls[0][0][calls[0][0].index("--proxy") + 1] == ""


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
