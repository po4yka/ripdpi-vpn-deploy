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
ENVIRONMENT = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
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


def host_identity(host):
    if not isinstance(host, str) or host.count(":") != 1:
        raise BindingError("invalid-host-binding")
    provider, environment = host.split(":")
    if provider not in PROVIDERS or ENVIRONMENT.fullmatch(environment) is None:
        raise BindingError("invalid-host-binding")
    return provider, environment


def resolve_binding(document, context, client, host, instance=None, *, enrollment=False):
    if not isinstance(client, str) or NAME.fullmatch(client) is None:
        raise BindingError("invalid-device-name")
    provider, environment = host_identity(host)
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


def registry_errors(doc: dict, *, allow_placeholders: bool = False, context: dict | None = None) -> list[tuple[str, str]]:
    """Bind each recovery key and fingerprint to its named device instance."""
    from transport_semantics import PLACEHOLDER
    errors = []
    registry = doc.get("client_registry") or {}
    if not isinstance(registry, dict):
        return [("client_registry", "must be a device mapping")]
    for index, instance in enumerate(doc.get("amneziawg_secrets", {}).get("instances", [])):
        for peer_index, peer in enumerate(instance.get("peers", [])):
            if peer.get("address_kind", "device") != "device":
                continue
            entry = registry.get(peer["name"])
            binding = entry.get("awg_binding") if isinstance(entry, dict) else None
            if not isinstance(binding, dict) or binding.get("instance") != instance["name"]:
                errors.append((f"amneziawg_secrets.instances.{index}.peers.{peer_index}",
                               "device peer requires registry binding"))
    for device, entry in registry.items():
        if (not isinstance(entry, dict) or not {
                "awg_binding", "awg_private_key", "awg_public_key_fingerprint", "awg_delivery_host"} <= entry.keys()):
            errors.append((f"client_registry.{device}", "incomplete AWG registry entry"))
            continue
        delivery_host = entry["awg_delivery_host"]
        if not isinstance(delivery_host, str):
            errors.append((f"client_registry.{device}.awg_delivery_host", "invalid AWG delivery host"))
        elif delivery_host:
            try:
                host_identity(delivery_host)
                if not isinstance(entry.get("hosts"), list) or delivery_host not in entry["hosts"]:
                    raise BindingError("invalid-host-binding")
            except BindingError:
                errors.append((f"client_registry.{device}.awg_delivery_host", "invalid AWG delivery host"))
        binding = entry.get("awg_binding")
        private = entry.get("awg_private_key", "")
        fingerprint = entry.get("awg_public_key_fingerprint", "")
        path = f"client_registry.{device}.awg_binding"
        if not isinstance(private, str) or not isinstance(fingerprint, str):
            errors.append((path, "invalid AWG recovery material"))
            continue
        if binding is None:
            if private or fingerprint:
                errors.append((path, "absent AWG binding must have no recovery material"))
            if any(peer.get("name") == device
                   for instance in doc.get("amneziawg_secrets", {}).get("instances", [])
                   for peer in instance.get("peers", [])):
                errors.append((path, "absent AWG binding has a retained device peer"))
            continue
        try:
            if not allow_placeholders and (PLACEHOLDER.fullmatch(private) or PLACEHOLDER.fullmatch(fingerprint)):
                errors.append((path, "unfilled REPLACE_WITH_* recovery material"))
                continue
            if allow_placeholders and PLACEHOLDER.fullmatch(private) and PLACEHOLDER.fullmatch(fingerprint):
                instances = doc["amneziawg_secrets"]["instances"]
                matches = [peer for item in instances if item["name"] == binding["instance"]
                           for peer in item["peers"] if peer["name"] == device]
                if len(matches) != 1:
                    raise ValueError
                continue
            selected = resolve_binding(doc, context or {}, device, binding["provider"] + ":" + binding["environment"], binding["instance"])
            if selected.identity != binding:
                raise ValueError
            peer_public = selected.peer["public_key"]
            if not PLACEHOLDER.fullmatch(fingerprint):
                expected = "sha256:" + __import__("hashlib").sha256(peer_public.encode()).hexdigest()[:16]
                if fingerprint.lower() != expected:
                    raise ValueError
            if not PLACEHOLDER.fullmatch(private) and public_key(private) != peer_public:
                raise ValueError
        except (ValueError, KeyError, TypeError, AttributeError):
            errors.append((path, "must match the named instance peer and recovery key"))
    return errors


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
