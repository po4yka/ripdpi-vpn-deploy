"""Actual SOCKS and destination sockets; owned gateway fixtures are not native proof."""
from __future__ import annotations

from contextlib import contextmanager
import selectors
import socket
import struct
import threading
import time

import pytest

import transport_egress_normalizer as normalizer
import transport_socks as wire
from transport_destination_policy import DestinationPolicy
from test_transport_destination_boundary import auth, config


class Destination:
    def __init__(self, family=socket.AF_INET, *, reset_after_bytes=False):
        self.listener = socket.socket(family, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1" if family == socket.AF_INET else "::1", 0))
        self.listener.listen()
        self.listener.settimeout(0.05)
        self.address = self.listener.getsockname()[:2]
        self.reset_after_bytes = reset_after_bytes
        self.payloads = []
        self.stopped = threading.Event()
        self.connections = set()
        self.workers = []
        self.worker = threading.Thread(target=self._accept)
        self.worker.start()

    def _accept(self):
        while not self.stopped.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.connections.add(connection)
            worker = threading.Thread(target=self._serve, args=(connection,))
            self.workers.append(worker)
            worker.start()

    def _serve(self, connection):
        try:
            connection.settimeout(0.05)
            while not self.stopped.is_set():
                try:
                    data = connection.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                self.payloads.append(data)
                if self.reset_after_bytes:
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                    break
                connection.sendall(data)
        except OSError:
            pass
        finally:
            connection.close()
            self.connections.discard(connection)

    def close(self):
        self.stopped.set()
        self.listener.close()
        for connection in tuple(self.connections):
            connection.close()
        self.worker.join(2)
        for worker in self.workers:
            worker.join(2)
        assert not self.worker.is_alive() and not any(worker.is_alive() for worker in self.workers)


class Gateway:
    def __init__(self, routes, on_request=None):
        self.routes, self.on_request = routes, on_request
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.05)
        self.port = self.listener.getsockname()[1]
        self.stopped = threading.Event()
        self.records, self.closed, self.payloads = [], [], []
        self.connections, self.workers = set(), []
        self.maximum_controls = 0
        self.lock = threading.Lock()
        self.worker = threading.Thread(target=self._accept)
        self.worker.start()

    def _accept(self):
        while not self.stopped.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self.lock:
                self.connections.add(connection)
                self.maximum_controls = max(self.maximum_controls, len(self.connections))
            worker = threading.Thread(target=self._serve, args=(connection,))
            self.workers.append(worker)
            worker.start()

    def _serve(self, connection):
        host = None
        target = None
        try:
            connection.settimeout(2)
            normalizer._frame(connection, wire.greeting)
            connection.sendall(b"\x05\x02")
            normalizer._frame(connection, lambda data: wire.authentication(
                data, "gateway-direct", "synthetic-backend-secret-" + "b" * 20))
            connection.sendall(b"\x01\x00")
            _, command, host, port = normalizer._frame(connection, wire.request)
            assert command == 1
            self.records.append((host, port, time.monotonic()))
            if self.on_request:
                self.on_request(host)
            route = self.routes.get(host, "refuse")
            if route == "refuse":
                connection.sendall(wire.FAILURE)
            elif route == "abrupt":
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            elif route == "stall":
                connection.settimeout(0.05)
                while not self.stopped.is_set():
                    try:
                        data = connection.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    self.payloads.append((host, data))
            else:
                target = socket.create_connection(route.address, timeout=1)
                connection.sendall(wire.reply("127.0.0.1", self.port))
                self._relay(connection, target, host)
        except (OSError, ValueError):
            pass
        finally:
            if target is not None:
                target.close()
            connection.close()
            with self.lock:
                self.connections.discard(connection)
            if host is not None:
                self.closed.append(host)

    def _relay(self, client, target, host):
        peers = {client: target, target: client}
        with selectors.DefaultSelector() as selector:
            for connection in peers:
                connection.settimeout(0.5)
                selector.register(connection, selectors.EVENT_READ)
            while not self.stopped.is_set():
                for key, _ in selector.select(0.05):
                    data = key.fileobj.recv(4096)
                    if not data:
                        return
                    if key.fileobj is client:
                        self.payloads.append((host, data))
                    peers[key.fileobj].sendall(data)

    def close(self):
        self.stopped.set()
        self.listener.close()
        with self.lock:
            connections = tuple(self.connections)
        for connection in connections:
            connection.close()
        self.worker.join(2)
        for worker in self.workers:
            worker.join(2)
        assert not self.worker.is_alive() and not any(worker.is_alive() for worker in self.workers)


class Resolver:
    def __init__(self, addresses):
        self.addresses, self.calls = addresses, []

    def resolve(self, host, port, network, cancelled):
        self.calls.append((host, port, network))
        return list(self.addresses)

    def close(self):
        pass


def eventually(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


@contextmanager
def running(addresses, routes, *, seconds=1, on_request=None):
    gateway = Gateway(routes, on_request)
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        settings = config(reserve.getsockname()[1], gateway.port)
    settings["limits"]["connect_seconds"] = seconds
    resolver = Resolver(addresses)
    server = normalizer.Normalizer(settings, resolver=resolver)
    server.start()
    worker = threading.Thread(target=server.serve)
    worker.start()
    try:
        yield server, settings, resolver, gateway
    finally:
        server.stop()
        worker.join(2)
        gateway.close()
        assert not worker.is_alive()
        assert not server.workers
        assert server.connections._value == settings["limits"]["max_connections"]


def connect(settings, *, payload=b"", host="fixture.example"):
    listener = settings["listeners"][0]
    connection = auth(listener["port"], listener)
    # Observe the server's deadline, not a coincident client-side read timeout.
    connection.settimeout(settings["limits"]["connect_seconds"] + 1)
    name = host.encode("ascii")
    request = b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack("!H", 443)
    connection.sendall(request + payload)
    return connection


def test_candidate_order_deduplicates_and_keeps_both_families_before_cap():
    policy = DestinationPolicy(["192.0.2.1"], [443], [])
    addresses = ["2001:db8::3", "192.0.2.3", "127.0.0.1", "::ffff:192.0.2.2",
                 "192.0.2.2", "2001:db8::2", "192.0.2.1"]
    assert policy.admitted_candidates(addresses, 443, "tcp") == (
        "192.0.2.2", "2001:db8::2", "192.0.2.3", "2001:db8::3")
    assert policy.admitted_candidates(["2001:db8::3", "2001:db8::2"], 443, "tcp") == (
        "2001:db8::2", "2001:db8::3")


@pytest.mark.parametrize("first", ["stall", "refuse", "abrupt"])
def test_ipv6_wins_after_ipv4_failure_with_exact_pipelined_bytes(first):
    endpoint = Destination(socket.AF_INET6)
    try:
        with running(["192.0.2.1", "2001:db8::2"], {"192.0.2.1": first, "2001:db8::2": endpoint}) as (_, settings, resolver, gateway):
            started = time.monotonic()
            with connect(settings, payload=b"one-private-application-payload") as connection:
                normalizer._frame(connection, wire.upstream_reply)
                assert connection.recv(4096) == b"one-private-application-payload"
                assert time.monotonic() - started < 1
            eventually(lambda: set(gateway.closed) == {"192.0.2.1", "2001:db8::2"})
            assert resolver.calls == [("fixture.example.", 443, "tcp")]
            assert gateway.payloads == [("2001:db8::2", b"one-private-application-payload")]
            assert b"".join(endpoint.payloads) == b"one-private-application-payload"
            assert len(gateway.records) == 2
    finally:
        endpoint.close()


def test_later_a_record_succeeds_after_refusal_without_dns_rebinding():
    endpoint = Destination()
    try:
        with running(["192.0.2.1", "127.0.0.1", "::ffff:192.0.2.2", "192.0.2.2"],
                     {"192.0.2.1": "refuse", "192.0.2.2": endpoint}) as (_, settings, resolver, gateway):
            gateway.on_request = lambda _: setattr(resolver, "addresses", ["127.0.0.1"])
            with connect(settings, payload=b"still-admitted") as connection:
                normalizer._frame(connection, wire.upstream_reply)
                assert connection.recv(4096) == b"still-admitted"
            assert [row[0] for row in gateway.records] == ["192.0.2.1", "192.0.2.2"]
            assert len(resolver.calls) == 1
    finally:
        endpoint.close()


def test_two_stalled_candidates_cannot_starve_third_admitted_address():
    endpoint = Destination()
    try:
        with running(["192.0.2.1", "192.0.2.2", "192.0.2.3"],
                     {"192.0.2.1": "stall", "192.0.2.2": "stall", "192.0.2.3": endpoint},
                     seconds=2) as (_, settings, _, gateway):
            started = time.monotonic()
            with connect(settings, payload=b"third-winner") as connection:
                normalizer._frame(connection, wire.upstream_reply)
                assert connection.recv(4096) == b"third-winner"
                assert time.monotonic() - started < 2
            eventually(lambda: len(gateway.closed) == 3)
            assert gateway.payloads == [("192.0.2.3", b"third-winner")]
    finally:
        endpoint.close()


def test_shared_deadline_and_candidate_cap_close_every_stalled_control(monkeypatch):
    original = normalizer._GatewayConnect
    sockets, counts = [], []

    class ObservedConnect(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            sockets.append(self.connection)
            counts.append(sum(connection.fileno() >= 0 for connection in sockets))

    monkeypatch.setattr(normalizer, "_GatewayConnect", ObservedConnect)
    addresses = [f"192.0.2.{index}" for index in range(1, 12)]
    with running(addresses, dict.fromkeys(addresses, "stall"), seconds=2) as (server, settings, _, gateway):
        started = time.monotonic()
        with connect(settings) as connection:
            with pytest.raises(wire.WireError, match="upstream-refused"):
                normalizer._frame(connection, wire.upstream_reply)
        elapsed = time.monotonic() - started
        assert 1.8 < elapsed < 2.5
        eventually(lambda: not gateway.connections and not server.workers)
        assert 2 <= len(gateway.records) <= 8
        assert max(counts) == 2
        assert all(connection.fileno() == -1 for connection in sockets)
        assert all(int(row[0].split(".")[-1]) <= 8 for row in gateway.records)
        assert not gateway.payloads
        assert server.connections._value == settings["limits"]["max_connections"]


def test_refused_answers_stop_at_eight_without_sending_denied_literals():
    addresses = ["127.0.0.1", "10.0.0.1", *[f"192.0.2.{index}" for index in range(1, 12)]]
    with running(addresses, {}) as (_, settings, _, gateway):
        with connect(settings) as connection:
            with pytest.raises(wire.WireError, match="upstream-refused"):
                normalizer._frame(connection, wire.upstream_reply)
        assert [row[0] for row in gateway.records] == [f"192.0.2.{index}" for index in range(1, 9)]
        eventually(lambda: len(gateway.closed) == 8)


def test_policy_change_before_later_attempt_prevents_its_connect():
    with running(["192.0.2.1", "192.0.2.2"], {"192.0.2.1": "refuse"}) as (server, settings, _, gateway):
        gateway.on_request = lambda _: setattr(server, "policy", DestinationPolicy(["192.0.2.2"], [443], []))
        with connect(settings) as connection:
            with pytest.raises(wire.WireError, match="upstream-refused"):
                normalizer._frame(connection, wire.upstream_reply)
        assert [row[0] for row in gateway.records] == ["192.0.2.1"]


def test_winner_reset_after_application_bytes_never_retries():
    endpoint = Destination(reset_after_bytes=True)
    unused = Destination()
    try:
        with running(["192.0.2.1", "192.0.2.2"], {"192.0.2.1": endpoint, "192.0.2.2": unused}) as (server, settings, _, gateway):
            with connect(settings) as connection:
                normalizer._frame(connection, wire.upstream_reply)
                connection.sendall(b"never-replay")
                assert connection.recv(4096) == b""
            eventually(lambda: not server.workers)
            assert [row[0] for row in gateway.records] == ["192.0.2.1"]
            assert b"".join(endpoint.payloads) == b"never-replay"
            assert not unused.payloads
    finally:
        endpoint.close()
        unused.close()


@pytest.mark.parametrize("stop", [False, True])
def test_cancellation_reclaims_both_inflight_controls_and_capacity(stop):
    with running(["192.0.2.1", "2001:db8::2"], {"192.0.2.1": "stall", "2001:db8::2": "stall"},
                 seconds=3) as (server, settings, _, gateway):
        connection = connect(settings)
        try:
            eventually(lambda: len(gateway.records) == 2)
            assert len(gateway.connections) == 2
            if stop:
                server.stop()
            else:
                connection.close()
            eventually(lambda: not gateway.connections and not server.workers)
            assert server.connections._value == settings["limits"]["max_connections"]
            assert not gateway.payloads
        finally:
            connection.close()
