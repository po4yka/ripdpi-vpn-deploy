#!/usr/bin/env python3
"""Authenticated loopback Alertmanager webhook to bounded Telegram delivery."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Callable
from urllib import error, parse, request

MAX_PAYLOAD_BYTES = 65536
MAX_RESPONSE_BYTES = 4096
MAX_ALERTS = 5
REQUEST_TIMEOUT_SECONDS = 5
RETRY_ATTEMPTS = 2
MAX_RETRY_AFTER_SECONDS = 5
MAX_MESSAGE_CHARS = 4096
TOKEN = re.compile(r"[0-9]{6,16}:[A-Za-z0-9_-]{20,128}\Z")
CHAT = re.compile(r"-?[0-9]{1,20}\Z")
SOURCE_ID = re.compile(r"[a-f0-9]{40,64}\Z")
FINGERPRINT = re.compile(r"[a-f0-9]{16,64}\Z")
ALIAS = re.compile(r"[A-Za-z0-9_.:/ -]{1,160}\Z")


class Refusal(ValueError):
    """The authenticated request does not satisfy the bounded contract."""


class DeliveryFailure(RuntimeError):
    """Telegram delivery failed with a categorical, non-secret reason."""


def _bounded_string(
    value: object,
    *,
    pattern: re.Pattern[str] | None = None,
    maximum: int = 160,
) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise Refusal("payload-contract")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise Refusal("payload-contract")
    return value


def _bounded_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > 32:
        raise Refusal("payload-contract")
    for key, item in value.items():
        _bounded_string(key, pattern=ALIAS)
        _bounded_string(item)
    return value


def parse_payload(raw: bytes, maximum: int = MAX_PAYLOAD_BYTES) -> dict[str, object]:
    if not raw or len(raw) > maximum:
        raise Refusal("payload-size")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal("payload-json") from exc
    required = {
        "version",
        "groupKey",
        "truncatedAlerts",
        "status",
        "receiver",
        "groupLabels",
        "commonLabels",
        "commonAnnotations",
        "externalURL",
        "alerts",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise Refusal("payload-contract")
    if value["version"] != "4" or value["status"] not in {"firing", "resolved"}:
        raise Refusal("payload-contract")
    if value["receiver"] not in {"telegram-primary", "telegram-critical"}:
        raise Refusal("payload-contract")
    if (
        not isinstance(value["truncatedAlerts"], int)
        or not 0 <= value["truncatedAlerts"] <= 10000
    ):
        raise Refusal("payload-contract")
    if (
        not isinstance(value["alerts"], list)
        or not 1 <= len(value["alerts"]) <= MAX_ALERTS
    ):
        raise Refusal("payload-contract")
    for field in ("groupLabels", "commonLabels", "commonAnnotations"):
        _bounded_mapping(value[field])
    _bounded_string(value["groupKey"], maximum=2048)
    if not isinstance(value["externalURL"], str) or len(value["externalURL"]) > 256:
        raise Refusal("payload-contract")
    common_labels = value["commonLabels"]
    common_annotations = value["commonAnnotations"]
    _bounded_string(common_labels.get("alertname"))
    _bounded_string(common_annotations.get("source_generation"), pattern=SOURCE_ID)
    for alert in value["alerts"]:
        if not isinstance(alert, dict) or set(alert) != {
            "status",
            "labels",
            "annotations",
            "startsAt",
            "endsAt",
            "generatorURL",
            "fingerprint",
        }:
            raise Refusal("payload-contract")
        if alert["status"] not in {"firing", "resolved"}:
            raise Refusal("payload-contract")
        _bounded_mapping(alert["labels"])
        _bounded_mapping(alert["annotations"])
        for key in ("environment", "node", "component"):
            _bounded_string(alert["labels"].get(key), pattern=ALIAS)
        for key in ("summary", "evidence_class", "runbook"):
            _bounded_string(alert["annotations"].get(key))
        _bounded_string(alert["startsAt"])
        _bounded_string(alert["endsAt"])
        if (
            not isinstance(alert["generatorURL"], str)
            or len(alert["generatorURL"]) > 256
        ):
            raise Refusal("payload-contract")
        _bounded_string(alert["fingerprint"], pattern=FINGERPRINT)
    return value


def _escaped(value: object) -> str:
    return html.escape(str(value), quote=False)


def _line(alert: dict[str, object]) -> str:
    labels = alert["labels"]
    annotations = alert["annotations"]
    prefix = "-" if alert["status"] == "firing" else "- recovered"
    timestamp = (
        "started=" + _escaped(alert["startsAt"])
        if alert["status"] == "firing"
        else "recovered=" + _escaped(alert["endsAt"])
    )
    return (
        f"{prefix} {_escaped(labels['environment'])}/{_escaped(labels['node'])}/"
        f"{_escaped(labels['component'])}: {_escaped(annotations['summary'])} "
        f"[{_escaped(annotations['evidence_class'])}] "
        f"{_escaped(annotations['runbook'])} {timestamp}"
    )


def render_message(payload: dict[str, object], *, max_alerts: int = MAX_ALERTS) -> str:
    if max_alerts != MAX_ALERTS:
        raise Refusal("message-bound")
    status = payload["status"]
    header = (
        ("FIRING" if status == "firing" else "RESOLVED")
        + ": "
        + _escaped(payload["commonLabels"]["alertname"])
        + " source="
        + _escaped(payload["commonAnnotations"]["source_generation"])
    )
    lines: list[str] = []
    omitted = int(payload["truncatedAlerts"])
    for alert in payload["alerts"]:
        candidate = _line(alert)
        footer = f"... omitted {omitted} alerts" if omitted else ""
        projected = "\n".join([header, *lines, candidate, footer]).rstrip()
        if len(projected) > MAX_MESSAGE_CHARS:
            omitted += 1
            continue
        lines.append(candidate)
    footer = f"... omitted {omitted} alerts" if omitted else ""
    message = "\n".join([header, *lines, footer]).rstrip()
    if not lines or len(message) > MAX_MESSAGE_CHARS:
        raise Refusal("message-size")
    return message


def _retry_after(headers: object) -> int:
    raw = headers.get("Retry-After") if headers is not None else None
    if not isinstance(raw, str) or re.fullmatch(r"[0-9]{1,4}", raw) is None:
        return 1
    return min(int(raw), MAX_RETRY_AFTER_SECONDS)


def deliver(
    *,
    api_url: str,
    token: str,
    chat_id: str,
    topic_id: int,
    message: str,
    opener: Callable[..., object] = request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    validate_delivery_contract(api_url, token, chat_id, topic_id)
    body: dict[str, object] = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if topic_id:
        body["message_thread_id"] = topic_id
    outbound = request.Request(
        api_url + "/bot" + parse.quote(token, safe=":_-") + "/sendMessage",
        data=json.dumps(body, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(RETRY_ATTEMPTS):
        delay = 1
        retryable = False
        try:
            with opener(outbound, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if response.status != 200 or len(raw) > MAX_RESPONSE_BYTES:
                    raise DeliveryFailure("upstream-response")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict) or parsed.get("ok") is not True:
                    raise DeliveryFailure("upstream-response")
                return
        except error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            delay = _retry_after(exc.headers) if exc.code == 429 else 1
        except (TimeoutError, OSError):
            retryable = True
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeliveryFailure("upstream-response") from exc
        if not retryable or attempt + 1 == RETRY_ATTEMPTS:
            raise DeliveryFailure("upstream-failure")
        sleeper(delay)
    raise DeliveryFailure("upstream-failure")


def _credential(name: str) -> str:
    directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if not directory or "/" in name or name in {".", ".."}:
        raise Refusal("credential-path")
    path = Path(directory) / name
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or len(raw) > 256 or b"\n" in raw or b"\r" in raw:
        raise Refusal("credential-content")
    value = raw.decode("ascii")
    if value.strip() != value:
        raise Refusal("credential-content")
    return value


def validate_delivery_contract(
    api_url: str, token: str, chat_id: str, topic_id: int
) -> None:
    if api_url != "https://api.telegram.org" or TOKEN.fullmatch(token) is None:
        raise Refusal("delivery-contract")
    if CHAT.fullmatch(chat_id) is None or not 0 <= topic_id <= 2**31 - 1:
        raise Refusal("delivery-contract")


def handler(config: dict[str, object]):  # type: ignore[no-untyped-def]
    class RelayHandler(BaseHTTPRequestHandler):
        server_version = "observability-telegram-relay"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            expected = "Bearer " + str(config["auth_token"])
            return hmac.compare_digest(supplied, expected)

        def _reply(self, status: int, category: str) -> None:
            body = json.dumps({"status": category}, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/-/ready" or not self._authorized():
                self._reply(404 if self.path != "/-/ready" else 401, "refused")
                return
            self._reply(200, "ready")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/alert":
                self._reply(404, "refused")
                return
            if not self._authorized():
                self._reply(401, "refused")
                return
            if self.headers.get("Content-Type") != "application/json":
                self._reply(400, "refused")
                return
            raw_length = self.headers.get("Content-Length", "")
            if re.fullmatch(r"[0-9]{1,6}", raw_length) is None:
                self._reply(400, "refused")
                return
            length = int(raw_length)
            if not 0 < length <= MAX_PAYLOAD_BYTES:
                self._reply(413, "refused")
                return
            try:
                payload = parse_payload(self.rfile.read(length))
                message = render_message(payload)
                deliver(
                    api_url=str(config["api_url"]),
                    token=str(config["bot_token"]),
                    chat_id=str(config["chat_id"]),
                    topic_id=int(config["topic_id"]),
                    message=message,
                )
            except (OSError, Refusal):
                self._reply(400, "refused")
                return
            except DeliveryFailure:
                self._reply(502, "delivery-failed")
                return
            self._reply(200, "delivered")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return RelayHandler


class RelayServer(ThreadingHTTPServer):
    """Serve a bounded number of authenticated loopback requests."""

    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address: tuple[str, int], request_handler) -> None:  # type: ignore[no-untyped-def]
        self._workers = threading.BoundedSemaphore(2)
        super().__init__(address, request_handler)

    def process_request(self, request_socket, client_address) -> None:  # type: ignore[no-untyped-def]
        self._workers.acquire()
        try:
            super().process_request(request_socket, client_address)
        except BaseException:
            self._workers.release()
            raise

    def process_request_thread(self, request_socket, client_address) -> None:  # type: ignore[no-untyped-def]
        try:
            super().process_request_thread(request_socket, client_address)
        finally:
            self._workers.release()

    def handle_error(self, _request, _client_address) -> None:  # type: ignore[no-untyped-def]
        print("telegram-relay: request-failed", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("serve", nargs="?")
    parser.add_argument("--listen", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--topic-id", type=int, required=True)
    parser.add_argument("--bot-credential", required=True)
    parser.add_argument("--auth-credential", required=True)
    args = parser.parse_args()
    try:
        if args.serve != "serve" or args.listen != "127.0.0.1:19095":
            raise Refusal("listen-contract")
        config = {
            "api_url": args.api_url,
            "chat_id": args.chat_id,
            "topic_id": args.topic_id,
            "bot_token": _credential(args.bot_credential),
            "auth_token": _credential(args.auth_credential),
        }
        validate_delivery_contract(
            str(config["api_url"]),
            str(config["bot_token"]),
            str(config["chat_id"]),
            int(config["topic_id"]),
        )
        if not re.fullmatch(r"[a-f0-9]{64}", config["auth_token"]):
            raise Refusal("auth-contract")
        server = RelayServer(("127.0.0.1", 19095), handler(config))
        server.serve_forever()
    except (OSError, Refusal, UnicodeError):
        print("telegram-relay: startup-refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
