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
        value = (
            str(self.start) if self.start == self.end else f"{self.start}-{self.end}"
        )
        return f"{self.protocol} {value}"


@dataclass(frozen=True)
class FirewallAcceptRule:
    position: int
    verdict: str
    selector: PortSelector | None
    source_restricted: bool
    input_restricted: bool
    loopback_only: bool
    established_only: bool
    protocols: frozenset[str]
    icmp_type_restricted: bool
    source_addresses: frozenset[str]
    input_interfaces: frozenset[str]
    unknown_predicate: bool
    dhcpv6_kind: str | None
    collector_ingress: bool


@dataclass(frozen=True)
class CollectorIngress:
    address: str
    sources: frozenset[str]


def _selector(protocol: object, port: object, port_range: object) -> PortSelector:
    if protocol not in {"tcp", "udp"}:
        raise ValueError(f"unsupported protocol {protocol!r}")
    if (port is None) == (port_range is None):
        raise ValueError(
            f"{protocol} listener must define exactly one port or port_range"
        )
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
        name = str(listener.get("name") or "")
        if name == "hysteria-acme" and selector != PortSelector("tcp", 80, 80):
            raise ValueError("native ACME challenge allowance requires exactly TCP/80")
        selectors[selector] = name
    return selectors


def _decode_tailnet_sources(encoded: str) -> frozenset[str]:
    try:
        raw = base64.b64decode(encoded, validate=True)
        document = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tailnet sources must be valid base64-encoded JSON") from exc
    return _tailnet_addresses(document)


def _tailnet_addresses(document: object) -> frozenset[str]:
    if not isinstance(document, list):
        raise ValueError("Tailnet sources must be a JSON array")
    result: set[str] = set()
    for value in document:
        if not isinstance(value, str):
            raise ValueError("Tailnet source must be an address string")
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("Tailnet source must be a canonical address") from exc
        network = ipaddress.ip_network(
            "100.64.0.0/10" if address.version == 4 else "fd7a:115c:a1e0::/48"
        )
        if str(address) != value or address not in network or value in result:
            raise ValueError(
                "Tailnet source must be a unique canonical Tailnet address"
            )
        result.add(value)
    return frozenset(result)


def _decode_collector_ingress(encoded: str) -> CollectorIngress | None:
    try:
        policy = json.loads(base64.b64decode(encoded, validate=True))
        if policy == {}:
            return None
        if (not isinstance(policy, dict) or set(policy) != {"address", "sources"}
                or not isinstance(policy["sources"], list)
                or not 1 <= len(policy["sources"]) <= 10):
            raise ValueError
        address = next(iter(_tailnet_addresses([policy["address"]])))
        sources = _tailnet_addresses(policy["sources"])
        for value in (address, *sources):
            ipaddress.IPv4Address(value)
        return CollectorIngress(address, sources)
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("invalid Tailnet collector ingress contract") from exc


def _run(*command: str) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def _uplink(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}", value) or value in {"lo", "tailscale0"}:
        raise argparse.ArgumentTypeError("DHCPv6 uplink must be a concrete interface")
    return value


def _decode_dhcpv6_servers(encoded: str) -> frozenset[str]:
    try:
        values = json.loads(base64.b64decode(encoded, validate=True))
        if not isinstance(values, list) or len(values) > 16:
            raise ValueError
        result = set()
        for value in values:
            if not isinstance(value, str) or '%' in value:
                raise ValueError
            address = ipaddress.IPv6Address(value)
            if (str(address) != value or address.is_unspecified or address.is_multicast
                    or address.is_loopback or address.ipv4_mapped is not None or value in result):
                raise ValueError
            result.add(value)
        return frozenset(result)
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("DHCPv6 servers must be bounded unique canonical IPv6 addresses") from exc


def _rule_matches(expressions: list) -> tuple[str, list[dict]] | None:
    matches = []
    verdicts = []
    for expression in expressions:
        if not isinstance(expression, dict):
            return None
        if expression == {"accept": None}:
            verdicts.append('accept')
        elif expression == {"drop": None}:
            verdicts.append('drop')
        elif set(expression) == {"counter"}:
            continue
        elif set(expression) == {"match"}:
            match = expression['match']
            if (not isinstance(match, dict) or set(match) != {'op', 'left', 'right'}
                    or match['op'] not in {'==', 'in'}):
                return None
            matches.append(match)
        else:
            return None
    if len(verdicts) != 1:
        return None
    return verdicts[0], matches


def _collector_rule(expressions: list, collector: CollectorIngress | None) -> bool:
    parsed = _rule_matches(expressions)
    if collector is None or parsed is None:
        return False
    verdict, matches = parsed
    if verdict != "accept" or len(matches) != 4 or any(match["op"] != "==" for match in matches):
        return False
    required = [
        ({"meta": {"key": "iifname"}}, {"tailscale0"}),
        ({"payload": {"protocol": "ip", "field": "daddr"}}, {collector.address}),
        ({"payload": {"protocol": "ip", "field": "saddr"}}, set(collector.sources)),
        ({"payload": {"protocol": "tcp", "field": "dport"}}, {9443}),
    ]
    for left, expected in required:
        found = [match for match in matches if match["left"] == left]
        if len(found) != 1:
            return False
        value = found[0]["right"]
        if isinstance(value, dict):
            if set(value) != {"set"} or not isinstance(value["set"], list):
                return False
            value = value["set"]
        values = value if isinstance(value, list) else [value]
        if (any(type(item) is not type(next(iter(expected))) for item in values)
                or len(values) != len(expected) or set(values) != expected):
            return False
    return True


def _dhcpv6_rule_kind(
    expressions: list, uplink: str, servers: frozenset[str]
) -> str | None:
    parsed = _rule_matches(expressions)
    if parsed is None:
        return None
    verdict, matches = parsed
    expected = [
        ({'payload': {'protocol': 'udp', 'field': 'sport'}}, 547),
        ({'payload': {'protocol': 'udp', 'field': 'dport'}}, 546),
    ]
    if verdict == 'drop':
        expected.append(({'meta': {'key': 'nfproto'}}, 'ipv6'))
        if len(matches) != 3:
            return None
    else:
        expected.extend([
            ({'meta': {'key': 'iifname'}}, uplink),
            ({'fib': {'result': 'type', 'flags': ['daddr']}}, 'local'),
        ])
        if len(matches) != 5:
            return None
    for left, right in expected:
        found = [m for m in matches if m['left'] == left
                 and type(m['right']) is type(right) and m['right'] == right]
        if len(found) != 1:
            return None
        matches.remove(found[0])
    if verdict == 'drop':
        return 'deny'
    source = matches[0]
    if source['left'] != {'payload': {'protocol': 'ip6', 'field': 'saddr'}}:
        return None
    right = source['right']
    if right == 'fe80::/10' or (
        right == {'prefix': {'addr': 'fe80::', 'len': 10}}
        and type(right['prefix']['len']) is int
    ):
        return 'link-local'
    if isinstance(right, str):
        values = [right]
    elif isinstance(right, dict) and set(right) == {'set'} and isinstance(right['set'], list):
        values = right['set']
    else:
        return None
    if (servers and all(isinstance(value, str) for value in values)
            and len(values) == len(servers) and frozenset(values) == servers):
        return 'approved-server'
    return None


def _right_values(value: object) -> set[object]:
    if isinstance(value, dict):
        if isinstance(value.get("set"), list):
            result: set[object] = set()
            for item in value["set"]:
                result.update(_right_values(item))
            return result
        prefix = value.get("prefix")
        if isinstance(prefix, dict):
            address = prefix.get("addr")
            length = prefix.get("len")
            if isinstance(address, str) and isinstance(length, int):
                try:
                    return {str(ipaddress.ip_network(f"{address}/{length}"))}
                except ValueError:
                    return set()
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(_right_values(item))
        return result
    return {value} if isinstance(value, (str, int)) else set()


def _dport_selector(protocol: str, value: object) -> PortSelector:
    if isinstance(value, int) and not isinstance(value, bool):
        return _selector(protocol, value, None)
    if isinstance(value, dict) and isinstance(value.get("range"), list):
        bounds = value["range"]
        if len(bounds) == 2 and all(isinstance(item, int) for item in bounds):
            return _selector(protocol, None, f"{bounds[0]}-{bounds[1]}")
    raise ValueError(f"unsupported nftables {protocol} dport expression")


def _firewall_rules(
    nft_output: str, dhcpv6_uplink: str, dhcpv6_servers: frozenset[str],
    collector: CollectorIngress | None,
) -> list[FirewallAcceptRule]:
    try:
        document = json.loads(nft_output)
    except json.JSONDecodeError as exc:
        raise ValueError("nftables JSON output is malformed") from exc
    objects = document.get("nftables") if isinstance(document, dict) else None
    if not isinstance(objects, list):
        raise ValueError("nftables JSON output is missing nftables array")

    source_sets: dict[str, tuple[str, set[object]]] = {}
    for item in objects:
        nft_set = item.get("set") if isinstance(item, dict) else None
        if not isinstance(nft_set, dict) or nft_set.get("table") != "filter":
            continue
        name = nft_set.get("name")
        if (
            nft_set.get("family") == "inet"
            and name in {"vpn_tailnet_ssh_v4", "vpn_tailnet_ssh_v6"}
            and isinstance(nft_set.get("elem"), list)
        ):
            source_sets[name] = (nft_set.get("type"), _right_values(nft_set["elem"]))

    accepted: list[FirewallAcceptRule] = []
    for position, item in enumerate(objects):
        rule = item.get("rule") if isinstance(item, dict) else None
        if not isinstance(rule, dict) or any(
            rule.get(key) != value
            for key, value in (
                ("family", "inet"),
                ("table", "filter"),
                ("chain", "input"),
            )
        ):
            continue
        expressions = rule.get("expr") if isinstance(rule, dict) else None
        if not isinstance(expressions, list):
            continue
        verdicts = [
            verdict
            for verdict in ("accept", "drop")
            if any(
                isinstance(expression, dict) and verdict in expression
                for expression in expressions
            )
        ]
        if len(verdicts) != 1:
            continue
        verdict = verdicts[0]

        protocol: str | None = None
        selector_value: object | None = None
        source_restricted = False
        input_restricted = False
        loopback_only = False
        established_only = False
        protocols: set[str] = set()
        icmp_type_restricted = False
        source_addresses: set[str] = set()
        input_interfaces: set[str] = set()
        unknown_predicate = False

        for expression in expressions:
            if not isinstance(expression, dict):
                unknown_predicate = True
                continue
            if "match" not in expression:
                if set(expression) - {"accept", "drop", "counter"}:
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
                    values = _right_values(right)
                    if isinstance(right, str) and right.startswith("@"):
                        name = right[1:]
                        family = (
                            "ipv4_addr" if payload_protocol == "ip" else "ipv6_addr"
                        )
                        entry = source_sets.get(name)
                        values = entry[1] if entry and entry[0] == family else set()
                    if values and all(isinstance(value, str) for value in values):
                        source_addresses.update(str(value) for value in values)
                    else:
                        unknown_predicate = True
                elif payload_protocol == "ip" and field == "protocol":
                    protocols.update(str(value) for value in _right_values(right))
                elif payload_protocol == "ip6" and field == "nexthdr":
                    protocols.update(str(value) for value in _right_values(right))
                elif payload_protocol in {"icmp", "icmpv6"} and field == "type":
                    icmp_type_restricted = bool(_right_values(right))
                    protocols.add("icmp" if payload_protocol == "icmp" else "ipv6-icmp")
                elif payload_protocol == "ip6" and field == "hoplimit" and right == 255:
                    pass
                else:
                    unknown_predicate = True
            elif isinstance(meta, dict) and meta.get("key") == "l4proto":
                protocols.update(str(value) for value in _right_values(right))
            elif isinstance(meta, dict) and meta.get("key") in {"iif", "iifname"}:
                input_restricted = True
                loopback_only = right in {"lo", 1}
                values = _right_values(right)
                if values and all(isinstance(value, str) for value in values):
                    input_interfaces.update(str(value) for value in values)
                elif not loopback_only:
                    unknown_predicate = True
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
                position=position,
                verdict=verdict,
                selector=selector,
                source_restricted=source_restricted,
                input_restricted=input_restricted,
                loopback_only=loopback_only,
                established_only=established_only,
                protocols=frozenset(protocols),
                icmp_type_restricted=icmp_type_restricted,
                source_addresses=frozenset(source_addresses),
                input_interfaces=frozenset(input_interfaces),
                unknown_predicate=unknown_predicate,
                dhcpv6_kind=_dhcpv6_rule_kind(expressions, dhcpv6_uplink, dhcpv6_servers),
                collector_ingress=_collector_rule(expressions, collector),
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
        protocol = (
            "tcp"
            if fields[0].startswith("tcp")
            else "udp" if fields[0].startswith("udp") else None
        )
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
    tailnet_sources: frozenset[str],
    dhcpv6_servers: frozenset[str],
    collector: CollectorIngress | None,
    native_acme: bool = False,
) -> list[str]:
    violations: list[str] = []
    conforming: dict[PortSelector, int] = {selector: 0 for selector in expected}
    ssh = PortSelector("tcp", ssh_port, ssh_port)
    tailnet_seen = {source: 0 for source in tailnet_sources}
    tailnet_accept_positions: list[int] = []
    tailnet_drop_positions: list[int] = []
    public_ssh_positions: list[int] = []
    dhcpv6_counts = {'link-local': 0, 'approved-server': 0}
    dhcpv6_accept_positions: list[int] = []
    dhcpv6_deny_positions: list[int] = []
    collector_seen = 0
    established_positions = [r.position for r in firewall if r.verdict == 'accept' and r.established_only]
    for rule in firewall:
        selector = rule.selector
        if rule.verdict == "drop":
            if rule.dhcpv6_kind == 'deny':
                dhcpv6_deny_positions.append(rule.position)
            if (
                selector == ssh
                and not rule.source_restricted
                and rule.input_restricted
                and rule.input_interfaces == frozenset({"tailscale0"})
                and not rule.unknown_predicate
            ):
                tailnet_drop_positions.append(rule.position)
            continue
        if rule.collector_ingress:
            collector_seen += 1
            continue
        if rule.dhcpv6_kind is not None:
            dhcpv6_counts[rule.dhcpv6_kind] += 1
            dhcpv6_accept_positions.append(rule.position)
            continue
        if selector is None:
            if rule.loopback_only or rule.established_only:
                continue
            if (
                rule.protocols
                and rule.protocols <= {"icmp", "ipv6-icmp"}
                and rule.icmp_type_restricted
                and not rule.unknown_predicate
            ):
                continue
            violations.append("unexpected broad firewall accept")
            continue
        if selector == ssh:
            tailnet_rule = (
                rule.source_restricted
                and rule.input_restricted
                and rule.input_interfaces == frozenset({"tailscale0"})
                and len(rule.source_addresses) == 1
                and rule.source_addresses <= tailnet_sources
                and not rule.unknown_predicate
            )
            if tailnet_rule:
                tailnet_seen[next(iter(rule.source_addresses))] += 1
                tailnet_accept_positions.append(rule.position)
                continue
            if (
                not rule.source_restricted
                or rule.input_restricted
                or rule.unknown_predicate
            ):
                violations.append(f"unexpected unrestricted firewall {ssh.label}")
            else:
                public_ssh_positions.append(rule.position)
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

    if collector is not None:
        if collector_seen != 1:
            violations.append("invalid Tailnet collector ingress rule count")
        if ("tcp", 9443) in sockets:
            violations.append("public Tailnet collector socket tcp 9443")
    if dhcpv6_counts['link-local'] != 1:
        violations.append('invalid DHCPv6 link-local reply rule count')
    if dhcpv6_counts['approved-server'] != int(bool(dhcpv6_servers)):
        violations.append('invalid DHCPv6 approved-server reply rule count')
    if len(dhcpv6_deny_positions) != 1:
        violations.append('invalid DHCPv6 reply deny rule count')
    else:
        deny = dhcpv6_deny_positions[0]
        if (any(position >= deny for position in dhcpv6_accept_positions)
                or any(position <= deny for position in established_positions)):
            violations.append('invalid DHCPv6 reply rule ordering')
    for selector, count in sorted(conforming.items()):
        expected_count = 2 if expected[selector] == "cdn-front" else 1
        if count < expected_count:
            violations.append(f"missing firewall {selector.label}")
        elif count > expected_count:
            violations.append(f"duplicate firewall {selector.label}")
    for _source, count in sorted(tailnet_seen.items()):
        if count == 0:
            violations.append("missing Tailnet SSH source rule")
        elif count > 1:
            violations.append("duplicate Tailnet SSH source rule")
    if len(tailnet_drop_positions) != 1:
        violations.append("invalid Tailnet SSH drop ordering")
    else:
        drop_position = tailnet_drop_positions[0]
        if any(
            position >= drop_position for position in tailnet_accept_positions
        ) or any(position <= drop_position for position in public_ssh_positions):
            violations.append("invalid Tailnet SSH drop ordering")
    for selector in sorted(expected):
        # CertMagic closes HTTP-01 after each challenge; its firewall rule stays required.
        if native_acme and expected[selector] == "hysteria-acme" and selector == PortSelector("tcp", 80, 80):
            continue
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
    parser.add_argument("--tailnet-sources-b64", required=True)
    parser.add_argument("--collector-ingress-b64", required=True)
    parser.add_argument("--dhcpv6-uplink", required=True, type=_uplink)
    parser.add_argument("--dhcpv6-servers-b64", required=True)
    parser.add_argument("--native-acme", action="store_true")
    args = parser.parse_args()
    try:
        expected = _decode_contract(args.contract_b64)
        tailnet_sources = _decode_tailnet_sources(args.tailnet_sources_b64)
        collector = _decode_collector_ingress(args.collector_ingress_b64)
        if collector is not None and (args.ssh_port == 9443 or any(
            selector.protocol == "tcp" and selector.start <= 9443 <= selector.end
            for selector in expected
        )):
            raise ValueError("Tailnet collector port overlaps a public or SSH listener")
        dhcpv6_servers = _decode_dhcpv6_servers(args.dhcpv6_servers_b64)
        firewall = _firewall_rules(
            _run("nft", "-j", "list", "table", "inet", "filter"),
            args.dhcpv6_uplink, dhcpv6_servers, collector,
        )
        sockets = _public_socket_ports(_run("ss", "-H", "-lntu"))
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"verify-public-listeners: {exc}", file=sys.stderr)
        return 2

    violations = _violations(
        expected, firewall, sockets, args.ssh_port, tailnet_sources, dhcpv6_servers, collector,
        args.native_acme,
    )
    if violations:
        print("\n".join(violations))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
