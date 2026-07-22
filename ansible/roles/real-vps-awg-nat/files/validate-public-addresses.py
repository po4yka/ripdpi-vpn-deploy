#!/usr/bin/env python3
"""Validate the echo lane's public-unicast address contract with the stdlib."""

from __future__ import annotations

import base64
import ipaddress
import json
import sys


def fail(message: str) -> int:
    print(f"public address contract: {message}", file=sys.stderr)
    return 2


def main() -> int:
    if len(sys.argv) != 2:
        return fail("expected one base64-encoded JSON payload")
    try:
        raw = base64.b64decode(sys.argv[1], validate=True)
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return fail("invalid payload")
    if not isinstance(payload, dict):
        return fail("payload must be an object")

    expected = {"required_ipv4", "optional_ipv6"}
    if set(payload) != expected:
        return fail("payload fields do not match the contract")
    for field, version, required in (
        ("required_ipv4", 4, True),
        ("optional_ipv6", 6, False),
    ):
        values = payload[field]
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            return fail(f"{field} must be a string list")
        if required and (not values or any(not value for value in values)):
            return fail(f"{field} must not contain empty values")
        for value in values:
            if not value and not required:
                continue
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                return fail(f"{field} contains an invalid address")
            if address.version != version:
                return fail(f"{field} contains the wrong address family")
            if not address.is_global or address.is_multicast:
                return fail(f"{field} must contain only public unicast addresses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
