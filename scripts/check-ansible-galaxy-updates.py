#!/usr/bin/env python3
"""Check pinned Ansible Galaxy collections for newer published versions.

Dependabot does not cover ``requirements.yml``. This script gives the repo a
scheduled, machine-readable signal for collection drift without changing the
lock file automatically. It installs each collection once without a version
constraint into a temporary collection path and compares the resolved latest
version with the pinned value in requirements.yml.

Exit codes:
  0: all pinned collections are current
  1: at least one newer version is available
  2: local usage/tooling error
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class CollectionPin:
    name: str
    version: str


def load_pins(path: Path) -> list[CollectionPin]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pins: list[CollectionPin] = []
    for item in doc.get("collections", []):
        name = str(item.get("name", "")).strip()
        version = str(item.get("version", "")).strip()
        if not name or not version:
            raise SystemExit(f"{path}: each collection entry must have name + version")
        pins.append(CollectionPin(name=name, version=version))
    if not pins:
        raise SystemExit(f"{path}: no collection pins found")
    return pins


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def resolve_latest_version(name: str, workdir: Path) -> str:
    workdir.mkdir(parents=True, exist_ok=True)
    collection_dir = workdir / "collections"
    req = workdir / "latest.yml"
    req.write_text(
        yaml.safe_dump({"collections": [{"name": name}]}, sort_keys=False),
        encoding="utf-8",
    )

    install = run([
        "ansible-galaxy",
        "collection",
        "install",
        "-r",
        str(req),
        "--collections-path",
        str(collection_dir),
        "--force",
    ])
    if install.returncode != 0:
        raise RuntimeError(
            f"ansible-galaxy install failed for {name}:\n{install.stdout}\n{install.stderr}"
        )

    listed = run([
        "ansible-galaxy",
        "collection",
        "list",
        "--collections-path",
        str(collection_dir),
        "--format",
        "json",
    ])
    if listed.returncode != 0:
        raise RuntimeError(
            f"ansible-galaxy list failed for {name}:\n{listed.stdout}\n{listed.stderr}"
        )

    payload = json.loads(listed.stdout)
    for collections in payload.values():
        meta = collections.get(name)
        if meta and meta.get("version"):
            return str(meta["version"])
    raise RuntimeError(f"could not find {name} in ansible-galaxy list output")


def newer(latest: str, pinned: str) -> bool:
    try:
        return Version(latest) > Version(pinned)
    except InvalidVersion:
        return latest != pinned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        default="requirements.yml",
        type=Path,
        help="Path to Ansible Galaxy requirements.yml",
    )
    args = parser.parse_args()

    if shutil.which("ansible-galaxy") is None:
        print("missing: ansible-galaxy", file=sys.stderr)
        return 2

    pins = load_pins(args.requirements)
    findings: list[tuple[CollectionPin, str]] = []

    with tempfile.TemporaryDirectory(prefix="galaxy-drift.") as tmp:
        workdir = Path(tmp)
        for pin in pins:
            latest = resolve_latest_version(pin.name, workdir / pin.name.replace(".", "-"))
            status = "OUTDATED" if newer(latest, pin.version) else "current"
            print(f"{pin.name}: pinned={pin.version} latest={latest} status={status}")
            if newer(latest, pin.version):
                findings.append((pin, latest))

    if findings:
        print("\nAnsible Galaxy collection updates available:")
        for pin, latest in findings:
            print(f"  - {pin.name}: {pin.version} -> {latest}")
        print("\nUpdate requirements.yml deliberately and run the full Ansible CI matrix.")
        return 1

    print("\nOK — Ansible Galaxy collection pins are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
