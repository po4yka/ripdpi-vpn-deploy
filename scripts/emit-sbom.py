#!/usr/bin/env python3
"""Emit a CycloneDX 1.5 SBOM for the pinned deploy.

Source of truth for pinned binaries:
  * secrets/prod.secrets.example.yaml — versions + release sha256s for
    xray, hysteria, geodata pins
  * scripts/scan-reality-targets.sh — RealiTLScanner pin
  * AmneziaWG go / tools — version strings from the schema (sha256
    pinning isn't part of v1 schema; recorded as "not-pinned")

System packages (restic, age, sops, gitleaks) live in the operator
workstation / VPS distro and are out of scope — those are tracked by
the host's package manager, not this repo.

Usage:
  scripts/emit-sbom.py                       # writes sbom/example.json
  VPN_SECRETS_FILE=/tmp/vpn-prod.secrets.yaml SBOM_LABEL=prod scripts/emit-sbom.py
                                             # writes sbom/prod.json
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re
import sys
import uuid

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "secrets" / "prod.secrets.example.yaml"
SBOM_DIR = REPO_ROOT / "sbom"
SBOM_DIR.mkdir(exist_ok=True)
SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.-]+$")


def _purl(scheme: str, *parts: str, **q: str) -> str:
    """Build a Package URL string."""
    base = f"pkg:{scheme}/" + "/".join(parts)
    if q:
        base += "?" + "&".join(f"{k}={v}" for k, v in q.items() if v)
    return base


def _release_hash(label: str, value: str | None) -> dict | None:
    if not value or value == "REPLACE_WITH_RELEASE_SHA256":
        return None
    return {"alg": "SHA-256", "content": value, "label": label}


def _public_str(mapping: dict, key: str) -> str | None:
    value = mapping.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _sbom_label(src_path: pathlib.Path) -> str:
    if src_path == DEFAULT_INPUT:
        return "example"
    label = os.environ.get("SBOM_LABEL", "custom")
    if not SAFE_LABEL.fullmatch(label) or label in {".", ".."}:
        raise ValueError("SBOM_LABEL must contain only letters, digits, dots, underscores, or dashes")
    return label


def component(name: str, version: str, purl: str, hashes: list[dict],
              source_url: str, description: str) -> dict:
    bom_ref = f"{name}@{version}"
    c: dict = {
        "type": "application",
        "bom-ref": bom_ref,
        "name": name,
        "version": version,
        "purl": purl,
        "externalReferences": [
            {"type": "distribution", "url": source_url},
        ],
        "description": description,
    }
    real_hashes = [h for h in hashes if h]
    if real_hashes:
        # CycloneDX hash entries don't carry our extra "label" — drop it
        c["hashes"] = [{"alg": h["alg"], "content": h["content"]} for h in real_hashes]
    return c


def reali_pin() -> tuple[str, str]:
    """Read the pinned RealiTLScanner version + sha256 from the script."""
    src = (REPO_ROOT / "scripts" / "scan-reality-targets.sh").read_text()
    ver = re.search(r'REALI_VERSION="([^"]+)"', src)
    sha = re.search(r'REALI_LINUX_SHA256="([^"]+)"', src)
    return (ver.group(1) if ver else "unknown",
            sha.group(1) if sha else "")


def main() -> int:
    src_path = pathlib.Path(os.environ.get("VPN_SECRETS_FILE") or DEFAULT_INPUT)
    if not src_path.exists():
        print("input config is missing", file=sys.stderr)
        return 2
    data = yaml.safe_load(src_path.read_text()) or {}
    try:
        label = _sbom_label(src_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    components: list[dict] = []

    xray = data.get("xray") or {}
    xray_version = _public_str(xray, "version")
    if xray_version:
        components.append(component(
            "xray-core",
            xray_version,
            _purl("github", "XTLS", "Xray-core", version=xray_version),
            [
                _release_hash("linux_amd64", _public_str(xray, "linux_amd64_sha256")),
                _release_hash("linux_arm64", _public_str(xray, "linux_arm64_sha256")),
            ],
            f"https://github.com/XTLS/Xray-core/releases/tag/{xray_version}",
            "P0 transport — VLESS+REALITY+XTLS-Vision",
        ))

    hys = data.get("hysteria") or {}
    hys_version = _public_str(hys, "version")
    if hys_version:
        components.append(component(
            "hysteria",
            hys_version,
            _purl("github", "apernet", "hysteria", version=hys_version),
            [
                _release_hash("linux_amd64", _public_str(hys, "linux_amd64_sha256")),
                _release_hash("linux_arm64", _public_str(hys, "linux_arm64_sha256")),
            ],
            f"https://github.com/apernet/hysteria/releases/tag/{hys_version}",
            "P2 transport — Hysteria2 UDP/QUIC",
        ))

    snell_secrets = data.get("snell_secrets") or {}
    snell_defaults_path = REPO_ROOT / "ansible" / "roles" / "snell" / "defaults" / "main.yml"
    if snell_secrets and snell_defaults_path.exists():
        snell_defaults = yaml.safe_load(snell_defaults_path.read_text()) or {}
        snell_version = _public_str(snell_defaults.get("snell") or {}, "version")
        if snell_version:
            components.append(component(
                "sing-box-snell", snell_version,
                _purl("github", "SagerNet", "sing-box", version=snell_version),
                [_release_hash("linux_amd64", _public_str(snell_secrets, "linux_amd64_sha256")),
                 _release_hash("linux_arm64", _public_str(snell_secrets, "linux_arm64_sha256"))],
                f"https://github.com/SagerNet/sing-box/releases/tag/{snell_version}",
                "P3 RESEARCH transport — Snell v4/v6 refinement candidate",
            ))

    geo = data.get("geodata") or {}
    geosite_url = _public_str(geo, "geosite_url")
    if geosite_url:
        components.append(component(
            "geosite",
            "pinned",
            _purl("generic", "geosite", url=geosite_url),
            [_release_hash("geosite", _public_str(geo, "geosite_sha256"))],
            geosite_url,
            "Xray routing geosite database",
        ))
    geoip_url = _public_str(geo, "geoip_url")
    if geoip_url:
        components.append(component(
            "geoip",
            "pinned",
            _purl("generic", "geoip", url=geoip_url),
            [_release_hash("geoip", _public_str(geo, "geoip_sha256"))],
            geoip_url,
            "Xray routing geoip database",
        ))

    _AWG_NO_HASH_PROP = [{"name": "sha256-pinned", "value": "false"}]

    awg_go = _public_str(data, "amneziawg_go_version")
    awg_tools = _public_str(data, "amneziawg_tools_version")
    if awg_go:
        c = component(
            "amneziawg-go", awg_go,
            _purl("github", "amnezia-vpn", "amneziawg-go", version=awg_go),
            [],
            f"https://github.com/amnezia-vpn/amneziawg-go/releases/tag/{awg_go}",
            "Userspace AmneziaWG implementation (no sha256 pin in v1 schema)",
        )
        c["properties"] = _AWG_NO_HASH_PROP
        components.append(c)
    if awg_tools:
        c = component(
            "amneziawg-tools", awg_tools,
            _purl("github", "amnezia-vpn", "amneziawg-tools", version=awg_tools),
            [],
            f"https://github.com/amnezia-vpn/amneziawg-tools/releases/tag/{awg_tools}",
            "AmneziaWG userspace tools (no sha256 pin in v1 schema)",
        )
        c["properties"] = _AWG_NO_HASH_PROP
        components.append(c)

    reali_ver, reali_sha = reali_pin()
    components.append(component(
        "RealiTLScanner", reali_ver,
        _purl("github", "XTLS", "RealiTLScanner", version=reali_ver),
        [_release_hash("linux-amd64", reali_sha)],
        f"https://github.com/XTLS/RealiTLScanner/releases/tag/{reali_ver}",
        "Operator-side REALITY target scanner",
    ))

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "metadata": {
            "timestamp": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds"),
            "tools": [{"name": "scripts/emit-sbom.py"}],
            "component": {
                "type": "application",
                "name": "vpn-deploy",
                "version": label,
                "description": "Reproducible VPN deployment automation",
            },
        },
        "components": components,
    }

    out = SBOM_DIR / f"{label}.json"
    payload = json.dumps(sbom, indent=2, sort_keys=False) + "\n"
    out.write_text(payload)
    print(f"wrote {out}  ({len(components)} components)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
