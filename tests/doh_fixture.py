"""A loopback DNS-over-HTTPS JSON resolver for tests of scripts/doh-lookup.py and its callers."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit

TYPES = {"A": 1, "TXT": 16}


@contextmanager
def doh_server(records: dict, queries: list | None = None, redirect_to: str | None = None):
    """Serve `records` ({(type, name): [data, ...]}); any other name does not exist. Yields the DOH_URL.

    With `redirect_to`, every request is answered with a redirect to that URL instead.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            key = (query["type"][0], query["name"][0])
            if queries is not None:
                queries.append(key)
            if redirect_to is not None:
                self.send_response(302)
                self.send_header("Location", redirect_to)
                self.end_headers()
                return
            data = records.get(key, [])
            body = json.dumps(
                {"Status": 0 if data else 3, "Answer": [{"type": TYPES[key[0]], "data": item} for item in data]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/dns-query"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
