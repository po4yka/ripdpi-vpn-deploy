#!/usr/bin/env python3
"""Serve bounded canonical payloads behind an operator-owned HTTPS origin."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import socket
import threading
from urllib.parse import parse_qs, urlsplit

from payload_probe_content import MAX_BYTES, payload


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.deadline = threading.Timer(10, self.expire)
        self.deadline.daemon = True
        self.deadline.start()

    def expire(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            # A closed client connection already satisfies the deadline shutdown.
            pass

    def finish(self):
        self.deadline.cancel()
        super().finish()

    def respond(self, upload=False):
        self.close_connection = True
        try:
            url = urlsplit(self.path)
            query = parse_qs(url.query, strict_parsing=True)
            if url.path != "/__throttle_probe" or set(query) != {"bytes"} or len(query["bytes"]) != 1:
                raise ValueError
            number = query["bytes"][0]
            if not number.isascii() or not number.isdigit() or len(number) > 5:
                raise ValueError
            size = int(number)
            if not 1 <= size <= MAX_BYTES or self.headers.get("Transfer-Encoding") is not None:
                raise ValueError
            lengths = self.headers.get_all("Content-Length", [])
            if upload:
                if lengths != [str(size)] or self.rfile.read(size) != payload(size):
                    raise ValueError
            elif lengths not in ([], ["0"]):
                raise ValueError
            data = payload(size)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
        except (ValueError, OSError, socket.timeout):
            try:
                self.send_error(400)
            except OSError:
                # The deadline or peer can close the socket before the error reply.
                pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond(upload=True)

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    # A single worker with a per-connection deadline bounds active work. An
    # existing HTTPS reverse proxy owns external TLS and concurrency admission.
    with HTTPServer((args.host, args.port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
