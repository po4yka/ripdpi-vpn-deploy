#!/usr/bin/env python3
"""Resolve the subscription listener port for one rendered inventory host."""

from __future__ import annotations

import argparse
import pathlib
import sys

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--default", type=int, default=8444)
    args = parser.parse_args()
    try:
        print(resolve(args.host, args.default))
    except ValueError as exc:
        print(f"resolve-subscription-port: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
