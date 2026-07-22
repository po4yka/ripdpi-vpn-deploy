"""Real-socket concurrency checks for the AWG/NAT evidence echo service."""

from __future__ import annotations

import errno
import importlib.util
import socket
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ECHO = ROOT / "scripts/real-vps-awg-nat-echo.py"


def _load_echo():
    spec = importlib.util.spec_from_file_location("awg_nat_echo_concurrency", ECHO)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _free_port(kind: int) -> int:
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _udp_roundtrip(port: int, payload: bytes = b"udp-control") -> float:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(0.5)
        started = time.monotonic()
        client.sendto(payload, ("127.0.0.1", port))
        response, _peer = client.recvfrom(4097)
        elapsed = time.monotonic() - started
    assert response == payload
    return elapsed


def _connect_when_ready(port: int) -> socket.socket:
    deadline = time.monotonic() + 1
    while True:
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=1)
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def _peer_was_closed(peer: socket.socket) -> bool:
    try:
        return peer.recv(1) == b""
    except ConnectionResetError:
        return True


class _FailingDatagramSocket:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.fail_send = fail_send

    def recvfrom(self, _size: int):
        if self.fail_send:
            return b"request", ("127.0.0.1", 12345)
        raise BlockingIOError(errno.EAGAIN, "temporarily unavailable")

    def sendto(self, _data: bytes, _peer: tuple[str, int]) -> None:
        raise BlockingIOError(errno.EAGAIN, "temporarily unavailable")


def test_udp_eagain_does_not_escape_selector_handler() -> None:
    module = _load_echo()
    allowed = frozenset({"127.0.0.1"})

    module.handle_udp_datagram(_FailingDatagramSocket(), allowed)
    module.handle_udp_datagram(_FailingDatagramSocket(fail_send=True), allowed)


def test_idle_tcp_peer_does_not_delay_udp_and_capacity_recovers_after_timeout() -> None:
    module = _load_echo()
    tcp_port = _free_port(socket.SOCK_STREAM)
    udp_port = _free_port(socket.SOCK_DGRAM)
    stop = threading.Event()
    server = threading.Thread(
        target=module.serve,
        args=("127.0.0.1", tcp_port, udp_port, frozenset({"127.0.0.1"})),
        kwargs={
            "max_tcp_connections": 1,
            "tcp_idle_timeout": 0.2,
            "stop_event": stop,
        },
        daemon=True,
    )
    server.start()

    idle = _connect_when_ready(tcp_port)
    idle.settimeout(1)
    try:
        time.sleep(0.05)
        assert _udp_roundtrip(udp_port) < 0.5

        overflow = socket.create_connection(("127.0.0.1", tcp_port), timeout=1)
        overflow.settimeout(1)
        with overflow:
            overflow.sendall(b"must-not-echo")
            assert _peer_was_closed(overflow)

        assert _peer_was_closed(idle)

        with socket.create_connection(("127.0.0.1", tcp_port), timeout=1) as client:
            client.settimeout(1)
            client.sendall(b"capacity-restored")
            assert client.recv(4097) == b"capacity-restored"
    finally:
        idle.close()
        stop.set()
        server.join(timeout=2)

    assert not server.is_alive()


def test_tcp_echo_streams_segments_on_the_same_connection() -> None:
    module = _load_echo()
    tcp_port = _free_port(socket.SOCK_STREAM)
    udp_port = _free_port(socket.SOCK_DGRAM)
    stop = threading.Event()
    server = threading.Thread(
        target=module.serve,
        args=("127.0.0.1", tcp_port, udp_port, frozenset({"127.0.0.1"})),
        kwargs={"stop_event": stop},
        daemon=True,
    )
    server.start()

    try:
        with _connect_when_ready(tcp_port) as client:
            client.settimeout(1)
            client.sendall(b"segment-a")
            assert client.recv(4097) == b"segment-a"
            time.sleep(0.05)
            client.sendall(b"segment-b")
            assert client.recv(4097) == b"segment-b"
    finally:
        stop.set()
        server.join(timeout=2)

    assert not server.is_alive()
