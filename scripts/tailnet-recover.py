#!/usr/bin/env python3
"""Reconcile one durable, unconfirmed Tailnet enrollment transaction.

Usage: sudo -n tailnet-recover.py
"""

import json
import sys

import tailnet_management as domain

try:
    print(json.dumps(domain.recover(paths=domain._production_paths()), sort_keys=True))
except domain.Busy:
    raise SystemExit(75) from None
except domain.Refusal as error:
    print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
    raise SystemExit(2) from None
