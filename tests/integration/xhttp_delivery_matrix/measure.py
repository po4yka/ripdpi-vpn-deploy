"""Measure real bidirectional echo through one owned native SOCKS endpoint."""
from __future__ import annotations
import json
import socket
import statistics
import sys
import time


def exact(connection, count):
    result = bytearray()
    while len(result) < count:
        data = connection.recv(count - len(result))
        if not data:
            raise EOFError('owned-echo-truncated')
        result.extend(data)
    return bytes(result)


def connection(port):
    sock = socket.create_connection(('127.0.0.1', port), timeout=10)
    sock.settimeout(10)
    try:
        sock.sendall(b'\x05\x01\x00')
        assert exact(sock, 2) == b'\x05\x00'
        sock.sendall(b'\x05\x01\x00\x01' + socket.inet_aton('192.0.2.80') + (9000).to_bytes(2, 'big'))
        header = exact(sock, 4)
        assert header[:2] == b'\x05\x00'
        assert header[3] in (1, 4)
        exact(sock, (4 if header[3] == 1 else 16) + 2)
        return sock
    except BaseException:
        sock.close()
        raise


def measure(port):
    latencies = []
    with connection(port) as sock:
        for _ in range(5):
            started = time.monotonic()
            sock.sendall(b'owned-latency')
            assert exact(sock, 13) == b'owned-latency'
            latencies.append((time.monotonic() - started) * 1000)
        payload = bytes(range(256)) * 64
        started = time.monotonic()
        for _ in range(64):
            sock.sendall(payload)
            assert exact(sock, len(payload)) == payload
        duration = time.monotonic() - started
    return dict(bytes_each_direction=1048576, duration_ms=duration * 1000,
                mib_per_second=1 / duration, latency_ms=statistics.median(latencies))


if __name__ == '__main__':
    print(json.dumps(measure(int(sys.argv[1]))))
