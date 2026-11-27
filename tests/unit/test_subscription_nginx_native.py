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
        "subscription_field_report": {"enabled": False},
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
        .replace("/var/www/subscription-host/share/", str(base) + "/share/")
        .replace("/var/www/public-site", str(base) + "/site")
    )
    (base / "site").mkdir(mode=0o755)
    (base / "site/404.html").write_text("synthetic-site-not-found")
    (base / "site/404.html").chmod(0o644)
    zone = render_template(
        ROOT / "ansible/roles/subscription-host/templates/rate-limit.conf.j2",
        dict(**context),
    )
    config = base / "nginx.conf"
    config.write_text(
        f"pid {base}/nginx.pid; error_log {base}/global.error.log warn; events {{}} http {{ access_log {base}/global.access.log; set_real_ip_from 127.0.0.1; real_ip_header X-Test-Peer; {zone} {site} }}"
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
        # A limited request must not mark the route: it is the same answer as
        # an unmatched path, in status, headers and body.
        assert set(statuses) == {502, 404}
        with pytest.raises(urllib.error.HTTPError) as limited:
            urllib.request.urlopen(f"{origin}/sub/{token}", context=tls, timeout=2)
        with pytest.raises(urllib.error.HTTPError) as absent:
            urllib.request.urlopen(f"{origin}/unknown/{token}", context=tls, timeout=2)
        answers = [
            (error.value.code, error.value.read(), sorted((k, v) for k, v in error.value.headers.items() if k != "Date"))
            for error in (limited, absent)
        ]
        assert answers[0] == answers[1]
        assert answers[0][:2] == (404, b"synthetic-site-not-found")
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
        assert all(marker in logs for marker in ("status=404", "status=502", "limit=REJECTED")), (
            "categorical diagnostics must retain rejected, upstream and rate-limit outcomes"
        )


def test_rate_limit_counts_an_ipv6_network_and_a_whole_ipv4_address():
    token = "SyntheticBearerBoundary00000002"
    with nginx_server(rate="1r/m", burst=1) as (origin, base):
        tls = ssl._create_unverified_context()

        def status(peer):
            request = urllib.request.Request(f"{origin}/sub/{token}", headers={"X-Test-Peer": peer})
            with pytest.raises(urllib.error.HTTPError) as failed:
                urllib.request.urlopen(request, context=tls, timeout=2)
            return failed.value.code

        # 502 is the closed upstream, so the request passed the limit; 404 is a refusal.
        # One request and one burst request pass for each key.
        assert [status("2001:db8:1:2::1"), status("2001:db8:1:2:ffff:a:b:c")] == [502, 502]
        assert status("2001:db8:1:2:1::9") == 404, "addresses in one /64 must share the limit"
        assert status("2001:db8:1:3::1") == 502
        assert [status("198.51.100.10"), status("198.51.100.10")] == [502, 502]
        assert status("198.51.100.11") == 502, "IPv4 neighbours must not share a limit"
        assert status("198.51.100.10") == 404


def test_share_bundle_files_are_served_only_from_their_own_token_directory():
    token = "SyntheticShareBoundary00000001"
    with nginx_server(routes_enabled=True, rate="1000r/s", burst=50) as (origin, base):
        bundle = base / "share" / token
        bundle.mkdir(parents=True)
        (bundle / "index.html").write_text("recipient-page")
        (bundle / "qr.svg").write_text("qr-image")
        (base / "share" / "outside.txt").write_text("outside-bundle")
        for path in (base / "share", bundle, *bundle.iterdir(), base / "share" / "outside.txt"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        tls = ssl._create_unverified_context()
        for path, body in ((f"/share/{token}/", b"recipient-page"), (f"/share/{token}/index.html", b"recipient-page"),
                           (f"/share/{token}/qr.svg", b"qr-image")):
            with urllib.request.urlopen(origin + path, context=tls, timeout=2) as response:
                assert response.status == 200 and response.read() == body
                assert response.headers.get_all("Cache-Control") == ["no-store"]
        for path in (f"/share/{token}", f"/share/{token}/missing", f"/share/{token}/..%2Foutside.txt",
                     f"/share/{token}/nested/qr.svg", "/share/" + "B" * 24 + "/"):
            with pytest.raises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(origin + path, context=tls, timeout=2)
            assert refused.value.code == 404
        time.sleep(0.1)
        logs = "\n".join(path.read_text() for path in base.glob("*.log"))
        assert token not in logs, "nginx share diagnostics exposed the synthetic bearer URI"


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
        # nginx owns the error body: the backend's page would name its software.
        gone = expired.value.read()
        assert b"410 Gone" in gone and b"Error response" not in gone and b"Error code" not in gone
        meta.write_text("{}")
        service.REVOKED_FILE.write_text(digest + "\n")
        with pytest.raises(urllib.error.HTTPError) as revoked:
            urllib.request.urlopen(urls.qr_singbox, context=tls, timeout=3)
        assert revoked.value.code == 410
        time.sleep(0.1)
        logs = "\n".join(path.read_text() for path in base.glob("*.log"))
        assert token not in logs, "nginx delivery diagnostics exposed synthetic bearer URI"
        assert "status=200" in logs and "status=410" in logs


def test_other_methods_on_bearer_routes_answer_as_an_unmatched_path(service):
    # The backend answers an unsupported method, HEAD included, with a 501 page that names http.server.
    token, _, _, _ = prepare_subscription(service)
    with (
        delivery_server(service) as backend,
        nginx_server(upstream=backend.server_port, rate="1000r/s", burst=20) as (origin, _),
    ):
        tls = ssl._create_unverified_context()

        def answer(method, path):
            request = urllib.request.Request(origin + path, method=method)
            with pytest.raises(urllib.error.HTTPError) as failed:
                urllib.request.urlopen(request, context=tls, timeout=3)
            headers = sorted((k, v) for k, v in failed.value.headers.items() if k != "Date")
            return failed.value.code, failed.value.read(), headers

        for method in ("HEAD", "POST", "PUT", "OPTIONS"):
            absent = answer(method, f"/unknown/{token}")
            assert absent[0] == 404
            for path in (f"/sub/{token}", f"/bootstrap/{token}"):
                assert answer(method, path) == absent, (method, path)
        assert answer("POST", f"/sub/{token}")[:2] == (404, b"synthetic-site-not-found")
