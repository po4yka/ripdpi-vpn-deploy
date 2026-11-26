#!/usr/bin/env python3
"""Evaluate all plan policies, rejecting empty or invalid evaluation results."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys


POLICY = Path(__file__).resolve().parents[1] / "terraform/policy"
REQUIRED = {
    "terraform.policy.admin_port", "terraform.policy.ssh_cidrs",
    "terraform.policy.secondary_ip", "terraform.policy.server_metadata",
    "terraform.policy.no_secrets_in_user_data", "terraform.policy.listener_family",
    "terraform.policy.egress_address",
}


def evaluate(plan: Path | bytes, *, environment=None) -> int:
    try:
        # Recovery reads an encrypted saved plan. Keep its decrypted view in pipes.
        stdin_plan = isinstance(plan, bytes)
        source = ["--parser", "json", "-"] if stdin_plan else [str(plan)]
        result = subprocess.run(
            ["conftest", "test", "--rego-version", "v0", "--all-namespaces",
             "--output", "json", "-p", str(POLICY), *source],
            input=plan if stdin_plan else None, env=environment, capture_output=True, timeout=120,
        )
        rows = json.loads(result.stdout)
        if not isinstance(rows, list):
            raise ValueError("invalid evaluation")
        checks = 0
        rejected = set()
        evaluated = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid result row")
            namespace = row.get("namespace")
            successes = row.get("successes", 0)
            if (not isinstance(namespace, str)
                    or not namespace
                    or type(successes) is not int or successes < 0):
                raise ValueError("invalid result summary")
            checks += successes
            count = successes
            for key in ("failures", "warnings", "exceptions"):
                entries = row.get(key, [])
                if not isinstance(entries, list) or any(
                    not isinstance(entry, dict) or not isinstance(entry.get("msg"), str)
                    for entry in entries
                ):
                    raise ValueError("invalid diagnostic summary")
                checks += len(entries)
                count += len(entries)
                if entries:
                    rejected.add(namespace)
            if count:
                evaluated.add(namespace)
        if checks == 0 or not REQUIRED.issubset(evaluated):
            print("Terraform policy check: incomplete policy evaluation", file=sys.stderr)
            return 1
        if result.returncode or rejected:
            print("Terraform policy check: rejected" +
                  (" (" + ", ".join(sorted(rejected)) + ")" if rejected else ""),
                  file=sys.stderr)
            return 1
        print(f"Terraform policy check: {checks} evaluations passed across {len(evaluated)} namespaces")
        return 0
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        # Conftest parser errors can include input text. Keep plan data private.
        print("Terraform policy check: invalid or missing Conftest evaluation report", file=sys.stderr)
        return 1


def check_green_management_key(plan: bytes, key_file: str, reserved_keys: str) -> bool:
    """Check the selected SSH identity against the exact Green provisioning plan."""
    try:
        document = json.loads(plan)
        actions = [row["change"]["actions"] for row in document["resource_changes"]
                   if row["address"] == "hcloud_server.vpn"]
        # A retry can retain an existing server. Its pinned SSH wait still runs
        # after apply because its retained user_data does not prove current access.
        if len(actions) != 1 or actions[0] not in (["create"], ["no-op"], ["update"]):
            print("Green plan must identify exactly one new or retained Hetzner server.", file=sys.stderr)
            return False

        keys = document["variables"]["admin_ssh_public_keys"]["value"]
        if not isinstance(keys, list) or not keys or not all(isinstance(key, str) for key in keys):
            raise ValueError
        first = " ".join(keys[0].split()[:2])
        if (not re.fullmatch(r"[0-9a-f]{64}:[0-9a-f]{64}", reserved_keys)
                or hashlib.sha256(first.encode()).hexdigest() in reserved_keys.split(":")):
            print("Green must have a first SSH key distinct from Blue's configured and registered keys.", file=sys.stderr)
            return False
        # Deployment uses BatchMode with IdentityAgent=none. Never prompt for a passphrase.
        public = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", key_file], stdin=subprocess.DEVNULL,
            capture_output=True, env={"PATH": os.defpath, "LC_ALL": "C"}, timeout=10, check=True,
        ).stdout.decode().split()[:2]
        if len(public) == 2 and any(key.split()[:2] == public for key in keys):
            return True
    except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError):
        # Parser and subprocess errors can contain plan data or the private key path.
        print("Cannot verify the Green plan or read the selected SSH identity.", file=sys.stderr)
        return False
    print("Green must authorize the selected inventory SSH identity. Keep its distinct "
          "first key and add the shared management public key to admin_ssh_public_keys.",
          file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_json", type=Path)
    args = parser.parse_args()
    if args.plan_json == Path("-"):
        plan = sys.stdin.buffer.read()
        key_file = os.environ.get("BLUE_GREEN_MANAGEMENT_KEY_FILE")
        reserved_keys = os.environ.get("BLUE_GREEN_RESERVED_KEY_DIGESTS", "")
        if key_file and not check_green_management_key(plan, key_file, reserved_keys):
            return 1
        return evaluate(plan)
    return evaluate(args.plan_json)


if __name__ == "__main__":
    raise SystemExit(main())
