"""Owned public address simulation inside an isolated, route-free Linux netns."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


def test_owned_public_path_uses_explicit_endpoint_and_preserves_private_target(tmp_path):
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    namespace = "rtv" + uuid.uuid4().hex[:8]
    certificate, key = tmp_path / "certificate.pem", tmp_path / "private.pem"
    def command(argv):
        return subprocess.run(argv, check=True, capture_output=True, timeout=15)
    command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
             "-out", str(certificate), "-subj", "/CN=owned.example", "-addext", "subjectAltName=DNS:owned.example", "-days", "1"])
    before = certificate.read_bytes(), key.read_bytes()
    command(["ip", "netns", "add", namespace])
    server = None
    try:
        command(["ip", "-n", namespace, "link", "set", "lo", "up"])
        command(["ip", "-n", namespace, "address", "add", "93.184.216.34/32", "dev", "lo"])
        server = subprocess.Popen(["ip", "netns", "exec", namespace, "openssl", "s_server", "-accept", "93.184.216.34:8444",
            "-cert", str(certificate), "-key", str(key), "-tls1_3", "-alpn", "h2,http/1.1", "-www", "-quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            assert server.poll() is None
            status = command(["ip", "netns", "exec", namespace, "ss", "-lnt"]).stdout
            if b"93.184.216.34:8444" in status:
                break
            time.sleep(.05)
        else:
            pytest.fail("owned native public fixture listener unavailable")
        environment = {**os.environ, "TARGET": "127.0.0.1:8443", "SERVER_NAMES": "owned.example",
            "REALITY_TARGET_PUBLIC_ENDPOINT": "93.184.216.34:8444", "REALITY_TARGET_CA_FILE": str(certificate)}
        result = subprocess.run(["ip", "netns", "exec", namespace, sys.executable,
            str(ROOT / "scripts/reality_target_validation.py"), "--mode", "owned-public", "--budget", "10"],
            env=environment, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout
        assert json.loads(result.stdout)["verdict"] == "passed"
        assert "owned.example" not in result.stdout and "93.184.216.34" not in result.stdout
        assert (certificate.read_bytes(), key.read_bytes()) == before
        assert not command(["ip", "-n", namespace, "route", "show", "default"]).stdout
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=2)
            except subprocess.TimeoutExpired:
                server.kill(); server.wait(timeout=2)
        command(["ip", "netns", "delete", namespace])
