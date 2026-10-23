#!/usr/bin/env python3
"""Serve bounded canonical payloads behind an operator-owned HTTPS origin."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import socket
from socketserver import ThreadingMixIn
import threading
from urllib.parse import parse_qs, urlsplit

from payload_probe_content import MAX_BYTES, payload


class Server(ThreadingMixIn, HTTPServer):
    """Bound active connections while allowing a control beside a body transfer."""

    max_workers = 4
    request_queue_size = 4

    def __init__(self, *args, **kwargs):
        self.workers = threading.BoundedSemaphore(self.max_workers)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.workers.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.workers.release()


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

    def respond(self, upload=False, head=False):
        self.close_connection = True
        try:
            url = urlsplit(self.path)
            query = parse_qs(url.query, strict_parsing=True)
            if url.path != "/__throttle_probe" or set(query) != {"bytes"} or len(query["bytes"]) != 1:
                raise ValueError
            number = query["bytes"][0]
            if not number.isascii() or not number.isdigit() or len(number) > 7:
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
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if not head:
                self.wfile.write(payload(size))
        except (ValueError, OSError, socket.timeout):
            try:
                self.send_error(400)
            except OSError:
                # The deadline or peer can close the socket before the error reply.
                pass

    def do_GET(self):
        self.respond()

    def do_HEAD(self):
        self.respond(head=True)

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
    # An existing HTTPS reverse proxy owns external TLS. Four workers and each
    # connection's total deadline also bound work at this optional local helper.
    with Server((args.host, args.port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
