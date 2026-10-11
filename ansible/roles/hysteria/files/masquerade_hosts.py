"""Build private origin resolution without changing global NSS authority."""
import ipaddress
import json
import re
import sys
from urllib.parse import urlsplit


def build(value):
    if not isinstance(value, dict) or set(value) != {"origin", "server_name", "nginx_enabled", "service_address"}:
        raise ValueError
    if (type(value["nginx_enabled"]) is not bool or
            any(not isinstance(value[key], str) for key in ("origin", "server_name", "service_address"))):
        raise ValueError
    origin = urlsplit(value["origin"])
    if origin.scheme != "https" or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment:
        raise ValueError
    hostname = origin.hostname
    enabled = value["nginx_enabled"] and hostname.rstrip(".").lower() == value["server_name"].rstrip(".").lower()
    content = "127.0.0.1 localhost\n::1 localhost ip6-localhost ip6-loopback\n"
    if enabled:
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?", hostname):
            raise ValueError
        address = ipaddress.IPv4Address(value["service_address"])
        content += str(address) + " " + hostname + "\n"
    return {"enabled": enabled, "content": content}


def main():
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError
        print(json.dumps(build(json.loads(raw))))
    except (ValueError, TypeError, KeyError):
        print("masquerade-hosts-invalid", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
