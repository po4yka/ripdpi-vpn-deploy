#!/usr/bin/env python3
"""Resolve one DNS record over HTTPS and print each answer on its own line.

The queried name can contain a node address, so it never crosses the network in
cleartext and a failed lookup has no cleartext fallback. A name with no record
prints nothing and exits 0; a lookup that did not run exits 1.

Usage: doh-lookup.py {A|TXT} <name>
Environment: DOH_URL selects a resolver with a JSON API (default: Cloudflare).
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request

from authenticated_http import NoRedirect

DEFAULT_URL = "https://cloudflare-dns.com/dns-query"
RECORD_TYPES = {"A": 1, "TXT": 16}
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in RECORD_TYPES:
        print("usage: doh-lookup.py {A|TXT} <name>", file=sys.stderr)
        return 2
    url = os.environ.get("DOH_URL") or DEFAULT_URL
    try:
        parts = urllib.parse.urlsplit(url)
        # Plain HTTP is admitted for a loopback resolver only: it never leaves the host.
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOOPBACK):
            raise ValueError("resolver")
        query = urllib.parse.urlencode({"name": argv[2], "type": argv[1]})
        request = urllib.request.Request(
            f"{url}{'&' if parts.query else '?'}{query}", headers={"Accept": "application/dns-json"}
        )
        # A redirect could leave HTTPS, and a proxy would read a plain loopback request.
        handlers = [NoRedirect()] + ([urllib.request.ProxyHandler({})] if parts.scheme == "http" else [])
        with urllib.request.build_opener(*handlers).open(request, timeout=5) as response:
            document = json.load(response)
        # 0 is an answer and 3 is a name that does not exist; any other status is a failed lookup.
        if document["Status"] not in (0, 3):
            raise ValueError("status")
        answers = [
            # TXT data is one or more quoted strings; resolvers differ on whether they keep the quotes.
            "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', str(answer["data"]))) or str(answer["data"])
            for answer in document.get("Answer", [])
            if answer["type"] == RECORD_TYPES[argv[1]]
        ]
    except (OSError, ValueError, KeyError, TypeError):
        print("doh-lookup: the encrypted lookup did not run; no cleartext query was sent", file=sys.stderr)
        return 1
    for answer in answers:
        print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
