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
from ansible.plugins.filter.core import FilterModule
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
    config = tmp_path / "caddy.json"
    values = {
        "naive": {
            "log_dir": str(tmp_path),
            "config_dir": str(tmp_path),
            "decoy_root": str(tmp_path),
            "bind_port": port,
        },
        "naive_secrets": {
            "server_name": "localhost",
            "clients": [
                {
                    "name": "device-a",
                    "username": "p2-user",
                    "password": "p2-local-test-password",
                },
                {
                    "name": "device-b",
                    "username": "p2-other",
                    "password": 'p2-quote-"-backtick-`-{$NAIVE_AUTH_TEST_UNSET}-backslash-\\-password-\\',
                },
            ],
            "probe_resistance_secret": "p2-local-test-secret",
        },
    }
    env = jinja2.Environment()
    env.filters.update(FilterModule().filters())
    template = env.from_string(
        (ROOT / "ansible/roles/naive/templates/caddy.json.j2").read_text()
    )
    config.write_text(template.render(**values))
    document = json.loads(config.read_text())
    servers = document["apps"]["http"]["servers"]
    listeners = {address for server in servers.values() for address in server["listen"]}
    assert listeners == {
        ":" + str(port)
    }, "only the configured manifest TCP port may listen"
    assert all(server.get("protocols") == ["h1", "h2"] for server in servers.values())
    valid = subprocess.run(
        [str(binary), "validate", "--config", str(config)],
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
            [str(binary), "run", "--config", str(config)],
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
                received = b""
                while len(received) < len(b"positive authenticated tunnel"):
                    block = accepted.recv(4096)
                    assert block
                    received += block
                assert received == b"positive authenticated tunnel"
                accepted.sendall(b"positive upstream reply")
                received = b""
                while len(received) < len(b"positive upstream reply"):
                    block = proxy.recv(4096)
                    assert block
                    received += block
                assert received == b"positive upstream reply"

        def connect(client, allowed):
            with context.wrap_socket(
                socket.create_connection(("127.0.0.1", port), 3),
                server_hostname="localhost",
            ) as proxy:
                proxy.settimeout(3)
                target = f"203.0.113.9:{upstream.getsockname()[1]}"
                auth = base64.b64encode(
                    (client["username"] + ":" + client["password"]).encode()
                ).decode()
                proxy.sendall(
                    f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nProxy-Authorization: Basic {auth}\r\n\r\n".encode()
                )
                response = proxy.recv(4096)
                assert (b"200" in response.split(b"\r\n", 1)[0]) is allowed
                if allowed:
                    with upstream.accept()[0] as accepted:
                        proxy.sendall(b"independent device tunnel")
                        received = b""
                        while len(received) < len(b"independent device tunnel"):
                            block = accepted.recv(4096)
                            assert block, "authenticated tunnel closed early"
                            received += block
                        assert received == b"independent device tunnel"
                else:
                    upstream.settimeout(0.1)
                    with pytest.raises(socket.timeout):
                        upstream.accept()
                    upstream.settimeout(3)

        clients = list(values["naive_secrets"]["clients"])
        connect(clients[1], True)
        for remaining in ([clients[1]], []):
            values["naive_secrets"]["clients"] = remaining
            config.write_text(template.render(**values))
            reload = subprocess.run(
                [
                    str(binary),
                    "reload",
                    "--config",
                    str(config),
                ],
                capture_output=True,
                timeout=10,
            )
            assert reload.returncode == 0, "exact composite must adopt revocation"
            connect(clients[0], False)
            connect(clients[1], bool(remaining))
            response = subprocess.run(
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
            assert response.returncode == 0 and response.stdout.endswith("\n2")
            assert "native exact Naive decoy" in response.stdout
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


def test_naive_unacknowledged_revocation_is_adopted_by_actual_unit():
    """Actual unit re-convergence closes config-publication/activation interruption."""
    import shutil

    assert sys.platform == "linux" and os.geteuid() == 0
    binary = Path(
        os.environ.get(
            "NAIVE_NATIVE_BINARY", str(ROOT / ".cache/p2-native-caddy/caddy")
        )
    ).resolve()
    assert binary.is_file()
    suffix = uuid.uuid4().hex[:12]
    principal = "p2-naive-" + suffix
    base = Path("/var/lib") / ("p2-naive-adoption-" + suffix)
    base.mkdir(mode=0o700)
    unit = "p2-naive-adoption-" + suffix + ".service"
    unit_file = Path("/etc/systemd/system") / unit
    shutil.copyfile(binary, base / "caddy")
    binary = base / "caddy"
    binary.chmod(0o755)
    config = base / "caddy.json"

    def run(argv):
        result = subprocess.run(argv, capture_output=True, timeout=20)
        if result.returncode:
            state = subprocess.run(
                [
                    "systemctl",
                    "show",
                    unit,
                    "--property=ActiveState,SubState,Result,ExecMainStatus",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
            journal = subprocess.run(
                ["journalctl", "-u", unit, "-n", "12", "--output=cat", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
            categories = [
                label
                for label in (
                    "permission denied",
                    "address already in use",
                    "Failed at step",
                )
                if label in journal
            ]
            assert (
                result.returncode == 0
            ), f"actual native command failed: {state}; categories={categories}"
        return result.stdout

    try:
        run(
            [
                "useradd",
                "--system",
                "--user-group",
                "--home-dir",
                str(base / "home"),
                principal,
            ]
        )
        import pwd

        account = pwd.getpwnam(principal)
        base.chmod(0o750)
        os.chown(base, 0, account.pw_gid)
        for directory in (base / "home", base / "logs"):
            directory.mkdir(mode=0o750)
            os.chown(directory, account.pw_uid, account.pw_gid)
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(base / "server.key"),
                "-out",
                str(base / "server.fullchain.pem"),
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost",
                "-days",
                "1",
            ]
        )
        (base / "index.html").write_text("actual decoy remains")
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        values = dict(
            naive=dict(
                log_dir=str(base / "logs"),
                config_dir=str(base),
                decoy_root=str(base),
                bind_port=port,
            ),
            naive_secrets=dict(
                server_name="localhost",
                clients=[
                    dict(
                        name="device",
                        username="device",
                        password="native-one-device-password",
                    )
                ],
                probe_resistance_secret="native-synthetic-secret",
            ),
        )
        env = jinja2.Environment()
        env.filters.update(FilterModule().filters())
        template = env.from_string(
            (ROOT / "ansible/roles/naive/templates/caddy.json.j2").read_text()
        )
        config.write_text(template.render(**values))
        config.chmod(0o640)
        for authority in (config, base / "server.key", base / "server.fullchain.pem"):
            authority.chmod(0o640)
            os.chown(authority, 0, account.pw_gid)
        canonical_unit = env.from_string(
            (ROOT / "ansible/roles/naive/templates/caddy-naive.service.j2").read_text()
        ).render(**values)
        unit_file.write_text(
            canonical_unit.replace("User=naive", "User=" + principal)
            .replace("Group=naive", "Group=" + principal)
            .replace("/usr/local/bin/caddy-naive", str(binary))
            .replace("/var/lib/naive", str(base / "home"))
        )
        unit_file.chmod(0o644)
        run(["setcap", "cap_net_bind_service=+ep", str(binary)])
        # Actual root validation creates the inode that formerly prevented the
        # canonical dedicated-user service from starting. Preserve its bytes.
        run([str(binary), "validate", "--config", str(config)])
        access_log = base / "logs/access.log"
        assert access_log.stat().st_uid == 0
        access_log.write_bytes(b"synthetic prior log\n")
        prepare_log = [
            sys.executable,
            str(ROOT / "ansible/roles/naive/files/prepare_log.py"),
            str(access_log),
            "--user",
            principal,
        ]
        assert json.loads(run(prepare_log))["changed"] is True
        assert access_log.read_bytes() == b"synthetic prior log\n"
        assert access_log.stat().st_uid == account.pw_uid
        assert access_log.stat().st_gid == account.pw_gid
        assert access_log.stat().st_mode & 0o777 == 0o640
        assert json.loads(run(prepare_log))["changed"] is False
        # Neither preparation nor its read-only preflight follows an unexpected
        # inode or repairs unsafe directory metadata.
        prior_log = access_log.read_bytes()
        access_log.unlink()
        target = base / "foreign.log"
        target.write_bytes(b"unrelated bytes")
        access_log.symlink_to(target)
        for suffix in ([], ["--inspect"]):
            refused = subprocess.run(
                prepare_log + suffix, capture_output=True, timeout=10
            )
            assert refused.returncode == 1
            assert target.read_bytes() == b"unrelated bytes"
            assert access_log.is_symlink()
        access_log.unlink()
        os.link(target, access_log)
        assert (
            subprocess.run(prepare_log, capture_output=True, timeout=10).returncode == 1
        )
        assert target.read_bytes() == b"unrelated bytes"
        access_log.unlink()
        access_log.write_bytes(prior_log)
        access_log.chmod(0o666)
        assert (
            subprocess.run(prepare_log, capture_output=True, timeout=10).returncode == 1
        )
        assert access_log.stat().st_mode & 0o777 == 0o666
        access_log.chmod(0o600)
        (base / "logs").chmod(0o777)
        assert (
            subprocess.run(
                prepare_log + ["--inspect"], capture_output=True, timeout=10
            ).returncode
            == 1
        )
        assert (base / "logs").stat().st_mode & 0o777 == 0o777
        (base / "logs").chmod(0o750)
        assert json.loads(run(prepare_log))["changed"] is True
        prepare_log[2] = str(base / "logs/site-error.log")
        assert json.loads(run(prepare_log))["changed"] is True
        assert json.loads(run(prepare_log))["changed"] is False
        helper = ROOT / "ansible/roles/naive/files/naive_activate.py"
        argv = [
            sys.executable,
            str(helper),
            "--binary",
            str(binary),
            "--unit-file",
            str(unit_file),
            "--config",
            str(config),
            "--certificate",
            str(base / "server.fullchain.pem"),
            "--key",
            str(base / "server.key"),
            "--unit",
            unit,
            "--state",
            str(base / "receipt"),
            "--server-name",
            "localhost",
            "--port",
            str(port),
        ]
        legacy = base / "Caddyfile"
        legacy.write_text(
            f"{{\n  log default {{\n    output file {base}/legacy-access.log\n  }}\n  auto_https off\n}}\n"
            f":{port}, localhost:{port} {{\n  tls {base}/server.fullchain.pem {base}/server.key\n"
            "  route {\n    forward_proxy {\n      basic_auth old-device old-synthetic-password\n"
            "      hide_ip\n      hide_via\n      probe_resistance synthetic-old-secret\n    }\n"
            f"    file_server {{\n      root {base}\n    }}\n  }}\n}}\n"
            "# NOTE: NaiveProxy v147.0.7727.49-3\n"
        )
        run(
            [str(binary), "validate", "--config", str(legacy), "--adapter", "caddyfile"]
        )
        legacy.chmod(0o640)
        os.chown(legacy, 0, account.pw_gid)
        assert json.loads(run(argv))["changed"] is True
        assert (
            not legacy.exists()
        ), "old credential-bearing role output must retire after new adoption"
        assert json.loads(run(argv))["changed"] is False
        previous_pid = run(
            ["systemctl", "show", unit, "--property=MainPID", "--value"]
        ).strip()
        # Disk publication survives while the old actual process still runs.
        values["naive_secrets"]["clients"] = []
        config.write_text(template.render(**values))
        assert (
            run(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
            == previous_pid
        )
        assert json.loads(run(argv))["changed"] is True
        assert (
            run(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
            != previous_pid
        )
        context = ssl.create_default_context(cafile=str(base / "server.fullchain.pem"))
        with context.wrap_socket(
            socket.create_connection(("127.0.0.1", port), 3),
            server_hostname="localhost",
        ) as client:
            client.settimeout(3)
            auth = base64.b64encode(b"device:native-one-device-password").decode()
            client.sendall(
                f"CONNECT 203.0.113.9:80 HTTP/1.1\r\nHost: 203.0.113.9\r\nProxy-Authorization: Basic {auth}\r\n\r\n".encode()
            )
            assert b"200" not in client.recv(4096).split(b"\r\n", 1)[0]
        decoy = run(
            [
                "curl",
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--max-time",
                "3",
                "--cacert",
                str(base / "server.fullchain.pem"),
                "--resolve",
                f"localhost:{port}:127.0.0.1",
                f"https://localhost:{port}/",
            ]
        )
        assert b"actual decoy remains" in decoy
        assert json.loads(run(argv))["changed"] is False
        # An interrupted acknowledgement cannot turn unchanged publication into acceptance.
        (base / "receipt/activated.json").unlink()
        assert json.loads(run(argv))["changed"] is True
        assert json.loads(run(argv))["changed"] is False
        receipt = base / "receipt/activated.json"
        valid_receipt = receipt.read_bytes()
        for malformed in (
            b'{"schema":true,"fingerprint":"' + b"a" * 64 + b'"}',
            b'{"schema":1,"schema":1,"fingerprint":"' + b"a" * 64 + b'"}',
        ):
            receipt.write_bytes(malformed)
            failed = subprocess.run(argv, capture_output=True, timeout=20)
            assert failed.returncode == 1
            assert receipt.read_bytes() == malformed
        receipt.write_bytes(valid_receipt)
        assert json.loads(run(argv))["changed"] is False
        # An atomic same-byte binary replacement leaves the old executable inode
        # in the live process. A current digest receipt must still adopt it.
        prior_pid = run(
            ["systemctl", "show", unit, "--property=MainPID", "--value"]
        ).strip()
        replacement = base / "replacement"
        shutil.copyfile(binary, replacement)
        replacement.chmod(0o755)
        os.replace(replacement, binary)
        assert json.loads(run(argv))["changed"] is True
        assert (
            run(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
            != prior_pid
        )
        assert json.loads(run(argv))["changed"] is False

    finally:
        subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=10)
        unit_file.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=10)
        shutil.rmtree(base)
        subprocess.run(["userdel", principal], capture_output=True, timeout=10)
        subprocess.run(["groupdel", principal], capture_output=True, timeout=10)
