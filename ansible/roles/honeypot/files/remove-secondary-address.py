#!/usr/bin/env python3
"""Remove the exact owned /32, accepting an already absent address only."""

import ipaddress
import json
import re
import subprocess
import sys


def remove(address: str, interface: str) -> None:
    address = str(ipaddress.IPv4Address(address))
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface):
        raise ValueError("invalid interface")
    inspected = subprocess.run(
        ["/usr/sbin/ip", "-j", "-4", "address", "show", "dev", interface],
        capture_output=True, text=True, check=True, timeout=15,
    )
    devices = json.loads(inspected.stdout)
    if (not isinstance(devices, list) or len(devices) != 1
            or not isinstance(devices[0], dict) or devices[0].get("ifname") != interface
            or not isinstance(devices[0].get("addr_info"), list)
            or not all(isinstance(item, dict) and isinstance(item.get("local"), str)
                       and type(item.get("prefixlen")) is int and 0 <= item["prefixlen"] <= 32
                       for item in devices[0]["addr_info"])):
        raise ValueError("invalid address inspection")
    if any(item["local"] == address and item["prefixlen"] == 32
           for item in devices[0]["addr_info"]):
        subprocess.run(
            ["/usr/sbin/ip", "address", "del", address + "/32", "dev", interface],
            capture_output=True, text=True, check=True, timeout=15,
        )


def main() -> int:
    try:
        if len(sys.argv) != 3:
            raise ValueError("expected address and interface")
        remove(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Dedicated honeypot address cleanup failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
