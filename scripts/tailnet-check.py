#!/usr/bin/env python3
"""Inspect restricted Tailnet management state without mutation.

Usage: provide the exact non-secret inventory target as JSON on stdin.
"""

import json
import sys

import tailnet_management as domain

try:
    target = domain._bounded_json(
        domain._read_stdin(65536), reason="tailnet-input-invalid", limit=65536
    )
    print(json.dumps(domain.check(paths=domain._production_paths(), target=target), sort_keys=True))
except domain.Refusal as error:
    print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
    raise SystemExit(2) from None
