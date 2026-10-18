#!/usr/bin/env python3
"""Validate a strict full-device, dual-stack sing-box kill-switch bundle.

Rules (each MUST pass, list grows over time):

  K1  TUN inbound has auto_route=true, strict_route=true, and unified
      IPv4 + IPv6 interface prefixes without partial capture policies
  K2  Route rules include a sniff action (so app traffic is identified)
  K3  Route final/rules/groups cannot reach direct egress or use bypass
  K4  Every DNS server detours through a non-direct outbound graph
  K5  No outbound carries an explicit "domain_strategy":"ipv6_only" or
      "prefer_ipv6" — those bypass v4-only tunnels silently. (Mixed-
      stack is fine when the TUN is dual-stack; we accept ipv4_only
      and prefer_ipv4.)

Each failure prints a short reason. Exit 0 clean, 1 on findings.

Usage:
  scripts/check-singbox-killswitch.py phone.singbox.json
  make emit-singbox CLIENT=phone > /tmp/phone.json \\
    && scripts/check-singbox-killswitch.py /tmp/phone.json
"""
from __future__ import annotations

import ipaddress
import json
import pathlib
import sys


def _outbound_direct_resolver(
    outbounds: list[dict], findings: list[str]
):
    """Return a resolver that fails closed on malformed outbound graphs."""
    by_tag: dict[str, dict] = {}
    for index, outbound in enumerate(outbounds):
        if not isinstance(outbound, dict):
            findings.append(f"K3: outbounds[{index}] must be an object")
            continue
        tag = outbound.get("tag")
        if not isinstance(tag, str) or not tag:
            findings.append(f"K3: outbounds[{index}] has no usable tag")
            continue
        if tag in by_tag:
            findings.append(f"K3: duplicate outbound tag {tag!r}")
            continue
        if not isinstance(outbound.get("type"), str) or not outbound["type"]:
            findings.append(f"K3: outbounds[{index}] has no usable type")
        by_tag[tag] = outbound

    cache: dict[str, bool] = {}

    def reaches_direct(tag: object, trail: tuple[str, ...] = ()) -> bool:
        if not isinstance(tag, str) or not tag:
            findings.append(f"K3: invalid outbound reference {tag!r}")
            return True
        if tag in cache:
            return cache[tag]
        if tag in trail:
            findings.append(
                "K3: outbound graph cycle: " + " -> ".join((*trail, tag))
            )
            return True
        outbound = by_tag.get(tag)
        if outbound is None:
            findings.append(f"K3: outbound reference {tag!r} is undefined")
            return True
        if outbound.get("type") == "direct":
            cache[tag] = True
            return True

        children = outbound.get("outbounds")
        if children is None and outbound.get("type") not in ("selector", "urltest"):
            cache[tag] = False
            return False
        if not isinstance(children, list) or not children:
            findings.append(f"K3: outbound group {tag!r} has no usable children")
            cache[tag] = True
            return True

        direct = any(reaches_direct(child, (*trail, tag)) for child in children)
        cache[tag] = direct
        return direct

    # Validate the full graph, including groups not referenced by route.final.
    for tag in by_tag:
        reaches_direct(tag)
    return reaches_direct


def check(bundle: dict) -> list[str]:
    findings: list[str] = []
    if not isinstance(bundle, dict):
        return ["K1: bundle must be an object"]

    inbounds = bundle.get("inbounds", [])
    if not isinstance(inbounds, list) or any(not isinstance(i, dict) for i in inbounds):
        return ["K1: inbounds must be a list of objects"]
    tuns = [i for i in inbounds if i.get("type") == "tun"]
    if not tuns:
        findings.append("K1: no TUN inbound at all — bundle isn't a kill-switch config")
        return findings
    if len(tuns) != 1:
        return ["K1: full-device certification requires exactly one TUN inbound"]
    tun = tuns[0]
    if tun.get("auto_route") is not True:
        findings.append("K1: TUN inbound.auto_route must be true")
    if tun.get("strict_route") is not True:
        findings.append("K1: TUN inbound.strict_route must be true")
    # A valid TUN route does not certify traffic excluded before that route.
    # Refuse selection policies rather than infer capture from external sets.
    capture_fields = (
        "route_address", "route_address_set", "route_exclude_address", "route_exclude_address_set",
        "include_interface", "exclude_interface", "include_uid", "include_uid_range",
        "exclude_uid", "exclude_uid_range", "include_android_user", "include_package", "exclude_package",
        "include_mac_address", "exclude_mac_address",
        "inet4_route_address", "inet6_route_address", "inet4_route_exclude_address", "inet6_route_exclude_address",
    )
    for field in capture_fields:
        if field in tun and tun[field] != []:
            findings.append(f"K1: TUN inbound.{field} prevents full-device capture certification")
    if "exclude_mptcp" in tun and tun["exclude_mptcp"] is not False:
        findings.append("K1: TUN inbound.exclude_mptcp can bypass the tunnel")
    if "netns" in tun and tun["netns"] != "":
        findings.append("K1: TUN inbound.netns limits capture to a network namespace")
    addresses = tun.get("address")
    if not isinstance(addresses, list) or not addresses:
        findings.append(
            "K1: TUN inbound.address must be a non-empty unified IPv4/IPv6 list"
        )
    else:
        families: set[int] = set()
        for address in addresses:
            try:
                if not isinstance(address, str):
                    raise ValueError
                families.add(ipaddress.ip_interface(address).version)
            except (TypeError, ValueError):
                findings.append(f"K1: TUN inbound.address contains invalid prefix {address!r}")
        if 4 not in families:
            findings.append("K1: TUN inbound.address has no IPv4 prefix")
        if 6 not in families:
            findings.append("K1: TUN inbound.address has no IPv6 prefix")
    outbounds = bundle.get("outbounds") or []
    if not isinstance(outbounds, list):
        findings.append("K3: outbounds must be a list")
        outbounds = []
    reaches_direct = _outbound_direct_resolver(outbounds, findings)

    route = bundle.get("route", {})
    if not isinstance(route, dict):
        findings.append("K3: route must be an object")
        route = {}
    final = route.get("final")
    if final == "direct":
        findings.append("K3: route.final == 'direct' — tunnel-down apps egress in clear")
    elif final not in ("select", "auto"):
        findings.append(f"K3: route.final is {final!r}, expected 'select' or 'auto'")
    elif reaches_direct(final):
        findings.append(f"K3: route.final {final!r} can resolve to direct egress")

    rules = route.get("rules") or []
    if not isinstance(rules, list):
        findings.append("K3: route.rules must be a list")
    else:
        if not any(
            isinstance(rule, dict) and rule.get("action") == "sniff"
            for rule in rules
        ):
            findings.append("K2: route.rules has no sniff action")
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                findings.append(f"K3: route.rules[{index}] must be an object")
                continue
            action = rule.get("action", "route")
            if action == "bypass":
                findings.append(
                    f"K3: route.rules[{index}] uses bypass — traffic can evade the tunnel"
                )
                continue
            if action == "route":
                outbound = rule.get("outbound")
                if outbound is None:
                    findings.append(
                        f"K3: route.rules[{index}] routes without an outbound"
                    )
                elif reaches_direct(outbound):
                    findings.append(
                        f"K3: route.rules[{index}] outbound {outbound!r} can resolve to direct egress"
                    )

    dns = bundle.get("dns", {})
    if not isinstance(dns, dict):
        findings.append("K4: dns must be an object")
        dns = {}
    dns_servers = dns.get("servers") or []
    if not isinstance(dns_servers, list) or not dns_servers:
        findings.append("K4: dns.servers must contain at least one tunneled resolver")
    else:
        for index, server in enumerate(dns_servers):
            if not isinstance(server, dict):
                findings.append(f"K4: dns.servers[{index}] must be an object")
                continue
            detour = server.get("detour")
            if detour is None or reaches_direct(detour):
                findings.append(
                    f"K4: dns.servers[{index}].detour {detour!r} can bypass the tunnel"
                )

    for ob in outbounds:
        if not isinstance(ob, dict):
            continue
        ds = ob.get("domain_strategy")
        if ds in ("ipv6_only", "prefer_ipv6"):
            findings.append(
                f"K5: outbound tag={ob.get('tag','?')!r} has domain_strategy={ds!r} — IPv6 may bypass an IPv4-only tunnel"
            )

    return findings


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check-singbox-killswitch.py <bundle.json>", file=sys.stderr)
        return 2
    path = pathlib.Path(argv[0])
    try:
        if argv[0] == "-":
            bundle = json.load(sys.stdin)
        elif not path.is_file():
            print(f"missing: {path}", file=sys.stderr)
            return 2
        else:
            bundle = json.loads(path.read_text())
    except (OSError, UnicodeError, ValueError):
        print("invalid or unreadable bundle JSON", file=sys.stderr)
        return 2

    findings = check(bundle)
    if not findings:
        print("OK — strict full-device dual-stack kill-switch verified (K1-K5)")
        return 0
    print(f"{len(findings)} finding(s):")
    for f in findings:
        print(f"  {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
