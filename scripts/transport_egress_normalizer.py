#!/usr/bin/env python3
"""Private SOCKS metadata normalization through fixed native gateways only."""
from __future__ import annotations

import argparse
from collections import deque
import errno
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

from transport_destination_policy import DestinationPolicy, PolicyError, canonical_name, normalize_address
from transport_private_authority import PrivateAuthorityError, read_private_file
from transport_socks import (FAILURE, MAX_HANDSHAKE, NeedMore, WireError, authentication,
                             datagram, encoded_datagram, greeting, reply, request,
                             upstream_auth, upstream_reply, upstream_request)

MAX_CONFIG = 131072
MAX_STREAM_BUFFER = 65536
MAX_RESOLVER_RESPONSE = 8192
LISTENERS = {"direct_xray": "direct", "direct_hysteria": "direct", "warp_xray": "warp"}


def _wait(readers, writers=(), timeout=0.2):
    """poll/epoll/kqueue rather than select's descriptor-number ceiling."""
    masks = {}
    for value in readers:
        masks[value] = masks.get(value, 0) | selectors.EVENT_READ
    for value in writers:
        masks[value] = masks.get(value, 0) | selectors.EVENT_WRITE
    with selectors.DefaultSelector() as selector:
        for value, events in masks.items():
            selector.register(value, events)
        events = selector.select(timeout)
    return ([key.fileobj for key, mask in events if mask & selectors.EVENT_READ],
            [key.fileobj for key, mask in events if mask & selectors.EVENT_WRITE])


class NormalizerError(ValueError):
    """Public messages never contain input values or exception details."""


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise NormalizerError("invalid-config-shape")


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise NormalizerError("invalid-config-number")


def _identity(value):
    _integer(value, 1, 2**32 - 2)


def _credential(value, password=False):
    if (not isinstance(value, str) or not (32 if password else 1) <= len(value) <= (128 if password else 63)
            or not value.isascii() or any(not 32 <= ord(character) <= 126 for character in value)):
        raise NormalizerError("invalid-config-credential")


def validate_config(raw, *, input_only=False):
    """Validate complete typed authority; input mode omits uncreated identities."""
    top = {"schema_version", "backends", "listeners", "resolver", "policy", "limits"}
    _keys(raw, top if input_only else top | {"runtime_uid"})
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise NormalizerError("invalid-config-version")
    if not input_only:
        _identity(raw["runtime_uid"])
    if not isinstance(raw["backends"], dict) or not raw["backends"] or set(raw["backends"]) - {"direct", "warp"}:
        raise NormalizerError("invalid-backends")
    pools, endpoints, passwords = [], set(), []
    for name, backend in raw["backends"].items():
        _keys(backend, {"address", "port", "username", "password", "udp_source_port_min", "udp_source_port_max"})
        try:
            address = normalize_address(backend["address"])
        except PolicyError:
            raise NormalizerError("invalid-backend-address") from None
        if (str(address) != backend["address"] or address.version != 4
                or (name == "direct" and str(address) != "127.0.0.1")
                or (name == "warp" and (address.is_loopback or not address.is_private or address.is_unspecified))):
            raise NormalizerError("invalid-backend-address")
        _integer(backend["port"], 1, 65535)
        _credential(backend["username"])
        _credential(backend["password"], True)
        passwords.append(backend["password"])
        endpoints.add((backend["address"], backend["port"]))
        pools.append((backend["udp_source_port_min"], backend["udp_source_port_max"]))
    listeners = raw["listeners"]
    if not isinstance(listeners, list) or not 1 <= len(listeners) <= 3:
        raise NormalizerError("invalid-listeners")
    names, used_backends = set(), set()
    for listener in listeners:
        fields = {"name", "address", "port", "username", "password", "backend", "udp_port_min", "udp_port_max"}
        _keys(listener, fields if input_only else fields | {"frontend_uid"})
        name = listener["name"]
        if not isinstance(name, str) or name not in LISTENERS or name in names or listener["backend"] != LISTENERS[name]:
            raise NormalizerError("invalid-listener-contract")
        names.add(name)
        used_backends.add(listener["backend"])
        if listener["address"] != "127.0.0.1":
            raise NormalizerError("invalid-listener-address")
        _integer(listener["port"], 1, 65535)
        endpoint = (listener["address"], listener["port"])
        if endpoint in endpoints:
            raise NormalizerError("duplicate-endpoint")
        endpoints.add(endpoint)
        if not input_only:
            _identity(listener["frontend_uid"])
            if listener["frontend_uid"] == raw["runtime_uid"]:
                raise NormalizerError("identity-not-separated")
        _credential(listener["username"])
        _credential(listener["password"], True)
        passwords.append(listener["password"])
        pools.append((listener["udp_port_min"], listener["udp_port_max"]))
    if used_backends != set(raw["backends"]):
        raise NormalizerError("unconsumed-backend")
    if len(set(passwords)) != len(passwords):
        raise NormalizerError("reused-config-credential")
    for low, high in pools:
        _integer(low, 1, 65535)
        _integer(high, low, 65535)
        if high - low > 8191 or any(low <= port <= high for _, port in endpoints):
            raise NormalizerError("invalid-port-pool")
    for index, (low, high) in enumerate(pools):
        if any(low <= other_high and other_low <= high for other_low, other_high in pools[:index]):
            raise NormalizerError("overlapping-port-pools")
    resolver = raw["resolver"]
    _keys(resolver, {"nameservers", "timeout_seconds", "attempts", "lookup_timeout_seconds", "workers"})
    if not isinstance(resolver["nameservers"], list) or not 1 <= len(resolver["nameservers"]) <= 3:
        raise NormalizerError("invalid-resolvers")
    policy = DestinationPolicy()
    for value in resolver["nameservers"]:
        try:
            if str(normalize_address(value)) != value or not policy.allows(value, 53, "udp"):
                raise NormalizerError("invalid-resolvers")
        except PolicyError:
            raise NormalizerError("invalid-resolvers") from None
    if len(set(resolver["nameservers"])) != len(resolver["nameservers"]):
        raise NormalizerError("invalid-resolvers")
    for name, low, high in (("timeout_seconds", 1, 5), ("attempts", 1, 2),
                            ("lookup_timeout_seconds", 1, 15), ("workers", 1, 8)):
        _integer(resolver[name], low, high)
    policy_raw = raw["policy"]
    _keys(policy_raw, {"owned_addresses", "management_tcp_ports", "management_udp_ports"})
    if not isinstance(policy_raw["owned_addresses"], list) or len(policy_raw["owned_addresses"]) > 256:
        raise NormalizerError("invalid-owned-addresses")
    try:
        if any(str(normalize_address(value)) != value for value in policy_raw["owned_addresses"]):
            raise NormalizerError("invalid-owned-addresses")
    except PolicyError:
        raise NormalizerError("invalid-owned-addresses") from None
    for name in ("management_tcp_ports", "management_udp_ports"):
        ports = policy_raw[name]
        if not isinstance(ports, list) or len(ports) > 256:
            raise NormalizerError("invalid-management-ports")
        for port in ports:
            _integer(port, 1, 65535)
        if len(set(ports)) != len(ports):
            raise NormalizerError("invalid-management-ports")
    limits = raw["limits"]
    ranges = {"max_connections": (1, 512), "max_associations": (1, 1024),
              "max_pending_packets": (1, 4096), "max_datagram_bytes": (22, 65507),
              "max_bindings_per_association": (1, 128), "handshake_seconds": (1, 60),
              "connect_seconds": (1, 60), "idle_seconds": (1, 86400),
              "udp_quarantine_seconds": (240, 86400)}
    _keys(limits, ranges)
    for name, bounds in ranges.items():
        _integer(limits[name], *bounds)
    return raw


def _duplicate_safe(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NormalizerError("duplicate-config-field")
        result[key] = value
    return result


def load_config(path, *, input_only=False):
    if path == "-":
        data = sys.stdin.buffer.read(MAX_CONFIG + 1)
    else:
        try:
            data = read_private_file(path, max_bytes=MAX_CONFIG)
        except PrivateAuthorityError:
            raise NormalizerError("unsafe-config-file") from None
    if len(data) > MAX_CONFIG:
        raise NormalizerError("oversized-config")
    try:
        return validate_config(json.loads(data, object_pairs_hook=_duplicate_safe), input_only=input_only)
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError):
        raise NormalizerError("invalid-config") from None


def validate_runtime_environment(config):
    if sys.platform != "linux" or os.geteuid() != config["runtime_uid"] or os.geteuid() == 0:
        raise NormalizerError("invalid-runtime-identity")
    for path in ("/etc/resolv.conf", "/etc/nsswitch.conf", "/etc/hosts"):
        metadata = os.stat(path)
        if (metadata.st_uid != 0 or metadata.st_mode & 0o022 or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > 16384):
            raise NormalizerError("unsafe-resolver-authority")
    lines = [line.split("#", 1)[0].strip() for line in Path("/etc/resolv.conf").read_text().splitlines()]
    lines = [line for line in lines if line]
    resolver = config["resolver"]
    expected = ["nameserver " + value for value in resolver["nameservers"]]
    expected.append(f"options timeout:{resolver['timeout_seconds']} attempts:{resolver['attempts']}")
    if lines != expected:
        raise NormalizerError("unsealed-resolver-authority")
    hosts = [line.split("#", 1)[0].strip() for line in Path("/etc/hosts").read_text().splitlines()]
    nss = [line.split("#", 1)[0].strip() for line in Path("/etc/nsswitch.conf").read_text().splitlines()]
    if any(hosts) or [line.split() for line in nss if line.partition(":")[0].strip() == "hosts"] != [["hosts:", "dns"]]:
        raise NormalizerError("unsealed-resolver-authority")
    if any(name in os.environ for name in ("LOCALDOMAIN", "RES_OPTIONS", "HOSTALIASES", "PYTHONPATH", "PYTHONHOME")):
        raise NormalizerError("unsealed-resolver-environment")
    try:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except OSError as error:
        if error.errno not in (errno.EPERM, errno.EACCES, errno.EAFNOSUPPORT):
            raise NormalizerError("unsealed-resolver-ipc") from None
    else:
        probe.close()
        raise NormalizerError("unsealed-resolver-ipc")


def resolver_worker():
    while True:
        line = sys.stdin.buffer.readline(1025)
        if not line:
            return 0
        if len(line) > 1024 or not line.endswith(b"\n"):
            return 1
        job = {}
        try:
            job = json.loads(line)
            _keys(job, {"id", "host", "port", "network"})
            _integer(job["id"], 1, 2**63 - 1)
            _integer(job["port"], 1, 65535)
            host = canonical_name(job["host"])
            if host != job["host"] or job["network"] not in ("tcp", "udp"):
                raise NormalizerError("invalid-resolver-request")
            rows = socket.getaddrinfo(host, job["port"], socket.AF_UNSPEC,
                                      socket.SOCK_STREAM if job["network"] == "tcp" else socket.SOCK_DGRAM, 0, 0)
            addresses = sorted({str(normalize_address(row[4][0])) for row in rows})
            if len(addresses) > 64:
                raise NormalizerError("oversized-resolver-answer")
            result = {"id": job["id"], "addresses": addresses}
        except (ValueError, KeyError, OSError, TypeError):
            identifier = job.get("id", 0) if isinstance(job, dict) else 0
            result = {"id": identifier if type(identifier) is int and 1 <= identifier < 2**63 else 0,
                      "addresses": []}
        sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
        sys.stdout.flush()


class ResolverPool:
    """Fixed subprocess slots; timeout/cancellation kills the owning worker."""
    def __init__(self, config, stopped):
        self.config, self.stopped = config, stopped
        self.condition = threading.Condition()
        self.available = deque()
        self.processes = set()
        self.counter = 0
        try:
            for _ in range(config["workers"]):
                self.available.append(self._spawn())
        except OSError:
            self.close()
            raise NormalizerError("resolver-unavailable") from None

    def _spawn(self):
        process = subprocess.Popen([sys.executable, "-Es", str(Path(__file__).resolve()), "--resolver-worker"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   bufsize=0, close_fds=True)
        self.processes.add(process)
        return process

    def resolve(self, host, port, network, cancelled=lambda: False):
        deadline = time.monotonic() + self.config["lookup_timeout_seconds"]
        process = None
        with self.condition:
            while not self.available:
                if self.stopped.is_set() or cancelled() or time.monotonic() >= deadline:
                    raise NormalizerError("resolution-unavailable")
                self.condition.wait(min(0.1, max(0.001, deadline - time.monotonic())))
            process = self.available.popleft()
            self.counter += 1
            job_id = self.counter
        good = False
        try:
            process.stdin.write(json.dumps({"id": job_id, "host": host, "port": port, "network": network}).encode() + b"\n")
            output = bytearray()
            while b"\n" not in output:
                if self.stopped.is_set() or cancelled() or time.monotonic() >= deadline:
                    raise NormalizerError("resolution-unavailable")
                if not _wait([process.stdout], timeout=0.1)[0]:
                    continue
                chunk = os.read(process.stdout.fileno(), 1024)
                if not chunk or len(output) + len(chunk) > MAX_RESOLVER_RESPONSE:
                    raise NormalizerError("resolution-unavailable")
                output.extend(chunk)
            value = json.loads(output)
            _keys(value, {"id", "addresses"})
            if value["id"] != job_id or not isinstance(value["addresses"], list) or len(value["addresses"]) > 64:
                raise NormalizerError("resolution-unavailable")
            addresses = [str(normalize_address(address)) for address in value["addresses"]]
            good = True
            return addresses
        except (OSError, ValueError, TypeError):
            raise NormalizerError("resolution-unavailable") from None
        finally:
            with self.condition:
                if not good or self.stopped.is_set():
                    self._close(process)
                    if not self.stopped.is_set():
                        self.available.append(self._spawn())
                else:
                    self.available.append(process)
                self.condition.notify()

    def _close(self, process):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=1)
        process.stdin.close()
        process.stdout.close()
        self.processes.discard(process)

    def close(self):
        with self.condition:
            for process in tuple(self.processes):
                self._close(process)
            self.available.clear()
            self.condition.notify_all()


def _frame(connection, parser, deadline=None):
    data = bytearray()
    deadline = deadline or time.monotonic() + (connection.gettimeout() or 5)
    # Read only the requested frame: never consume application data ahead of it.
    while len(data) <= MAX_HANDSHAKE:
        try:
            value = parser(data)
            return value
        except NeedMore:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WireError("handshake-expired")
            connection.settimeout(remaining)
            chunk = connection.recv(1)
            if not chunk:
                raise WireError("control-closed")
            data.extend(chunk)
    raise WireError("oversized-handshake")


def _closed(connection):
    if _wait([connection], timeout=0)[0]:
        return not connection.recv(1, socket.MSG_PEEK)
    return False


def _expected(data, expected):
    if len(data) < len(expected):
        raise NeedMore
    if bytes(data) != expected:
        raise WireError("upstream-authentication-refused")
    return len(data)


class PortPool:
    def __init__(self, low, high, address="127.0.0.1"):
        self.ports = deque(range(low, high + 1))
        self.address = address
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            for _ in range(len(self.ports)):
                port = self.ports.popleft()
                connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16384)
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
                    connection.bind((self.address, port))
                    connection.setblocking(False)
                    return connection, port
                except OSError:
                    connection.close()
                    self.ports.append(port)
            raise NormalizerError("association-capacity")

    def release(self, connection, port):
        connection.close()
        with self.lock:
            self.ports.append(port)


class Normalizer:
    def __init__(self, config, *, resolver=None, clock=time.monotonic):
        self.config = validate_config(config)
        self.limits = config["limits"]
        self.clock = clock
        self.stopped = threading.Event()
        self.resolver = resolver or ResolverPool(config["resolver"], self.stopped)
        self.policy = DestinationPolicy(**config["policy"])
        self.connections = threading.BoundedSemaphore(self.limits["max_connections"])
        self.associations = threading.BoundedSemaphore(self.limits["max_associations"])
        self.pending = threading.BoundedSemaphore(self.limits["max_pending_packets"])
        self.front_pools = {item["name"]: PortPool(item["udp_port_min"], item["udp_port_max"])
                            for item in config["listeners"]}
        # Source binding chooses the kernel path to the exact fixed backend.
        self.back_pools = {name: PortPool(item["udp_source_port_min"], item["udp_source_port_max"], "0.0.0.0")
                           for name, item in config["backends"].items()}
        self.listeners = []
        self.workers = set()
        self.lock = threading.Lock()

    def start(self):
        try:
            for item in self.config["listeners"]:
                connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                connection.bind((item["address"], item["port"]))
                connection.listen(min(self.limits["max_connections"], 128))
                connection.setblocking(False)
                self.listeners.append((connection, item))
        except OSError:
            self.stop()
            raise NormalizerError("listener-unavailable") from None

    def serve(self):
        try:
            while not self.stopped.is_set():
                try:
                    ready = _wait([item[0] for item in self.listeners])[0]
                except (OSError, ValueError):
                    if self.stopped.is_set():
                        break
                    raise NormalizerError("listener-unavailable") from None
                for listening, item in self.listeners:
                    if listening not in ready:
                        continue
                    try:
                        connection, source = listening.accept()
                    except BlockingIOError:
                        continue
                    if not self.connections.acquire(blocking=False):
                        connection.close()
                        continue
                    worker = threading.Thread(target=self._handle, args=(connection, source, item), daemon=True)
                    with self.lock:
                        self.workers.add(worker)
                    worker.start()
        finally:
            self.stop()

    def stop(self):
        self.stopped.set()
        for connection, _ in self.listeners:
            connection.close()
        self.listeners.clear()
        # A process stop loses quarantine; the generation controller MUST stop
        # both native gateways before allowing a new normalizer generation.
        self.resolver.close()
        with self.lock:
            workers = tuple(self.workers)
        deadline = time.monotonic() + 2
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=max(0, deadline - time.monotonic()))

    def _literal(self, host, port, network, control):
        try:
            value = str(normalize_address(host))
        except PolicyError:
            values = self.resolver.resolve(canonical_name(host), port, network,
                                           lambda: self.stopped.is_set() or _closed(control)
                                           or (network == "udp" and bool(_wait([control], timeout=0)[0])))
            value = self.policy.select_admitted(values, port, network)
        if not self.policy.allows(value, port, network):
            raise PolicyError("destination-denied")
        return value

    def _backend(self, item, command, host="0.0.0.0", port=0):
        backend = self.config["backends"][item["backend"]]
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            deadline = time.monotonic() + self.limits["connect_seconds"]
            connection.settimeout(self.limits["connect_seconds"])
            connection.connect((backend["address"], backend["port"]))
            connection.sendall(b"\x05\x01\x02")
            _frame(connection, lambda data: _expected(data, b"\x05\x02"), deadline)
            connection.sendall(upstream_auth(backend["username"], backend["password"]))
            _frame(connection, lambda data: _expected(data, b"\x01\x00"), deadline)
            connection.sendall(upstream_request(command, host, port))
            _, address, bound_port = _frame(connection, upstream_reply, deadline)
            if command == 3 and (address != backend["address"] or bound_port != backend["port"]):
                raise WireError("unexpected-upstream-relay")
            return connection, backend
        except (OSError, ValueError):
            connection.close()
            raise NormalizerError("upstream-unavailable") from None

    def _handle(self, connection, source, item):
        backend_control = None
        phase = "greeting"
        try:
            deadline = time.monotonic() + self.limits["handshake_seconds"]
            connection.settimeout(self.limits["handshake_seconds"])
            _, response = _frame(connection, greeting, deadline)
            connection.sendall(response)
            phase = "authentication"
            _, response = _frame(connection, lambda data: authentication(data, item["username"], item["password"]), deadline)
            connection.sendall(response)
            phase = "request"
            _, command, host, port = _frame(connection, request, deadline)
            if command == 1:
                literal = self._literal(host, port, "tcp", connection)
                if _closed(connection):
                    return
                backend_control, _ = self._backend(item, command, literal, port)
                connection.settimeout(self.limits["connect_seconds"])
                connection.sendall(reply(item["address"], item["port"]))
                phase = "relay"
                self._relay(connection, backend_control)
            else:
                if item["name"] != "direct_hysteria" and (host not in ("0.0.0.0", "::") or port):
                    raise WireError("invalid-association-metadata")
                self._association(connection, source, item)
        except (OSError, ValueError):
            if phase != "relay":
                try:
                    connection.sendall(b"\x05\xff" if phase == "greeting" else
                                       b"\x01\x01" if phase == "authentication" else FAILURE)
                except OSError:
                    pass
        finally:
            connection.close()
            if backend_control is not None:
                backend_control.close()
            self.connections.release()
            with self.lock:
                self.workers.discard(threading.current_thread())

    def _relay(self, client, backend):
        last = self.clock()
        buffers = {client: bytearray(), backend: bytearray()}
        peers = {client: backend, backend: client}
        read_open, pending_fin = set(peers), set()
        for connection in peers:
            connection.setblocking(False)
        while not self.stopped.is_set() and self.clock() - last < self.limits["idle_seconds"]:
            readers = [connection for connection in read_open if len(buffers[peers[connection]]) < MAX_STREAM_BUFFER]
            writers = [connection for connection in peers if buffers[connection]]
            if not readers and not writers:
                return
            readable, writable = _wait(readers, writers)
            for connection in writable:
                try:
                    sent = connection.send(buffers[connection])
                except BlockingIOError:
                    continue
                if not sent:
                    return
                del buffers[connection][:sent]
                last = self.clock()
            for connection in readable:
                try:
                    data = connection.recv(min(16384, MAX_STREAM_BUFFER - len(buffers[peers[connection]])))
                except BlockingIOError:
                    continue
                if not data:
                    read_open.remove(connection)
                    pending_fin.add(peers[connection])
                    continue
                buffers[peers[connection]].extend(data)
                last = self.clock()
            for connection in tuple(pending_fin):
                if not buffers[connection]:
                    connection.shutdown(socket.SHUT_WR)
                    pending_fin.remove(connection)

    def _association(self, control, source, item):
        if not self.associations.acquire(blocking=False):
            raise NormalizerError("association-capacity")
        front = upstream = backend_control = None
        front_port = upstream_port = None
        try:
            front, front_port = self.front_pools[item["name"]].acquire()
            backend_control, backend = self._backend(item, 3)
            upstream, upstream_port = self.back_pools[item["backend"]].acquire()
            upstream.connect((backend["address"], backend["port"]))
            control.sendall(reply(item["address"], front_port))
            control.setblocking(False)
            backend_control.setblocking(False)
            source_ip = str(normalize_address(source[0]))
            pinned_source = None
            bindings, admitted = {}, set()
            last = self.clock()
            maximum = self.limits["max_datagram_bytes"]
            while not self.stopped.is_set() and self.clock() - last < self.limits["idle_seconds"]:
                ready = _wait([control, backend_control, front, upstream])[0]
                if control in ready or backend_control in ready:
                    # No control data is part of an established UDP association.
                    break
                if front in ready:
                    frame, address = front.recvfrom(maximum + 1)
                    if pinned_source is not None and address != pinned_source:
                        continue
                    if str(normalize_address(address[0])) != source_ip or not self.pending.acquire(blocking=False):
                        continue
                    try:
                        host, port, payload = datagram(frame, maximum)
                        if not payload:
                            continue
                        key = (host, port)
                        if key not in bindings:
                            if len(bindings) >= self.limits["max_bindings_per_association"]:
                                continue
                            bindings[key] = self._literal(host, port, "udp", control)
                        literal = bindings[key]
                        if not self.policy.allows(literal, port, "udp"):
                            continue
                        if _wait([control, backend_control], timeout=0)[0] or self.stopped.is_set():
                            break
                        packet = encoded_datagram(literal, port, payload, maximum)
                        upstream.send(packet)
                        admitted.add((literal, port))
                        pinned_source = address
                        last = self.clock()
                    except (OSError, ValueError):
                        continue
                    finally:
                        self.pending.release()
                if upstream in ready:
                    frame = upstream.recv(maximum + 1)
                    try:
                        host, port, payload = datagram(frame, maximum)
                        if ((host, port) not in admitted or pinned_source is None
                                or not self.policy.allows(host, port, "udp")):
                            continue
                        front.sendto(encoded_datagram(host, port, payload, maximum), pinned_source)
                        last = self.clock()
                    except (OSError, ValueError):
                        continue
        finally:
            control.close()
            if backend_control is not None:
                backend_control.close()
            sockets = [value for value in (front, upstream) if value is not None]
            quiet = self.clock()
            while sockets and not self.stopped.is_set() and self.clock() - quiet < self.limits["udp_quarantine_seconds"]:
                ready = _wait(sockets)[0]
                for connection in ready:
                    # Drain at most 16 frames per socket per pass. Never release
                    # a busy tuple to satisfy capacity or an absolute age.
                    for _ in range(16):
                        try:
                            connection.recvfrom(65508)
                            quiet = self.clock()
                        except BlockingIOError:
                            break
                        except OSError:
                            break
                if ready:
                    self.stopped.wait(0.01)
            if front is not None:
                self.front_pools[item["name"]].release(front, front_port)
            if upstream is not None:
                self.back_pools[item["backend"]].release(upstream, upstream_port)
            self.associations.release()


def main():
    class CategoricalParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, "normalizer-unavailable\n")

    parser = CategoricalParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--validate-input", action="store_true")
    parser.add_argument("--resolver-worker", action="store_true")
    args = parser.parse_args()
    try:
        if args.resolver_worker:
            if args.config or args.validate or args.validate_input:
                raise NormalizerError("invalid-command")
            return resolver_worker()
        if not args.config or (args.validate and args.validate_input):
            raise NormalizerError("invalid-command")
        config = load_config(args.config, input_only=args.validate_input)
        if args.validate or args.validate_input:
            print("normalizer-config-valid")
            return 0
        if args.config == "-":
            raise NormalizerError("runtime-private-config-required")
        validate_runtime_environment(config)
        server = Normalizer(config)
        signal.signal(signal.SIGTERM, lambda *_: server.stopped.set())
        signal.signal(signal.SIGINT, lambda *_: server.stopped.set())
        server.start()
        print("normalizer-ready", flush=True)
        server.serve()
        return 0
    except NormalizerError as error:
        print("normalizer-unavailable:" + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as error:
        print("normalizer-unavailable:" + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
