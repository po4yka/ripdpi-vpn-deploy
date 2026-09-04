#!/usr/bin/env python3
"""Validate exact canonical Tailnet source addresses from bounded JSON stdin.

Usage: printf '%s' '["100.64.1.2"]' | tailnet-validate-sources.py
"""

import json
import sys

import tailnet_management as domain

try:
    value = domain._bounded_json(
        domain._read_stdin(8192),
        reason="tailnet-approved-sources-invalid",
        limit=8192,
    )
    sources = domain.validate_sources(value)
    print(
        json.dumps(
            {
                "status": "valid",
                "count": len(sources),
                "fragment": domain.canonical_sources_fragment(sources),
            }
        )
    )
except domain.Refusal as error:
    print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
    raise SystemExit(2) from None
