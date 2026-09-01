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
    "network_exposure_gate",
}
DNS_NAME = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)
CONTRACT_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
INTERFACE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,15}")
SOURCE_ID = re.compile(r"[a-z][a-z0-9-]{0,63}")
HOST_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}")
SHA256 = re.compile(r"[0-9a-f]{64}")
NETWORK_EXPOSURE_KEYS = {
    "mode", "artifact", "trusted_key", "trusted_key_sha256", "source_id",
    "promotion_approved", "promotion_digest", "authorized_hosts",
}


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous YAML instead of accepting the last repeated field."""


def _construct_unique_mapping(loader: UniqueKeyLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError("extra-vars document contains a duplicate key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                _construct_unique_mapping)


def validate_network_exposure(config: object) -> None:
    if not isinstance(config, dict) or set(config) != NETWORK_EXPOSURE_KEYS:
        raise ValueError("network_exposure_gate must contain exactly the required keys")
    mode = config["mode"]
    if mode not in {"disabled", "log_only", "canary", "enforce"}:
        raise ValueError("network_exposure_gate mode is unsupported")
    if type(config["promotion_approved"]) is not bool:
        raise ValueError("network_exposure_gate promotion_approved must be boolean")
    hosts = config["authorized_hosts"]
    if (not isinstance(hosts, list) or len(hosts) != len(set(hosts))
            or any(not isinstance(host, str) or HOST_ALIAS.fullmatch(host) is None for host in hosts)):
        raise ValueError("network_exposure_gate authorized_hosts must contain unique exact aliases")
    if mode == "disabled":
        if (any(config[key] != "" for key in (
                "artifact", "trusted_key", "trusted_key_sha256", "source_id", "promotion_digest"))
                or config["promotion_approved"] or hosts):
            raise ValueError("network_exposure_gate disabled mode must contain no external inputs")
        return
    for key in ("artifact", "trusted_key"):
        value = config[key]
        if (not isinstance(value, str) or not value or len(value) > 4096
                or any(character in value for character in "\x00\r\n")
                or not Path(value).expanduser().is_absolute()):
            raise ValueError(f"network_exposure_gate {key} must be an absolute local path")
    if (not isinstance(config["trusted_key_sha256"], str)
            or SHA256.fullmatch(config["trusted_key_sha256"]) is None):
        raise ValueError("network_exposure_gate trusted_key_sha256 must be lowercase SHA-256")
    if not isinstance(config["source_id"], str) or SOURCE_ID.fullmatch(config["source_id"]) is None:
        raise ValueError("network_exposure_gate source_id is invalid")
    promoted = mode in {"canary", "enforce"}
    if promoted:
        if (config["promotion_approved"] is not True
                or not isinstance(config["promotion_digest"], str)
                or SHA256.fullmatch(config["promotion_digest"]) is None or not hosts):
            raise ValueError("network_exposure_gate promotion is incomplete")
    elif config["promotion_approved"] or config["promotion_digest"] != "" or hosts:
        raise ValueError("network_exposure_gate log_only mode cannot carry promotion authority")


def validate(path: Path) -> None:
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
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

    if "network_exposure_gate" in document:
        validate_network_exposure(document["network_exposure_gate"])


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
