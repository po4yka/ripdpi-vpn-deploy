"""Admit the exact recipient payload-failover contract without private diagnostics."""
from __future__ import annotations

from copy import deepcopy
import ipaddress
import re
from urllib.parse import urlsplit


BOUNDS = {
    "interval_seconds": (30, 3600),
    "timeout_seconds": (1, 30),
    "failure_threshold": (2, 10),
    "recovery_threshold": (2, 10),
    "cooldown_seconds": (30, 3600),
    "max_backoff_seconds": (60, 3600),
}
FIELDS = {"schema_version", "selector_tag", "probes", *BOUNDS}


def https_origin(url):
    """Return a canonical HTTPS origin; ambiguous authorities are refused."""
    if (not isinstance(url, str) or not 1 <= len(url) <= 2048
            or not url.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in url)
            or "\\" in url or "#" in url or not url.startswith("https://")):
        raise ValueError("invalid-payload-failover-policy")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port if parts.port is not None else 443
        if (parts.scheme != "https" or not host or parts.username is not None
                or parts.password is not None or "%" in host
                or not 1 <= port <= 65535):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
            host = (address.ipv4_mapped or address).compressed if address.version == 6 else address.compressed
        except ValueError:
            host = host.rstrip(".").lower()
            if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", host.rsplit(".", 1)[-1]):
                raise ValueError
            if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                raise ValueError
            if any(not 1 <= len(label) <= 63 or label.startswith("-") or label.endswith("-")
                   for label in host.split(".")):
                raise ValueError
        return host, port
    except (ValueError, TypeError):
        raise ValueError("invalid-payload-failover-policy") from None


def validate_policy(value):
    """Return a detached complete policy, or None for an unconfigured capability."""
    if value is None:
        return None
    invalid = ValueError("invalid-payload-failover-policy")
    if (not isinstance(value, dict) or set(value) != FIELDS
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["selector_tag"] != "select"):
        raise invalid
    for field, (low, high) in BOUNDS.items():
        if type(value[field]) is not int or not low <= value[field] <= high:
            raise invalid
    if (value["timeout_seconds"] > value["interval_seconds"]
            or value["max_backoff_seconds"] < value["interval_seconds"]):
        raise invalid
    probes = value["probes"]
    if not isinstance(probes, list) or len(probes) != 2:
        raise invalid
    origins = set()
    for probe in probes:
        if (not isinstance(probe, dict) or set(probe) != {"url", "expected_bytes", "sha256"}
                or type(probe["expected_bytes"]) is not int or not 32768 <= probe["expected_bytes"] <= 65536
                or not isinstance(probe["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", probe["sha256"])):
            raise invalid
        origins.add(https_origin(probe["url"]))
    if len(origins) != 2:
        raise invalid
    return deepcopy(value)
