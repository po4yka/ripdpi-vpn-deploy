"""Byte-level probes through an actual authenticated native frontend client."""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import socket
import struct
import sys

CONFIG = json.load(sys.stdin)


def exact(connection, count):
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise EOFError
        data.extend(chunk)
    return bytes(data)


def encoded(host, port):
    try:
        address = ipaddress.ip_address(host)
        value = bytes([1 if address.version == 4 else 4]) + address.packed
    except ValueError:
        name = host.encode("ascii")
        value = bytes([3, len(name)]) + name
    return value + struct.pack("!H", port)


def reply(connection):
    header = exact(connection, 4)
    if header[:3] != b"\x05\0\0":
        raise ValueError("native-request-refused")
    size = 4 if header[3] == 1 else 16 if header[3] == 4 else exact(connection, 1)[0]
    address = exact(connection, size)
    port = struct.unpack("!H", exact(connection, 2))[0]
    host = socket.inet_ntop(socket.AF_INET if size == 4 else socket.AF_INET6, address)
    return ("127.0.0.1" if host in ("0.0.0.0", "::") else host), port


def control():
    connection = socket.create_connection(("127.0.0.1", CONFIG["port"]), timeout=3)
    connection.sendall(b"\x05\x01\0")
    if exact(connection, 2) != b"\x05\0":
        raise ValueError("native-client-negotiation-refused")
    return connection


def tcp(host, port=9000, payload=b"public-probe", dns=False):
    connection = None
    try:
        connection = control()
        connection.sendall(b"\x05\x01\0" + encoded(host, port))
        reply(connection)
        connection.sendall((struct.pack("!H", len(payload)) if dns else b"") + payload)
        data = exact(connection, struct.unpack("!H", exact(connection, 2))[0] if dns else len(payload))
        return b"guarded-txt" in data if dns else data == payload
    except (OSError, EOFError, ValueError):
        return False
    finally:
        if connection:
            connection.close()


def udp(sock, relay, host, port=9000, payload=b"udp-probe", dns=False):
    sock.sendto(bytes(3) + encoded(host, port) + payload, relay)
    try:
        packet = sock.recv(65507)
        if packet[:3] != bytes(3):
            return False
        size = 4 if packet[3] == 1 else 16 if packet[3] == 4 else packet[4] + 1
        data = packet[4 + size + 2:]
        return b"guarded-txt" in data if dns else data == payload
    except socket.timeout:
        return False


if CONFIG.get("negative_auth"):
    result = {"wrong_auth_refused": not tcp("192.0.2.80")}
else:
    result = {}
    public = ("192.0.2.80", "2001:db8::80", "::ffff:192.0.2.80", "mixed4.test", "fresh4.test", "mixed6.test", "fresh6.test", "mapped.test")
    denied = ("127.0.0.2", "::1", "::ffff:127.0.0.2", "private4.test", "private6.test")
    for index, host in enumerate(public):
        result["tcp-public-" + str(index)] = tcp(host)
    for index, host in enumerate(denied):
        result["tcp-denied-" + str(index)] = not tcp(host)
    association = control()
    association.sendall(b"\x05\x03\0\x01" + bytes(6))
    relay = reply(association)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    # Names change in one association, with denied targets between successes.
    sequence = [("mixed4.test", True), ("private4.test", False), ("fresh4.test", True),
                ("mixed6.test", True), ("private6.test", False), ("fresh6.test", True),
                ("mapped.test", True), ("::ffff:127.0.0.2", False), ("::ffff:192.0.2.80", True)]
    for index, (host, expected) in enumerate(sequence):
        result["udp-sequence-" + str(index)] = udp(sock, relay, host, payload=("packet-" + str(index)).encode()) is expected
    query = b"\x23\x01" + struct.pack("!HHHHH", 0x0100, 1, 0, 0, 0) + b"\x03txt\x04test\0" + struct.pack("!HH", 16, 1)
    result["dns-tcp-txt"] = tcp("192.0.2.53", 53, query, True)
    result["dns-udp-txt"] = udp(sock, relay, "192.0.2.53", 53, query, True)
    result["dns-private-tcp"] = not tcp("127.0.0.2", 53, query, True)
    result["dns-private-udp"] = not udp(sock, relay, "127.0.0.2", 53, query, True)
    result["tcp-public-recovery"] = tcp("192.0.2.80")
    result["udp-public-recovery"] = udp(sock, relay, "fresh4.test", payload=b"recovery")
    association.close()
    sock.close()
Path(CONFIG["result"]).write_text(json.dumps(result))
raise SystemExit(0 if all(result.values()) else 1)
