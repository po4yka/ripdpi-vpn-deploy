"""Real nginx/systemd TLS publication, boot ownership and compensation proof."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import pathlib
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def run(*args, check=True):
    result = subprocess.run(
        list(args), check=False, capture_output=True, text=True, timeout=45
    )
    if check and result.returncode:
        raise AssertionError(result.stderr)
    return result


def test_real_nginx_complete_tls_boot_and_failed_activation_compensation():
    assert (
        sys.platform == "linux" and os.geteuid() == 0
    ), "requires disposable native Linux root/systemd lane"
    assert shutil.which("nginx") and shutil.which(
        "openssl"
    ), "requires native nginx and openssl"
    HELPER = (ROOT / "ansible/roles/nginx-xhttp/files/nginx_transaction.py").read_text()
    suffix = uuid.uuid4().hex[:12]
    unit = "vpn-p2-nginx-" + suffix + ".service"
    unit_file = pathlib.Path("/etc/systemd/system") / unit
    base = pathlib.Path("/var/lib") / ("vpn-p2-nginx-" + suffix)
    assert not base.exists() and not unit_file.exists()
    base.mkdir(mode=0o700)
    config = base / "config"
    config.mkdir(mode=0o750)
    logs = base / "logs"
    logs.mkdir(mode=0o750)
    tls = config / "tls"
    tls.mkdir(mode=0o750)
    helper = base / "helper.py"
    helper.write_text(HELPER)
    helper.chmod(0o750)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    run(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(tls / "server.key"),
        "-out",
        str(tls / "server.crt"),
        "-subj",
        "/CN=transaction.example.test",
        "-addext",
        "subjectAltName=IP:127.0.0.1",
        "-days",
        "1",
    )
    certificate = (tls / "server.crt").read_bytes()
    key = (tls / "server.key").read_bytes()
    (tls / "server.crt").unlink()
    (tls / "server.key").unlink()
    runtime = "/run/vpn-p2-nginx-" + suffix
    unit_text = f'[Unit]\nDescription=Owned nginx transaction regression\n[Service]\nType=simple\nLoadCredential=server.crt:{tls}/server.crt\nLoadCredential=server.key:{tls}/server.key\nRuntimeDirectory=vpn-p2-nginx-{suffix}\nExecStart=/usr/sbin/nginx -c {config}/nginx.conf -g "daemon off;"\nPrivateTmp=true\nProtectSystem=strict\nNoNewPrivileges=true\nRestrictNamespaces=true\nReadWritePaths={logs}\n[Install]\nWantedBy=multi-user.target\n'

    def configuration(body):
        return f'pid {runtime}/nginx.pid;\nerror_log {logs}/error.log;\nevents {{}}\nhttp {{ access_log {logs}/access.log; server {{ listen 127.0.0.1:{port} ssl; ssl_certificate /run/credentials/{unit}/server.crt; ssl_certificate_key /run/credentials/{unit}/server.key; location / {{ return 200 "{body}"; }} }} }}\n'

    def file(path, data, mode):
        return {
            "path": str(path),
            "kind": "file",
            "content_b64": base64.b64encode(
                data if isinstance(data, bytes) else data.encode()
            ).decode(),
            "mode": mode,
            "uid": 0,
            "gid": 0,
        }

    def request(body, private_key=key, unit_data=unit_text, check=False):
        return {
            "owner": "native-regression",
            "roots": [str(config)],
            "files": [
                file(config / "nginx.conf", configuration(body), "0640"),
                file(tls / "server.crt", certificate, "0644"),
                file(tls / "server.key", private_key, "0600"),
                file(unit_file, unit_data, "0644"),
            ],
            "validate_argv": [
                "/usr/sbin/nginx",
                "-t",
                "-c",
                str(config / "nginx.conf"),
            ],
            "unit": unit,
            "activation": "restart",
            "check": check,
            "credential_root": str(tls),
            "runtime_directories": [runtime],
            "activate_inactive": True,
            "desired_enabled": True,
        }

    def publish(document):
        return subprocess.run(
            ["/usr/bin/python3", str(helper)],
            input=json.dumps(document),
            text=True,
            capture_output=True,
            timeout=90,
        )

    def body():
        context = ssl.create_default_context(cafile=str(tls / "server.crt"))
        for attempt in range(30):
            try:
                return (
                    urllib.request.urlopen(
                        f"https://127.0.0.1:{port}/", context=context, timeout=1
                    )
                    .read()
                    .decode()
                )
            except OSError as error:
                last = type(error).__name__ + ": " + str(error)
                time.sleep(0.1)
        print(
            run(
                "systemctl",
                "show",
                unit,
                "--property=ActiveState,Result,ExecMainStatus",
                check=False,
            ).stdout
        )
        print(
            run(
                "journalctl",
                "-u",
                unit,
                "--no-pager",
                "--output=cat",
                "--lines=10",
                check=False,
            ).stdout
        )
        raise AssertionError("owned nginx did not answer: " + last)

    def snapshot():
        return {
            str(path): path.read_bytes()
            for path in [
                config / "nginx.conf",
                tls / "server.crt",
                tls / "server.key",
                unit_file,
            ]
        }

    try:
        before_root = run(
            "findmnt", "-n", "-o", "TARGET,PROPAGATION", "-T", "/run"
        ).stdout
        predictive = publish(request("old", check=True))
        assert predictive.returncode == 0, predictive.stderr
        assert not unit_file.exists() and not (config / "nginx.conf").exists()
        fresh_failed = publish(
            request(
                "old",
                unit_data=unit_text.replace(
                    "/usr/sbin/nginx -c "
                    + str(config)
                    + '/nginx.conf -g "daemon off;"',
                    "/bin/false",
                ),
            )
        )
        assert fresh_failed.returncode == 1
        assert not unit_file.exists() and not (config / "nginx.conf").exists()
        assert not os.path.lexists(
            pathlib.Path("/etc/systemd/system/multi-user.target.wants") / unit
        )
        assert not (
            pathlib.Path("/var/lib/vpn-nginx-publication") / unit / "pending.json"
        ).exists()
        first = publish(request("old"))
        assert first.returncode == 0, first.stderr
        assert body() == "old"
        assert run("systemctl", "is-enabled", unit).stdout.strip() == "enabled"
        prior = snapshot()
        fifo = config / "unrelated-fifo"
        os.mkfifo(fifo, 0o600)
        preparation_failed = publish(request("old"))
        assert preparation_failed.returncode == 1
        assert snapshot() == prior and body() == "old"
        assert not (
            pathlib.Path("/var/lib/vpn-nginx-publication") / unit / "pending.json"
        ).exists()
        fifo.unlink()
        preparation_retry = publish(request("old"))
        assert preparation_retry.returncode == 0, preparation_retry.stderr
        assert json.loads(preparation_retry.stdout)["changed"] is False
        invalid = publish(request("new", private_key=b"not-a-private-key"))
        assert invalid.returncode == 1
        assert snapshot() == prior and body() == "old"
        repeated = publish(request("old"))
        assert repeated.returncode == 0, repeated.stderr
        assert json.loads(repeated.stdout)["changed"] is False
        valid = publish(request("new"))
        assert valid.returncode == 0, valid.stderr
        assert body() == "new"
        prior = snapshot()
        failed = publish(
            request(
                "rejected",
                unit_data=unit_text.replace(
                    "/usr/sbin/nginx -c "
                    + str(config)
                    + '/nginx.conf -g "daemon off;"',
                    "/bin/false",
                ),
            )
        )
        assert failed.returncode == 1
        assert snapshot() == prior and body() == "new"
        assert run("systemctl", "is-enabled", unit).stdout.strip() == "enabled"
        run("systemctl", "disable", unit)
        failed = publish(
            request(
                "rejected",
                unit_data=unit_text.replace(
                    "/usr/sbin/nginx -c "
                    + str(config)
                    + '/nginx.conf -g "daemon off;"',
                    "/bin/false",
                ),
            )
        )
        assert failed.returncode == 1
        assert snapshot() == prior and body() == "new"
        assert (
            run("systemctl", "is-enabled", unit, check=False).stdout.strip()
            == "disabled"
        )
        assert (
            run("findmnt", "-n", "-o", "TARGET,PROPAGATION", "-T", "/run").stdout
            == before_root
        )
        print(
            json.dumps(
                {
                    "predictive_no_publication": True,
                    "credential_exact_namespace": True,
                    "valid_https_start": True,
                    "invalid_key_preserves_bytes_and_https": True,
                    "unchanged_is_idempotent": True,
                    "valid_restart_replaces_body": True,
                    "failed_activation_restores_complete_prior_tree_unit_https": True,
                    "parent_run_mount_preserved": True,
                }
            )
        )
    finally:
        run("systemctl", "stop", unit, check=False)
        run("systemctl", "disable", unit, check=False)
        unit_file.unlink(missing_ok=True)
        run("systemctl", "daemon-reload", check=False)
        state = pathlib.Path("/var/lib/vpn-nginx-publication") / unit
        if state.exists():
            shutil.rmtree(state)
        shutil.rmtree(base)
