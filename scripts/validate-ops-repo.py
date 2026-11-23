#!/usr/bin/env python3
"""Refuse an ops repository checkout that holds plaintext secrets or a loose pin.

Usage: validate-ops-repo.py <ops repository root>

Inside a Git checkout it scans the files Git would commit (tracked plus
untracked, not ignored); elsewhere it scans every file. Findings name the path
and the rule, never file content. Exit 0 when clean, 1 on findings, 2 on usage
errors. See docs/reference/ops-repository.md.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from tofu_backend import s3_settings

UPSTREAM = "https://github.com/po4yka/ripdpi-vpn-deploy"
AUTHORITIES = {"ops-repo", "b2-recovery", "gh-environment", "password-manager", "temporary"}
SECRET_SECTIONS = set(json.loads((Path(__file__).resolve().parents[1] / "secrets/schema.json").read_text())["properties"])
PRIVATE_MARKER = re.compile(rb"AGE-SECRET-KEY-|-----BEGIN [A-Z ]*PRIVATE KEY( BLOCK)?-----|^\s*PrivateKey\s*=", re.MULTILINE)
FORBIDDEN_NAMES = re.compile(r"(\.tfstate(\.backup)?|\.tfplan|\.secrets\.ya?ml|\.dec|^\.env|^keys\.txt)$")
SOPS_NAMES = re.compile(r".\.sops\.(ya?ml|json)$")
STRUCTURED_NAMES = re.compile(r"\.(ya?ml|json)$")
SCAN_LIMIT = 16 * 1024 * 1024


def check_pin(root: Path) -> list[str]:
    path = root / "upstream.lock"
    if not path.is_file():
        return ["upstream.lock: missing"]
    fields = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    findings = []
    if fields.get("repository") != UPSTREAM:
        findings.append(f"upstream.lock: repository must be {UPSTREAM}")
    if not re.fullmatch(r"[0-9a-f]{40}", fields.get("revision", "")):
        findings.append("upstream.lock: revision must be a full 40-character commit SHA")
    return findings


def policy_recipients(root: Path) -> tuple[set[str], list[str]]:
    path = root / "config/.sops.yaml"
    if not path.is_file():
        return set(), []
    try:
        rules = (yaml.safe_load(path.read_text()) or {}).get("creation_rules") or []
    except (yaml.YAMLError, UnicodeDecodeError, AttributeError):
        return set(), ["config/.sops.yaml: not a SOPS policy mapping"]
    recipients: set[str] = set()
    for rule in rules if isinstance(rules, list) else [None]:
        if not isinstance(rule, dict) or "key_groups" in rule:
            return set(), ["config/.sops.yaml: rules must be mappings with an age recipient list"]
        keys = rule.get("age", "")
        recipients |= {key.strip() for key in (keys if isinstance(keys, list) else str(keys).split(",")) if key.strip()}
    return recipients, []


def load(path: Path):
    text = path.read_text()
    return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)


def leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaves(item)
    else:
        yield value


def check_structured(path: Path, relative: str, recipients: set[str]) -> list[str]:
    try:
        document = load(path)
    except (ValueError, yaml.YAMLError, UnicodeDecodeError):
        return [f"{relative}: not valid YAML or JSON"]
    is_sops_name = bool(SOPS_NAMES.search(path.name))
    if not isinstance(document, dict):
        return [f"{relative}: SOPS document without age metadata"] if is_sops_name else []
    metadata = document.get("sops")
    if not is_sops_name and metadata is None:
        if SECRET_SECTIONS & set(document):
            return [f"{relative}: plaintext deployment secret sections"]
        return []
    entries = metadata.get("age") if isinstance(metadata, dict) else None
    if not isinstance(entries, list) or not entries or not all(isinstance(entry, dict) for entry in entries):
        return [f"{relative}: SOPS document without age metadata"]
    if not {entry.get("recipient") for entry in entries} <= recipients:
        return [f"{relative}: encrypted to a recipient outside config/.sops.yaml"]
    body = {key: value for key, value in document.items() if key != "sops"}
    # SOPS leaves empty strings and nulls as they are; every other value is an ENC[...] string.
    if any(isinstance(value, str) and value and not value.startswith("ENC[") or isinstance(value, (int, float, bool))
           for value in leaves(body)):
        return [f"{relative}: SOPS document with unencrypted values"]
    return []


def candidate_files(root: Path) -> list[Path]:
    if (root / ".git").exists():
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                capture_output=True, check=True).stdout.decode().split("\0")
        return sorted({root / name for name in listed if name})
    return sorted(path for path in root.rglob("*") if ".git" not in path.relative_to(root).parts)


def validate(root: Path) -> list[str]:
    recipients, findings = policy_recipients(root)
    findings += check_pin(root) + check_catalog(root)
    for path in candidate_files(root):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            findings.append(f"{relative}: symbolic links are not allowed")
            continue
        if not path.is_file():
            continue
        if FORBIDDEN_NAMES.search(path.name) or "terraform.tfstate.d" in path.parts:
            findings.append(f"{relative}: state, plan or decrypted secret file")
            continue
        if path.stat().st_size > SCAN_LIMIT:
            findings.append(f"{relative}: larger than the scan limit")
            continue
        if PRIVATE_MARKER.search(path.read_bytes()):
            findings.append(f"{relative}: private key material")
            continue
        if path.name.endswith(".s3.tfbackend"):
            try:
                s3_settings(path.read_bytes(), path.name.removesuffix(".s3.tfbackend"))
            except ValueError as error:
                findings.append(f"{relative}: {error}")
            continue
        if STRUCTURED_NAMES.search(path.name) and path.name not in (".sops.yaml", ".sops.yml", "catalog.json"):
            findings.extend(check_structured(path, relative, recipients))
    return findings


def check_catalog(root: Path) -> list[str]:
    path = root / "catalog.json"
    if not path.is_file():
        return ["catalog.json: missing"]
    try:
        credentials = json.loads(path.read_text()).get("credentials")
    except (ValueError, AttributeError):
        return ["catalog.json: must be a JSON object"]
    if not isinstance(credentials, list):
        return ["catalog.json: credentials must be a list"]
    return [f"catalog.json: credentials[{index}] has no allowed authority"
            for index, entry in enumerate(credentials)
            if not isinstance(entry, dict) or entry.get("authority") not in AUTHORITIES]


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not Path(argv[1]).is_dir():
        print("usage: validate-ops-repo.py <ops repository root>", file=sys.stderr)
        return 2
    findings = validate(Path(argv[1]).resolve())
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
