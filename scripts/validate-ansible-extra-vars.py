#!/usr/bin/env python3
"""Validate the narrow, non-secret overrides accepted by live Make targets."""

from __future__ import annotations

import argparse
import ipaddress
import re
from pathlib import Path

import yaml

ALLOWED_KEYS = {
    "ansible_host",
    "ansible_port",
    "firewall_forward_interface_contract",
    "public_site_canonical_url",
}
DNS_NAME = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)
CONTRACT_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
INTERFACE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,15}")


def validate(path: Path) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not document:
        raise ValueError("extra-vars document must be a non-empty mapping")

    unknown = sorted(set(document) - ALLOWED_KEYS)
    if unknown:
        raise ValueError("extra-vars document contains a non-allowlisted key")

    if "ansible_host" in document:
        host = document["ansible_host"]
        if not isinstance(host, str) or not host.strip():
            raise ValueError("ansible_host must be a non-empty string")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if DNS_NAME.fullmatch(host) is None:
                raise ValueError(
                    "ansible_host must be an IP address or DNS name"
                ) from None

    if "ansible_port" in document:
        port = document["ansible_port"]
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 1 <= port <= 65535
        ):
            raise ValueError("ansible_port must be an integer from 1 through 65535")

    if "public_site_canonical_url" in document:
        url = document["public_site_canonical_url"]
        # Origin only: the nginx-xhttp assert pins this value to
        # https://<nginx_xhttp.server_name>, so a path would never converge.
        if (
            not isinstance(url, str)
            or not url.startswith("https://")
            or "/" in url[len("https://"):]
        ):
            raise ValueError(
                "public_site_canonical_url must be an https origin (https://<host>)"
            )
        host = url[len("https://"):]
        if DNS_NAME.fullmatch(host) is None:
            raise ValueError("public_site_canonical_url host is not a valid DNS name")

    if "firewall_forward_interface_contract" in document:
        contracts = document["firewall_forward_interface_contract"]
        if not isinstance(contracts, list) or len(contracts) != 1:
            raise ValueError(
                "firewall_forward_interface_contract must contain exactly one entry"
            )
        contract = contracts[0]
        expected = {"name", "input_interface", "output_interface"}
        if not isinstance(contract, dict) or set(contract) != expected:
            raise ValueError("forwarding entry must contain exactly the required keys")
        if (
            not isinstance(contract["name"], str)
            or CONTRACT_NAME.fullmatch(contract["name"]) is None
        ):
            raise ValueError("forwarding name contains unsupported characters")
        for key in ("input_interface", "output_interface"):
            value = contract[key]
            if not isinstance(value, str) or INTERFACE_NAME.fullmatch(value) is None:
                raise ValueError(f"{key} is not a safe Linux interface name")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        validate(args.path)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        print(f"validate-ansible-extra-vars: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
