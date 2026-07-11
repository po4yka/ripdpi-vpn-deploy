"""Public SOCKS5 seam for per-connection cascade classification."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "scripts" / "cascade-classifier-proxy.py"
PROXY_PASSWORD = b"test_proxy_password_abcdefghijklmnopqrstuvwxyz0123456789"


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        encoded.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(encoded)


def _field(number: int, payload: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(payload)) + payload


def _geoip_dat(network: str, prefix: int) -> bytes:
    packed = socket.inet_pton(socket.AF_INET, network)
    cidr = _field(1, packed) + _varint(2 << 3) + _varint(prefix)
    return _field(1, _field(1, b"RU") + _field(2, cidr))


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class EchoServer:
    def __init__(self) -> None:
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = int(self.listener.getsockname()[1])
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        try:
            connection, _ = self.listener.accept()
        except OSError:
            return
        with connection:
            payload = connection.recv(64)
            connection.sendall(payload)

    def __enter__(self) -> EchoServer:
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.listener.close()
        self.thread.join(timeout=2)


def _password_file(dataset: Path) -> Path:
    path = dataset.parent / "proxy-password"
    path.write_bytes(PROXY_PASSWORD + b"\n")
    path.chmod(0o600)
    return path


def _start_proxy(dataset: Path, port: int, foreign_interface: str) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            str(PROXY),
            "--dataset",
            str(dataset),
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(port),
            "--direct-interface",
            foreign_interface,
            "--foreign-interface",
            foreign_interface,
            "--password-file",
            str(_password_file(dataset)),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(process.stderr.read() if process.stderr else "proxy exited")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                return process
        except OSError:
            time.sleep(0.02)
    process.terminate()
    raise AssertionError("classifier proxy did not bind")


def _socks_round_trip(proxy_port: int, target_port: int) -> bytes:
    with socket.create_connection(("127.0.0.1", proxy_port), timeout=2) as client:
        client.sendall(b"\x05\x01\x02")
        assert client.recv(2) == b"\x05\x02"
        username = b"cascade-xray"
        password = PROXY_PASSWORD
        client.sendall(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
        assert client.recv(2) == b"\x01\x00"
        client.sendall(b"\x05\x01\x00\x01" + socket.inet_aton("127.0.0.1") + target_port.to_bytes(2, "big"))
        reply = client.recv(10)
        assert reply[:2] == b"\x05\x00"
        client.sendall(b"cascade")
        return client.recv(7)


def _loopback_interface() -> str:
    return "lo0" if sys.platform == "darwin" else "lo"


def test_ru_connection_uses_direct_path_and_completes(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_geoip_dat("127.0.0.0", 8))
    proxy_port = _free_port()

    with EchoServer() as target:
        proxy = _start_proxy(dataset, proxy_port, _loopback_interface())
        try:
            assert _socks_round_trip(proxy_port, target.port) == b"cascade"
        finally:
            proxy.terminate()
            proxy.wait(timeout=2)


def test_foreign_connection_binds_to_configured_leg_and_completes(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_geoip_dat("192.0.2.0", 24))
    proxy_port = _free_port()

    with EchoServer() as target:
        proxy = _start_proxy(dataset, proxy_port, _loopback_interface())
        try:
            assert _socks_round_trip(proxy_port, target.port) == b"cascade"
        finally:
            proxy.terminate()
            proxy.wait(timeout=2)


def test_empty_dataset_refuses_to_open_classifier_listener(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(b"")
    port = _free_port()

    result = subprocess.run(
        [
            sys.executable,
            str(PROXY),
            "--dataset",
            str(dataset),
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(port),
            "--direct-interface",
            _loopback_interface(),
            "--foreign-interface",
            _loopback_interface(),
            "--password-file",
            str(_password_file(dataset)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=3,
    )

    assert result.returncode == 3
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_non_loopback_listener_is_rejected_before_bind(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_geoip_dat("127.0.0.0", 8))

    result = subprocess.run(
        [
            sys.executable,
            str(PROXY),
            "--dataset",
            str(dataset),
            "--listen-host",
            "0.0.0.0",
            "--listen-port",
            str(_free_port()),
            "--direct-interface",
            _loopback_interface(),
            "--foreign-interface",
            _loopback_interface(),
            "--password-file",
            str(_password_file(dataset)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=3,
    )

    assert result.returncode != 0
    assert "loopback" in result.stderr.lower()


def test_runtime_dataset_loss_blocks_new_connections(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_geoip_dat("127.0.0.0", 8))
    proxy_port = _free_port()

    with EchoServer() as target:
        proxy = _start_proxy(dataset, proxy_port, _loopback_interface())
        try:
            dataset.write_bytes(b"")
            with socket.create_connection(("127.0.0.1", proxy_port), timeout=2) as client:
                client.sendall(b"\x05\x01\x02")
                assert client.recv(2) == b"\x05\x02"
                username = b"cascade-xray"
                password = PROXY_PASSWORD
                client.sendall(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
                assert client.recv(2) == b"\x01\x00"
                client.sendall(b"\x05\x01\x00\x01" + socket.inet_aton("127.0.0.1") + target.port.to_bytes(2, "big"))
                assert client.recv(2) == b"\x05\x01"
        finally:
            proxy.terminate()
            proxy.wait(timeout=2)


def test_proxy_requires_local_xray_authentication(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_geoip_dat("127.0.0.0", 8))
    proxy_port = _free_port()
    proxy = _start_proxy(dataset, proxy_port, _loopback_interface())
    try:
        with socket.create_connection(("127.0.0.1", proxy_port), timeout=2) as client:
            client.sendall(b"\x05\x01\x00")
            assert client.recv(2) == b"\x05\xff"
    finally:
        proxy.terminate()
        proxy.wait(timeout=2)


def test_domain_form_request_is_blocked_before_host_resolution(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_geoip_dat("127.0.0.0", 8))
    proxy_port = _free_port()
    proxy = _start_proxy(dataset, proxy_port, _loopback_interface())
    try:
        with socket.create_connection(("127.0.0.1", proxy_port), timeout=2) as client:
            client.sendall(b"\x05\x01\x02")
            assert client.recv(2) == b"\x05\x02"
            username = b"cascade-xray"
            password = PROXY_PASSWORD
            client.sendall(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
            assert client.recv(2) == b"\x01\x00"
            domain = b"destination.invalid"
            client.sendall(b"\x05\x01\x00\x03" + bytes([len(domain)]) + domain + b"\x01\xbb")
            assert client.recv(2) == b"\x05\x01"
    finally:
        proxy.terminate()
        proxy.wait(timeout=2)


def test_route_state_selects_distinct_configured_interfaces() -> None:
    spec = importlib.util.spec_from_file_location("cascade_classifier_proxy", PROXY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.interface_for_state("ru", "physical0", "tunnel0") == "physical0"
    assert module.interface_for_state("foreign", "physical0", "tunnel0") == "tunnel0"
