"""Canonical recipient address policy; never resolves or dials a destination."""
from __future__ import annotations

import argparse
import ipaddress
import json

IPV4_DENY = ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
             "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4")
IPV6_DENY = ("::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8")
_NETWORKS = tuple(ipaddress.ip_network(value) for value in (*IPV4_DENY, *IPV6_DENY))


class PolicyError(ValueError):
    """Fixed categorical diagnostics only."""


def normalize_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if not isinstance(value, str) or len(value) > 45 or "%" in value:
        raise PolicyError("invalid-address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise PolicyError("invalid-address") from None
    return address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address


def canonical_name(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 254:
        raise PolicyError("invalid-name")
    try:
        name = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise PolicyError("invalid-name") from None
    if len(name) > 253 or value.endswith(".."):
        raise PolicyError("invalid-name")
    labels = name.split(".")
    if any(not label or len(label) > 63 or label[0] == "-" or label[-1] == "-"
           or any(not (character.isalnum() or character in "-_") for character in label) for label in labels):
        raise PolicyError("invalid-name")
    return name + "."


class DestinationPolicy:
    def __init__(self, owned_addresses=(), management_tcp_ports=(), management_udp_ports=()):
        self.owned = frozenset(str(normalize_address(value)) for value in owned_addresses)
        self.management = {"tcp": frozenset(management_tcp_ports), "udp": frozenset(management_udp_ports)}

    def allows(self, address: str, port: int, network: str) -> bool:
        if type(port) is not int or not 1 <= port <= 65535 or network not in self.management:
            return False
        normalized = normalize_address(address)
        if any(normalized.version == prefix.version and normalized in prefix for prefix in _NETWORKS):
            return False
        return not (str(normalized) in self.owned and port in self.management[network])

    def select_admitted(self, addresses, port: int, network: str) -> str:
        candidates = {str(normalize_address(value)) for value in addresses}
        candidates = [value for value in candidates if self.allows(value, port, network)]
        if not candidates:
            raise PolicyError("destination-denied")
        # A stable family preference does not inherit host gai.conf authority.
        return min(candidates, key=lambda value: (normalize_address(value).version, int(normalize_address(value))))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-policy", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps({"ipv4": list(IPV4_DENY), "ipv6": list(IPV6_DENY)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
