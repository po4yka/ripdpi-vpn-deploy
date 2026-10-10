"""Policy and real socket helper behavior; fixture gateways are not native proof."""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time

import pytest

from transport_destination_policy import (DestinationPolicy, IPV4_DENY, IPV6_DENY,
                                          PolicyError, canonical_name, normalize_address)
import transport_egress_normalizer as normalizer
import transport_socks as wire

ROOT = Path(__file__).resolve().parents[2]


def config(port=12080, backend_port=12090):
    return {"schema_version": 1, "runtime_uid": max(os.geteuid(), 501),
            "backends": {"direct": {"address": "127.0.0.1", "port": backend_port,
                                     "username": "gateway-direct", "password": "synthetic-backend-secret-" + "b" * 20,
                                     "udp_source_port_min": 20000, "udp_source_port_max": 20007}},
            "listeners": [{"name": "direct_xray", "address": "127.0.0.1", "port": port,
                           "frontend_uid": max(os.geteuid(), 501) + 1, "username": "normalizer-direct-xray",
                           "password": "synthetic-frontend-secret-" + "a" * 20, "backend": "direct",
                           "udp_port_min": 21000, "udp_port_max": 21007}],
            "resolver": {"nameservers": ["192.0.2.53"], "timeout_seconds": 1,
                         "attempts": 1, "lookup_timeout_seconds": 1, "workers": 2},
            "policy": {"owned_addresses": ["192.0.2.10"], "management_tcp_ports": [22, 12090],
                       "management_udp_ports": [12090]},
            "limits": {"max_connections": 8, "max_associations": 4, "max_pending_packets": 4,
                       "max_datagram_bytes": 4096, "max_bindings_per_association": 4,
                       "handshake_seconds": 1, "connect_seconds": 1, "idle_seconds": 300,
                       "udp_quarantine_seconds": 240}}


@pytest.mark.parametrize("address", ["0.0.0.0", "0.4.3.2", "10.1.2.3", "100.64.1.2", "127.8.9.10",
                                     "169.254.169.254", "172.31.4.5", "192.168.1.1", "224.2.3.4",
                                     "240.1.2.3", "255.255.255.255", "::", "::1", "fc00::2",
                                     "fe80::4", "ff01::2", "::ffff:127.0.0.1", "::ffff:10.1.2.3"])
def test_forbidden_representations_share_policy(address):
    assert not DestinationPolicy().allows(address, 443, "tcp")
    assert not DestinationPolicy().allows(address, 53, "udp")


@pytest.mark.parametrize("address", ["192.0.2.80", "198.51.100.4", "8.8.8.8", "2001:db8::80", "::ffff:192.0.2.80"])
def test_public_shaped_fixture_authorities_are_admitted(address):
    assert DestinationPolicy().allows(address, 443, "tcp")


def test_owned_management_and_mixed_answers_keep_public_capability():
    policy = DestinationPolicy(["192.0.2.10"], [22], [22])
    assert not policy.allows("::ffff:192.0.2.10", 22, "tcp")
    assert policy.allows("192.0.2.10", 443, "tcp")
    assert policy.allows("192.0.2.11", 22, "tcp")
    assert policy.select_admitted(["127.0.0.1", "::ffff:192.0.2.80"], 443, "tcp") == "192.0.2.80"
    with pytest.raises(PolicyError, match="destination-denied"):
        policy.select_admitted(["::ffff:127.0.0.1"], 443, "tcp")


def test_cli_policy_is_the_exact_canonical_table():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/transport_destination_policy.py"), "--print-policy"],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {"ipv4": list(IPV4_DENY), "ipv6": list(IPV6_DENY)}


@pytest.mark.parametrize("value", ["", "a..example", "name\x00.example", "bad name", "-bad.example", "a" * 64 + ".test"])
def test_invalid_names_are_bounded_and_categorical(value):
    with pytest.raises(PolicyError, match="invalid-name"):
        canonical_name(value)


def test_names_are_absolute_canonical_and_idna():
    assert canonical_name("Example.TEST") == "example.test."
    assert canonical_name("bücher.example") == "xn--bcher-kva.example."
    assert canonical_name("_service.example") == "_service.example."
    assert str(normalize_address("::ffff:192.0.2.80")) == "192.0.2.80"


@pytest.mark.parametrize("frame", [b"", b"\0\0\1\1" + bytes(6), b"\1\0\0\1" + bytes(6),
                                   b"\0\0\0\x09" + bytes(6), b"\0\0\0\3\xffx", b"\0\0\0\1" + bytes(6)])
def test_malformed_udp_never_becomes_a_destination(frame):
    with pytest.raises(wire.WireError):
        wire.datagram(frame, 4096)


def test_wire_literal_normalization_and_fragmented_authentication():
    frame = b"\0\0\0\4" + socket.inet_pton(socket.AF_INET6, "::ffff:192.0.2.80") + struct.pack("!H", 9000) + b"data"
    assert wire.datagram(frame, 4096) == ("192.0.2.80", 9000, b"data")
    assert wire.encoded_datagram("::ffff:192.0.2.80", 9000, b"data", 4096)[3] == 1
    message = wire.upstream_auth("user", "password")
    for length in range(len(message)):
        with pytest.raises(wire.NeedMore):
            wire.authentication(message[:length], "user", "password")
    assert wire.authentication(message, "user", "password")[1] == b"\1\0"


@pytest.mark.parametrize("mutation", ["boolean", "uid", "wildcard", "password", "pool", "endpoint", "resolver", "lifetime", "unknown"])
def test_strict_configuration_rejects_unsafe_authority(mutation):
    value = config()
    if mutation == "boolean":
        value["schema_version"] = True
    elif mutation == "uid":
        value["listeners"][0]["frontend_uid"] = value["runtime_uid"]
    elif mutation == "wildcard":
        value["listeners"][0]["address"] = "0.0.0.0"
    elif mutation == "password":
        value["listeners"][0]["password"] = value["backends"]["direct"]["password"]
    elif mutation == "pool":
        value["listeners"][0]["udp_port_min"] = 20000
    elif mutation == "endpoint":
        value["listeners"][0]["port"] = 21000
    elif mutation == "resolver":
        value["resolver"]["nameservers"] = ["127.0.0.53"]
    elif mutation == "lifetime":
        value["limits"]["lifetime_seconds"] = 300
    else:
        value["sensitive-marker"] = "sensitive-marker"
    with pytest.raises(normalizer.NormalizerError) as error:
        normalizer.validate_config(value)
    assert "sensitive-marker" not in str(error.value)


def test_early_and_final_cli_validation_remain_read_only_and_redacted(tmp_path):
    value = config()
    for argument, document in (("--validate", value), ("--validate-input", copy.deepcopy(value))):
        if argument == "--validate-input":
            document.pop("runtime_uid")
            document["listeners"][0].pop("frontend_uid")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/transport_egress_normalizer.py"), argument, "--config", "-"],
                                input=json.dumps(document), text=True, capture_output=True, timeout=2)
        assert result.returncode == 0 and result.stdout == "normalizer-config-valid\n"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/transport_egress_normalizer.py"), "--secret-marker"],
                            text=True, capture_output=True)
    assert result.returncode != 0 and "secret-marker" not in result.stdout + result.stderr
    candidate = tmp_path / "config.json"
    candidate.write_text(json.dumps(value))
    candidate.chmod(0o644)
    with pytest.raises(normalizer.NormalizerError, match="unsafe-config-file"):
        normalizer.load_config(str(candidate))


def test_printable_ascii_space_is_valid_private_authority():
    value = config()
    value["listeners"][0]["password"] = "synthetic secret with spaces " + "a" * 20
    assert normalizer.validate_config(value) is value


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class OwnedResolver:
    def __init__(self):
        self.calls = []
        self.answers = {"public.test.": ["127.0.0.1", "192.0.2.80"],
                        "next.test.": ["192.0.2.81"], "v6.test.": ["2001:db8::80"],
                        "private.test.": ["127.0.0.1"]}

    def resolve(self, name, port, network, cancelled=lambda: False):
        self.calls.append((name, port, network))
        return self.answers.get(name, [])

    def close(self):
        pass


class WireGateway:
    """Real sockets with an explicit fixture protocol peer, not Xray evidence."""
    def __init__(self):
        self.stop = threading.Event()
        self.tcp = socket.socket()
        self.tcp.bind(("127.0.0.1", 0))
        self.port = self.tcp.getsockname()[1]
        self.tcp.listen()
        self.tcp.settimeout(0.1)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", self.port))
        self.udp.settimeout(0.1)
        self.records = []
        self.source = None
        self.workers = []
        for target in (self._accept, self._udp):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self.workers.append(thread)

    def _accept(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            thread = threading.Thread(target=self._control, args=(connection,), daemon=True)
            thread.start()
            self.workers.append(thread)

    def _control(self, connection):
        with connection:
            connection.settimeout(2)
            try:
                normalizer._frame(connection, wire.greeting)
                connection.sendall(b"\x05")
                connection.sendall(b"\x02")
                normalizer._frame(connection, lambda data: wire.authentication(data, "gateway-direct", "synthetic-backend-secret-" + "b" * 20))
                connection.sendall(b"\x01\x00")
                _, command, host, port = normalizer._frame(connection, wire.request)
                self.records.append((command, host, port))
                connection.sendall(wire.reply("127.0.0.1", self.port))
                while not self.stop.is_set():
                    data = connection.recv(16384)
                    if not data:
                        if command == 1:
                            connection.sendall(b"after-half-close")
                        return
                    if command == 1:
                        connection.sendall(data)
            except (OSError, ValueError):
                return

    def _udp(self):
        while not self.stop.is_set():
            try:
                frame, source = self.udp.recvfrom(65508)
            except socket.timeout:
                continue
            except OSError:
                return
            self.source = source
            host, port, payload = wire.datagram(frame, 65507)
            self.records.append(("udp", host, port, payload))
            self.udp.sendto(frame, source)

    def close(self):
        self.stop.set()
        self.tcp.close()
        self.udp.close()
        for worker in self.workers:
            worker.join(0.2)


def auth(port, listener):
    connection = socket.create_connection(("127.0.0.1", port), timeout=2)
    connection.sendall(b"\x05\x01\x02")
    normalizer._frame(connection, lambda data: normalizer._expected(data, b"\x05\x02"))
    connection.sendall(wire.upstream_auth(listener["username"], listener["password"]))
    normalizer._frame(connection, lambda data: normalizer._expected(data, b"\x01\x00"))
    return connection


@contextmanager
def running(clock=None, mutate=lambda value: None):
    gateway = WireGateway()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        value = config(probe.getsockname()[1], gateway.port)
    mutate(value)
    resolver = OwnedResolver()
    server = normalizer.Normalizer(value, resolver=resolver, clock=clock or time.monotonic)
    server.start()
    worker = threading.Thread(target=server.serve, daemon=True)
    worker.start()
    try:
        yield server, value, resolver, gateway
    finally:
        server.stop()
        worker.join(2)
        gateway.close()


def udp_control(value):
    listener = value["listeners"][0]
    control = auth(listener["port"], listener)
    control.sendall(wire.upstream_request(3, "0.0.0.0", 0))
    _, host, port = normalizer._frame(control, wire.upstream_reply)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(0.5)
    return control, client, (host, port)


def send_name(client, relay, name, marker, port=9000):
    encoded = name.encode("utf-8")
    frame = bytes(3) + bytes([3, len(encoded)]) + encoded + struct.pack("!H", port) + marker
    client.sendto(frame, relay)
    return wire.datagram(client.recv(4096), 4096)


def test_tcp_domain_selection_relay_and_half_close():
    with running() as (_, value, resolver, gateway):
        connection = auth(value["listeners"][0]["port"], value["listeners"][0])
        name = b"public.test"
        connection.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack("!H", 9000))
        normalizer._frame(connection, wire.upstream_reply)
        connection.sendall(b"payload")
        assert connection.recv(7) == b"payload"
        connection.shutdown(socket.SHUT_WR)
        assert connection.recv(1024) == b"after-half-close"
        connection.close()
        assert (1, "192.0.2.80", 9000) in gateway.records
        assert resolver.calls == [("public.test.", 9000, "tcp")]


def test_named_udp_bindings_and_new_families_deliver_exactly_once():
    with running() as (_, value, resolver, gateway):
        control, client, relay = udp_control(value)
        try:
            for number in range(6):
                assert send_name(client, relay, "PUBLIC.test", bytes([number])) == ("192.0.2.80", 9000, bytes([number]))
            resolver.answers["public.test."] = ["127.0.0.1"]
            assert send_name(client, relay, "public.test", b"still-bound")[0] == "192.0.2.80"
            assert send_name(client, relay, "next.test", b"fresh-v4")[0] == "192.0.2.81"
            assert send_name(client, relay, "v6.test", b"fresh-v6")[0] == "2001:db8::80"
            with pytest.raises(socket.timeout):
                send_name(client, relay, "private.test", b"denied")
            assert send_name(client, relay, "v6.test", b"recovered")[2] == b"recovered"
            assert resolver.calls.count(("public.test.", 9000, "udp")) == 1
            records = [item for item in gateway.records if item[0] == "udp"]
            assert len(records) == 10
            assert all(item[1] not in ("127.0.0.1", "public.test.") for item in records)
        finally:
            control.close()
            client.close()


def test_active_tcp_and_udp_have_idle_not_absolute_age():
    clock = Clock()
    with running(clock) as (_, value, _, _):
        stream = auth(value["listeners"][0]["port"], value["listeners"][0])
        stream.sendall(wire.upstream_request(1, "192.0.2.80", 9000))
        normalizer._frame(stream, wire.upstream_reply)
        control, client, relay = udp_control(value)
        try:
            for _ in range(6):
                clock.advance(150)
                assert send_name(client, relay, "public.test", b"active")[2] == b"active"
                stream.sendall(b"active")
                assert stream.recv(6) == b"active"
            assert clock() > 300
        finally:
            control.close()
            client.close()
            stream.close()


def test_wrong_private_authentication_never_contacts_backend():
    with running() as (_, value, resolver, gateway):
        connection = socket.create_connection(("127.0.0.1", value["listeners"][0]["port"]), timeout=2)
        connection.sendall(b"\x05\x01\x02")
        normalizer._frame(connection, lambda data: normalizer._expected(data, b"\x05\x02"))
        connection.sendall(wire.upstream_auth(value["listeners"][0]["username"], "wrong-private-marker"))
        assert connection.recv(2) == b"\x01\x01"
        connection.close()
        assert gateway.records == [] and resolver.calls == []


def test_handshake_budget_is_absolute_across_frames():
    with running() as (_, value, _, gateway):
        connection = socket.create_connection(("127.0.0.1", value["listeners"][0]["port"]), timeout=2)
        connection.sendall(b"\x05\x01\x02")
        normalizer._frame(connection, lambda data: normalizer._expected(data, b"\x05\x02"))
        connection.sendall(b"\x01")
        time.sleep(1.1)
        assert connection.recv(2) == b"\x01\x01"
        connection.close()
        assert gateway.records == []


def test_fresh_association_resolves_changed_answer_and_existing_policy_is_rechecked():
    with running() as (server, value, resolver, gateway):
        old, client, relay = udp_control(value)
        fresh = fresh_client = None
        try:
            assert send_name(client, relay, "public.test", b"bound")[0] == "192.0.2.80"
            resolver.answers["public.test."] = ["127.0.0.1"]
            fresh, fresh_client, fresh_relay = udp_control(value)
            with pytest.raises(socket.timeout):
                send_name(fresh_client, fresh_relay, "public.test", b"new-private")
            assert send_name(client, relay, "public.test", b"old-public")[0] == "192.0.2.80"
            assert resolver.calls.count(("public.test.", 9000, "udp")) == 2
            server.policy = DestinationPolicy(["192.0.2.80"], [], [9000])
            with pytest.raises(socket.timeout):
                send_name(client, relay, "public.test", b"new-management")
            assert len([item for item in gateway.records if item[0] == "udp"]) == 2
        finally:
            old.close();client.close()
            if fresh:
                fresh.close();fresh_client.close()


def test_binding_exhaustion_and_wrong_source_cannot_reassign_association():
    with running(mutate=lambda value: value["limits"].update(max_bindings_per_association=1)) as (_, value, _, gateway):
        control, client, relay = udp_control(value)
        rogue = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rogue.settimeout(0.2)
        try:
            assert send_name(client, relay, "public.test", b"accepted")[2] == b"accepted"
            with pytest.raises(socket.timeout):
                send_name(rogue, relay, "public.test", b"wrong-source")
            with pytest.raises(socket.timeout):
                send_name(client, relay, "next.test", b"over-budget")
            assert send_name(client, relay, "public.test", b"recover")[2] == b"recover"
            assert len([item for item in gateway.records if item[0] == "udp"]) == 2
        finally:
            rogue.close()
            control.close()
            client.close()


def test_resolver_workers_are_killed_and_replaced_on_deadline(tmp_path, monkeypatch):
    worker = tmp_path / "worker.py"
    worker.write_text("import json,sys,time\nfor line in sys.stdin:\n j=json.loads(line)\n"
                      " if j['host']=='slow.test.': time.sleep(30)\n"
                      " print(json.dumps({'id':j['id'],'addresses':['192.0.2.80']}),flush=True)\n")
    actual = subprocess.Popen
    monkeypatch.setattr(normalizer.subprocess, "Popen", lambda *args, **kwargs: actual([sys.executable, str(worker)], **kwargs))
    stopped = threading.Event()
    pool = normalizer.ResolverPool(config()["resolver"], stopped)
    old = tuple(pool.processes)
    try:
        assert pool.resolve("public.test.", 9000, "udp") == ["192.0.2.80"]
        started = time.monotonic()
        with pytest.raises(normalizer.NormalizerError, match="resolution-unavailable"):
            pool.resolve("slow.test.", 9000, "udp")
        assert time.monotonic() - started < 2
        assert len(pool.processes) == 2 and any(process.poll() is not None for process in old)
        assert pool.resolve("public.test.", 9000, "udp") == ["192.0.2.80"]
    finally:
        stopped.set()
        pool.close()


def test_sustained_late_packets_keep_paired_tuples_quarantined():
    clock = Clock()
    def one(value):
        value["limits"]["max_associations"] = 1
        value["listeners"][0]["udp_port_max"] = value["listeners"][0]["udp_port_min"]
        value["backends"]["direct"]["udp_source_port_max"] = value["backends"]["direct"]["udp_source_port_min"]
    with running(clock, one) as (server, value, _, gateway):
        control, client, relay = udp_control(value)
        try:
            assert send_name(client, relay, "public.test", b"old")[2] == b"old"
            source = gateway.source
            control.close()
            time.sleep(0.25)
            clock.advance(200)
            gateway.udp.sendto(wire.encoded_datagram("192.0.2.80", 9000, b"late", 4096), source)
            time.sleep(0.1)
            clock.advance(100)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                with pytest.raises(OSError):
                    probe.bind(relay)
            replacement = auth(value["listeners"][0]["port"], value["listeners"][0])
            replacement.sendall(wire.upstream_request(3, "0.0.0.0", 0))
            assert replacement.recv(10) == wire.FAILURE
            replacement.close()
            with pytest.raises(socket.timeout):
                client.recv(4096)
            clock.advance(241)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not server.front_pools["direct_xray"].ports:
                time.sleep(0.02)
            new_control, new_client, new_relay = udp_control(value)
            try:
                assert new_relay == relay
                assert send_name(new_client, new_relay, "public.test", b"new")[2] == b"new"
            finally:
                new_control.close()
                new_client.close()
        finally:
            control.close()
            client.close()
