"""Actual self-steal convergence and interleaved shared-authority TLS retirement."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
import time
import uuid

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def command(argv, *, data=None, check=True, timeout=90):
    result = subprocess.run(
        argv, input=data, capture_output=True, text=True, timeout=timeout
    )
    if check:
        assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-1000:]
    return result


def test_actual_role_rotation_and_prebuilt_disable_collect_latest_tls_under_lock(
    tmp_path,
):
    assert os.geteuid() == 0 and sys.platform == "linux"
    suffix = uuid.uuid4().hex[:12]
    tls = Path("/etc/nginx") / ("vpn-p2-self-steal-" + suffix)
    site = Path("/var/www") / ("vpn-p2-self-steal-" + suffix)
    assert (
        not tls.exists() and not site.exists()
    ), "fixture must not overwrite retained self-steal authority"
    helper = ROOT / "ansible/roles/nginx-xhttp/files/nginx_transaction.py"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    pairs = []
    for name in ("a", "b"):
        key, certificate = tmp_path / f"{name}.key", tmp_path / f"{name}.crt"
        command(
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
                "/CN=edge.example.test",
                "-addext",
                "subjectAltName=DNS:edge.example.test",
                "-days",
                "30",
            ]
        )
        pairs.append((certificate.read_text(), key.read_text()))
    variables = {
        "vpn": {"enable_xray_reality": True, "enable_reality_self_steal": True},
        "xray": {"target": f"127.0.0.1:{port}", "server_names": ["edge.example.test"]},
        "xray_port": 443,
        "xray_fallback_port": 8080,
        "nginx_xhttp_port": 10085,
        "reality_self_steal_port": port,
        "reality_self_steal_tls_dir": str(tls),
        "reality_self_steal_site_root": str(site),
    }

    def role(pair, enabled=True, check=False, expect_success=True):
        play = tmp_path / "converge.yml"
        public = {
            **variables,
            "reality_self_steal_role_enabled": enabled,
            "reality_self_steal": {
                "server_name": "edge.example.test",
                "cert_pem": pair[0],
                "key_pem": pair[1],
            },
        }
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": True,
                        "become": False,
                        "vars": public,
                        "roles": [
                            {"role": str(ROOT / "ansible/roles/reality-self-steal")}
                        ],
                    }
                ]
            )
        )
        play.chmod(0o600)
        return command(
            ["ansible-playbook", "-i", "localhost,", str(play)]
            + (["--check"] if check else []),
            timeout=120,
            check=expect_success,
        )

    def certificate_matches(pair):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", port), timeout=2) as plain:
            with context.wrap_socket(
                plain, server_hostname="edge.example.test"
            ) as connection:
                actual = connection.getpeercert(binary_form=True)
                connection.sendall(
                    b"GET / HTTP/1.1\r\nHost: edge.example.test\r\nConnection: close\r\n\r\n"
                )
                response = connection.recv(65536)
        return actual == ssl.PEM_cert_to_DER_cert(pair[0]) and b"200 OK" in response

    def release(pair):
        digest = hashlib.sha256(
            (
                hashlib.sha256(pair[0].encode()).hexdigest()
                + hashlib.sha256(pair[1].encode()).hexdigest()
            ).encode()
        ).hexdigest()
        return tls / "releases" / digest

    def file(path, content, mode):
        return {
            "path": str(path),
            "kind": "file",
            "uid": 0,
            "gid": 0,
            "mode": mode,
            "content_b64": base64.b64encode(content.encode()).decode(),
        }

    def request(pair=None):
        common = {
            "owner": "reality-self-steal",
            "roots": ["/etc/nginx", str(site)],
            "validate_argv": ["/usr/sbin/nginx", "-t"],
            "unit": "nginx.service",
            "activation": "reload",
            "check": False,
            "credential_root": "",
            "runtime_directories": [],
            "activate_inactive": pair is not None,
            "desired_enabled": True if pair else None,
            "prune_releases": {
                "root": str(tls / "releases"),
                "keep": release(pair).name if pair else None,
            },
        }
        if pair:
            rows = [
                file(release(pair) / "fullchain.pem", pair[0], "0644"),
                file(release(pair) / "privkey.pem", pair[1], "0600"),
                {
                    "path": str(tls / "current"),
                    "kind": "link",
                    "target": str(release(pair)),
                    "uid": 0,
                    "gid": 0,
                    "mode": "0777",
                },
                file(
                    Path("/etc/nginx/sites-available/reality-self-steal.conf"),
                    Path(
                        "/etc/nginx/sites-available/reality-self-steal.conf"
                    ).read_text(),
                    "0640",
                ),
                {
                    "path": "/etc/nginx/sites-enabled/reality-self-steal.conf",
                    "kind": "link",
                    "target": "/etc/nginx/sites-available/reality-self-steal.conf",
                    "uid": 0,
                    "gid": 0,
                    "mode": "0777",
                },
                {"path": "/etc/nginx/sites-enabled/default", "kind": "absent"},
            ]
            rows += [
                file(site / path.name, path.read_text(), "0644")
                for path in (
                    ROOT / "ansible/roles/reality-self-steal/files/public-site"
                ).iterdir()
                if path.is_file()
            ]
        else:
            rows = [
                {"path": str(path), "kind": "absent"}
                for path in [
                    tls / "current",
                    Path("/etc/nginx/sites-available/reality-self-steal.conf"),
                    Path("/etc/nginx/sites-enabled/reality-self-steal.conf"),
                ]
            ]
            rows += [
                {"path": str(site / path.name), "kind": "absent"}
                for path in (
                    ROOT / "ansible/roles/reality-self-steal/files/public-site"
                ).iterdir()
                if path.is_file()
            ]
        return {**common, "files": rows}

    def publish(document, check=True):
        return command(
            [sys.executable, str(helper)], data=json.dumps(document), check=check
        )

    process = None
    try:
        role(pairs[0], check=True)
        assert (
            not tls.exists() and not site.exists()
        ), "check mode published credentials"
        role(pairs[0])
        assert certificate_matches(pairs[0])
        old_disable = request()  # constructed BEFORE the concurrent new release exists
        rotate = request(pairs[1])
        barrier = tmp_path / "barrier"
        wrapper = tmp_path / "pause.py"
        wrapper.write_text(
            "import importlib.util,json,os,signal,sys\nfrom pathlib import Path\n"
            + f"s=importlib.util.spec_from_file_location('tx',{str(helper)!r});m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=m.persist\ndef persist(path,value):\n original(path,value)\n if path.name=='pending.json' and value.get('phase')=='prepared':\n  Path({str(barrier)!r}).write_text('ready');os.kill(os.getpid(),signal.SIGSTOP)\nm.persist=persist\nprint(json.dumps(m.publish(json.load(sys.stdin))))\n"
        )
        process = subprocess.Popen(
            [sys.executable, str(wrapper)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.stdin.write(json.dumps(rotate))
        process.stdin.close()
        deadline = time.monotonic() + 20
        while not barrier.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert publish(old_disable, check=False).returncode != 0
        assert certificate_matches(pairs[0]), "losing writer changed active TLS"
        process.send_signal(signal.SIGCONT)
        process.wait(timeout=60)
        assert process.returncode == 0, process.stderr.read()
        process = None
        deadline = time.monotonic() + 5
        while not certificate_matches(pairs[1]):
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert json.loads(publish(rotate).stdout)["changed"] is False
        publish(old_disable)
        assert not (release(pairs[0]) / "privkey.pem").exists()
        assert not (
            release(pairs[1]) / "privkey.pem"
        ).exists(), "prebuilt disable missed the concurrent new credential"
        assert not (tls / "current").exists()
        assert json.loads(publish(old_disable).stdout)["changed"] is False
        command(["systemctl", "is-active", "--quiet", "nginx.service"])
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            except OSError:
                break
            assert time.monotonic() < deadline, "retired listener remained available"
            time.sleep(0.02)
        # Actual caller reconvergence remains idempotent after dynamic pruning.
        role(pairs[1])
        result = role(pairs[1])
        assert "changed=0" in result.stdout
        # All desired absence files disappear before activation, leaving cached TLS.
        # Missing/stale absence receipt must still adopt the empty active runtime.
        for row in old_disable["files"]:
            Path(row["path"]).unlink(missing_ok=True)
        for path in (tls / "releases").glob("*/*"):
            path.unlink()
        publish(old_disable)
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            except OSError:
                break
            assert time.monotonic() < deadline, "unchanged absence left cached listener"
            time.sleep(0.02)
        role(pairs[1], enabled=False)
        result = role(pairs[1], enabled=False)
        assert "changed=0" in result.stdout
    finally:
        if process is not None:
            process.kill()
            process.wait(timeout=5)
        role(pairs[1], enabled=False)
