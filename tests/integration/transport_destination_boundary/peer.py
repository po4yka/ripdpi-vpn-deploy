"""Owned namespace-only public/private receivers and authoritative DNS fixture."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import struct
import sys
import threading

ROOT = Path(sys.argv[1])
LOCK = threading.Lock()
COUNTS = {name: 0 for name in ("public_tcp", "public_udp", "private_tcp", "private_udp",
                             "queries", "dns_tcp_txt", "dns_udp_txt", "private_dns")}


def record(key):
    with LOCK:
        COUNTS[key] += 1
        candidate = ROOT / "counts.new"
        candidate.write_text(json.dumps(COUNTS))
        candidate.replace(ROOT / "counts.json")


def exact(connection, count):
    data = bytearray()
    while len(data) < count:
        part = connection.recv(count - len(data))
        if not part:
            raise EOFError
        data.extend(part)
    return bytes(data)


def echo(address, family, private, udp):
    connection = socket.socket(family, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
    connection.bind((address, 9000))
    if not udp:
        connection.listen()

    def serve_tcp(peer):
        with peer:
            try:
                while True:
                    data = peer.recv(4096)
                    if not data:
                        return
                    peer.sendall(data)
            except OSError:
                return

    while True:
        if udp:
            data, peer = connection.recvfrom(4096)
            record("private_udp" if private else "public_udp")
            connection.sendto(data, peer)
        else:
            peer, _ = connection.accept()
            record("private_tcp" if private else "public_tcp")
            threading.Thread(target=serve_tcp, args=(peer,), daemon=True).start()


def dns_response(request, transport):
    offset, labels = 12, []
    while request[offset]:
        size = request[offset]
        if size > 63 or offset + size + 1 >= len(request):
            raise ValueError
        labels.append(request[offset + 1:offset + size + 1].decode("ascii"))
        offset += size + 1
    offset += 1
    qtype, qclass = struct.unpack("!HH", request[offset:offset + 4])
    end = offset + 4
    name = ".".join(labels)
    record("queries")
    records = []
    if qtype == 1:
        answers = {"public.test": ["192.0.2.80"], "fresh4.test": ["192.0.2.81"],
                   "mixed4.test": ["127.0.0.2", "192.0.2.80"], "private4.test": ["127.0.0.2"]}
        records = [socket.inet_pton(socket.AF_INET, value) for value in answers.get(name, [])]
    elif qtype == 28:
        answers = {"fresh6.test": ["2001:db8::80"], "mixed6.test": ["::1", "2001:db8::80"],
                   "private6.test": ["::1"], "mapped.test": ["::ffff:127.0.0.2", "::ffff:192.0.2.80"]}
        records = [socket.inet_pton(socket.AF_INET6, value) for value in answers.get(name, [])]
    elif qtype == 16 and name == "txt.test":
        record("dns_" + transport + "_txt")
        text = b"guarded-txt"
        records = [bytes([len(text)]) + text]
    response = request[:2] + struct.pack("!HHHHH", 0x8180, 1, len(records), 0, 0) + request[12:end]
    for payload in records:
        response += b"\xc0\x0c" + struct.pack("!HHIH", qtype, qclass, 0, len(payload)) + payload
    return response


def dns(udp, private=False):
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
    connection.bind(("127.0.0.2" if private else "192.0.2.53", 53))
    if not udp:
        connection.listen()
    while True:
        try:
            if udp:
                request, peer = connection.recvfrom(4096)
                if private:
                    record("private_dns")
                connection.sendto(dns_response(request, "udp"), peer)
            else:
                peer, _ = connection.accept()
                with peer:
                    if private:
                        record("private_dns")
                    peer.settimeout(3)
                    request = exact(peer, struct.unpack("!H", exact(peer, 2))[0])
                    response = dns_response(request, "tcp")
                    peer.sendall(struct.pack("!H", len(response)) + response)
        except (OSError, ValueError, IndexError, EOFError, struct.error):
            continue


for value, family, private in (("192.0.2.80", socket.AF_INET, False), ("192.0.2.81", socket.AF_INET, False),
                               ("2001:db8::80", socket.AF_INET6, False), ("127.0.0.2", socket.AF_INET, True),
                               ("::1", socket.AF_INET6, True)):
    for udp in (False, True):
        threading.Thread(target=echo, args=(value, family, private, udp), daemon=True).start()
for udp in (False, True):
    for private in (False, True):
        threading.Thread(target=dns, args=(udp, private), daemon=True).start()
record("queries")
threading.Event().wait()
