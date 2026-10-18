"""Generated recipient targets fetch real payloads through the delivery handler."""
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

import pytest
import test_subscription_retention
from vpnd.commands.share import build_sub_urls

service = test_subscription_retention.service


@contextmanager
def delivery_server(service):
    server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def prepare_subscription(service):
    token = "SyntheticDeliveryBoundary00000001"
    digest = service._hash(token)
    body = b'{"outbounds":[]}'
    (service.SUBSCRIPTION_DIR / "sub" / digest).write_bytes(body)
    meta = service.SUBSCRIPTION_DIR / "sub" / (digest + ".meta")
    meta.write_text("{}")
    return token, digest, body, meta


def test_generated_import_and_qr_targets_serve_exact_payload_and_retain_authority(service):
    token, digest, body, meta = prepare_subscription(service)
    with delivery_server(service) as server:
        urls = build_sub_urls("http://127.0.0.1:" + str(server.server_port), token)
        imported = parse_qs(urlsplit(urls.singbox_deeplink).query)["url"][0]
        for target in (urls.subscription_url, imported, urls.qr_singbox):
            with urlopen(target, timeout=3) as response:
                assert response.status == 200
                assert response.headers.get_content_type() == "application/json"
                assert response.headers["Cache-Control"] == "no-store"
                assert response.headers["Referrer-Policy"] == "no-referrer"
                assert response.read() == body
        meta.write_text(json.dumps({"expires": 0}))
        with pytest.raises(HTTPError) as expired:
            urlopen(imported, timeout=3)
        assert expired.value.code == 410
        meta.write_text("{}")
        service.REVOKED_FILE.write_text(digest + "\n")
        with pytest.raises(HTTPError) as revoked:
            urlopen(urls.qr_singbox, timeout=3)
        assert revoked.value.code == 410
