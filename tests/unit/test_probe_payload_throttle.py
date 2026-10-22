"""Real curl/HTTP/TLS/SOCKS evidence plus deterministic classification cases."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import selectors
import socket
import socketserver
import ssl
import subprocess
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/probe-payload-throttle.sh"
sys.path.insert(0, str(ROOT / "scripts"))
import payload_probe_content as probe  # noqa: E402

spec = importlib.util.spec_from_file_location("payload_canary", ROOT / "scripts/serve-payload-probe.py")
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)


def run_probe(tmp_path, port, *args, env_extra=None):
    env = dict(os.environ, HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"))
    env.update(env_extra or {})
    result = subprocess.run(["bash", str(SCRIPT), "--host", "localhost", "--port", str(port),
        "--scheme", "http", "--asn", "AS64500", "--sizes", "1024,16384,32768", "--no-state", *args],
        capture_output=True, text=True, env=env, timeout=40)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 1, result.stdout
    return json.loads(result.stdout)


@contextmanager
def origin(handler=canary.Handler, tls=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    if tls:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class Fault(BaseHTTPRequestHandler):
    mode = "empty"
    requests = []

    def do_GET(self):
        type(self).requests.append(self.path)
        size = int(self.path.rsplit("=", 1)[1])
        if self.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "/redirected")
            self.end_headers()
            return
        data = {"empty": b"", "short": probe.payload(size)[:-1], "corrupt": b"x" * size,
                "oversize": probe.payload(size) + b"x", "404": b"missing", "truncated": probe.payload(size)[:-1],
                "chunked": b"x" * (size + 200)}[self.mode]
        self.send_response(404 if self.mode == "404" else 200)
        if self.mode != "chunked":
            self.send_header("Content-Length", str(size if self.mode == "truncated" else len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


@pytest.mark.parametrize("mode", ["empty", "short", "corrupt", "oversize", "404", "redirect", "chunked"])
def test_real_success_status_cannot_fake_payload(tmp_path, mode):
    handler = type("Response", (Fault,), {"mode": mode, "requests": []})
    with origin(handler) as port:
        result = run_probe(tmp_path, port)
    assert result["verdict"] == "error"
    assert not any(row["completed"] for row in result["sizes"])
    assert len(handler.requests) == 3  # redirect never follows another origin/path


def test_real_download_and_upload(tmp_path):
    with origin() as port:
        result = run_probe(tmp_path, port, "--upload")
    assert len(result["sizes"]) == 6
    assert all(row["completed"] for row in result["sizes"])
    assert {row["direction"] for row in result["sizes"]} == {"download", "upload"}
    assert all(isinstance(row["rtt_ms"], int) for row in result["sizes"])
    assert not (tmp_path / "state").exists()


def test_tls_verified_with_owned_ca_and_rejected_without_it(tmp_path):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost", "-keyout", str(key), "-out", str(cert)],
        check=True, capture_output=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    with origin(tls=context) as port:
        accepted = run_probe(tmp_path, port, "--scheme", "https", "--ca-file", str(cert), "--upload")
        refused = run_probe(tmp_path, port, "--scheme", "https")
    assert all(row["completed"] for row in accepted["sizes"])
    assert refused["verdict"] == "error"
    assert not any(row["completed"] for row in refused["sizes"])


def receive_exact(connection, count):
    data = b""
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise ConnectionError("short SOCKS message")
        data += chunk
    return data


class Socks(socketserver.BaseRequestHandler):
    def handle(self):
        client = self.request
        client.settimeout(5)
        version, count = receive_exact(client, 2)
        assert version == 5
        assert 0 in receive_exact(client, count)
        client.sendall(b"\x05\x00")
        header = receive_exact(client, 4)
        assert header == b"\x05\x01\x00\x03"  # DNS is resolved at SOCKS endpoint
        length = receive_exact(client, 1)[0]
        host = receive_exact(client, length).decode()
        port = int.from_bytes(receive_exact(client, 2), "big")
        self.server.targets.append((host, port))
        with socket.create_connection(("127.0.0.1", port), timeout=5) as upstream:
            client.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            with selectors.DefaultSelector() as selected:
                selected.register(client, selectors.EVENT_READ, upstream)
                selected.register(upstream, selectors.EVENT_READ, client)
                while True:
                    events = selected.select(timeout=5)
                    if not events:
                        return
                    for key, _ in events:
                        data = key.fileobj.recv(65536)
                        if not data:
                            return
                        key.data.sendall(data)


@contextmanager
def socks():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Socks)
    server.daemon_threads = True
    server.targets = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_socks_dns_and_upload_ignore_proxy_environment(tmp_path):
    (tmp_path / ".curlrc").write_text("proxy = http://127.0.0.1:1\nlocation\ninsecure\n")
    with origin() as port, socks() as proxy:
        result = run_probe(tmp_path, port, "--socks-port", str(proxy.server_address[1]), "--upload",
            env_extra={"NO_PROXY": "*", "ALL_PROXY": "http://127.0.0.1:1"})
        assert proxy.targets == [("localhost", port)] * 6
    assert all(row["completed"] for row in result["sizes"])


def test_failed_socks_never_falls_back(tmp_path):
    handler = type("Response", (Fault,), {"requests": []})
    with origin(handler) as port, socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))  # owned but deliberately not listening
        result = run_probe(tmp_path, port, "--socks-port", str(unavailable.getsockname()[1]))
    assert result["verdict"] == "blocked"
    assert handler.requests == []


def test_direct_ignores_ambient_proxy(tmp_path):
    (tmp_path / ".curlrc").write_text("proxy = http://127.0.0.1:1\n")
    with origin() as port:
        result = run_probe(tmp_path, port, env_extra={"ALL_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1"})
    assert all(row["completed"] for row in result["sizes"])


@pytest.mark.parametrize("args", [["--port", "0"], ["--timeout", "31"], ["--socks-port", "65536"],
    ["--asn", "../../escape"], ["--sizes", "1024,65537"], ["--sizes", "1024,1024"],
    ["--sizes", "32768,1024"], ["--echo-path", "/foo?x=1"], ["--host", "-option"], ["--port"]])
def test_invalid_inputs_before_network(tmp_path, args):
    handler = type("Response", (Fault,), {"requests": []})
    with origin(handler) as port:
        result = run_probe(tmp_path, port, *args)
    assert result["verdict"] == "error"
    assert handler.requests == []
    assert not (tmp_path / "state").exists()


def row(size, duration=10, completed=True, direction="download"):
    result = {"bytes": size, "completed": completed, "rtt_ms": duration if completed else None, "direction": direction}
    if not completed:
        result["error_kind"] = "network"
    return result


@pytest.mark.parametrize("rows,verdict,threshold", [
    ([row(1024), row(32768)], "ok", None),
    ([row(1024), row(32768, 100)], "ok", None),
    ([row(1024), row(32768, 1000)], "throttled", 32768),
    ([row(1024), row(32768, completed=False)], "throttled", 32768),
    ([row(1024, completed=False), row(32768, completed=False)], "blocked", None),
    ([row(1024), row(4096)], "unknown", None),
    ([row(32768)], "unknown", None),
    ([row(1024, completed=False), row(4096), row(32768)], "unknown", None),
])
def test_classification_without_host_timing(rows, verdict, threshold):
    result = probe.classify(rows)
    assert result["verdict"] == verdict
    assert result["threshold_bytes"] == threshold


def test_canary_rejects_corrupt_upload_and_invalid_bounds(tmp_path):
    with origin() as port:
        for query, body in [("1024", b"x" * 1024), ("65537", b""), ("1&bytes=2", b"x")]:
            result = subprocess.run(["curl", "--disable", "--silent", "--proxy", "", "--noproxy", "*",
                "--max-time", "2", "--data-binary", "@-", "--output", os.devnull, "--write-out", "%{http_code}",
                f"http://127.0.0.1:{port}/__throttle_probe?bytes={query}"], input=body, capture_output=True)
            assert result.stdout == b"400"


def test_hash_manifest_and_state(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/payload_probe_content.py"), "--hashes", "32768,65536"],
        capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [{"expected_bytes": n, "sha256": hashlib.sha256(probe.payload(n)).hexdigest()} for n in (32768, 65536)]
    with origin() as port:
        args = ["--host", "localhost", "--port", str(port), "--scheme", "http", "--asn", "64500", "--sizes", "1024,32768"]
        result = subprocess.run(["bash", str(SCRIPT), *args], env=dict(os.environ, XDG_STATE_HOME=str(tmp_path)), capture_output=True, text=True)
    state = tmp_path / "vpn-deploy/payload-throttle/AS64500.json"
    assert json.loads(state.read_text()) == json.loads(result.stdout)
    assert state.stat().st_mode & 0o777 == 0o600
    assert list(state.parent.iterdir()) == [state]


def test_fixed_payload_vectors():
    assert hashlib.sha256(probe.payload(32768)).hexdigest() == "80e00fc9e65a58c5ad59c399511a2ed5f27140f43e3b58f93c2f00a0c0df8816"
    assert hashlib.sha256(probe.payload(65536)).hexdigest() == "ed487b9ebb4e4ee04d86b44bc4eff46f6689bae9b8c7d8c598c57b8110a7e993"


def test_real_timeout_and_truncated_body_are_not_completed(tmp_path):
    class Stall(Fault):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "1024")
            self.end_headers()
            threading.Event().wait(1.5)

    with origin(Stall) as port:
        result = run_probe(tmp_path, port, "--sizes", "1024", "--timeout", "1")
    assert result["verdict"] == "blocked"
    assert result["sizes"][0]["error_kind"] == "network"
    with origin(type("Truncated", (Fault,), {"mode": "truncated"})) as port:
        result = run_probe(tmp_path, port, "--sizes", "1024")
    assert not result["sizes"][0]["completed"]


def test_canary_total_deadline_stops_trickled_upload():
    # Use a shorter timer solely to make the real socket deadline test quick.
    class ShortDeadline(canary.Handler):
        def setup(self):
            super().setup()
            self.deadline.cancel()
            self.deadline = threading.Timer(0.2, self.expire)
            self.deadline.start()

    with origin(ShortDeadline) as port, socket.create_connection(("127.0.0.1", port)) as connection:
        connection.settimeout(2)
        connection.sendall(b"POST /__throttle_probe?bytes=1024 HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1024\r\n\r\nx")
        assert connection.recv(1024) == b""


def test_socks_requires_explicit_asn_before_any_discovery(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("discovery must not execute for an incomplete SOCKS request")
    monkeypatch.setattr(probe.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="proxy-requires-asn"):
        probe.probe(["--host", "control.example", "--socks-port", "1080", "--no-state"])


def test_constant_transfer_rate_is_not_payload_throttling():
    rows = [row(size, size // 1024 * 10) for size in (1024, 4096, 16384, 32768, 65536)]
    assert probe.classify(rows)["verdict"] == "ok"


def test_upload_has_its_own_rate_baseline():
    rows = [row(size, size // 1024 * 10) for size in (1024, 4096, 32768)]
    rows += [row(1024, 100, direction="upload"), row(32768, 3200, direction="upload")]
    assert probe.classify(rows)["verdict"] == "ok"
    rows[-1]["rtt_ms"] = 10000
    assert probe.classify(rows)["verdict"] == "throttled"
