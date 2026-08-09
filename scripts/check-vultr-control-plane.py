#!/usr/bin/env python3
"""Fail-fast authenticated probe for Vultr operator API access."""

from __future__ import annotations

import os
import socket
import sys
import urllib.error
import urllib.request


API_URL = "https://api.vultr.com/v2/account"
TIMEOUT_SECONDS = 10


def main() -> int:
    token = os.environ.get("TF_VAR_vultr_api_key") or os.environ.get("VULTR_API_KEY")
    if not token:
        print(
            "vultr control plane: missing TF_VAR_vultr_api_key (or VULTR_API_KEY)",
            file=sys.stderr,
        )
        return 2

    request = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "ripdpi-vpn-deploy-control-plane-check/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        if exc.code == 401 and "Unauthorized IP address" in body:
            print(
                "vultr control plane: API allowlist rejected the current operator egress; "
                "add its exact IP/CIDR in Vultr Console access control and retry",
                file=sys.stderr,
            )
            return 78
        if exc.code in {401, 403}:
            print("vultr control plane: API credentials rejected", file=sys.stderr)
            return 77
        print(f"vultr control plane: API returned HTTP {exc.code}", file=sys.stderr)
        return 69
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        print("vultr control plane: API endpoint is unreachable", file=sys.stderr)
        return 69

    if not 200 <= status < 300:
        print(f"vultr control plane: API returned HTTP {status}", file=sys.stderr)
        return 69
    print("vultr control plane: OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
