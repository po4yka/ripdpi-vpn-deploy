#!/usr/bin/env python3
"""Execute one bootstrap transaction request from private SSH stdin."""

import json
import sys

import tailnet_management as domain
from tailnet_firewall import Firewall


def main():
    request = json.loads(domain._read_stdin(65536))
    if not isinstance(request, dict):
        raise domain.Refusal("tailnet-input-invalid")
    action = request.get("action")
    fields = {
        "enroll": {"action", "binding", "auth_key"},
        "confirm": {"action", "capability", "contexts"},
        "rollback": {"action", "capability"},
        "status": {"action", "binding"},
    }
    if not isinstance(action, str) or action not in fields or set(request) != fields[action]:
        raise domain.Refusal("tailnet-input-invalid")
    options = {"paths": domain._production_paths(), "firewall": Firewall()}
    if action == "enroll":
        return domain.enroll(**options, binding=request["binding"], auth_key=request["auth_key"])
    if action == "confirm":
        return domain.confirm(**options, capability=request["capability"], contexts=request["contexts"])
    if action == "rollback":
        return domain.rollback(**options, capability=request["capability"])
    return domain.transaction_status(**options, binding=request["binding"])


if __name__ == "__main__":
    try:
        print(json.dumps(main(), sort_keys=True))
    except domain.Refusal as error:
        print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
        raise SystemExit(2) from None
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "error", "reason": "tailnet-request-failed"}), file=sys.stderr)
        raise SystemExit(2) from None
