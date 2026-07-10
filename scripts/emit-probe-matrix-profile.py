#!/usr/bin/env python3
"""Emit one secret-bearing 0600 probe-matrix target profile atomically.

Usage:
  emit-probe-matrix-profile.py --target-id ID --endpoint ADDRESS --vars-file HOST_VARS --secrets-file DECRYPTED_SECRETS --output PROFILE_JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

import yaml


TECHNICAL_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid mapping in {path}")
    return data


def build(target_id: str, endpoint: str, variables: dict, secrets: dict) -> dict:
    if not TECHNICAL_ID.fullmatch(target_id) or not endpoint:
        raise ValueError("target id and endpoint are required")
    target = variables.get("probe_matrix_target") or {}
    protected = secrets.get("probe_matrix_target_secrets") or {}
    xray = secrets.get("xray") or {}
    ports = target.get("ports") or {}
    paths = target.get("paths") or {}
    server_name = target.get("server_name")
    required_ports = ("mtproto", "xhttp_vless", "xhttp_trojan", "tcp_trojan", "tls_non_443")
    if not isinstance(server_name, str) or not server_name or any(not isinstance(ports.get(name), int) for name in required_ports):
        raise ValueError("probe_matrix_target ports and server_name are required")
    document = {
        "schema_version": 1,
        "target_id": target_id,
        "endpoint": endpoint,
        "expected_xray_version": xray.get("version"),
        "expected_mtg_version": protected.get("mtg_version"),
        "expected_mtproto_helper_version": "gotd-v0.160.0",
        "protocols": {
            "mtproto": {"port": ports["mtproto"], "secret": protected.get("mtproto_secret")},
            "xhttp-vless": {"port": ports["xhttp_vless"], "server_name": server_name, "path": paths.get("xhttp_vless"), "uuid": protected.get("vless_uuid")},
            "xhttp-trojan": {"port": ports["xhttp_trojan"], "server_name": server_name, "path": paths.get("xhttp_trojan"), "password": protected.get("xhttp_trojan_password")},
            "tcp-trojan": {"port": ports["tcp_trojan"], "server_name": server_name, "password": protected.get("tcp_trojan_password")},
            "tls-non-443": {"port": ports["tls_non_443"], "server_name": server_name},
        },
    }
    if any(value in (None, "") for value in (document["expected_xray_version"], document["expected_mtg_version"], protected.get("mtproto_secret"), protected.get("vless_uuid"), protected.get("xhttp_trojan_password"), protected.get("tcp_trojan_password"), paths.get("xhttp_vless"), paths.get("xhttp_trojan"))):
        raise ValueError("probe matrix credentials, runtime version, and paths are required")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--vars-file", required=True, type=Path)
    parser.add_argument("--secrets-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        document = build(args.target_id, args.endpoint, load(args.vars_file), load(args.secrets_file))
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{args.output.name}.", dir=args.output.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, args.output)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"emit-probe-matrix-profile: {exc}", file=os.sys.stderr)
        return 1
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
