#!/usr/bin/env python3
"""Inspect restricted Tailnet management state without mutation.

Usage: sudo -n tailnet-check.py
"""

import json
import sys

import tailnet_management as domain

try:
    print(json.dumps(domain.check(paths=domain._production_paths()), sort_keys=True))
except domain.Refusal as error:
    print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
    raise SystemExit(2) from None
