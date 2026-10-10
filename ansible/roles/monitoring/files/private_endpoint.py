#!/usr/bin/env python3
"""Normalize one literal private exporter endpoint before any host mutation."""

from __future__ import annotations

import ipaddress
import json
import re
import sys


def validate(value):
    if not isinstance(value, dict) or set(value) != {
        "endpoint",
        "approved_tailnet_addresses",
        "local_addresses",
    }:
        raise ValueError("invalid endpoint request")
    endpoint = value["endpoint"]
    if not isinstance(endpoint, str) or len(endpoint) > 128:
        raise ValueError("invalid endpoint")
    match = re.fullmatch(r"(?:\[([0-9a-fA-F:]+)\]|([0-9.]+)):([0-9]{1,5})", endpoint)
    if not match:
        raise ValueError("literal address and port required")
    address = ipaddress.ip_address(match[1] or match[2])
    port = int(match[3])
    if not 1 <= port <= 65535 or address.is_unspecified:
        raise ValueError("invalid listener")
    lists = []
    for key in ("approved_tailnet_addresses", "local_addresses"):
        entries = value[key]
        if (
            not isinstance(entries, list)
            or len(entries) > 256
            or any(not isinstance(item, str) or len(item) > 64 for item in entries)
        ):
            raise ValueError("invalid address approval")
        lists.append({ipaddress.ip_address(item) for item in entries})
    tailnet = (
        address in ipaddress.ip_network("100.64.0.0/10")
        if address.version == 4
        else address in ipaddress.ip_network("fd7a:115c:a1e0::/48")
    )
    if not address.is_loopback and not (
        tailnet and address in lists[0] and address in lists[1]
    ):
        raise ValueError("listener is not approved private local authority")
    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return {"endpoint": f"{host}:{port}", "address": address.compressed, "port": port}


def main():
    try:
        value = validate(json.loads(sys.stdin.read(32769)))
    except (ValueError, TypeError):
        print("private exporter endpoint rejected", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
