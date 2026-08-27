#!/usr/bin/env python3
"""Render the standard client profile and validate it with pinned sing-box."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "secrets-sample.yml"
STUBS_BIN = REPO_ROOT / "tests" / "stubs" / "bin"
EMITTER = REPO_ROOT / "scripts" / "emit-singbox.sh"
VERSION_PATTERN = re.compile(r"\bsing-box version (\d+\.\d+\.\d+)\b")


class CompatibilityError(RuntimeError):
    """The pinned binary or generated client profile is incompatible."""


def run(
    command: list[str], *, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CompatibilityError(
            f"cannot execute {command[0]}: {type(exc).__name__}"
        ) from exc


def fixture_document() -> dict:
    try:
        document = yaml.safe_load(FIXTURE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CompatibilityError(f"cannot load fixture: {type(exc).__name__}") from exc
    document["xray"][
        "reality_public_key"
    ] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    clients = document["hysteria"].setdefault("clients", [])
    if not any(client.get("name") == "laptop" for client in clients):
        clients.append(
            {
                "name": "laptop",
                "password": "fixture-hysteria-password-laptop-001",
            }
        )
    return document


def render_profile(directory: Path) -> Path:
    secrets = directory / "secrets.json"
    secrets.write_text(json.dumps(fixture_document()), encoding="utf-8")
    secrets.chmod(0o600)

    bin_dir = directory / "bin"
    bin_dir.mkdir(mode=0o700)
    sops = bin_dir / "sops"
    sops.write_text('#!/bin/sh\nset -eu\ncat "$SOPS_FILE"\n', encoding="utf-8")
    sops.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{STUBS_BIN}:{environment.get('PATH', '')}",
            "SOPS_FILE": str(secrets),
            "STUB_LOG": str(directory / "stub.log"),
        }
    )
    for variable in ("HOSTS", "SOPS_FILES", "COHORTS", "PROVIDER", "ENV", "VPN_SECRETS_FILE"):
        environment.pop(variable, None)

    rendered = run(["bash", str(EMITTER), "laptop"], environment=environment)
    if rendered.returncode != 0:
        raise CompatibilityError(
            f"emit-singbox failed with exit {rendered.returncode}: {rendered.stderr.strip()}"
        )
    try:
        json.loads(rendered.stdout)
    except json.JSONDecodeError as exc:
        raise CompatibilityError("emit-singbox returned malformed JSON") from exc
    profile = directory / "client.sing-box.json"
    profile.write_text(rendered.stdout, encoding="utf-8")
    profile.chmod(0o600)
    return profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--binary", default="sing-box")
    args = parser.parse_args()

    binary = shutil.which(args.binary)
    if not binary:
        print(
            f"sing-box compatibility: binary not found: {args.binary}", file=sys.stderr
        )
        return 2
    version = run([binary, "version"])
    match = VERSION_PATTERN.search(version.stdout + version.stderr)
    if version.returncode != 0 or not match or match.group(1) != args.expected_version:
        observed = match.group(1) if match else "unknown"
        print(
            f"sing-box compatibility: expected {args.expected_version}, observed {observed}",
            file=sys.stderr,
        )
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="sing-box-client-check-") as temporary:
            profile = render_profile(Path(temporary))
            print(
                f"running sing-box check -c {profile.name} with pinned {args.expected_version}"
            )
            checked = run([binary, "check", "-c", str(profile)])
            if checked.returncode != 0:
                raise CompatibilityError(
                    f"sing-box check failed with exit {checked.returncode}: {checked.stderr.strip()}"
                )
    except CompatibilityError as exc:
        print(f"sing-box compatibility: {exc}", file=sys.stderr)
        return 1

    print(f"sing-box compatibility: OK ({args.expected_version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
