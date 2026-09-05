#!/usr/bin/env python3
"""Validate a secrets YAML file against the formal schema.

The schema (secrets/schema.json) is the contract that every Ansible
role consumes at deploy time. Today a malformed entry (missing key,
wrong type, fragmented URL) surfaces as a render-time error on the
VPS — `xray test -config` fails, or the role's restart handler dies
mid-play. This script catches that drift at PR time and at the
operator's pre-deploy-check stage.

Modes:
  default                Lenient: accepts REPLACE_WITH_* placeholders.
                         This is what runs in pre-commit on the example
                         schema and what an operator runs against a
                         half-filled draft.
  --strict               Reject any REPLACE_WITH_* placeholder. This is
                         what runs in pre-deploy-check against the real
                         decrypted secrets file.

Default input: VPN_SECRETS_FILE if set, otherwise
secrets/prod.secrets.example.yaml.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "secrets" / "schema.json"
DEFAULT_TARGET = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"
OBSERVABILITY_CONFIG = REPO_ROOT / "ansible" / "group_vars" / "all.yml"

PLACEHOLDER = re.compile(r"REPLACE_WITH_[A-Z0-9_]+")
AWG_FINGERPRINT = re.compile(r"^sha256:([0-9a-fA-F]{16})$")
OBSERVABILITY_ROTATION_MAX_SECONDS = 24 * 60 * 60


def _observability_selector_enabled() -> bool:
    """Read the single tracked observability enablement selector fail-closed."""
    try:
        metadata = OBSERVABILITY_CONFIG.lstat()
        if (
            not OBSERVABILITY_CONFIG.is_file()
            or OBSERVABILITY_CONFIG.is_symlink()
            or metadata.st_size > 1024 * 1024
        ):
            raise ValueError
        document = yaml.safe_load(OBSERVABILITY_CONFIG.read_text())
        contract = document["observability_contract"]
        if (
            not isinstance(contract, dict)
            or not isinstance(contract.get("enabled"), bool)
            or contract.get("schema_version") != 1
            or contract.get("credential_mode") != "systemd"
        ):
            raise ValueError
        return contract["enabled"]
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError("invalid tracked observability selector") from exc


def _awg_peer_pubkeys(doc: dict) -> dict[str, str]:
    """Map peer name -> public key across all AmneziaWG collections."""
    peers: dict[str, str] = {}
    sections = [doc.get("amneziawg_secrets") or {}]
    sections += (doc.get("amneziawg_secrets") or {}).get("instances") or []
    for section in sections:
        for peer in section.get("peers") or []:
            if isinstance(peer, dict) and peer.get("name") and peer.get("public_key"):
                peers[peer["name"]] = peer["public_key"]
    return peers


def _registry_errors(doc: dict) -> list[tuple[str, str]]:
    """Validate client_registry relationships JSON Schema cannot express."""
    errors: list[tuple[str, str]] = []
    registry = doc.get("client_registry") or {}
    if not isinstance(registry, dict):
        return [("client_registry", "must be a mapping of device name to entry")]
    awg_peers = _awg_peer_pubkeys(doc)
    for device, entry in registry.items():
        if not isinstance(entry, dict):
            continue
        fingerprint = entry.get("awg_public_key_fingerprint") or ""
        match = AWG_FINGERPRINT.match(fingerprint)
        if match:
            expected = {
                __import__("hashlib").sha256(key.encode()).hexdigest()[:16]
                for key in awg_peers.values()
            }
            if match.group(1).lower() not in expected:
                errors.append(
                    (
                        f"client_registry.{device}.awg_public_key_fingerprint",
                        "does not match any amneziawg_secrets peer public key",
                    )
                )
    return errors


def _walk_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def _duplicate_values(items: list[object], key: str) -> set[str]:
    values = [item[key] for item in items if isinstance(item, dict) and key in item]
    return {value for value in values if values.count(value) > 1}


def _silence_gateway_authorities(observability: dict) -> list[str]:
    gateway = observability.get("silence_gateway") or {}
    material = [
        value
        for key, value in gateway.items()
        if key == "sender_token" or key.endswith("_pem")
    ]
    material.extend(operator.get("token") for operator in gateway.get("operators", []))
    return [value for value in material if isinstance(value, str)]


def _rotation_interval_is_bounded(rotation: dict) -> bool:
    started_value = rotation.get("started_at")
    expires_value = rotation.get("expires_at")
    if all(
        isinstance(value, str) and PLACEHOLDER.fullmatch(value)
        for value in (started_value, expires_value)
    ):
        return True
    if not all(isinstance(value, str) for value in (started_value, expires_value)):
        return False
    try:
        started = datetime.fromisoformat(started_value.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(expires_value.replace("Z", "+00:00"))
        if started.tzinfo is None or expires.tzinfo is None:
            return False
        seconds = (expires - started).total_seconds()
    except (KeyError, TypeError, ValueError):
        return False
    return 0 < seconds <= OBSERVABILITY_ROTATION_MAX_SECONDS


def _observability_rotation_errors(
    observability: dict, deadman: dict
) -> list[tuple[str, str]]:
    """Enforce one complete, bounded credential-authority rotation at a time."""
    errors: list[tuple[str, str]] = []
    control_rotation = observability.get("rotation")
    deadman_rotation = deadman.get("rotation")
    active = [rotation for rotation in (control_rotation, deadman_rotation) if rotation]
    if len(active) > 1:
        return [
            (
                "observability rotation",
                "only one observability credential authority may rotate at a time",
            )
        ]
    if not active:
        return errors

    rotation = active[0]
    if not isinstance(rotation, dict):
        return [("observability rotation", "rotation must be a mapping")]
    authority = rotation.get("authority")
    common = {"authority", "started_at", "expires_at"}
    if control_rotation:
        required_by_authority = {
            "receiver": common | {"next_ca_pem"},
            "ingress": common
            | {"next_certificate_pem", "next_private_key_pem"},
            "sender": common
            | {
                "sender_node_id",
                "next_certificate_pem",
                "next_private_key_pem",
            },
            "telegram": common | {"next_token"},
        }
    else:
        required_by_authority = {
            "pulse": common | {"next_token"},
            "telegram": common | {"next_token"},
        }
    required = required_by_authority.get(authority)
    if required is None or set(rotation) != required:
        errors.append(
            (
                "observability rotation",
                "rotation must contain exactly one complete credential authority",
            )
        )
    if not _rotation_interval_is_bounded(rotation):
        errors.append(
            (
                "observability rotation",
                "rotation interval must be positive and no longer than 24 hours",
            )
        )

    senders = observability.get("senders") or []
    if authority == "sender" and rotation.get("sender_node_id") not in {
        sender.get("node_id") for sender in senders if isinstance(sender, dict)
    }:
        errors.append(("observability rotation", "sender authority does not exist"))

    active_material = {
        value
        for value in (
            observability.get("receiver_ca_pem"),
            observability.get("ingress_certificate_pem"),
            observability.get("ingress_private_key_pem"),
            (observability.get("telegram") or {}).get("bot_token"),
            (observability.get("telegram") or {}).get("relay_auth_token"),
            deadman.get("pulse_token"),
            (deadman.get("telegram") or {}).get("bot_token"),
        )
        if isinstance(value, str)
    }
    active_material.update(
        value
        for sender in senders
        if isinstance(sender, dict)
        for value in (sender.get("certificate_pem"), sender.get("private_key_pem"))
        if isinstance(value, str)
    )
    active_material.update(_silence_gateway_authorities(observability))
    next_material = [
        value
        for key, value in rotation.items()
        if key.startswith("next_") and isinstance(value, str)
    ]
    if len(next_material) != len(set(next_material)) or any(
        value in active_material for value in next_material
    ):
        errors.append(
            (
                "observability rotation",
                "next credential authority must be unique",
            )
        )
    return errors


def _semantic_errors(
    doc: dict, *, observability_enabled: bool = False
) -> list[tuple[str, str]]:
    """Validate relationships and network values JSON Schema cannot express."""
    errors: list[tuple[str, str]] = []

    if observability_enabled and not all(
        isinstance(doc.get(name), dict)
        for name in ("observability_secrets", "observability_deadman_secrets")
    ):
        errors.append(
            (
                "observability secrets required when enabled",
                "both control-plane and dead-man secret blocks are required",
            )
        )

    xray = doc.get("xray") or {}
    xray_clients = xray.get("clients") or []
    client_names = {client.get("name") for client in xray_clients if isinstance(client, dict)}
    for key in ("name", "uuid", "short_id"):
        if _duplicate_values(xray_clients, key):
            errors.append(("xray.clients", f"duplicate {key}"))
    cohorts = xray.get("cohorts") or []
    if _duplicate_values(cohorts, "name"):
        errors.append(("xray.cohorts", "duplicate name"))
    for cohort_index, cohort in enumerate(cohorts):
        if not isinstance(cohort, dict):
            continue
        refs = cohort.get("clients") or []
        if len(refs) != len(set(refs)):
            errors.append((f"xray.cohorts.{cohort_index}.clients", "duplicate client reference"))
        for name in refs:
            if name not in client_names:
                errors.append((f"xray.cohorts.{cohort_index}.clients", "unknown xray client reference"))

    for path, peers in [("amneziawg_secrets.peers", (doc.get("amneziawg_secrets") or {}).get("peers") or [])]:
        for key in ("name", "public_key"):
            if _duplicate_values(peers, key):
                errors.append((path, f"duplicate {key}"))
        for index, peer in enumerate(peers):
            if not isinstance(peer, dict):
                continue
            try:
                ipaddress.ip_network(peer.get("allowed_ips", ""), strict=False)
            except ValueError:
                errors.append((f"{path}.{index}.allowed_ips", "must be a valid IPv4 or IPv6 CIDR"))

    instances = (doc.get("amneziawg_secrets") or {}).get("instances") or []
    if _duplicate_values(instances, "name"):
        errors.append(("amneziawg_secrets.instances", "duplicate name"))
    if _duplicate_values(instances, "listen_port"):
        errors.append(("amneziawg_secrets.instances", "duplicate listen_port"))
    for index, instance in enumerate(instances):
        if not isinstance(instance, dict):
            continue
        for field in ("address_v4", "address_v6"):
            if field not in instance:
                continue
            try:
                ipaddress.ip_network(instance[field], strict=False)
            except ValueError:
                errors.append((f"amneziawg_secrets.instances.{index}.{field}", "must be a valid IPv4 or IPv6 CIDR"))
        peers = instance.get("peers") or []
        for key in ("name", "public_key"):
            if _duplicate_values(peers, key):
                errors.append((f"amneziawg_secrets.instances.{index}.peers", f"duplicate {key}"))
        for peer_index, peer in enumerate(peers):
            if not isinstance(peer, dict):
                continue
            try:
                ipaddress.ip_network(peer.get("allowed_ips", ""), strict=False)
            except ValueError:
                errors.append((f"amneziawg_secrets.instances.{index}.peers.{peer_index}.allowed_ips", "must be a valid IPv4 or IPv6 CIDR"))

    for path, clients in [("hysteria.clients", (doc.get("hysteria") or {}).get("clients") or [])]:
        if _duplicate_values(clients, "name"):
            errors.append((path, "duplicate name"))
    variants = (doc.get("snell_secrets") or {}).get("variants") or []
    if _duplicate_values(variants, "id"):
        errors.append(("snell_secrets.variants", "duplicate id"))
    psks = [item.get("psk") for item in variants if isinstance(item, dict)]
    if len(psks) != len(set(psks)):
        errors.append(("snell_secrets.variants", "PSKs must be unique across variants"))
    all_userkeys: list[str] = []
    for index, variant in enumerate(variants):
        users = variant.get("users") or [] if isinstance(variant, dict) else []
        for key in ("name", "userkey"):
            if _duplicate_values(users, key):
                errors.append((f"snell_secrets.variants.{index}.users", f"duplicate {key}"))
        all_userkeys.extend(user.get("userkey") for user in users if isinstance(user, dict) and user.get("userkey"))
    if len(all_userkeys) != len(set(all_userkeys)):
        errors.append(("snell_secrets.variants.users", "userkeys must be unique across variants"))

    observability = doc.get("observability_secrets") or {}
    deadman = doc.get("observability_deadman_secrets") or {}
    senders = observability.get("senders") or []
    if ("ui_username" in observability) != ("ui_password" in observability):
        errors.append(
            (
                "observability UI credentials",
                "username and password must be configured together",
            )
        )
    for key in ("node_id", "certificate_pem", "private_key_pem"):
        if _duplicate_values(senders, key):
            errors.append(
                (
                    "observability_secrets.senders",
                    f"duplicate observability credential authority ({key})",
                )
            )
    authorities = [
        observability.get("receiver_ca_pem"),
        observability.get("ingress_certificate_pem"),
        observability.get("ingress_private_key_pem"),
        observability.get("ui_password"),
        (observability.get("telegram") or {}).get("bot_token"),
        (observability.get("telegram") or {}).get("relay_auth_token"),
        deadman.get("pulse_token"),
        deadman.get("canary_token"),
        (deadman.get("pulse_tls") or {}).get("ca_pem"),
        (deadman.get("pulse_tls") or {}).get("server_cert_pem"),
        (deadman.get("pulse_tls") or {}).get("server_key_pem"),
        (deadman.get("telegram") or {}).get("bot_token"),
    ]
    authorities.extend(
        value
        for sender in senders
        if isinstance(sender, dict)
        for value in (sender.get("certificate_pem"), sender.get("private_key_pem"))
    )
    actual_authorities = [value for value in authorities if isinstance(value, str)]
    actual_authorities.extend(_silence_gateway_authorities(observability))
    gateway = observability.get("silence_gateway") or {}
    if _duplicate_values(gateway.get("operators", []), "owner"):
        errors.append(
            ("observability_secrets.silence_gateway.operators", "duplicate owner")
        )
    if len(actual_authorities) != len(set(actual_authorities)):
        errors.append(
            (
                "observability_secrets",
                "duplicate observability credential authority",
            )
        )
    errors.extend(_observability_rotation_errors(observability, deadman))
    return errors


def _observability_topology_errors(
    doc: dict, topology_path: Path
) -> list[tuple[str, str]]:
    """Bind sender credential identities to the validated VPN topology."""
    try:
        metadata = topology_path.lstat()
        if (
            not topology_path.is_file()
            or topology_path.is_symlink()
            or metadata.st_size > 1024 * 1024
        ):
            raise ValueError
        topology = json.loads(topology_path.read_text())
        nodes = topology["nodes"]
        if not isinstance(nodes, list):
            raise ValueError
        vpn_node_ids = {
            node["node_id"]
            for node in nodes
            if isinstance(node, dict) and node.get("host_class") == "vpn"
        }
        if not vpn_node_ids or any(
            not isinstance(node_id, str) for node_id in vpn_node_ids
        ):
            raise ValueError
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return [("observability topology", "cannot validate sender identities")]

    senders = (doc.get("observability_secrets") or {}).get("senders") or []
    sender_node_ids = {
        sender.get("node_id") for sender in senders if isinstance(sender, dict)
    }
    if sender_node_ids != vpn_node_ids:
        return [
            (
                "observability_secrets.senders",
                "observability sender node IDs must exactly match topology VPN node IDs",
            )
        ]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "secrets_file",
        nargs="?",
        help="Path to a secrets YAML file. Defaults to "
        "$VPN_SECRETS_FILE or secrets/prod.secrets.example.yaml.",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Reject any REPLACE_WITH_* placeholder. Run this against "
        "real secrets before deploy.",
    )
    ap.add_argument(
        "--print-observability-selector",
        action="store_true",
        help="Print the validated tracked observability enablement selector.",
    )
    ap.add_argument(
        "--observability-topology",
        type=Path,
        help="Validated topology JSON used to bind exact sender node identities.",
    )
    args = ap.parse_args()

    if args.print_observability_selector:
        try:
            print("true" if _observability_selector_enabled() else "false")
        except ValueError:
            print("validate-secrets: invalid tracked observability selector", file=sys.stderr)
            return 2
        return 0

    target = (
        Path(args.secrets_file)
        if args.secrets_file
        else Path(os.environ.get("VPN_SECRETS_FILE") or DEFAULT_TARGET)
    )
    if not target.is_file():
        print(f"validate-secrets: not a file: {target}", file=sys.stderr)
        return 2

    try:
        import jsonschema
    except ImportError:
        print(
            "validate-secrets: missing 'jsonschema' — `pip install jsonschema`",
            file=sys.stderr,
        )
        return 2

    schema = json.loads(SCHEMA.read_text())
    try:
        doc = yaml.safe_load(target.read_text()) or {}
    except yaml.YAMLError as exc:
        print(f"validate-secrets: YAML parse error: {exc}", file=sys.stderr)
        return 1

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        print(f"validate-secrets: {len(errors)} schema violation(s) in {target}:",
              file=sys.stderr)
        for e in errors:
            loc = ".".join(str(p) for p in e.absolute_path) or "<root>"
            print(f"  {loc}: failed {e.validator} constraint", file=sys.stderr)
        return 1

    try:
        observability_enabled = (
            _observability_selector_enabled() if args.strict else False
        )
    except ValueError:
        print("validate-secrets: invalid tracked observability selector", file=sys.stderr)
        return 2
    semantic_errors = _semantic_errors(
        doc,
        observability_enabled=observability_enabled,
    ) + _registry_errors(doc)
    if args.observability_topology is not None:
        semantic_errors += _observability_topology_errors(
            doc, args.observability_topology
        )
    if semantic_errors:
        print(f"validate-secrets: {len(semantic_errors)} semantic violation(s) in {target}:", file=sys.stderr)
        for loc, message in semantic_errors:
            print(f"  {loc}: {message}", file=sys.stderr)
        return 1

    if args.strict:
        offenders = []
        for path, value in _walk_strings(doc):
            if PLACEHOLDER.search(value):
                offenders.append((path, value))
        if offenders:
            print(
                f"validate-secrets: --strict found {len(offenders)} "
                f"unfilled REPLACE_WITH_* placeholder(s) in {target}:",
                file=sys.stderr,
            )
            for path, _value in offenders[:20]:
                print(f"  {path}", file=sys.stderr)
            if len(offenders) > 20:
                print(f"  ... and {len(offenders) - 20} more", file=sys.stderr)
            return 1

    print(f"validate-secrets: OK — {target} conforms to schema"
          + (" (strict)" if args.strict else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
