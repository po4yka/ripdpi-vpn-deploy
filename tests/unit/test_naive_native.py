"""Exact composite Caddy parser and real authenticated TCP proxy, with no UDP."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import jinja2
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_exact_naive_composite_accepts_tcp_and_disables_http3(tmp_path):
    assert sys.platform == "linux", "requires exact Linux composite binary"
    binary = Path(
        os.environ.get(
            "NAIVE_NATIVE_BINARY", str(ROOT / ".cache/p2-native-caddy/caddy")
        )
    ).resolve()
    assert (
        binary.is_file()
    ), "requires reviewed exact xcaddy/Caddy/forwardproxy composite build"
    info = subprocess.run(
        [str(binary), "build-info"], capture_output=True, text=True, timeout=5
    )
    assert info.returncode == 0
    assert "v2.11.2" in info.stdout
    assert (
        "github.com/klzgrad/forwardproxy" in info.stdout
        and "d62c80d3dd2c" in info.stdout
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (tmp_path / "server.fullchain.pem").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
    )
    (tmp_path / "server.key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (tmp_path / "index.html").write_text("native exact Naive decoy")
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    config = tmp_path / "Caddyfile"
    values = {
        "naive": {
            "log_dir": str(tmp_path),
            "config_dir": str(tmp_path),
            "decoy_root": str(tmp_path),
            "bind_port": port,
        },
        "naive_secrets": {
            "server_name": "localhost",
            "username": "p2-user",
            "password": "p2-local-test-password",
            "probe_resistance_secret": "p2-local-test-secret",
        },
    }
    config.write_text(
        jinja2.Template(
            (ROOT / "ansible/roles/naive/templates/Caddyfile.j2").read_text()
        ).render(**values)
    )
    adapted = subprocess.run(
        [str(binary), "adapt", "--config", str(config), "--adapter", "caddyfile"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert adapted.returncode == 0, adapted.stderr
    document = json.loads(adapted.stdout)
    servers = document["apps"]["http"]["servers"]
    listeners = {address for server in servers.values() for address in server["listen"]}
    assert listeners == {
        ":" + str(port)
    }, "only the configured manifest TCP port may listen"
    assert all(server.get("protocols") == ["h1", "h2"] for server in servers.values())
    valid = subprocess.run(
        [str(binary), "validate", "--config", str(config), "--adapter", "caddyfile"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert valid.returncode == 0, valid.stderr
    assert (
        os.geteuid() == 0
    ), "positive native proxy fixture requires a private root network namespace"
    namespace = "p2-naive-" + uuid.uuid4().hex[:7]
    original_network = os.open("/proc/self/ns/net", os.O_RDONLY)
    process = None
    upstream = None
    try:
        subprocess.run(
            ["ip", "netns", "add", namespace],
            check=True,
            capture_output=True,
            timeout=5,
        )
        target_network = os.open("/run/netns/" + namespace, os.O_RDONLY)
        try:
            os.setns(target_network, os.CLONE_NEWNET)
        finally:
            os.close(target_network)
        subprocess.run(
            ["ip", "link", "set", "lo", "up"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["ip", "addr", "add", "203.0.113.9/32", "dev", "lo"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        process = subprocess.Popen(
            [str(binary), "run", "--config", str(config), "--adapter", "caddyfile"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        upstream = socket.socket()
        upstream.bind(("203.0.113.9", 0))
        upstream.listen()
        upstream.settimeout(3)
        context = ssl.create_default_context(
            cafile=str(tmp_path / "server.fullchain.pem")
        )
        context.set_alpn_protocols(["http/1.1"])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), 0.1):
                    break
            except OSError:
                assert (
                    process.poll() is None
                ), "exact Caddy process failed before serving"
                time.sleep(0.05)
        sockets = subprocess.run(
            ["ss", "-H", "-lnup"], capture_output=True, text=True, check=True, timeout=5
        ).stdout
        assert not any(
            str(port) == row.split()[3].rsplit(":", 1)[-1]
            for row in sockets.splitlines()
        ), "HTTP3/UDP must be absent"
        with context.wrap_socket(
            socket.create_connection(("127.0.0.1", port), 3),
            server_hostname="localhost",
        ) as client:
            client.settimeout(3)
            client.sendall(
                b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            )
            response = b""
            while data := client.recv(4096):
                response += data
            assert b"200 OK" in response and b"native exact Naive decoy" in response
        h2 = subprocess.run(
            [
                "curl",
                "--noproxy",
                "*",
                "--http2",
                "--silent",
                "--show-error",
                "--max-time",
                "3",
                "--cacert",
                str(tmp_path / "server.fullchain.pem"),
                "--resolve",
                f"localhost:{port}:127.0.0.1",
                "--write-out",
                "\n%{http_version}",
                f"https://localhost:{port}/",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert h2.returncode == 0 and h2.stdout.endswith("\n2"), h2.stderr
        assert "native exact Naive decoy" in h2.stdout
        with context.wrap_socket(
            socket.create_connection(("127.0.0.1", port), 3),
            server_hostname="localhost",
        ) as denied:
            denied.settimeout(3)
            target = f"203.0.113.9:{upstream.getsockname()[1]}"
            denied.sendall(
                f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode()
            )
            response = denied.recv(4096)
            assert (
                b"200" not in response.split(b"\r\n", 1)[0]
            ), "unauthenticated CONNECT must not establish a tunnel"
            upstream.settimeout(0.1)
            with pytest.raises(socket.timeout):
                upstream.accept()
            upstream.settimeout(3)
        with context.wrap_socket(
            socket.create_connection(("127.0.0.1", port), 3),
            server_hostname="localhost",
        ) as proxy:
            proxy.settimeout(3)
            target = f"203.0.113.9:{upstream.getsockname()[1]}"
            auth = base64.b64encode(b"p2-user:p2-local-test-password").decode()
            proxy.sendall(
                f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nProxy-Authorization: Basic {auth}\r\n\r\n".encode()
            )
            response = b""
            while b"\r\n\r\n" not in response:
                response += proxy.recv(4096)
            assert b"200" in response.split(b"\r\n", 1)[0], response
            with upstream.accept()[0] as accepted:
                accepted.settimeout(3)
                proxy.sendall(b"positive authenticated tunnel")
                assert accepted.recv(4096) == b"positive authenticated tunnel"
                accepted.sendall(b"positive upstream reply")
                assert proxy.recv(4096) == b"positive upstream reply"
    finally:
        if upstream:
            upstream.close()
        if process:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        os.setns(original_network, os.CLONE_NEWNET)
        os.close(original_network)
        subprocess.run(
            ["ip", "netns", "delete", namespace], capture_output=True, timeout=5
        )
