#!/usr/bin/env python3
"""Normalize fleet manifest and live observations into stable status output."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from typing import Any, Iterable


DECLARED_KEYS = (
    "status",
    "schema_version",
    "generated_at",
    "hostname",
    "enabled_transports",
    "public_listeners",
    "security_controls",
    "recovery",
)
UNKNOWN_VALUES = {"", "?", "-", "unknown"}
SECURITY_TYPES = {
    "ssh_strict": bool,
    "ssh_allow_tcp_forwarding": bool,
    "ssh_prune_moduli": bool,
    "unattended_upgrades": bool,
    "fail2ban": bool,
    "crowdsec": bool,
    "firewall_egress_policy": str,
}
RECOVERY_TYPES = {
    "backup": {"enabled": bool, "local_repo": str, "remote_sync": bool},
    "watchdog": {"enabled": bool, "state_file": str},
    "monitoring": {"enabled": bool, "node_exporter_listen": str},
}


def _empty_declared(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "schema_version": None,
        "generated_at": None,
        "hostname": None,
        "enabled_transports": [],
        "public_listeners": [],
        "security_controls": {},
        "recovery": {},
    }


def _typed_subset(source: dict[str, Any], types: dict[str, type]) -> dict[str, Any] | None:
    result = {}
    for key, expected_type in types.items():
        if key not in source:
            continue
        if not isinstance(source[key], expected_type):
            return None
        result[key] = source[key]
    return result


def _sanitize_capabilities(
    listeners: list[Any], security: dict[str, Any], recovery: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]] | None:
    clean_listeners = []
    for listener in listeners:
        if not isinstance(listener, dict):
            return None
        if not isinstance(listener.get("proto"), str) or not isinstance(listener.get("role"), str):
            return None
        clean_listener = {"proto": listener["proto"], "role": listener["role"]}
        if "port" in listener:
            if isinstance(listener["port"], bool) or not isinstance(listener["port"], int):
                return None
            clean_listener["port"] = listener["port"]
        if "range" in listener:
            if not isinstance(listener["range"], str):
                return None
            clean_listener["range"] = listener["range"]
        clean_listeners.append(clean_listener)

    clean_security = _typed_subset(security, SECURITY_TYPES)
    if clean_security is None:
        return None
    clean_recovery = {}
    for section, field_types in RECOVERY_TYPES.items():
        if section not in recovery:
            continue
        if not isinstance(recovery[section], dict):
            return None
        clean_section = _typed_subset(recovery[section], field_types)
        if clean_section is None:
            return None
        clean_recovery[section] = clean_section
    if "rollback_artifacts" in recovery:
        artifacts = recovery["rollback_artifacts"]
        if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
            return None
        clean_recovery["rollback_artifacts"] = list(artifacts)
    return clean_listeners, clean_security, clean_recovery


def normalize_manifest(
    raw: str,
    *,
    expected_provider: str,
    expected_environment: str,
    available: bool,
) -> dict[str, Any]:
    """Return only the supported, non-secret schema-1 capability fields."""
    if not available:
        return _empty_declared("unavailable")
    if not raw.strip():
        return _empty_declared("missing")
    try:
        manifest = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _empty_declared("invalid")
    if not isinstance(manifest, dict):
        return _empty_declared("invalid")

    schema_version = manifest.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        return _empty_declared("invalid")
    if schema_version != 1:
        declared = _empty_declared("unsupported")
        declared["schema_version"] = schema_version
        generated_at = manifest.get("generated_at")
        declared["generated_at"] = generated_at if isinstance(generated_at, str) else None
        return declared

    generated_at = manifest.get("generated_at")
    hostname = manifest.get("hostname")
    provider = manifest.get("provider")
    environment = manifest.get("environment")
    transports = manifest.get("enabled_transports")
    listeners = manifest.get("public_listeners")
    security = manifest.get("security_controls")
    recovery = manifest.get("recovery")
    valid_types = (
        isinstance(generated_at, str)
        and isinstance(hostname, str)
        and isinstance(provider, str)
        and isinstance(environment, str)
        and isinstance(transports, list)
        and all(isinstance(item, str) for item in transports)
        and isinstance(listeners, list)
        and isinstance(security, dict)
        and isinstance(recovery, dict)
    )
    if not valid_types or provider != expected_provider or environment != expected_environment:
        return _empty_declared("invalid")
    sanitized = _sanitize_capabilities(listeners, security, recovery)
    if sanitized is None:
        return _empty_declared("invalid")
    clean_listeners, clean_security, clean_recovery = sanitized

    return {
        "status": "ok",
        "schema_version": 1,
        "generated_at": generated_at,
        "hostname": hostname,
        "enabled_transports": list(transports),
        "public_listeners": clean_listeners,
        "security_controls": clean_security,
        "recovery": clean_recovery,
    }


def _nullable(value: str | None) -> str | None:
    if value is None or value.strip().lower() in UNKNOWN_VALUES:
        return None
    return value.strip()


def build_record(
    *,
    provider: str,
    environment: str,
    address: str | None,
    terraform_output: str,
    ssh: str,
    asn: str | None,
    xray_version: str | None,
    config_updated_at: str | None,
    watchdog: str,
    tcp_443: str,
    manifest_raw: str,
    manifest_available: bool,
) -> dict[str, Any]:
    """Keep declared capabilities and live observations in separate layers."""
    normalized_asn = _nullable(asn)
    if normalized_asn is not None and not re.fullmatch(r"AS[0-9]+", normalized_asn):
        normalized_asn = None
    return {
        "identity": {
            "provider": provider,
            "environment": environment,
            "address": _nullable(address),
        },
        "declared": normalize_manifest(
            manifest_raw,
            expected_provider=provider,
            expected_environment=environment,
            available=manifest_available,
        ),
        "observed": {
            "terraform_output": terraform_output if terraform_output in {"ok", "missing"} else "missing",
            "ssh": ssh if ssh in {"ok", "unreachable", "not_attempted"} else "not_attempted",
            "asn": normalized_asn,
            "xray_version": _nullable(xray_version),
            "config_updated_at": _nullable(config_updated_at),
            "watchdog": watchdog if watchdog in {"ok", "fail"} else "unknown",
            "tcp_443": tcp_443 if tcp_443 in {"reachable", "blocked"} else "not_probed",
        },
    }


def render_json(records: Iterable[dict[str, Any]]) -> str:
    payload = {"schema_version": 1, "hosts": list(records)}
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_table(records: Iterable[dict[str, Any]]) -> str:
    rows = []
    for record in records:
        identity = record["identity"]
        declared = record["declared"]
        observed = record["observed"]
        transports = declared["enabled_transports"]
        rows.append(
            (
                identity["provider"],
                identity["environment"],
                identity["address"] or "missing",
                observed["asn"] or "unknown",
                observed["xray_version"] or "unknown",
                observed["config_updated_at"] or "unknown",
                observed["watchdog"],
                observed["tcp_443"],
                declared["status"],
                ",".join(transports) if transports else "none",
            )
        )
    headers = (
        "PROV",
        "ENV",
        "IP",
        "ASN",
        "XRAY_VER",
        "LAST_DEPLOY",
        "WATCHDOG",
        "TCP_443",
        "MANIFEST",
        "TRANSPORTS",
    )
    widths = [max(len(str(value)) for value in (header, *(row[index] for row in rows))) for index, header in enumerate(headers)]
    lines = [" ".join(header.ljust(widths[index]) for index, header in enumerate(headers))]
    lines.append(" ".join("-" * width for width in widths))
    lines.extend(" ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)) for row in rows)
    return "\n".join(lines) + "\n"


def _decode_manifest(encoded: str, available: bool) -> str:
    if not available or not encoded.strip():
        return ""
    try:
        return base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return "{invalid-base64"


def _read_jsonl() -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(sys.stdin, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL record at line {line_number}: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"invalid JSONL record at line {line_number}: expected object")
        records.append(record)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--provider", required=True)
    record.add_argument("--environment", required=True)
    record.add_argument("--address", default="")
    record.add_argument("--terraform-output", required=True)
    record.add_argument("--ssh", required=True)
    record.add_argument("--asn", default="")
    record.add_argument("--xray-version", default="")
    record.add_argument("--config-updated-at", default="")
    record.add_argument("--watchdog", default="unknown")
    record.add_argument("--tcp-443", default="not_probed")
    record.add_argument("--manifest-available", choices=("true", "false"), required=True)
    render = subparsers.add_parser("render")
    render.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "record":
            available = args.manifest_available == "true"
            manifest_raw = _decode_manifest(sys.stdin.read(), available)
            result = build_record(
                provider=args.provider,
                environment=args.environment,
                address=args.address,
                terraform_output=args.terraform_output,
                ssh=args.ssh,
                asn=args.asn,
                xray_version=args.xray_version,
                config_updated_at=args.config_updated_at,
                watchdog=args.watchdog,
                tcp_443=args.tcp_443,
                manifest_raw=manifest_raw,
                manifest_available=available,
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        else:
            records = _read_jsonl()
            sys.stdout.write(render_json(records) if args.json else render_table(records))
    except ValueError as exc:
        print(f"fleet-status: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
