"""Resolve private AWG device authority; errors contain categories only."""
from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import base64
import argparse
import json
import re
import sys

from transport_semantics import awg_errors, effective_awg_instances

NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
PROVIDERS = {"upcloud", "vultr", "scaleway", "hetzner"}


class BindingError(ValueError):
    """A bounded refusal with no private values."""


@dataclass(frozen=True)
class DeviceBinding:
    provider: str
    environment: str
    index: int
    instance: dict = field(repr=False)
    peer: dict = field(repr=False)

    @property
    def identity(self):
        return {"provider": self.provider, "environment": self.environment,
                "instance": self.instance["name"]}


def resolve_binding(document, context, client, host, instance=None, *, enrollment=False):
    if not isinstance(client, str) or NAME.fullmatch(client) is None:
        raise BindingError("invalid-device-name")
    if not isinstance(host, str) or host.count(":") != 1:
        raise BindingError("invalid-host-binding")
    provider, environment = host.split(":")
    if provider not in PROVIDERS or NAME.fullmatch(environment) is None:
        raise BindingError("invalid-host-binding")
    if not isinstance(document, dict) or not isinstance(context, dict):
        raise BindingError("invalid-awg-contract")
    raw = document.get("amneziawg_secrets")
    defaults, cohort = context.get("amneziawg", {}), context.get("amneziawg_cohort", {})
    if awg_errors(raw, defaults, cohort):
        raise BindingError("invalid-awg-contract")
    instances = effective_awg_instances(raw, defaults, cohort)
    peer_count = sum(peer["name"] == client for item in instances for peer in item["peers"])
    if enrollment and peer_count:
        raise BindingError("device-already-enrolled")
    if peer_count > 1:
        raise BindingError("ambiguous-device-binding")
    matches = []
    for index, effective in enumerate(instances):
        if instance is not None and effective["name"] != instance:
            continue
        peers = [peer for peer in effective["peers"] if peer["name"] == client]
        if enrollment:
            matches.append(DeviceBinding(provider, environment, index, effective, {}))
        elif peers:
            if peers[0].get("address_kind", "device") != "device":
                raise BindingError("routed-peer-not-device")
            try:
                server = ipaddress.IPv4Interface(effective["address_v4"])
                address = ipaddress.IPv4Interface(peers[0]["allowed_ips"])
                if (address.network.prefixlen != 32 or address.ip not in server.network
                        or address.ip in (server.ip, server.network.network_address, server.network.broadcast_address)):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise BindingError("invalid-device-address") from None
            matches.append(DeviceBinding(provider, environment, index, effective, peers[0]))
    if not matches:
        raise BindingError("missing-device-binding")
    if len(matches) != 1:
        raise BindingError("ambiguous-device-binding")
    result = matches[0]
    if not enrollment:
        try:
            entry = document["client_registry"][client]
            if (entry["awg_binding"] != result.identity
                    or entry["status"] not in ("issued", "delivered", "active", "stale")):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise BindingError("invalid-registry-binding") from None
    return result


def allocate_address(instance):
    """Find the first free IPv4 host in work bounded by the peer collection."""
    try:
        server = ipaddress.IPv4Interface(instance["address_v4"])
        candidate = int(server.network.network_address) + 1
        last = int(server.network.broadcast_address) - 1
        claims = [(int(server.ip), int(server.ip))]
        for peer in instance["peers"]:
            prefix = ipaddress.ip_network(peer["allowed_ips"], strict=True)
            if prefix.version == 4:
                claims.append((int(prefix.network_address), int(prefix.broadcast_address)))
        for start, end in sorted(claims):
            if start <= candidate <= end:
                candidate = end + 1
        if candidate > last:
            raise BindingError("address-pool-exhausted")
        return str(ipaddress.IPv4Address(candidate)) + "/32"
    except (ValueError, KeyError, TypeError) as failure:
        if isinstance(failure, BindingError):
            raise
        raise BindingError("invalid-address-pool") from None


def public_key(private):
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    try:
        raw = base64.b64decode(private, validate=True)
        if len(raw) != 32:
            raise ValueError
        result = X25519PrivateKey.from_private_bytes(raw).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return base64.b64encode(result).decode()
    except (ValueError, TypeError):
        raise BindingError('invalid-awg-key') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["normalize"])
    parser.parse_args()
    try:
        payload = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise BindingError("invalid-awg-contract")
        request = json.loads(payload)
        raw = request["secrets"]["amneziawg_secrets"]
        context = request["context"]
        defaults, cohort = context.get("amneziawg", {}), context.get("amneziawg_cohort", {})
        if awg_errors(raw, defaults, cohort):
            raise BindingError("invalid-awg-contract")
        json.dump(effective_awg_instances(raw, defaults, cohort), sys.stdout)
        return 0
    except (KeyError, ValueError, TypeError, AttributeError):
        print("invalid-awg-contract", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
