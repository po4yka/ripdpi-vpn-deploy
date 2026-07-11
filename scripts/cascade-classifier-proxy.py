#!/usr/bin/env python3
"""Loopback-only SOCKS5 CONNECT adapter with fail-closed per-connection routing."""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import re
import select
import socket
import socketserver
import sys
import threading
from pathlib import Path

from cascade_classifier_lib import DatasetUnavailable, load_ru_networks, resolve_and_classify


DATASET_UNAVAILABLE_EXIT = 3
SOCKS_GENERAL_FAILURE = b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00"
SOCKS_USERNAME = b"cascade-xray"


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("unexpected EOF")
        chunks.extend(chunk)
    return bytes(chunks)


def _request_destination(connection: socket.socket) -> tuple[str, int]:
    version, command, reserved, atyp = _recv_exact(connection, 4)
    if version != 5 or command != 1 or reserved != 0:
        raise DatasetUnavailable("only SOCKS5 CONNECT is supported")
    if atyp == 1:
        destination = socket.inet_ntop(socket.AF_INET, _recv_exact(connection, 4))
    elif atyp == 4:
        destination = socket.inet_ntop(socket.AF_INET6, _recv_exact(connection, 16))
    elif atyp == 3:
        _recv_exact(connection, _recv_exact(connection, 1)[0])
        raise DatasetUnavailable("domain-form SOCKS destinations are blocked; Xray must resolve to an IP")
    else:
        raise DatasetUnavailable("unsupported SOCKS address type")
    return destination, int.from_bytes(_recv_exact(connection, 2), "big")


def _authenticate(connection: socket.socket, password: bytes) -> bool:
    version, username_length = _recv_exact(connection, 2)
    username = _recv_exact(connection, username_length)
    password_length = _recv_exact(connection, 1)[0]
    offered_password = _recv_exact(connection, password_length)
    accepted = version == 1 and hmac.compare_digest(username, SOCKS_USERNAME) and hmac.compare_digest(offered_password, password)
    connection.sendall(b"\x01\x00" if accepted else b"\x01\x01")
    return accepted


def _bind_to_interface(outbound: socket.socket, interface: str) -> None:
    index = socket.if_nametoindex(interface)
    if hasattr(socket, "SO_BINDTODEVICE"):
        outbound.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\x00")
    elif sys.platform == "darwin":
        option = 25 if outbound.family == socket.AF_INET else 125
        level = socket.IPPROTO_IP if outbound.family == socket.AF_INET else socket.IPPROTO_IPV6
        outbound.setsockopt(level, option, index)
    else:
        raise OSError("platform cannot bind an outbound socket to an interface")


def _relay(left: socket.socket, right: socket.socket) -> None:
    sockets = [left, right]
    while sockets:
        readable, _, _ = select.select(sockets, [], [], 30)
        if not readable:
            return
        for source in readable:
            data = source.recv(65536)
            if not data:
                return
            destination = right if source is left else left
            destination.sendall(data)


def interface_for_state(state: str, direct_interface: str, foreign_interface: str) -> str:
    if state == "ru":
        return direct_interface
    if state == "foreign":
        return foreign_interface
    raise DatasetUnavailable(f"unsupported classifier state: {state}")


class DatasetStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.signature: tuple[int, int, int, int, int] | None = None
        self.cached_networks: list = []
        self.networks()

    def _signature(self) -> tuple[int, int, int, int, int]:
        try:
            stat = self.path.stat()
        except OSError as exc:
            raise DatasetUnavailable(f"dataset missing or unreadable: {self.path}") from exc
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def networks(self) -> list:
        with self.lock:
            current = self._signature()
            if current != self.signature:
                networks = load_ru_networks(self.path)
                confirmed = self._signature()
                if confirmed != current:
                    raise DatasetUnavailable("dataset changed during reload")
                self.cached_networks = networks
                self.signature = confirmed
            elif self._signature() != current:
                raise DatasetUnavailable("dataset changed during classification")
            return self.cached_networks


class ClassifierProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        connection: socket.socket = self.request
        server: ClassifierProxyServer = self.server
        try:
            version, methods = _recv_exact(connection, 2)
            offered = _recv_exact(connection, methods)
            if version != 5 or 2 not in offered:
                connection.sendall(b"\x05\xff")
                return
            connection.sendall(b"\x05\x02")
            if not _authenticate(connection, server.password):
                return
            destination, port = _request_destination(connection)
            state, (family, sockaddr) = resolve_and_classify(server.dataset.networks(), destination, port)
            with socket.socket(family, socket.SOCK_STREAM) as outbound:
                interface = interface_for_state(state, server.direct_interface, server.foreign_interface)
                _bind_to_interface(outbound, interface)
                outbound.settimeout(server.connect_timeout)
                outbound.connect(sockaddr)
                bound = outbound.getsockname()
                packed = socket.inet_pton(family, bound[0])
                atyp = b"\x04" if family == socket.AF_INET6 else b"\x01"
                connection.sendall(b"\x05\x00\x00" + atyp + packed + int(bound[1]).to_bytes(2, "big"))
                _relay(connection, outbound)
        except (ConnectionError, DatasetUnavailable, OSError, UnicodeError):
            try:
                connection.sendall(SOCKS_GENERAL_FAILURE)
            except OSError:
                pass


class ClassifierProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], dataset: DatasetStore, password: bytes, direct_interface: str, foreign_interface: str, connect_timeout: float) -> None:
        self.dataset = dataset
        self.password = password
        self.direct_interface = direct_interface
        self.foreign_interface = foreign_interface
        self.connect_timeout = connect_timeout
        super().__init__(address, ClassifierProxyHandler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", required=True, type=int)
    parser.add_argument("--direct-interface", required=True)
    parser.add_argument("--foreign-interface", required=True)
    parser.add_argument("--password-file", required=True, type=Path)
    parser.add_argument("--connect-timeout", type=float, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not ipaddress.ip_address(args.listen_host).is_loopback:
            raise ValueError("classifier listener must use a loopback address")
        if not 1 <= args.listen_port <= 65535:
            raise ValueError("listen port must be between 1 and 65535")
        socket.if_nametoindex(args.direct_interface)
        socket.if_nametoindex(args.foreign_interface)
        password = args.password_file.read_bytes().strip()
        if args.password_file.stat().st_mode & 0o077 or not re.fullmatch(rb"[A-Za-z0-9_-]{43,255}", password):
            raise ValueError("classifier password file must be private base64url text containing 43 to 255 bytes")
        dataset = DatasetStore(args.dataset)
    except DatasetUnavailable as exc:
        print(json.dumps({"reason": str(exc), "state": "dataset-unavailable"}, sort_keys=True), file=sys.stderr)
        return DATASET_UNAVAILABLE_EXIT
    except (OSError, ValueError) as exc:
        print(f"cascade classifier proxy configuration error: {exc}", file=sys.stderr)
        return 2

    with ClassifierProxyServer((args.listen_host, args.listen_port), dataset, password, args.direct_interface, args.foreign_interface, args.connect_timeout) as server:
        print(json.dumps({"listen_host": args.listen_host, "listen_port": args.listen_port, "state": "ready"}), flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
