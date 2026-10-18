"""Real native bearer failure logging and independent TLS identity preflight."""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import test_subscription_retention
from template_render import render_template
from test_subscription_delivery_urls import (
    build_sub_urls,
    delivery_server,
    prepare_subscription,
)

service = test_subscription_retention.service

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


@contextmanager
def nginx_server(*, routes_enabled=True, upstream=None, rate="5r/m", burst=1):
    assert os.geteuid() == 0 and shutil.which("nginx")
    base = Path("/var/lib") / ("vpn-p2-bearer-" + uuid.uuid4().hex[:12])
    base.mkdir(mode=0o755)
    with socket.socket() as socket_file:
        socket_file.bind(("127.0.0.1", 0))
        port = socket_file.getsockname()[1]
    if upstream is None:
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
            "rate_burst": burst,
            "rate_limit": rate,
            "enable_bootstrap": routes_enabled,
        },
        "subscription_port": port,
        "nginx_xhttp": {"server_name": "unused.example.test"},
        "vpn": {"share_bundles": [{"token": "synthetic"}] if routes_enabled else []},
    }
    site = render_template(
        ROOT / "ansible/roles/subscription-host/templates/subscription.conf.j2",
        dict(**context),
    )
    site = (
        site.replace(
            "/etc/nginx/tls/subscription-host/server.fullchain.pem", str(certificate)
        )
        .replace("/etc/nginx/tls/subscription-host/server.key", str(key))
        .replace("/var/log/nginx/", str(base) + "/")
    )
    zone = render_template(
        ROOT / "ansible/roles/subscription-host/templates/rate-limit.conf.j2",
        dict(**context),
    )
    config = base / "nginx.conf"
    config.write_text(
        f"pid {base}/nginx.pid; error_log {base}/global.error.log warn; events {{}} http {{ access_log {base}/global.access.log; {zone} {site} }}"
    )
    process = subprocess.Popen(
        ["/usr/sbin/nginx", "-c", str(config), "-g", "daemon off;"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for attempt in range(40):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                assert process.poll() is None, "owned nginx exited before readiness"
                time.sleep(0.05)
        else:
            pytest.fail("owned nginx listener did not become ready")
        yield f"https://127.0.0.1:{port}", base
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stderr.close()
        shutil.rmtree(base)


@pytest.mark.parametrize("routes_enabled", [True, False])
def test_bearer_rate_and_upstream_failures_keep_only_categorical_diagnostics(routes_enabled):
    token = "SyntheticBearerBoundary00000001"
    statuses = []
    with nginx_server(routes_enabled=routes_enabled) as (origin, base):
        tls = ssl._create_unverified_context()
        for prefix in (("sub", "bootstrap") if routes_enabled else ("sub",)):
            for _ in range(5):
                with pytest.raises(urllib.error.HTTPError) as failed:
                    urllib.request.urlopen(f"{origin}/{prefix}/{token}", context=tls, timeout=2)
                statuses.append(failed.value.code)
        assert 502 in statuses and 429 in statuses
        unmatched = [
            f"/sub/{token}.json", f"/sub/{token}%2Ejson", f"/sub/{token}/extra",
            f"/unknown/{token}", f"/share/{token}",
        ]
        if not routes_enabled:
            unmatched.append(f"/bootstrap/{token}")
        for path in unmatched:
            with pytest.raises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(origin + path, context=tls, timeout=2)
            assert refused.value.code == 404
            assert refused.value.headers.get_all("Cache-Control") == ["no-store"]
            assert refused.value.headers.get_all("Referrer-Policy") == ["no-referrer"]
        time.sleep(0.1)
        logs = "\n".join(path.read_text() for path in base.glob("*.log"))
        assert token not in logs, "nginx failure diagnostics exposed synthetic bearer URI"
        assert all("status=" + str(code) in logs for code in (404, 502, 429)), (
            "categorical diagnostics must retain rejected, upstream and rate-limit outcomes"
        )


def test_generated_import_and_qr_targets_cross_real_nginx_and_backend(service):
    token, digest, body, meta = prepare_subscription(service)
    with (
        delivery_server(service) as backend,
        nginx_server(upstream=backend.server_port, rate="1000r/s", burst=20) as (origin, base),
    ):
        urls = build_sub_urls(origin, token)
        imported = parse_qs(urlsplit(urls.singbox_deeplink).query)["url"][0]
        tls = ssl._create_unverified_context()
        for target in (urls.subscription_url, imported, urls.qr_singbox):
            with urllib.request.urlopen(target, context=tls, timeout=3) as response:
                assert response.status == 200 and response.read() == body
                assert response.headers.get_all("Cache-Control") == ["no-store"]
                assert response.headers.get_all("Referrer-Policy") == ["no-referrer"]
        meta.write_text('{"expires":0}')
        with pytest.raises(urllib.error.HTTPError) as expired:
            urllib.request.urlopen(imported, context=tls, timeout=3)
        assert expired.value.code == 410
        meta.write_text("{}")
        service.REVOKED_FILE.write_text(digest + "\n")
        with pytest.raises(urllib.error.HTTPError) as revoked:
            urllib.request.urlopen(urls.qr_singbox, context=tls, timeout=3)
        assert revoked.value.code == 410
        time.sleep(0.1)
        logs = "\n".join(path.read_text() for path in base.glob("*.log"))
        assert token not in logs, "nginx delivery diagnostics exposed synthetic bearer URI"
        assert "status=200" in logs and "status=410" in logs
