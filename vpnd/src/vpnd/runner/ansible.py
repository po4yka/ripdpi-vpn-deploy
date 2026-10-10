"""Resolve safe exact inventory host keys in the selected scope."""

import ipaddress
import json
import re
from .process import Cmd
from ..state import ipv4_limit


def playbook(ctx, name):
    return (
        Cmd.new("ansible-playbook")
        .args(
            [
                ctx.ansible_dir / "playbooks" / f"{name}.yml",
                "--inventory",
                ctx.ansible_dir / "inventory/generated.ini",
            ]
        )
        .cwd(ctx.root)
        .env("ANSIBLE_CONFIG", ctx.ansible_cfg())
        .env("VPN_SECRETS_FILE", ctx.secrets_file)
        .sensitive(ctx.secrets_file)
        .describe(f"ansible-playbook playbooks/{name}.yml")
    )


def inventory_limit(raw, env, provider, expected_ip=None):
    inventory = json.loads(raw)
    hostvars = inventory.get("_meta", {}).get("hostvars")
    if not isinstance(hostvars, dict):
        raise ValueError("inventory is missing hostvars")
    pending = ["vpn"]
    visited = set()
    candidates = set()
    while pending:
        group = pending.pop()
        if group in visited:
            continue
        visited.add(group)
        value = inventory.get(group)
        if not isinstance(value, dict):
            raise ValueError(f"inventory is missing group '{group}'")
        for field in ("hosts", "children"):
            values = value.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError("invalid inventory hosts/groups")
            if field == "hosts":
                candidates.update(values)
            else:
                pending.extend(values)
    selected = []
    for name in sorted(candidates):
        variables = hostvars.get(name)
        if not isinstance(variables, dict):
            raise ValueError(f"missing variables for inventory host '{name}'")
        for field in ("env", "provider"):
            if not isinstance(variables.get(field), str):
                raise ValueError(f"missing {field} for inventory host '{name}'")
        if variables["env"] != env or variables["provider"] != provider:
            continue
        address = variables.get("vpn_service_address", variables.get("ansible_host"))
        if not isinstance(address, str):
            raise ValueError(f"missing address for inventory host '{name}'")
        try:
            address = str(ipaddress.IPv4Address(address))
        except ipaddress.AddressValueError:
            raise ValueError(f"invalid IPv4 for inventory host '{name}'") from None
        if expected_ip is not None and expected_ip != address:
            continue
        if (
            not re.fullmatch(r"[A-Za-z0-9._-]+", name)
            or name in inventory
            or name in {"all", "ungrouped"}
        ):
            raise ValueError(f"inventory host '{name}' is not a safe exact limit")
        selected.append(name)
    if not selected or (expected_ip is not None and len(selected) != 1):
        raise ValueError(
            f"expected {'exactly one' if expected_ip is not None else 'at least one'} matching inventory hosts, found {len(selected)}"
        )
    return ",".join(selected)


async def scoped_limit(ctx, host=None):
    expected = ipv4_limit(*host) if host is not None else None
    command = (
        Cmd.new("ansible-inventory")
        .args(["--inventory", ctx.ansible_dir / "inventory/generated.ini", "--list"])
        .env("ANSIBLE_CONFIG", ctx.ansible_cfg())
        .cwd(ctx.root)
        .describe("resolve exact inventory hosts for the selected environment and provider")
    )
    output = await command.capture(ctx.explain)
    return (
        "<validated inventory host keys>"
        if ctx.explain
        else inventory_limit(output.stdout, ctx.env, ctx.provider, expected)
    )


def site(ctx):
    return playbook(ctx, "site")


def verify(ctx):
    return playbook(ctx, "verify")


def smoke(ctx):
    return playbook(ctx, "smoke-test")


def rotate(ctx):
    return playbook(ctx, "rotate-credentials")


def dry_run(ctx):
    return (
        site(ctx).args(["--check", "--diff"]).describe("ansible-playbook site.yml --check --diff")
    )
