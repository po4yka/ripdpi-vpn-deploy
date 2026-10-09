"""Real native bearer failure logging and independent TLS identity preflight."""

from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from jinja2 import Environment, StrictUndefined
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_bearer_rate_and_upstream_failures_keep_only_categorical_diagnostics():
    assert os.geteuid() == 0 and shutil.which("nginx")
    base = Path("/var/lib") / ("vpn-p2-bearer-" + uuid.uuid4().hex[:12])
    base.mkdir(mode=0o755)
    with socket.socket() as socket_file:
        socket_file.bind(("127.0.0.1", 0))
        port = socket_file.getsockname()[1]
    with socket.socket() as socket_file:
        socket_file.bind(("127.0.0.1", 0))
        upstream = socket_file.getsockname()[1]
    certificate, key = base / "certificate.pem", base / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-subj",
            "/CN=sub.example.test",
            "-addext",
            "subjectAltName=DNS:sub.example.test",
            "-days",
            "1",
        ],
        check=True,
        capture_output=True,
    )
    spec = importlib.util.spec_from_file_location(
        "subscription_tls",
        ROOT / "ansible/roles/subscription-host/files/subscription_tls.py",
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    authority = {
        "certificate": certificate.read_text(),
        "private_key": key.read_text(),
        "hostname": "sub.example.test",
    }
    helper.validate(authority)
    with pytest.raises(ValueError):
        helper.validate({**authority, "hostname": "other.example.test"})
    with pytest.raises(ValueError):
        helper.validate({**authority, "private_key": "invalid-key"})
    context = {
        "subscription": {
            "port": port,
            "server_name": "sub.example.test",
            "bootstrap_listen_port": upstream,
            "rate_burst": 1,
            "enable_bootstrap": True,
        },
        "subscription_port": port,
        "nginx_xhttp": {"server_name": "unused.example.test"},
        "vpn": {"share_bundles": [{"token": "synthetic"}]},
    }
    environment = Environment(undefined=StrictUndefined, autoescape=False)
    site = environment.from_string(
        (
            ROOT / "ansible/roles/subscription-host/templates/subscription.conf.j2"
        ).read_text()
    ).render(**context)
    site = (
        site.replace(
            "/etc/nginx/tls/subscription-host/server.fullchain.pem", str(certificate)
        )
        .replace("/etc/nginx/tls/subscription-host/server.key", str(key))
        .replace("/var/log/nginx/", str(base) + "/")
    )
    zone = environment.from_string(
        (
            ROOT / "ansible/roles/subscription-host/templates/rate-limit.conf.j2"
        ).read_text()
    ).render(**context)
    config = base / "nginx.conf"
    config.write_text(
        f"pid {base}/nginx.pid; error_log {base}/global.error.log warn; events {{}} http {{ access_log {base}/global.access.log; {zone} {site} }}"
    )
    process = subprocess.Popen(
        ["/usr/sbin/nginx", "-c", str(config), "-g", "daemon off;"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    token = "SyntheticBearerBoundary00000001"
    statuses = []
    try:
        for attempt in range(40):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        tls = ssl._create_unverified_context()
        for prefix in ("sub", "bootstrap"):
            for _ in range(5):
                try:
                    urllib.request.urlopen(
                        f"https://127.0.0.1:{port}/{prefix}/{token}",
                        context=tls,
                        timeout=2,
                    )
                except urllib.error.HTTPError as error:
                    statuses.append(error.code)
        assert 502 in statuses and 429 in statuses
        time.sleep(0.1)
    finally:
        process.terminate()
        process.wait(timeout=10)
    try:
        logs = "\n".join(path.read_text() for path in base.glob("*.log"))
        assert (
            token not in logs
        ), "nginx failure diagnostics exposed synthetic bearer URI"
        assert (
            "status=502" in logs and "status=429" in logs
        ), "categorical diagnostics must retain upstream and rate-limit outcomes"
    finally:
        shutil.rmtree(base)
