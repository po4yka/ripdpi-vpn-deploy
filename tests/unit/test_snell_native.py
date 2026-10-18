"""Real pinned Snell parsers, authentication, bytes and observed TCP reuse."""

from contextlib import ExitStack, contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import select
from secrets import token_hex
import socket
import socketserver
import struct
import subprocess
import tarfile
import threading
import time

import pytest
import yaml

from template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


@pytest.fixture(scope="module")
def snell_binary(pytestconfig):
    pin = json.loads((ROOT / "scripts/hysteria-runtimes.json").read_text())["sing_box"]
    defaults = yaml.safe_load(
        (ROOT / "ansible/roles/snell/defaults/main.yml").read_text()
    )["snell"]
    assert (
        defaults["version"] == "v" + pin["version"]
    ), "Snell runtime and native qualification pins differ"
    if selected := os.environ.get("SNELL_NATIVE_BINARY"):
        # Required CI supplies the binary only after setup-disposable-ci admits
        # the exact release archive checksum. Protocol tests still execute it.
        binary = Path(selected).resolve()
        assert binary.is_file(), "admitted Snell binary is missing"
        require_version(binary, pin["version"])
        return binary
    architecture = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64"}[
        platform.machine()
    ]
    target = platform.system().lower() + "-" + architecture
    cache = Path(str(pytestconfig.cache.makedir("snell-native-artifacts")))
    filename = "sing-box-" + pin["version"] + "-" + target
    archive = Path(
        os.environ.get("SNELL_NATIVE_ARCHIVE", str(cache / (filename + ".tar.gz")))
    )
    if not archive.exists():
        assert (
            "SNELL_NATIVE_ARCHIVE" not in os.environ
        ), "selected Snell archive is missing"
        fetched = subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--connect-timeout",
                "15",
                "--max-time",
                "120",
                "--max-filesize",
                "120000000",
                "https://github.com/SagerNet/sing-box/releases/download/v"
                + pin["version"]
                + "/"
                + filename
                + ".tar.gz",
            ],
            capture_output=True,
            timeout=125,
        )
        assert fetched.returncode == 0, "pinned Snell release download failed"
        data = fetched.stdout
        assert len(data) <= 120_000_000, "Snell archive exceeds size bound"
    else:
        assert archive.stat().st_size <= 120_000_000
        data = archive.read_bytes()
    assert (
        hashlib.sha256(data).hexdigest() == pin["sha256"][target]
    ), "Snell archive checksum refused"
    if not archive.exists():
        archive.write_bytes(data)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as bundle:
        member = bundle.getmember(filename + "/sing-box")
        assert member.isfile() and member.size <= 120_000_000
        executable = bundle.extractfile(member).read()
    binary = cache / "sing-box-verified"
    binary.write_bytes(executable)
    binary.chmod(0o755)
    require_version(binary, pin["version"])
    return binary


def require_version(binary, expected):
    version = subprocess.run(
        [str(binary), "version"], capture_output=True, text=True, timeout=5, check=True
    )
    assert version.stdout.splitlines()[0] == "sing-box version " + expected


def free_port():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


@contextmanager
def engine(binary, path, document):
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    checked = subprocess.run(
        [str(binary), "check", "-c", str(path)], capture_output=True, timeout=5
    )
    assert (
        checked.returncode == 0
    ), "real Snell parser refused role-generated configuration"
    with path.with_suffix(".log").open("wb") as log:
        process = subprocess.Popen(
            [str(binary), "run", "-c", str(path)], stdout=log, stderr=log
        )
        try:
            # Startup messages contain no fixture credentials. Wait for the real
            # runtime startup acknowledgement without opening a probe connection.
            deadline = time.monotonic() + 5
            while "sing-box started" not in path.with_suffix(".log").read_text():
                assert process.poll() is None, "Snell engine exited during startup"
                assert (
                    time.monotonic() < deadline
                ), "Snell engine did not acknowledge startup"
                time.sleep(0.02)
            yield process
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


class ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


@contextmanager
def service(handler):
    with ThreadedServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive(), "owned Snell fixture did not stop"


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        with self.server.counter_lock:
            self.server.connections += 1
        self.request.settimeout(3)
        while block := self.request.recv(4096):
            self.request.sendall(block)


class CountedTransport(socketserver.BaseRequestHandler):
    def handle(self):
        with self.server.counter_lock:
            self.server.connections += 1
        with socket.create_connection(
            ("127.0.0.1", self.server.destination), timeout=3
        ) as upstream:
            channels = {self.request: upstream, upstream: self.request}
            while channels:
                readable, _, _ = select.select(list(channels), [], [], 3)
                if not readable:
                    continue
                for source in readable:
                    try:
                        block = source.recv(65536)
                        if block:
                            channels[source].sendall(block)
                            continue
                        channels[source].shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    del channels[source]


def receive_exact(stream, size):
    received = b""
    while len(received) < size:
        block = stream.recv(size - len(received))
        if not block:
            break
        received += block
    return received


def socks_echo(port, destination, payload, *, allowed):
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.settimeout(3)
        client.sendall(b"\x05\x01\x00")
        assert receive_exact(client, 2) == b"\x05\x00"
        client.sendall(
            b"\x05\x01\x00\x01\x7f\x00\x00\x01" + struct.pack("!H", destination)
        )
        reply = receive_exact(client, 4)
        if not allowed and (not reply or reply[1] != 0):
            return
        assert reply[:2] == b"\x05\x00", "authenticated Snell SOCKS request refused"
        assert reply[3] in (1, 4), "unexpected SOCKS reply address"
        assert len(receive_exact(client, (4 if reply[3] == 1 else 16) + 2)) > 2
        # The mixed inbound can acknowledge SOCKS before upstream authentication.
        # Only returned application bytes establish a successful Snell tunnel.
        client.sendall(payload)
        if not allowed:
            client.shutdown(socket.SHUT_WR)
        try:
            received = receive_exact(client, len(payload))
        except (ConnectionResetError, TimeoutError):
            assert not allowed, "authenticated Snell stream reset or timed out"
            return
        if allowed:
            assert received == payload, "authenticated Snell bytes changed"
        else:
            assert received == b"", "wrong Snell userkey forwarded application data"


@pytest.mark.parametrize("variant_id", ["v4-stream", "v6-default", "v6-unshaped"])
@pytest.mark.parametrize("reuse", [False, True], ids=["fresh", "reuse"])
@pytest.mark.parametrize("credential_style", ["hex", "json-escaped"])
def test_real_snell_variants_authentication_and_connection_reuse(
    tmp_path, snell_binary, variant_id, reuse, credential_style
):
    defaults = yaml.safe_load(
        (ROOT / "ansible/roles/snell/defaults/main.yml").read_text()
    )["snell"]
    variants = [
        {**variant, "listen_port": free_port()} for variant in defaults["variants"]
    ]
    selected = next(variant for variant in variants if variant["id"] == variant_id)
    suffix = "" if credential_style == "hex" else '"\\\n\t\r'
    secrets = [
        {
            "id": variant["id"],
            "psk": token_hex(32) + suffix,
            "users": [
                {
                    "name": "native-device",
                    "userkey": token_hex(32) + suffix,
                }
            ],
        }
        for variant in variants
    ]
    values = {
        "snell": {**defaults, "listen_addr": "127.0.0.1", "variants": variants},
        "snell_secrets": {"variants": secrets},
    }
    server = json.loads(
        render_template(ROOT / "ansible/roles/snell/templates/config.json.j2", values)
    )
    for inbound, secret in zip(server["inbounds"], secrets):
        assert inbound["psk"] == secret["psk"], "server PSK changed during rendering"
        assert inbound["users"] == secret["users"], "server userkeys changed during rendering"
    server["log"] = {"level": "info"}
    with ExitStack() as stack:
        stack.enter_context(engine(snell_binary, tmp_path / "server.json", server))
        echo = stack.enter_context(service(Echo))
        echo.connections, echo.counter_lock = 0, threading.Lock()
        counted = stack.enter_context(service(CountedTransport))
        counted.destination, counted.connections = selected["listen_port"], 0
        counted.counter_lock = threading.Lock()
        values["snell"]["smoke_port_base"] = free_port()
        # Render the actual role's client contract, then select only the variant
        # under test and point its encrypted TCP transport at the counting relay.
        client = json.loads(
            render_template(
                ROOT / "ansible/roles/snell/templates/smoke-client.json.j2", values
            )
        )
        index = variants.index(selected)
        inbound, outbound = client["inbounds"][index], client["outbounds"][index]
        assert outbound["psk"] == secrets[index]["psk"], "smoke PSK changed during rendering"
        assert outbound["userkey"] == secrets[index]["users"][0]["userkey"], "smoke userkey changed during rendering"
        inbound["listen_port"] = free_port()
        outbound.update(server_port=counted.server_address[1], reuse=reuse)
        wrong_userkey = token_hex(32)
        assert wrong_userkey != outbound["userkey"]
        wrong = {**outbound, "tag": "wrong-key", "userkey": wrong_userkey}
        wrong_inbound = {**inbound, "tag": "wrong-in", "listen_port": free_port()}
        client.update(
            log={"level": "info"},
            inbounds=[inbound, wrong_inbound],
            outbounds=[outbound, wrong],
            route={
                "rules": [
                    {"inbound": [inbound["tag"]], "outbound": outbound["tag"]},
                    {"inbound": [wrong_inbound["tag"]], "outbound": wrong["tag"]},
                ]
            },
        )
        stack.enter_context(engine(snell_binary, tmp_path / "client.json", client))
        for sequence in range(2):
            socks_echo(
                inbound["listen_port"],
                echo.server_address[1],
                b"real-snell-authenticated-payload-" + bytes([sequence]) * 32768,
                allowed=True,
            )
            time.sleep(0.1)
            assert counted.connections == (
                1 if reuse else sequence + 1
            ), "Snell outer connection reuse differs from policy"
        socks_echo(
            wrong_inbound["listen_port"],
            echo.server_address[1],
            b"wrong-key",
            allowed=False,
        )
        deadline = time.monotonic() + 2
        while "bad user key" not in (tmp_path / "server.log").read_text():
            assert (
                time.monotonic() < deadline
            ), "real Snell server did not reject the wrong userkey"
            time.sleep(0.02)
        assert (
            echo.connections == 2
        ), "wrong Snell userkey reached the application destination"
