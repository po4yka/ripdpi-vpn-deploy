#!/usr/bin/env python3
"""Send bounded watchdog notifications without credential-bearing argv or env."""

from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import signal
import stat
import sys
from urllib.parse import quote, urlencode, urlsplit

MAX_BYTES = 16384


class DeliveryError(Exception):
    """A categorical error that never includes credentials or destinations."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DeliveryError("invalid-credential")
        result[key] = value
    return result


def load_credentials(directory: Path) -> dict:
    descriptor = os.open(
        directory / "notifications.json",
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
    )
    try:
        metadata = os.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid not in {0, os.geteuid()}
            or mode not in {0o400, 0o600}
            and not (mode == 0o440 and metadata.st_uid == metadata.st_gid == 0)
        ):
            raise DeliveryError("invalid-credential")
        raw = os.read(descriptor, MAX_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_BYTES:
        raise DeliveryError("invalid-credential")
    document = json.loads(raw, object_pairs_hook=_pairs)
    if not isinstance(document, dict) or document.get("provider") not in {
        "ntfy",
        "pushover",
    }:
        raise DeliveryError("invalid-credential")
    return document


def deliver(config: dict, title: str, tags: str, body: str, timeout: float) -> None:
    if any("\r" in value or "\n" in value for value in (title, tags)):
        raise DeliveryError("invalid-message")
    headers = {}
    if config["provider"] == "ntfy":
        origin = urlsplit(config["url"])
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.username is not None
            or origin.password is not None
            or origin.query
            or origin.fragment
            or origin.scheme == "http"
            and origin.hostname not in {"127.0.0.1", "::1", "localhost"}
        ):
            raise DeliveryError("invalid-destination")
        topic = config["topic"]
        token = config.get("token", "")
        if not isinstance(topic, str) or not topic or not isinstance(token, str):
            raise DeliveryError("invalid-credential")
        if "\r" in token or "\n" in token:
            raise DeliveryError("invalid-credential")
        path = origin.path.rstrip("/") + "/" + quote(topic, safe="")
        headers = {"Title": title, "Priority": "high", "Tags": tags}
        if token:
            headers["Authorization"] = "Bearer " + token
        payload = body.encode("utf-8")
    else:
        origin = urlsplit("https://api.pushover.net/1/messages.json")
        path = origin.path
        if any(
            not isinstance(config.get(key), str) or not config[key]
            for key in ("token", "user")
        ):
            raise DeliveryError("invalid-credential")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = urlencode(
            {
                "token": config["token"],
                "user": config["user"],
                "title": title,
                "message": body,
                "priority": 1,
            }
        ).encode("ascii")
    connection_type = (
        http.client.HTTPSConnection
        if origin.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_type(origin.hostname, origin.port, timeout=timeout)
    try:
        connection.request("POST", path, body=payload, headers=headers)
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise DeliveryError("delivery-refused")
    finally:
        connection.close()


def _expired(_number, _frame):
    raise DeliveryError("timeout")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--tags", default="")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)
    try:
        if not 0 < args.timeout <= 30:
            raise DeliveryError("invalid-timeout")
        directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
        if not directory or not Path(directory).is_absolute():
            raise DeliveryError("credential-unavailable")
        body = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise DeliveryError("invalid-message")
        config = load_credentials(Path(directory))
        signal.signal(signal.SIGALRM, _expired)
        signal.setitimer(signal.ITIMER_REAL, args.timeout)
        try:
            deliver(config, args.title, args.tags, body.decode("utf-8"), args.timeout)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    except (
        DeliveryError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        http.client.HTTPException,
    ):
        print("watchdog notification failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
