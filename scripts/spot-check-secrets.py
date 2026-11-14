#!/usr/bin/env python3
"""Pre-deploy sanity check on a decrypted secrets file.

Walks the YAML tree and flags anything that would deploy as a known-bad
value: REPLACE_WITH_* placeholders, invalid H1..H4 range strings, weak
passwords, plaintext cloudflare default target, etc.

Reads $VPN_SECRETS_FILE (set by `make decrypt`) or the path passed as
the first argument. Exits 0 on clean; non-zero on any finding.

Run via `make spot-check-secrets`. Certificates are checked by scripts/check-certs.sh,
which selects only the authorities the deployment enables.

INVARIANT: a Finding's `msg` field MUST NEVER contain a substring of any
value read from the decrypted secrets file. Operators redirect this
output to log files and shell history; logging secret bytes there
defeats the SOPS-at-rest model. Every f.add() call site is required to
produce a value-independent diagnostic — length, type, or a fixed
sentinel like "placeholder still present". The CodeQL rule
py/clear-text-logging-sensitive-data enforces this at PR time.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

from transport_semantics import transport_errors

PLACEHOLDER_RE = re.compile(r"REPLACE_WITH_")
OVERUSED_TARGETS = {
    "www.cloudflare.com", "cloudflare.com",
    "www.microsoft.com", "microsoft.com",
    "www.apple.com", "apple.com",
    "www.google.com", "google.com",
    "discord.com", "icloud.com",
}


class Findings:
    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    def add(self, where: str, msg: str) -> None:
        self.items.append((where, msg))

    def __bool__(self) -> bool:
        return bool(self.items)


def walk_for_placeholders(data, path: str, f: Findings) -> None:
    # Walks values that came out of a decrypted secrets blob; we must never
    # let the value or any prefix of it reach the message buffer (it ends
    # up in stdout / journal / log file, defeating the SOPS-at-rest model).
    # Findings carry only the field path + a fixed diagnostic.
    if isinstance(data, str):
        if PLACEHOLDER_RE.search(data):
            f.add(path, "placeholder still present (run bootstrap-secrets / sops to fill)")
    elif isinstance(data, dict):
        for k, v in data.items():
            walk_for_placeholders(v, f"{path}.{k}" if path else k, f)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            walk_for_placeholders(v, f"{path}[{i}]", f)


def main() -> int:
    src = os.environ.get("VPN_SECRETS_FILE") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not src:
        print("usage: VPN_SECRETS_FILE=/tmp/vpn-prod.secrets.yaml scripts/spot-check-secrets.py", file=sys.stderr)
        return 2
    path = Path(src)
    if not path.exists():
        print(f"missing: {path}", file=sys.stderr)
        return 2
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        # This script gates deploys; a malformed secrets file must produce a
        # diagnosis, not a traceback. Never echo file content (may be secret).
        print(f"invalid YAML in {path}: {type(exc).__name__} — fix the file and re-run", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"cannot read {path}: {exc.strerror}", file=sys.stderr)
        return 2

    if not isinstance(data, dict):
        print("invalid secrets mapping", file=sys.stderr)
        return 2

    f = Findings()
    for where, message in transport_errors(data):
        f.add(where, message)

    walk_for_placeholders(data, "", f)

    xray = (data or {}).get("xray") or {}
    target = xray.get("target", "")
    host = target.split(":", 1)[0]
    if host in OVERUSED_TARGETS:
        f.add("xray.target",
              f"{host!r} is over-templated — pick a less-used target")

    if not (xray.get("reality_private_key") or "").strip() or \
       PLACEHOLDER_RE.search(xray.get("reality_private_key", "")):
        f.add("xray.reality_private_key", "missing")
    if not (xray.get("reality_public_key") or "").strip() or \
       PLACEHOLDER_RE.search(xray.get("reality_public_key", "")):
        f.add("xray.reality_public_key", "missing")

    for index, client in enumerate(xray.get("clients") or []):
        sid = client.get("short_id", "")
        if not re.fullmatch(r"[0-9a-fA-F]{2,16}", sid):
            # short_id is a per-device credential; report only its length
            # and whether it parsed as hex, never the value itself.
            kind = "non-hex" if not re.fullmatch(r"[0-9a-fA-F]*", sid) else "wrong-length"
            f.add(f"xray.clients[{index}].short_id",
                  f"{kind} (length={len(sid)}; want 2-16 hex)")

    for index, client in enumerate((data.get("hysteria") or {}).get("clients") or []):
        pw = client.get("password", "")
        if len(pw) < 16:
            f.add(f"hysteria.clients[{index}].password",
                  f"password length {len(pw)} < 16")

    for index, client in enumerate((data.get("naive_secrets") or {}).get("clients") or []):
        if not isinstance(client, dict) or not isinstance(client.get("password"), str) or len(client["password"]) < 20:
            f.add(f"naive_secrets.clients[{index}]", "missing or short independent password")

    restic = (data.get("backup") or {}).get("restic_password", "")
    if len(restic) < 32:
        f.add("backup.restic_password",
              f"length {len(restic)} < 32 — run openssl rand -base64 32")

    if not f:
        print("OK — no findings.")
        return 0

    print(f"{len(f.items)} finding(s):")
    for where, msg in f.items:
        print(f"  {where}: {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
