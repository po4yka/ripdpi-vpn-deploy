#!/usr/bin/env python3
"""Prepare encrypted private-IP observability PKI, without contacting a host.

The output is an encrypted PKI bundle, not complete deployment secrets. Merge
its runtime fields into SOPS only after the exact topology is approved. Never
reuse its per-node private keys or its authority keys as deployment identities.
"""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import tempfile


def _helpers():
    specification = importlib.util.spec_from_file_location(
        "observability_preparation",
        Path(__file__).with_name("prepare-observability-staging.py"),
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


helpers = _helpers()
ALIAS = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def validate_config(config):
    if (
        not isinstance(config, dict)
        or set(config)
        != {
            "schema_version",
            "collector_address",
            "observer_address",
            "node_ids",
            "recipient",
        }
        or config["schema_version"] != 1
    ):
        raise ValueError("config")
    for key in ("collector_address", "observer_address"):
        address = ipaddress.IPv4Address(config[key])
        if str(address) != config[key] or not (
            address in ipaddress.ip_network("10.0.0.0/8")
            or address in ipaddress.ip_network("172.16.0.0/12")
            or address in ipaddress.ip_network("192.168.0.0/16")
            or address in ipaddress.ip_network("100.64.0.0/10")
        ):
            raise ValueError("address")
    if config["collector_address"] == config["observer_address"]:
        raise ValueError("independence")
    nodes = config["node_ids"]
    if (
        not isinstance(nodes, list)
        or not 1 <= len(nodes) <= 10
        or any(not isinstance(node, str) or not ALIAS.fullmatch(node) for node in nodes)
        or len(set(nodes)) != len(nodes)
    ):
        raise ValueError("nodes")
    if not isinstance(config["recipient"], str) or not re.fullmatch(
        r"age1[0-9a-z]{58}", config["recipient"]
    ):
        raise ValueError("recipient")
    return config


def generate(config, directory):
    """Real OpenSSL authorities, IP SAN servers and unique client identities."""
    validate_config(config)
    receiver = helpers._certificate_authority(directory, "observability-receiver-ca")
    observer = helpers._certificate_authority(directory, "observability-observer-ca")
    ingress = helpers._certificate(
        directory,
        ca="observability-receiver-ca",
        name="ingress",
        common_name="collector",
        purpose="serverAuth",
        sans=("IP:" + config["collector_address"],),
    )
    kuma = helpers._certificate(
        directory,
        ca="observability-observer-ca",
        name="observer",
        common_name="observer",
        purpose="serverAuth",
        sans=("IP:" + config["observer_address"],),
    )
    senders = []
    for index, node in enumerate(sorted(config["node_ids"])):
        certificate = helpers._certificate(
            directory,
            ca="observability-receiver-ca",
            name=f"sender-{index}",
            common_name=node,
            purpose="clientAuth",
        )
        senders.append(
            {
                "node_id": node,
                "certificate_pem": certificate["certificate"],
                "private_key_pem": certificate["private_key"],
            }
        )
    return {
        "schema_version": 1,
        "runtime": {
            "observability_secrets": {
                "receiver_ca_pem": receiver["certificate"],
                "receiver_crl_pem": receiver["crl"],
                "ingress_certificate_pem": ingress["certificate"],
                "ingress_private_key_pem": ingress["private_key"],
                "senders": senders,
            },
            "observability_kuma_secrets": {
                "tls": {
                    "ca_pem": observer["certificate"],
                    "server_cert_pem": kuma["certificate"],
                    "server_key_pem": kuma["private_key"],
                }
            },
        },
        # Preserve the private CA state in the encrypted artifact for revocation.
        # This authority section must never be deployed onto an enrolled node.
        "authorities": {
            "receiver": receiver,
            "observer": observer,
            "files": {
                path.name: path.read_text()
                for path in directory.iterdir()
                if path.is_file() and path.name.startswith("observability-")
            },
        },
    }


def prepare(config_path, output):
    config = validate_config(
        json.loads(
            helpers._private_bytes(config_path, "config rejected"),
            object_pairs_hook=unique_object,
        )
    )
    absolute, parent, name = helpers._private_target(output, "output rejected")
    try:
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("output exists")
        # Temporary plaintext is private and removed on all normal/error exits.
        with tempfile.TemporaryDirectory(prefix="observability-pki-") as temporary:
            directory = Path(temporary).resolve()
            directory.chmod(0o700)
            bundle = generate(config, directory)
            ciphertext = helpers._encrypt_sops(bundle, config["recipient"])
        current = helpers._open_secure_directory(
            absolute.parent, "output rejected", private=True
        )
        try:
            if not helpers._same_descriptor(parent, current):
                raise ValueError("output changed")
        finally:
            os.close(current)
        helpers._write_private_at(parent, name, ciphertext)
        os.fsync(parent)
        current = helpers._open_secure_directory(
            absolute.parent, "output rejected", private=True
        )
        try:
            if not helpers._same_descriptor(parent, current):
                raise ValueError("output changed")
        finally:
            os.close(current)
    finally:
        os.close(parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.config, args.output)
    except (helpers.PreparationError, OSError, ValueError, TypeError, KeyError):
        print(
            "observability-pki: private input, output or cryptographic operation rejected",
            file=sys.stderr,
        )
        return 2
    print('{"schema_version":1,"state":"encrypted-pki-prepared"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
