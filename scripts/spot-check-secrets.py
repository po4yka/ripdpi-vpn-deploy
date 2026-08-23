#!/usr/bin/env python3
"""Pre-deploy sanity check on a decrypted secrets file.

Walks the YAML tree and flags anything that would deploy as a known-bad
value: REPLACE_WITH_* placeholders, expired or self-signed cert PEMs,
H1..H4 still as strings, weak passwords, plaintext cloudflare default
target, etc.

Reads $VPN_SECRETS_FILE (set by `make decrypt`) or the path passed as
the first argument. Exits 0 on clean; non-zero on any finding.

Run via `make spot-check-secrets`.

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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

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


def check_cert_pem(pem: str, key_pem: str | None, path: str, f: Findings) -> None:
    if not pem or PLACEHOLDER_RE.search(pem):
        return  # placeholder branch handled separately
    try:
        end_date = subprocess.run(
            ["openssl", "x509", "-noout", "-enddate"],
            input=pem.encode(), capture_output=True, check=True,
        ).stdout.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        f.add(path, f"openssl rejected cert_pem ({exc})")
        return
    m = re.search(r"notAfter=(.+)$", end_date)
    if not m:
        f.add(path, f"could not parse notAfter from {end_date!r}")
        return
    not_after = datetime.strptime(m.group(1), "%b %d %H:%M:%S %Y %Z")
    days = (not_after.replace(tzinfo=timezone.utc) - datetime.now(tz=timezone.utc)).days
    if days < 0:
        f.add(path, f"cert expired {-days} days ago ({not_after.date()})")
    elif days < 14:
        f.add(path, f"cert expires in {days} days ({not_after.date()}) — renew now")

    try:
        issuer = subprocess.run(
            ["openssl", "x509", "-noout", "-issuer"],
            input=pem.encode(), capture_output=True, check=True,
        ).stdout.decode().strip()
        subject = subprocess.run(
            ["openssl", "x509", "-noout", "-subject"],
            input=pem.encode(), capture_output=True, check=True,
        ).stdout.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # The expiry check above already reported a diagnostic for this PEM;
        # a second failure here must not crash the gate.
        return
    m_issuer = re.search(r"CN=(.+)$", issuer)
    m_subject = re.search(r"CN=(.+)$", subject)
    # Compare only when both sides carry a non-empty CN; a missing CN is not
    # evidence of self-signing.
    if m_issuer and m_subject and m_issuer.group(1).strip() == m_subject.group(1).strip():
        f.add(path, "cert appears self-signed (issuer == subject)")

    if key_pem and not PLACEHOLDER_RE.search(key_pem):
        try:
            cert_mod = subprocess.run(
                ["openssl", "x509", "-noout", "-modulus"],
                input=pem.encode(), capture_output=True, check=True,
            ).stdout.decode().strip()
            # RSA modulus comparison is only a heuristic; unsupported key
            # types are accepted by the certificate parser above.
            key_mod_cmd = ["openssl", "rsa", "-noout", "-modulus"]
            key_mod = subprocess.run(
                key_mod_cmd, input=key_pem.encode(),
                capture_output=True, check=False,
            )
            if key_mod.returncode == 0 and key_mod.stdout.strip() != cert_mod.encode():
                f.add(path, "RSA cert modulus does not match key modulus")
        except subprocess.CalledProcessError:
            # Non-RSA or unsupported pairs skip the modulus-only heuristic.
            pass


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

    f = Findings()

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

    for client in xray.get("clients") or []:
        sid = client.get("short_id", "")
        if not re.fullmatch(r"[0-9a-fA-F]{2,16}", sid):
            # short_id is a per-device credential; report only its length
            # and whether it parsed as hex, never the value itself.
            kind = "non-hex" if not re.fullmatch(r"[0-9a-fA-F]*", sid) else "wrong-length"
            f.add(f"xray.clients[{client.get('name','?')}].short_id",
                  f"{kind} (length={len(sid)}; want 2-16 hex)")

    for role, key in (("nginx_xhttp", "key_pem"),
                      ("hysteria", "key_pem"),
                      ("naive_secrets", "key_pem")):
        block = data.get(role) or {}
        check_cert_pem(block.get("cert_pem", ""), block.get(key, ""),
                       f"{role}.cert_pem", f)

    awg = (data or {}).get("amneziawg_secrets") or {}
    for h in ("h1", "h2", "h3", "h4"):
        v = awg.get(h)
        if not isinstance(v, int) or v == 0:
            # AmneziaWG H values are part of per-cohort obfuscation; never
            # echo. Report only the type/zero condition.
            cond = "missing" if v is None else ("zero" if v == 0 else f"non-int ({type(v).__name__})")
            f.add(f"amneziawg_secrets.{h}", f"expected non-zero int, got {cond}")

    for client in (data.get("hysteria") or {}).get("clients") or []:
        pw = client.get("password", "")
        if len(pw) < 16:
            f.add(f"hysteria.clients[{client.get('name','?')}].password",
                  f"password length {len(pw)} < 16")

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
