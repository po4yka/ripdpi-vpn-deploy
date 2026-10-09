"""The scenario's ephemeral AOP identities exercise real nginx client TLS."""

from __future__ import annotations
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
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_cdn_scenario_generated_authority_accepts_only_signed_client():
    assert os.geteuid() == 0
    base = Path("/var/lib") / ("vpn-p2-aop-" + uuid.uuid4().hex[:12])
    base.mkdir(mode=0o755)
    process = None
    try:
        converge = yaml.safe_load(
            (ROOT / "ansible/roles/cdn-front/molecule/cdn-on/converge.yml").read_text()
        )[0]
        task = next(
            row
            for row in converge["pre_tasks"]
            if row["name"]
            == "Generate the disposable AOP CA authorized client and rejected client"
        )
        generated = subprocess.run(
            [
                "/bin/bash",
                "-c",
                task["ansible.builtin.shell"]["cmd"].replace(
                    "/etc/nginx/tls", str(base)
                ),
            ],
            capture_output=True,
            timeout=30,
        )
        assert generated.returncode == 0, generated.stderr.decode()
        server_key = base / "server.key"
        server_cert = base / "server.crt"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(server_key),
                "-out",
                str(server_cert),
                "-subj",
                "/CN=cdn.example.test",
                "-days",
                "1",
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        (base / "cloudflare.real_ip").write_text(
            "set_real_ip_from 198.51.100.0/24;\nreal_ip_header CF-Connecting-IP;\nreal_ip_recursive on;\n"
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            backend = listener.getsockname()[1]
        variables = {
            "cdn_front": {
                "port": port,
                "server_name": "cdn.example.test",
                "cf_prefix_dir": str(base),
                "aop_cert_path": str(base / "cloudflare-aop.pem"),
                "upstream_addr": "127.0.0.1",
                "upstream_port": backend,
                "xhttp_path": "/app-sync",
            }
        }
        site = (
            Environment(undefined=StrictUndefined, autoescape=False)
            .from_string(
                (
                    ROOT / "ansible/roles/cdn-front/templates/cdn-front.conf.j2"
                ).read_text()
            )
            .render(**variables)
        )
        site = site.replace(
            "/etc/nginx/tls/cdn.example.test.fullchain.pem", str(server_cert)
        ).replace("/etc/nginx/tls/cdn.example.test.key", str(server_key))
        config = base / "nginx.conf"
        config.write_text(
            f"pid {base}/nginx.pid;error_log {base}/error.log;events {{}}http {{access_log {base}/access.log;{site}}}"
        )
        process = subprocess.Popen(
            ["/usr/sbin/nginx", "-c", str(config), "-g", "daemon off;"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        for identity, status in [
            ("aop-client", 502),
            (None, 400),
            ("aop-rejected", 400),
        ]:
            context = ssl._create_unverified_context()
            if identity:
                context.load_cert_chain(
                    str(base / (identity + ".crt")), str(base / (identity + ".key"))
                )
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(
                    f"https://127.0.0.1:{port}/app-sync", context=context, timeout=3
                )
            assert error.value.code == status
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
        shutil.rmtree(base)
