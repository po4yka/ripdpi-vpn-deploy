#!/usr/bin/env python3
"""Small owner-operated TCP/UDP echo used by the AWG evidence lane."""

from __future__ import annotations

import argparse
import ipaddress
import selectors
import socket
import time
from contextlib import suppress
from threading import Event

MAX_MESSAGE = 4096
MAX_TCP_CONNECTIONS = 64
MAX_ACCEPTS_PER_TICK = 16
TCP_IDLE_TIMEOUT_SECONDS = 10.0


class TcpConnection:
    __slots__ = ("deadline", "received", "output", "sent", "close_after_write")

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.received = 0
        self.output = bytearray()
        self.sent = 0
        self.close_after_write = False


def is_allowed(peer_address: str, allowed: frozenset[str]) -> bool:
    return str(ipaddress.ip_address(peer_address)) in allowed


def bind_socket(kind: int, address: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.socket(family, kind)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    sock.bind((address, port))
    if kind == socket.SOCK_STREAM:
        sock.listen(32)
    sock.setblocking(False)
    return sock


def close_connection(
    selector: selectors.BaseSelector,
    connection: socket.socket,
) -> None:
    with suppress(KeyError):
        selector.unregister(connection)
    connection.close()


def handle_udp_datagram(udp: socket.socket, allowed: frozenset[str]) -> None:
    try:
        data, peer = udp.recvfrom(MAX_MESSAGE + 1)
    except (BlockingIOError, OSError):
        return
    if not is_allowed(peer[0], allowed) or not data or len(data) > MAX_MESSAGE:
        return
    try:
        udp.sendto(data, peer)
    except (BlockingIOError, OSError):
        return


def update_tcp_interest(
    selector: selectors.BaseSelector,
    connection: socket.socket,
    state: TcpConnection,
) -> bool:
    events = 0
    if not state.close_after_write:
        events |= selectors.EVENT_READ
    if state.sent < len(state.output):
        events |= selectors.EVENT_WRITE
    if events == 0:
        return False
    selector.modify(connection, events, state)
    return True


def serve(
    address: str,
    tcp_port: int,
    udp_port: int,
    allowed: frozenset[str],
    *,
    max_tcp_connections: int = MAX_TCP_CONNECTIONS,
    tcp_idle_timeout: float = TCP_IDLE_TIMEOUT_SECONDS,
    stop_event: Event | None = None,
) -> None:
    selector = selectors.DefaultSelector()
    tcp = bind_socket(socket.SOCK_STREAM, address, tcp_port)
    udp = bind_socket(socket.SOCK_DGRAM, address, udp_port)
    selector.register(tcp, selectors.EVENT_READ, "tcp-listener")
    selector.register(udp, selectors.EVENT_READ, "udp")
    connections: dict[socket.socket, TcpConnection] = {}

    try:
        while stop_event is None or not stop_event.is_set():
            now = time.monotonic()
            next_deadline = min(
                (state.deadline for state in connections.values()),
                default=now + 1.0,
            )
            timeout = max(0.0, min(1.0, next_deadline - now))

            for key, events in selector.select(timeout):
                if key.data == "tcp-listener":
                    for _ in range(MAX_ACCEPTS_PER_TICK):
                        try:
                            connection, peer = tcp.accept()
                        except BlockingIOError:
                            break
                        connection.setblocking(False)
                        if (
                            not is_allowed(peer[0], allowed)
                            or len(connections) >= max_tcp_connections
                        ):
                            connection.close()
                            continue
                        state = TcpConnection(
                            deadline=time.monotonic() + tcp_idle_timeout
                        )
                        connections[connection] = state
                        selector.register(connection, selectors.EVENT_READ, state)
                    continue

                if key.data == "udp":
                    handle_udp_datagram(udp, allowed)
                    continue

                connection = key.fileobj
                state = key.data
                if events & selectors.EVENT_READ:
                    try:
                        data = connection.recv(MAX_MESSAGE - state.received + 1)
                    except BlockingIOError:
                        data = None
                    except OSError:
                        close_connection(selector, connection)
                        connections.pop(connection, None)
                        continue
                    if data == b"":
                        state.close_after_write = True
                    elif data is not None and state.received + len(data) > MAX_MESSAGE:
                        close_connection(selector, connection)
                        connections.pop(connection, None)
                        continue
                    elif data:
                        state.received += len(data)
                        state.output.extend(data)
                        state.deadline = time.monotonic() + tcp_idle_timeout
                        if state.received == MAX_MESSAGE:
                            state.close_after_write = True

                    if not update_tcp_interest(selector, connection, state):
                        close_connection(selector, connection)
                        connections.pop(connection, None)
                        continue

                if events & selectors.EVENT_WRITE:
                    try:
                        sent = connection.send(state.output[state.sent :])
                    except BlockingIOError:
                        continue
                    except OSError:
                        close_connection(selector, connection)
                        connections.pop(connection, None)
                        continue
                    if sent <= 0:
                        close_connection(selector, connection)
                        connections.pop(connection, None)
                        continue
                    state.sent += sent
                    if state.sent == len(state.output):
                        state.output.clear()
                        state.sent = 0
                    if not update_tcp_interest(selector, connection, state):
                        close_connection(selector, connection)
                        connections.pop(connection, None)

            now = time.monotonic()
            for connection, state in list(connections.items()):
                if state.deadline <= now:
                    close_connection(selector, connection)
                    connections.pop(connection, None)
    finally:
        for connection in list(connections):
            close_connection(selector, connection)
        selector.close()
        tcp.close()
        udp.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True)
    parser.add_argument("--tcp-port", required=True, type=int)
    parser.add_argument("--udp-port", required=True, type=int)
    parser.add_argument("--allow-address", required=True, action="append")
    args = parser.parse_args()
    allowed = frozenset(
        str(ipaddress.ip_address(value)) for value in args.allow_address
    )
    serve(args.address, args.tcp_port, args.udp_port, allowed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
