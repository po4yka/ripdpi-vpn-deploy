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

PLACEHOLDER = re.compile(r"REPLACE_WITH_[A-Z0-9_]+")


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


def _semantic_errors(doc: dict) -> list[tuple[str, str]]:
    """Validate relationships and network values JSON Schema cannot express."""
    errors: list[tuple[str, str]] = []

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
    return errors


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
    args = ap.parse_args()

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

    semantic_errors = _semantic_errors(doc)
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
