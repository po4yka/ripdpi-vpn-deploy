#!/usr/bin/env python3
"""Consume one enrollment capability and configure restricted Tailnet access.

Usage: printf '%s' "$TAILSCALE_AUTH_KEY" | sudo -n tailnet-configure.py
"""

import json
import sys

import tailnet_management as domain

try:
    raw = domain._read_stdin(4096)
    key = raw[:-1] if raw.endswith("\n") else raw
    print(
        json.dumps(
            domain.configure(paths=domain._production_paths(), auth_key=key),
            sort_keys=True,
        )
    )
except domain.Refusal as error:
    print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
    raise SystemExit(2) from None
