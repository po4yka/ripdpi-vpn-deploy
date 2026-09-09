#!/usr/bin/env python3
"""Restore unconfirmed firewall policy before networking; never call tailscaled."""

import json
import sys

import tailnet_management as domain
from tailnet_firewall import Firewall

try:
    print(json.dumps(domain.recover_firewall(paths=domain._production_paths(), firewall=Firewall()), sort_keys=True))
except domain.Busy:
    raise SystemExit(75) from None
except domain.Refusal as error:
    print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
    raise SystemExit(2) from None
