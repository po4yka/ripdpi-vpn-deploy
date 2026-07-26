#!/usr/bin/env python3
"""Verify that the runtime public socket and firewall state match a listener contract."""

from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import re
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class PortSelector:
    protocol: str
    start: int
    end: int

    @property
    def label(self) -> str:
        value = str(self.start) if self.start == self.end else f"{self.start}-{self.end}"
        return f"{self.protocol} {value}"


@dataclass(frozen=True)
class FirewallAcceptRule:
    selector: PortSelector | None
    source_restricted: bool
    input_restricted: bool
    loopback_only: bool
    established_only: bool
    protocols: frozenset[str]
    unknown_predicate: bool


def _selector(protocol: object, port: object, port_range: object) -> PortSelector:
    if protocol not in {"tcp", "udp"}:
        raise ValueError(f"unsupported protocol {protocol!r}")
    if (port is None) == (port_range is None):
        raise ValueError(f"{protocol} listener must define exactly one port or port_range")
    if port is not None:
        if not isinstance(port, int) or isinstance(port, bool):
            raise ValueError(f"{protocol} port must be an integer")
        start = end = port
    else:
        match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", str(port_range))
        if match is None:
            raise ValueError(f"invalid {protocol} port range {port_range!r}")
        start, end = (int(value) for value in match.groups())
    if start < 1 or end > 65535 or start > end:
        raise ValueError(f"invalid {protocol} port selector {start}-{end}")
    return PortSelector(protocol, start, end)


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _decode_contract(encoded: str) -> dict[PortSelector, str]:
    try:
        raw = base64.b64decode(encoded, validate=True)
        doc = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("listener contract must be valid base64-encoded JSON") from exc
    if not isinstance(doc, list):
        raise ValueError("listener contract must be a JSON array")
    selectors: dict[PortSelector, str] = {}
    for index, listener in enumerate(doc):
        if not isinstance(listener, dict):
            raise ValueError(f"listener contract entry {index} must be an object")
        selector = _selector(
            listener.get("protocol"), listener.get("port"), listener.get("port_range")
        )
        if selector in selectors:
            raise ValueError(f"duplicate listener selector {selector.label}")
        selectors[selector] = str(listener.get("name") or "")
    return selectors


def _run(*command: str) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def _right_values(value: object) -> set[object]:
    if isinstance(value, dict) and isinstance(value.get("set"), list):
        value = value["set"]
    if isinstance(value, list):
        return {item for item in value if isinstance(item, (str, int))}
    return {value} if isinstance(value, (str, int)) else set()


def _dport_selector(protocol: str, value: object) -> PortSelector:
    if isinstance(value, int) and not isinstance(value, bool):
        return _selector(protocol, value, None)
    if isinstance(value, dict) and isinstance(value.get("range"), list):
        bounds = value["range"]
        if len(bounds) == 2 and all(isinstance(item, int) for item in bounds):
            return _selector(protocol, None, f"{bounds[0]}-{bounds[1]}")
    raise ValueError(f"unsupported nftables {protocol} dport expression")


def _firewall_rules(nft_output: str) -> list[FirewallAcceptRule]:
    try:
        document = json.loads(nft_output)
    except json.JSONDecodeError as exc:
        raise ValueError("nftables JSON output is malformed") from exc
    objects = document.get("nftables") if isinstance(document, dict) else None
    if not isinstance(objects, list):
        raise ValueError("nftables JSON output is missing nftables array")

    accepted: list[FirewallAcceptRule] = []
    for item in objects:
        rule = item.get("rule") if isinstance(item, dict) else None
        expressions = rule.get("expr") if isinstance(rule, dict) else None
        if not isinstance(expressions, list) or not any(
            isinstance(expr, dict) and "accept" in expr for expr in expressions
        ):
            continue

        protocol: str | None = None
        selector_value: object | None = None
        source_restricted = False
        input_restricted = False
        loopback_only = False
        established_only = False
        protocols: set[str] = set()
        unknown_predicate = False

        for expression in expressions:
            if not isinstance(expression, dict):
                unknown_predicate = True
                continue
            if "match" not in expression:
                if set(expression) - {"accept", "counter"}:
                    unknown_predicate = True
                continue
            match = expression["match"]
            if not isinstance(match, dict):
                unknown_predicate = True
                continue
            if match.get("op") not in {"==", "in"}:
                unknown_predicate = True
                continue
            left = match.get("left")
            right = match.get("right")
            if not isinstance(left, dict):
                unknown_predicate = True
                continue
            payload = left.get("payload")
            meta = left.get("meta")
            conntrack = left.get("ct")
            if isinstance(payload, dict):
                payload_protocol = payload.get("protocol")
                field = payload.get("field")
                if payload_protocol in {"tcp", "udp"} and field == "dport":
                    protocol = payload_protocol
                    selector_value = right
                elif payload_protocol in {"ip", "ip6"} and field == "saddr":
                    source_restricted = True
                elif payload_protocol == "ip" and field == "protocol":
                    protocols.update(str(value) for value in _right_values(right))
                elif payload_protocol == "ip6" and field == "nexthdr":
                    protocols.update(str(value) for value in _right_values(right))
                else:
                    unknown_predicate = True
            elif isinstance(meta, dict) and meta.get("key") == "l4proto":
                protocols.update(str(value) for value in _right_values(right))
            elif isinstance(meta, dict) and meta.get("key") in {"iif", "iifname"}:
                input_restricted = True
                loopback_only = right in {"lo", 1}
            elif isinstance(conntrack, dict) and conntrack.get("key") == "state":
                states = {str(value) for value in _right_values(right)}
                established_only = bool(states) and states <= {"established", "related"}
                if not established_only:
                    unknown_predicate = True
            else:
                unknown_predicate = True

        selector = None
        if protocol is not None:
            selector = _dport_selector(protocol, selector_value)
        accepted.append(
            FirewallAcceptRule(
                selector=selector,
                source_restricted=source_restricted,
                input_restricted=input_restricted,
                loopback_only=loopback_only,
                established_only=established_only,
                protocols=frozenset(protocols),
                unknown_predicate=unknown_predicate,
            )
        )
    return accepted


def _split_local_address(value: str) -> tuple[str, int] | None:
    if value.startswith("["):
        close = value.rfind("]:")
        if close < 0:
            return None
        host, port_raw = value[1:close], value[close + 2 :]
    else:
        try:
            host, port_raw = value.rsplit(":", 1)
        except ValueError:
            return None
    if not port_raw.isdigit():
        return None
    port = int(port_raw)
    if not 1 <= port <= 65535:
        return None
    return host.split("%", 1)[0], port


def _is_public_capable_bind(host: str) -> bool:
    if host in {"*", "0.0.0.0", "::"}:
        return True
    if host.lower() == "localhost":
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_global and not address.is_multicast


def _public_socket_ports(ss_output: str) -> set[tuple[str, int]]:
    ports: set[tuple[str, int]] = set()
    for line in ss_output.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        protocol = "tcp" if fields[0].startswith("tcp") else "udp" if fields[0].startswith("udp") else None
        parsed = _split_local_address(fields[4])
        if protocol is None or parsed is None:
            continue
        host, port = parsed
        if _is_public_capable_bind(host):
            ports.add((protocol, port))
    return ports


def _violations(
    expected: dict[PortSelector, str],
    firewall: list[FirewallAcceptRule],
    sockets: set[tuple[str, int]],
    ssh_port: int,
) -> list[str]:
    violations: list[str] = []
    conforming: dict[PortSelector, int] = {selector: 0 for selector in expected}
    ssh = PortSelector("tcp", ssh_port, ssh_port)
    for rule in firewall:
        selector = rule.selector
        if selector is None:
            if rule.loopback_only or rule.established_only:
                continue
            if rule.protocols and rule.protocols <= {"icmp", "ipv6-icmp"}:
                continue
            violations.append("unexpected broad firewall accept")
            continue
        if selector == ssh:
            if (
                not rule.source_restricted
                or rule.input_restricted
                or rule.unknown_predicate
            ):
                violations.append(f"unexpected unrestricted firewall {ssh.label}")
            continue
        if selector not in expected:
            violations.append(f"unexpected firewall {selector.label}")
            continue
        is_cdn_front = expected[selector] == "cdn-front"
        scope_matches = (
            rule.source_restricted and not rule.input_restricted
            if is_cdn_front
            else not rule.source_restricted and not rule.input_restricted
        )
        if not scope_matches or rule.unknown_predicate:
            violations.append(f"restricted or unsupported firewall {selector.label}")
            continue
        conforming[selector] += 1

    for selector, count in sorted(conforming.items()):
        expected_count = 2 if expected[selector] == "cdn-front" else 1
        if count < expected_count:
            violations.append(f"missing firewall {selector.label}")
        elif count > expected_count:
            violations.append(f"duplicate firewall {selector.label}")
    for selector in sorted(expected):
        for port in range(selector.start, selector.end + 1):
            if (selector.protocol, port) in sockets:
                continue
            if selector.start == selector.end:
                violations.append(f"missing {selector.protocol} {port}")
            else:
                violations.append(
                    f"missing {selector.protocol} {port} "
                    f"(required by range {selector.start}-{selector.end})"
                )
            break
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-b64", required=True)
    parser.add_argument("--ssh-port", required=True, type=_port)
    args = parser.parse_args()
    try:
        expected = _decode_contract(args.contract_b64)
        firewall = _firewall_rules(
            _run("nft", "-j", "list", "chain", "inet", "filter", "input")
        )
        sockets = _public_socket_ports(_run("ss", "-H", "-lntu"))
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"verify-public-listeners: {exc}", file=sys.stderr)
        return 2

    violations = _violations(expected, firewall, sockets, args.ssh_port)
    if violations:
        print("\n".join(violations))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
