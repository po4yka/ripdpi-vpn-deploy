#!/usr/bin/env python3
"""Check a local adoption plan against the bootstrap identity in its prior state."""
import argparse
import hashlib
import json
import sys

import yaml


SERVERS = {
    "hetzner": "hcloud_server.vpn",
    "scaleway": "scaleway_instance_server.vpn",
    "vultr": "vultr_instance.vpn",
}


def admit(plan, provider):
    if plan.get("errored") is not False:
        return False
    inputs = {key: entry["value"] for key, entry in plan["variables"].items()}
    resources = {row["address"]: row["values"] for row in plan["prior_state"]["values"]["root_module"]["resources"]}
    server = resources[SERVERS[provider]]
    port = resources["terraform_data.ssh_port"]
    name, user = inputs["server_name"], inputs["admin_user"]
    keys = inputs["admin_ssh_public_keys"]
    if not isinstance(keys, list) or len(keys) != 1:
        return False
    key = keys[0]
    if (not server["id"] or server["hostname" if provider == "vultr" else "name"] != name
            or port["input"] != inputs["ssh_port"] or port["output"] != inputs["ssh_port"]):
        return False

    guards = {"terraform_data.admin_user": user}
    if provider == "hetzner":
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
        if admin["name"] != user or keys != [key.strip()]:
            return False
        guards["terraform_data.admin_ssh_public_key"] = hashlib.sha256(key.strip().encode()).hexdigest()

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
    provider = parser.parse_args().provider
    try:
        accepted = admit(json.load(sys.stdin), provider)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, yaml.YAMLError):
        accepted = False
    if not accepted:
        sys.exit("Refused: the plan does not add only the missing guards for the retained bootstrap identity.")
    print("Only the expected bootstrap guard creations were admitted.")


if __name__ == "__main__":
    main()
