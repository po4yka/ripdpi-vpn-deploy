#!/usr/bin/env python3
"""Client payload drift check against the encrypted client_registry.

Renders nothing to disk and stores nothing: it recomputes the payload
identity (deploy-source-identity digest plus a hash of the consumed
Terraform outputs) for a device's recorded issuance options and compares
it with the identity recorded at last delivery.

Verdicts (stdout, single line):
  current   — identity unchanged since last delivery      (exit 0)
  stale     — identity changed; device must re-fetch      (exit 1)
              prints the changed component as a hint
  unknown   — no registry entry or no delivery recorded   (exit 2)

Modes:
  client-drift.py <client>                     verdict mode
  client-drift.py --print-identity --hosts h1,h2
                      print "<source> <outputs>" for the given host pairs
                      (used by issue-sub-token.sh at issuance time)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_PAIR = re.compile(r"^[a-z0-9][a-z0-9_-]*:[a-z0-9][a-z0-9_-]*$")

IDENTITY_KEYS = ("server_ipv4", "admin_user", "server_hostname")


def _secrets_file() -> Path:
    candidate = os.environ.get("SOPS_FILE") or os.environ.get("VPN_SECRETS_FILE")
    if not candidate:
        candidate = (
            Path.home()
            / ".config"
            / "vpn-provision"
            / f"{os.environ.get('ENV', 'prod')}.secrets.sops.yaml"
        )
    return Path(candidate).resolve()


def _registry_entry(client: str) -> dict | None:
    result = subprocess.run(
        [
            "sops",
            "--decrypt",
            "--extract",
            '["client_registry"]',
            "--output-type",
            "json",
            str(_secrets_file()),
        ],
        capture_output=True,
        text=True,
    )
    registry = json.loads(result.stdout or "{}") if result.returncode == 0 else {}
    # Tolerate a full-document dump (older sops --extract behaviour).
    if "client_registry" in registry and isinstance(registry["client_registry"], dict):
        registry = registry["client_registry"]
    entry = registry.get(client)
    return entry if isinstance(entry, dict) else None


def _source_digest() -> str:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "deploy-source-identity.sh"), "--digest"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"deploy-source-identity failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _outputs_digest(hosts: list[str]) -> str:
    """sha256 over the endpoint outputs each host pair contributes."""
    sops_files = [p for p in (os.environ.get("SOPS_FILES") or "").split(",") if p]
    accumulator = ""
    for index, pair in enumerate(hosts):
        provider, env = pair.split(":", 1)
        command_env = dict(os.environ, PROVIDER=provider, ENV=env)
        if index < len(sops_files):
            command_env["SOPS_FILE"] = sops_files[index]
        result = subprocess.run(
            [
                str(REPO_ROOT / "scripts" / "terraform-env.sh"),
                "output",
                "-json",
            ],
            capture_output=True,
            text=True,
            env=command_env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"terraform output failed for {pair}: {result.stderr.strip()}"
            )
        outputs = json.loads(result.stdout or "{}")
        for key in IDENTITY_KEYS:
            block = outputs.get(key) or {}
            value = block.get("value") if isinstance(block, dict) else block
            accumulator += f"{pair}:{key}={value};"
    return hashlib.sha256(accumulator.encode()).hexdigest()


def _print_identity(hosts: list[str]) -> int:
    try:
        print(_source_digest(), _outputs_digest(hosts))
    except RuntimeError as exc:
        print(f"client-drift: {exc}", file=sys.stderr)
        return 2
    return 0


def _verdict(client: str) -> tuple[str, str]:
    entry = _registry_entry(client)
    if entry is None:
        return "unknown", f"no client_registry entry for device '{client}'"
    identity = entry.get("last_payload_identity") or {}
    if not identity.get("source") and not identity.get("outputs"):
        return "unknown", "no delivery recorded in the registry entry"
    hosts = entry.get("hosts") or []
    invalid = [h for h in hosts if not HOST_PAIR.match(h)]
    if invalid:
        return "unknown", f"invalid host pairs in registry entry: {', '.join(invalid)}"
    try:
        source = _source_digest()
        outputs = _outputs_digest(hosts)
    except RuntimeError as exc:
        return "unknown", str(exc)
    changed = []
    if identity.get("source") and identity["source"] != source:
        changed.append("source")
    if identity.get("outputs") and identity["outputs"] != outputs:
        changed.append("outputs")
    if changed:
        return "stale", "changed: " + ", ".join(changed)
    return "current", "payload identity matches the last delivery"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", nargs="?", help="device name in client_registry")
    parser.add_argument(
        "--print-identity",
        action="store_true",
        help="print '<source> <outputs>' for --hosts instead of a verdict",
    )
    parser.add_argument("--hosts", default="", help="comma-separated provider:env pairs")
    args = parser.parse_args()

    if args.print_identity:
        hosts = [h for h in args.hosts.split(",") if h]
        if not hosts or any(not HOST_PAIR.match(h) for h in hosts):
            parser.error("--hosts requires comma-separated provider:env pairs")
        return _print_identity(hosts)

    if not args.client:
        parser.error("a client name is required")
    verdict, detail = _verdict(args.client)
    print(f"{verdict}: {detail}")
    return {"current": 0, "stale": 1, "unknown": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
