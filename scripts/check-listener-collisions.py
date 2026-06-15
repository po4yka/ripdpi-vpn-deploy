#!/usr/bin/env python3
"""Validate public listener manifests for protocol/port collisions.

Input is JSON on stdin:
  {
    "listeners": [
      {"role": "xray", "protocol": "tcp", "port": 443, "enabled": true, "reason": "P0"}
    ],
    "allowlist": [
      {"protocol": "tcp", "port": 443, "reason": "intentional shared bind"}
    ]
  }

Only enabled listeners participate. Findings are phrased with role names and
protocol/port only; no secret values are required or printed.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Listener:
    role: str
    protocol: str
    reason: str
    port: int | None = None
    start: int | None = None
    end: int | None = None

    @property
    def label(self) -> str:
        if self.port is not None:
            return f"{self.protocol}/{self.port}"
        return f"{self.protocol}/{self.start}-{self.end}"

    @property
    def is_range(self) -> bool:
        return self.port is None

    def describe(self) -> str:
        return f"{self.role} ({self.reason})"


def _parse_range(value: Any) -> tuple[int, int]:
    if isinstance(value, str):
        parts = value.split("-", 1)
        if len(parts) != 2:
            raise ValueError(f"invalid range {value!r}")
        start, end = int(parts[0]), int(parts[1])
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        start, end = int(value[0]), int(value[1])
    else:
        raise ValueError(f"invalid range {value!r}")
    _validate_port(start)
    _validate_port(end)
    if start > end:
        raise ValueError(f"invalid descending range {start}-{end}")
    return start, end


def _validate_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise ValueError(f"invalid port {port}")


def _listener(item: dict[str, Any]) -> Listener | None:
    if not item.get("enabled", False):
        return None
    protocol = str(item.get("protocol", "")).lower()
    if protocol not in {"tcp", "udp"}:
        raise ValueError(f"{item.get('role', '<unknown>')}: invalid protocol {protocol!r}")
    role = str(item.get("role", "<unknown>"))
    reason = str(item.get("reason", "public listener"))
    if "range" in item and item.get("range") not in (None, ""):
        start, end = _parse_range(item["range"])
        return Listener(role=role, protocol=protocol, reason=reason, start=start, end=end)
    port = int(item["port"])
    _validate_port(port)
    return Listener(role=role, protocol=protocol, reason=reason, port=port)


def _allow_key(item: Any) -> str:
    if isinstance(item, str):
        return item.lower()
    if not isinstance(item, dict):
        raise ValueError(f"invalid allowlist item {item!r}")
    protocol = str(item.get("protocol", "")).lower()
    if protocol not in {"tcp", "udp"}:
        raise ValueError(f"invalid allowlist protocol {protocol!r}")
    if "range" in item:
        start, end = _parse_range(item["range"])
        return f"{protocol}/{start}-{end}"
    port = int(item["port"])
    _validate_port(port)
    return f"{protocol}/{port}"


def check(payload: dict[str, Any]) -> list[str]:
    allow = {_allow_key(item) for item in payload.get("allowlist", [])}
    listeners = []
    for item in payload.get("listeners", []):
        listener = _listener(item)
        if listener is not None:
            listeners.append(listener)

    findings: list[str] = []
    exact_by_key: dict[str, list[Listener]] = {}
    ranges: list[Listener] = []
    for listener in listeners:
        if listener.is_range:
            ranges.append(listener)
        else:
            exact_by_key.setdefault(listener.label, []).append(listener)

    for key, group in sorted(exact_by_key.items()):
        if len(group) > 1 and key not in allow:
            roles = ", ".join(listener.describe() for listener in group)
            findings.append(f"{key}: duplicate enabled listeners: {roles}")

    exacts = [listener for group in exact_by_key.values() for listener in group]
    for range_listener in ranges:
        for exact in exacts:
            if exact.protocol != range_listener.protocol:
                continue
            assert exact.port is not None
            assert range_listener.start is not None and range_listener.end is not None
            if range_listener.start <= exact.port <= range_listener.end:
                allowed = (
                    exact.label in allow
                    or range_listener.label in allow
                    or f"{exact.protocol}/{exact.port}" in allow
                )
                if not allowed:
                    findings.append(
                        f"{exact.protocol}/{exact.port}: {exact.describe()} is inside "
                        f"{range_listener.label} owned by {range_listener.describe()}"
                    )

    return findings


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        findings = check(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"listener collision guard: invalid manifest: {exc}", file=sys.stderr)
        return 2
    if not findings:
        print("listener collision guard: OK")
        return 0
    print(f"listener collision guard: {len(findings)} finding(s):", file=sys.stderr)
    for finding in findings:
        print(f"  - {finding}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
