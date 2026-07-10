#!/usr/bin/env python3
"""Fail closed when provider-edge and runtime public listener contracts differ."""
from __future__ import annotations

import json
import sys
from typing import Any


def _key(item: dict[str, Any], *, runtime: bool) -> tuple[str, str, int | str]:
    name = str(item.get("role" if runtime else "name", ""))
    protocol = str(item.get("protocol", "")).lower()
    if protocol not in {"tcp", "udp"} or not name:
        raise ValueError("listener requires a non-empty name/role and tcp or udp protocol")
    port_range = item.get("range" if runtime else "port_range")
    port = item.get("port")
    if (port is None) == (port_range is None):
        raise ValueError(f"{name}: specify exactly one of port or port_range")
    if port is not None:
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"{name}: invalid port {port!r}")
        return name, protocol, port
    if not isinstance(port_range, str) or "-" not in port_range:
        raise ValueError(f"{name}: invalid port range {port_range!r}")
    start, end = port_range.split("-", 1)
    if not (start.isdigit() and end.isdigit() and 1 <= int(start) <= int(end) <= 65535):
        raise ValueError(f"{name}: invalid port range {port_range!r}")
    return name, protocol, port_range


def check(payload: dict[str, Any]) -> list[str]:
    expected = {_key(item, runtime=False) for item in payload["expected"]}
    actual = {
        _key(item, runtime=True)
        for item in payload["actual"]
        if item.get("enabled", False)
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    findings = []
    if missing:
        findings.append(f"provider contract lacks runtime listener(s): {missing}")
    if unexpected:
        findings.append(f"runtime manifest lacks provider contract listener(s): {unexpected}")
    return findings


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        findings = check(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"listener contract: invalid input: {exc}", file=sys.stderr)
        return 2
    if not findings:
        print("listener contract: OK")
        return 0
    print("listener contract mismatch:", file=sys.stderr)
    for finding in findings:
        print(f"  - {finding}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
