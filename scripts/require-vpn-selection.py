#!/usr/bin/env python3
"""Require VPN members in Ansible's already limited inventory JSON."""

import json
import sys


def has_vpn_hosts(document):
    if not isinstance(document, dict):
        return False
    pending = ["vpn"]
    seen = set()
    while pending:
        group = pending.pop()
        if group in seen:
            continue
        seen.add(group)
        entry = document.get(group, {})
        if not isinstance(entry, dict):
            return False
        hosts, children = entry.get("hosts", []), entry.get("children", [])
        if (not isinstance(hosts, list) or not isinstance(children, list)
                or any(not isinstance(item, str) or not item for item in hosts + children)):
            return False
        if hosts:
            return True
        pending.extend(children)
    return False


def main():
    try:
        accepted = has_vpn_hosts(json.load(sys.stdin))
    except (ValueError, OSError):
        accepted = False
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
