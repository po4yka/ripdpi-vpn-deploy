#!/usr/bin/env python3
"""Export aggregate Hysteria2 traffic for the node_exporter textfile.

The loopback Traffic Stats API answers per user; this process sums the
values and drops every user identifier before anything is written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

MAX_RESPONSE_BYTES = 1024 * 1024


class CollectionError(RuntimeError):
    """A redacted collector failure safe to report to journald."""


def _loopback(listen: str) -> str:
    host, _, port = listen.rpartition(":")
    if host != "127.0.0.1" or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise CollectionError("traffic API must listen on 127.0.0.1")
    return f"http://{listen}"


def fetch(base: str, path: str, secret: str, timeout: float) -> dict:
    request = urllib.request.Request(base + path, headers={"Authorization": secret})
    # No proxy: the request must stay on loopback whatever the environment says.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise CollectionError(type(exc).__name__) from None
    if len(payload) > MAX_RESPONSE_BYTES:
        raise CollectionError("oversized traffic API response")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, ValueError):
        raise CollectionError("malformed traffic API response") from None
    if not isinstance(document, dict):
        raise CollectionError("unexpected traffic API response")
    return document


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CollectionError("invalid traffic API value")
    return value


def aggregate(traffic: dict, online: dict) -> tuple[int, int, int]:
    """Return (transmit, receive, online connections) summed over all users."""
    transmit = receive = 0
    for counters in traffic.values():
        if not isinstance(counters, dict):
            raise CollectionError("invalid traffic API record")
        transmit += _count(counters.get("tx", 0))
        receive += _count(counters.get("rx", 0))
    connections = sum(_count(value) for value in online.values())
    return transmit, receive, connections


def render_metrics(transmit: int, receive: int, connections: int, collected_at: int) -> str:
    return "\n".join(
        [
            "# HELP vpn_hysteria_traffic_collection_success Whether the last Traffic Stats API query succeeded.",
            "# TYPE vpn_hysteria_traffic_collection_success gauge",
            "vpn_hysteria_traffic_collection_success 1",
            "# HELP vpn_hysteria_traffic_collected_timestamp_seconds Unix timestamp of the last Traffic Stats API query.",
            "# TYPE vpn_hysteria_traffic_collected_timestamp_seconds gauge",
            f"vpn_hysteria_traffic_collected_timestamp_seconds {collected_at}",
            "# HELP vpn_hysteria_transmit_bytes_total Bytes sent by all clients since the server started.",
            "# TYPE vpn_hysteria_transmit_bytes_total counter",
            f"vpn_hysteria_transmit_bytes_total {transmit}",
            "# HELP vpn_hysteria_receive_bytes_total Bytes received by all clients since the server started.",
            "# TYPE vpn_hysteria_receive_bytes_total counter",
            f"vpn_hysteria_receive_bytes_total {receive}",
            "# HELP vpn_hysteria_online_connections Connected client instances over all users.",
            "# TYPE vpn_hysteria_online_connections gauge",
            f"vpn_hysteria_online_connections {connections}",
            "",
        ]
    )


def render_failure(collected_at: int) -> str:
    return "\n".join(
        [
            "# HELP vpn_hysteria_traffic_collection_success Whether the last Traffic Stats API query succeeded.",
            "# TYPE vpn_hysteria_traffic_collection_success gauge",
            "vpn_hysteria_traffic_collection_success 0",
            "# HELP vpn_hysteria_traffic_collected_timestamp_seconds Unix timestamp of the last Traffic Stats API query attempt.",
            "# TYPE vpn_hysteria_traffic_collected_timestamp_seconds gauge",
            f"vpn_hysteria_traffic_collected_timestamp_seconds {collected_at}",
            "",
        ]
    )


def atomic_write(path: Path, content: str) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def read_secret(path: Path) -> str:
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        raise CollectionError("traffic API secret unavailable") from None
    if not secret:
        raise CollectionError("traffic API secret unavailable")
    return secret


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", required=True)
    parser.add_argument("--secret-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    collected_at = int(time.time())
    try:
        base = _loopback(args.listen)
        secret = read_secret(args.secret_file)
        totals = aggregate(
            fetch(base, "/traffic", secret, args.timeout),
            fetch(base, "/online", secret, args.timeout),
        )
        atomic_write(args.output, render_metrics(*totals, collected_at))
    except CollectionError as exc:
        try:
            atomic_write(args.output, render_failure(collected_at))
        except OSError as write_exc:
            print(
                f"hysteria-traffic-exporter: failure metric update failed ({type(write_exc).__name__})",
                file=sys.stderr,
            )
        print(f"hysteria-traffic-exporter: collection failed ({exc})", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"hysteria-traffic-exporter: output update failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
