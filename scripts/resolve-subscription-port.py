#!/usr/bin/env python3
"""Resolve the subscription listener port for one rendered inventory host."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import secrets
import sys
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
GROUP_VARS = ROOT / "ansible" / "group_vars"
INVENTORY = ROOT / "ansible" / "inventory" / "generated.ini"


def _load(name: str) -> dict[str, object]:
    path = GROUP_VARS / f"{name}.yml"
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"invalid group vars: {path}")
    return payload


def _cohort(host: str) -> str | None:
    if not INVENTORY.exists():
        return None
    section: str | None = None
    for raw in INVENTORY.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if (
            section
            and ":" not in section
            and line.split()[0] == host
            and section.startswith("vpn-")
        ):
            return section.removeprefix("vpn-")
    return None


def resolve(host: str, default: int) -> int:
    values: dict[str, object] = {}
    for name in ("all", "vpn"):
        values.update(_load(name))
    cohort = _cohort(host)
    if cohort:
        values.update(_load(f"vpn-{cohort}"))
    raw = values.get("subscription_port", default)
    if isinstance(raw, bool):
        raise ValueError("subscription_port must be an integer")
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("subscription_port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("subscription_port is outside 1..65535")
    return port


def bootstrap_grant(host: str, overrides: dict, expires: str = "") -> dict:
    """Use the role's lifetime contract; mutable metadata can only shorten it."""
    defaults = yaml.safe_load(
        (ROOT / "ansible/roles/subscription-host/defaults/main.yml").read_text()
    )["subscription"]
    subscription = defaults
    names = ["all", "vpn"]
    cohort = _cohort(host)
    if cohort:
        names.append(f"vpn-{cohort}")
    for name in names:
        block = _load(name).get("subscription")
        if block is not None:
            if not isinstance(block, dict):
                raise ValueError("subscription configuration must be an object")
            # Ansible replaces a dictionary at the higher precedence, rather
            # than inheriting individual keys from the prior group dictionary.
            subscription = block
    if (
        overrides.get("_replace_policy")
        or "bootstrap_max_lifetime_seconds" in overrides
    ):
        subscription = overrides
    lifetime = subscription.get(
        "bootstrap_max_lifetime_seconds", defaults["bootstrap_max_lifetime_seconds"]
    )
    if type(lifetime) is not int or not 60 <= lifetime <= 2592000:
        raise ValueError("bootstrap lifetime is outside 60..2592000 seconds")
    issued = int(time.time())
    if not 0 < issued <= 9999999999 - lifetime:
        raise ValueError("issued epoch is outside the bootstrap contract")
    deadline = issued + lifetime
    if expires:
        try:
            expiration = dt.date.fromisoformat(expires)
        except ValueError as exc:
            raise ValueError("expiry must be YYYY-MM-DD") from exc
        if expiration.isoformat() != expires:
            raise ValueError("expiry must be YYYY-MM-DD")
        shortened = int(
            dt.datetime.combine(expiration, dt.time(), dt.timezone.utc).timestamp()
        )
        if not issued < shortened <= deadline:
            raise ValueError("expiry must shorten the intrinsic future deadline")
        deadline = shortened
    return {
        "token": f"b1_{issued:010d}_{secrets.token_urlsafe(32)}",
        "expires": deadline,
        "lifetime": lifetime,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--default", type=int, default=8444)
    parser.add_argument("--bootstrap-grant", action="store_true")
    parser.add_argument("--expires", default="")
    args = parser.parse_args()
    try:
        if args.bootstrap_grant:
            overrides = json.load(sys.stdin)
            if not isinstance(overrides, dict):
                raise ValueError("subscription overrides must be an object")
            print(json.dumps(bootstrap_grant(args.host, overrides, args.expires)))
        else:
            print(resolve(args.host, args.default))
    except (ValueError, OSError, TypeError) as exc:
        print(f"resolve-subscription-port: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
