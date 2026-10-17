"""Measure verified bytes on one actual authenticated SOCKS/XHTTP session."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from transport_socks import upstream_request, upstream_reply, NeedMore


def exact(connection, length):
    data = bytearray()
    while len(data) < length:
        part = connection.recv(length - len(data))
        if not part:
            raise EOFError("authenticated-transfer-truncated")
        data.extend(part)
    return bytes(data)


def main():
    port = int(sys.argv[1])
    assert 1 <= port <= 65535
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        connection.sendall(b"\x05\x01\x00")
        assert exact(connection, 2) == b"\x05\x00"
        connection.sendall(upstream_request(1, "192.0.2.80", 9000))
        reply = bytearray()
        while True:
            reply.extend(exact(connection, 1))
            try:
                upstream_reply(reply)
                break
            except NeedMore:
                assert len(reply) <= 512
        block = bytes(range(256)) * 128
        for _ in range(128):
            connection.sendall(block)
            assert exact(connection, len(block)) == block, "authenticated-transfer-corrupt"
            assert time.monotonic() - started < 30, "authenticated-transfer-budget-exhausted"
    elapsed = time.monotonic() - started
    print(json.dumps({"upload_bytes": 4194304, "download_bytes": 4194304,
                      "seconds": round(elapsed, 6), "bytes_per_second": round(4194304 / elapsed)}))


if __name__ == "__main__":
    main()
