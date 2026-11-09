"""Canonical recipient address policy; never resolves or dials a destination."""
from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import ipaddress
import json
from itertools import zip_longest
import re
import socket
import sys

IPV4_DENY = ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
             "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4",
             "240.0.0.0/4")
# NAT64 and 6to4 embed an IPv4 address, so they can reach the private IPv4 ranges.
IPV6_DENY = ("::/128", "::1/128", "64:ff9b::/96", "2002::/16", "fc00::/7", "fe80::/10", "ff00::/8")
# The direct gateway answers normalizer lookups here over DNS-over-HTTPS; it is
# the one loopback resolver the denied 127.0.0.0/8 prefix admits.
LOCAL_DNS_FORWARDER = "127.0.0.2"
_NETWORKS = tuple(ipaddress.ip_network(value) for value in (*IPV4_DENY, *IPV6_DENY))
MAX_DENY_BYTES = 33554432
MAX_DENY_NAMES = 500000
MAX_DENY_RANGES = 200000
MAX_ALLOW_NAMES = 256
# Comment lines do not count as entries, so bound them before splitlines allocates.
MAX_DENY_COMMENT_LINES = 4096
_LABEL = rb"(?!-)[a-z0-9_-]{1,63}(?<!-)"
# Feed lines are A-labels. A full canonical_name call per line costs seconds on the smallest node.
_DENY_NAME = re.compile(rb"(?:" + _LABEL + rb"\.)*" + _LABEL)


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
        # Normalize case before the codec so patch-level Unicode handling cannot
        # give uppercase deviation characters a different admission policy.
        # Do not casefold: that would erase the sharp-s identity before checking.
        requested = value.rstrip(".").lower()
        name = requested.encode("idna").decode("ascii").lower()
        # The stdlib codec uses IDNA2003. Never let its compatibility mappings
        # silently select a different DNS identity. ASCII A-labels stay explicit.
        if not requested.isascii() and name.encode("ascii").decode("idna").lower() != requested:
            raise PolicyError("invalid-name")
    except UnicodeError:
        raise PolicyError("invalid-name") from None
    if len(name) > 253 or value.endswith(".."):
        raise PolicyError("invalid-name")
    labels = name.split(".")
    if any(not label or len(label) > 63 or label[0] == "-" or label[-1] == "-"
           or any(not (character.isalnum() or character in "-_") for character in label) for label in labels):
        raise PolicyError("invalid-name")
    return name + "."


def _suffixes(name: str):
    remainder = name.rstrip(".").encode("ascii")
    while remainder:
        yield remainder
        remainder = remainder.partition(b".")[2]


def _deny_lines(data: bytes, limit: int):
    # CRLF counts twice here, which still bounds the allocation.
    if data.count(b"\n") + data.count(b"\r") > 2 * limit + MAX_DENY_COMMENT_LINES:
        raise PolicyError("oversized-deny-data")
    for line in data.splitlines():
        line = line.strip()
        if line and not line.startswith(b"#"):
            yield line


def _parse_names(data: bytes) -> frozenset[bytes]:
    names = set()
    for line in _deny_lines(data, MAX_DENY_NAMES):
        line = line.lower()
        if len(line) > 253 or not _DENY_NAME.fullmatch(line):
            raise PolicyError("invalid-deny-data")
        names.add(line)
        if len(names) > MAX_DENY_NAMES:
            raise PolicyError("oversized-deny-data")
    return frozenset(names)


def _parse_ranges(data: bytes) -> dict[int, tuple[tuple[int, ...], tuple[int, ...]]]:
    intervals = {4: [], 6: []}
    count = 0
    for line in _deny_lines(data, MAX_DENY_RANGES):
        count += 1
        if count > MAX_DENY_RANGES:
            raise PolicyError("oversized-deny-data")
        try:
            network = ipaddress.ip_network(line.decode("ascii"), strict=False)
        except ValueError:
            raise PolicyError("invalid-deny-data") from None
        # Lookups normalize mapped addresses to IPv4, so such a range could never match.
        if network.version == 6 and network.network_address.ipv4_mapped is not None:
            raise PolicyError("invalid-deny-data")
        intervals[network.version].append((int(network.network_address), int(network.broadcast_address)))
    merged = {}
    for version, values in intervals.items():
        starts, ends = [], []
        for low, high in sorted(values):
            if ends and low <= ends[-1] + 1:
                ends[-1] = max(ends[-1], high)
            else:
                starts.append(low)
                ends.append(high)
        merged[version] = (tuple(starts), tuple(ends))
    return merged


class DenyList:
    """Operator-pinned names and ranges; the private-address isolation stays separate."""

    def __init__(self, names: frozenset[bytes], ranges, allow_domains=()):
        self.names = names
        self.ranges = ranges
        self.allow = frozenset(canonical_name(value).rstrip(".").encode("ascii") for value in allow_domains)

    def name_allowed(self, name: str) -> bool:
        return any(value in self.allow for value in _suffixes(name))

    def name_denied(self, name: str) -> bool:
        return any(value in self.names for value in _suffixes(name))

    def address_denied(self, address) -> bool:
        starts, ends = self.ranges[address.version]
        index = bisect_right(starts, int(address)) - 1
        return index >= 0 and int(address) <= ends[index]


def _pinned_bytes(path: str, digest: str) -> bytes:
    try:
        with open(path, "rb") as source:
            data = source.read(MAX_DENY_BYTES + 1)
    except OSError:
        raise PolicyError("unavailable-deny-data") from None
    if len(data) > MAX_DENY_BYTES:
        raise PolicyError("oversized-deny-data")
    if hashlib.sha256(data).hexdigest() != digest:
        raise PolicyError("deny-digest-mismatch")
    return data


def load_deny_list(spec: dict) -> DenyList:
    return DenyList(_parse_names(_pinned_bytes(spec["names_path"], spec["names_sha256"])),
                    _parse_ranges(_pinned_bytes(spec["ranges_path"], spec["ranges_sha256"])),
                    spec["allow_domains"])


class DestinationPolicy:
    def __init__(self, owned_addresses=(), management_tcp_ports=(), management_udp_ports=(), deny=None):
        self.owned = frozenset(str(normalize_address(value)) for value in owned_addresses)
        self.management = {"tcp": frozenset(management_tcp_ports), "udp": frozenset(management_udp_ports)}
        self.deny = deny

    def admit_name(self, name: str) -> bool:
        """Refuse a listed name before resolution; True exempts the name from range denial."""
        if self.deny is None:
            return False
        if self.deny.name_allowed(name):
            return True
        if self.deny.name_denied(name):
            raise PolicyError("destination-denied")
        return False

    def allows(self, address: str, port: int, network: str) -> bool:
        if type(port) is not int or not 1 <= port <= 65535 or network not in self.management:
            return False
        normalized = normalize_address(address)
        if any(normalized.version == prefix.version and normalized in prefix for prefix in _NETWORKS):
            return False
        return not (str(normalized) in self.owned and port in self.management[network])

    def admitted_candidates(self, addresses, port: int, network: str, range_exempt: bool = False) -> tuple[str, ...]:
        candidates = {normalize_address(value) for value in addresses}
        candidates = [value for value in candidates if self.allows(str(value), port, network)]
        if self.deny is not None and not range_exempt:
            candidates = [value for value in candidates if not self.deny.address_denied(value)]
        if not candidates:
            raise PolicyError("destination-denied")
        # Stable family ordering never inherits host gai.conf authority. Preserve
        # IPv6 opportunity even when the bounded dial set has many IPv4 answers.
        ipv4 = sorted((value for value in candidates if value.version == 4), key=int)
        ipv6 = sorted((value for value in candidates if value.version == 6), key=int)
        return tuple(str(value) for pair in zip_longest(ipv4, ipv6) for value in pair if value is not None)


def _refuse_fully_denied_answer(deny: DenyList, name: str) -> None:
    try:
        answers = {normalize_address(item[4][0]) for item in socket.getaddrinfo(name, None)}
    except (OSError, UnicodeError, PolicyError):
        # An unresolved name cannot show a range match; runtime acceptance still decides.
        return
    if answers and all(deny.address_denied(value) for value in answers):
        raise PolicyError("destination-denied")


def check_deny_data(request: dict) -> dict:
    """Admit candidate data on the node before the accepted generation stops."""
    deny = load_deny_list(request)
    policy = DestinationPolicy(deny=deny)
    for host in request["required_destinations"]:
        try:
            address = normalize_address(host)
        except PolicyError:
            name = canonical_name(host)
            if not policy.admit_name(name):
                _refuse_fully_denied_answer(deny, name)
        else:
            if deny.address_denied(address):
                raise PolicyError("destination-denied")
    return {"names": len(deny.names), "ranges": sum(len(starts) for starts, _ in deny.ranges.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-policy", action="store_true")
    mode.add_argument("--check-deny-data", action="store_true", help="read a JSON request from stdin")
    args = parser.parse_args()
    if args.check_deny_data:
        try:
            print(json.dumps(check_deny_data(json.loads(sys.stdin.buffer.read(MAX_ALLOW_NAMES * 512))), separators=(",", ":")))
        except PolicyError as error:
            print(str(error), file=sys.stderr)
            return 1
        except (KeyError, TypeError, ValueError):
            print("invalid-deny-request", file=sys.stderr)
            return 1
        return 0
    print(json.dumps({"ipv4": list(IPV4_DENY), "ipv6": list(IPV6_DENY)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
