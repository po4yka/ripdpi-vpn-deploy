#!/usr/bin/env python3
"""Check a local adoption plan against the bootstrap identity in its prior state."""
import argparse
import hashlib
from importlib import import_module
import json
import sys

import yaml


SERVERS = {
    "hetzner": "hcloud_server.vpn",
    "scaleway": "scaleway_instance_server.vpn",
    "vultr": "vultr_instance.vpn",
}


def key_material(line):
    algorithm, body, *_ = line.strip().split()
    return f"{algorithm} {body}"


def admit(plan, provider, upgrade_digest=False):
    if plan.get("errored") is not False:
        return False
    inputs = {key: entry["value"] for key, entry in plan["variables"].items()}
    resources = {row["address"]: row["values"] for row in plan["prior_state"]["values"]["root_module"]["resources"]}
    server = resources[SERVERS[provider]]
    port = resources["terraform_data.ssh_port"]
    name, user = inputs["server_name"], inputs["admin_user"]
    keys = inputs["admin_ssh_public_keys"]
    if not isinstance(keys, list) or not keys or (not upgrade_digest and len(keys) != 1):
        return False
    key = keys[0]
    if (not server["id"] or server["hostname" if provider == "vultr" else "name"] != name
            or port["input"] != inputs["ssh_port"] or port["output"] != inputs["ssh_port"]):
        return False

    guards = {"terraform_data.admin_user": user}
    if provider == "hetzner":
        if upgrade_digest:
            return False
        registered = resources["hcloud_ssh_key.admin"]
        if (registered["name"] != f"{name}-{user}" or registered["public_key"] != key
                or server["ssh_keys"] != [registered["id"]]):
            return False
    else:
        cloud_init = server["user_data"]
        if provider == "scaleway":
            cloud_init = cloud_init["cloud-init"]
        admin = yaml.safe_load(cloud_init)["users"][-1]
        keys = [value.strip() for value in admin["ssh_authorized_keys"]]
        if (admin["name"] != user or key_material(keys[0]) != key_material(key)
                or (not upgrade_digest and len(keys) != 1)):
            return False
        address = "terraform_data.admin_ssh_public_key"
        digest = hashlib.sha256(key_material(key).encode()).hexdigest()
        if upgrade_digest:
            legacy_digest = hashlib.sha256(keys[0].encode()).hexdigest()
            if provider == "vultr":
                registered = resources["vultr_ssh_key.admin"]
                if (not registered["id"] or server["ssh_key_ids"] != [registered["id"]]
                        or key_material(registered["ssh_key"]) != key_material(key)):
                    return False
            previous = resources[address]
            changes = plan["resource_changes"]
            return (resources["terraform_data.admin_user"]["output"] == user
                    and previous["input"] == previous["output"] == legacy_digest
                    and len(changes) == 1 and changes[0]["address"] == address
                    and changes[0]["change"]["actions"] == ["update"]
                    and changes[0]["change"]["after"]["input"] == digest)
        guards[address] = digest

    changes = plan["resource_changes"]
    return (not guards.keys() & resources.keys()
            and len(changes) == len(guards)
            and {entry["address"] for entry in changes} == guards.keys()
            and all(entry["change"]["actions"] == ["create"]
                    and entry["change"]["after"]["input"] == guards[entry["address"]]
                    for entry in changes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=SERVERS)
    parser.add_argument("--upgrade-digest", action="store_true", help="verify a legacy bootstrap key digest update")
    args = parser.parse_args()
    raw = sys.stdin.buffer.read()
    try:
        accepted = admit(json.loads(raw), args.provider, args.upgrade_digest)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, yaml.YAMLError):
        accepted = False
    if not accepted:
        sys.exit("Refused: the plan does not contain the expected guard changes for the retained bootstrap identity.")
    if args.upgrade_digest and import_module("terraform-plan-policy").evaluate(raw):
        sys.exit("Refused: the guard update did not pass the plan policies.")
    print("Only the expected bootstrap guard changes were admitted.")


if __name__ == "__main__":
    main()
