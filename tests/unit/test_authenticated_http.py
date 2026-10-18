"""Real local HTTP requests exercise each authenticated client's redirect boundary."""

import runpy
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

import pytest
from authenticated_http import https_origin, open_no_redirect

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def server(records, *, status=200, destination=None):
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            records.append((self.path, self.headers.get("Authorization")))
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(status)
            if destination is not None:
                self.send_header("Location", destination)
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = do_POST = handle_request

        def log_message(self, *_args):
            pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("client", ["vultr", "github", "notification"])
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("cross_origin", [False, True])
def test_clients_do_not_send_bearer_to_any_redirect(client, status, cross_origin, monkeypatch):
    source_requests, destination_requests = [], []
    with server(destination_requests) as destination:
        target = destination + "/destination" if cross_origin else "/destination"
        with server(source_requests, status=status, destination=target) as origin:
            if client == "vultr":
                module = runpy.run_path(str(ROOT / "scripts/check-vultr-control-plane.py"))
                monkeypatch.setenv("TF_VAR_vultr_api_key", "synthetic-bearer")
                monkeypatch.setitem(module["main"].__globals__, "API_URL", origin + "/start")
                assert module["main"]() == 69
            elif client == "github":
                module = runpy.run_path(str(ROOT / "scripts/check-amneziawg-arm64-upstream.py"))
                monkeypatch.setenv("GH_TOKEN", "synthetic-bearer")
                monkeypatch.setitem(module["_github_get"].__globals__, "API_ROOT", origin)
                with pytest.raises(error.HTTPError) as failure:
                    module["_github_get"]("/start")
                assert failure.value.code == status
                failure.value.close()
            else:
                module = runpy.run_path(str(ROOT / "scripts/monitor-protocol-liveness.py"))
                monkeypatch.setenv("NTFY_URL", "https://notification.example")
                monkeypatch.setenv("NTFY_TOPIC", "synthetic-topic")
                monkeypatch.setenv("NTFY_TOKEN", "synthetic-bearer")

                def fixture_transport(outbound, *, timeout):
                    assert outbound.full_url.startswith("https://notification.example/")
                    local = request.Request(origin + "/start", data=outbound.data,
                                            headers=dict(outbound.header_items()), method=outbound.method)
                    return open_no_redirect(local, timeout=timeout)

                monkeypatch.setitem(module["send_notification"].__globals__, "open_no_redirect", fixture_transport)
                assert module["send_notification"]("alert", {"decision": "unknown"}) == "failed"
    assert source_requests == [("/start", "Bearer synthetic-bearer")]
    assert destination_requests == []


@pytest.mark.parametrize("origin", [
    "http://notification.example", "https://{}@notification.example".format(":".join(("user", "password"))),
    "https://notification.example/path", "https://notification.example?query=1",
    "https://notification.example#fragment", "https://notification.example?",
    "https://notification.example#", "https://notification.example:0",
    "https://notification.example:65536", "https://bad_host", "https://bad..host",
    "https://notification.example:", "https://[::1]unexpected",
    "https://notification.example\\@elsewhere.example", "https://notification.example\n",
])
def test_notification_origin_refuses_before_transport(origin, monkeypatch):
    module = runpy.run_path(str(ROOT / "scripts/monitor-protocol-liveness.py"))
    monkeypatch.setenv("NTFY_URL", origin)
    monkeypatch.setenv("NTFY_TOPIC", "synthetic-topic")
    monkeypatch.setenv("NTFY_TOKEN", "synthetic-bearer")

    def unexpected(*_args, **_kwargs):
        pytest.fail("invalid origin reached HTTP transport")

    monkeypatch.setitem(module["send_notification"].__globals__, "open_no_redirect", unexpected)
    assert module["send_notification"]("alert", {"decision": "unknown"}) == "failed"


@pytest.mark.parametrize("origin", ["https://notification.example", "https://127.0.0.1:9444/", "https://[::1]:9444"])
def test_https_origins_preserve_explicit_authority(origin):
    assert https_origin(origin) == origin.rstrip("/")
