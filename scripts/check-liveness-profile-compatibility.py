#!/usr/bin/env python3
"""Check canonical sentinel profiles with the real pinned runtime parsers."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from liveness_profiles import build_profiles

ROOT = Path(__file__).resolve().parent.parent


class CompatibilityError(RuntimeError):
    """A real emitter or runtime parser rejected the fixture."""


def run(command, environment=None):
    try:
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CompatibilityError("command unavailable or timed out") from None
    if result.returncode:
        raise CompatibilityError("emitter or runtime parser rejected configuration")
    return result.stdout


def private_json(path, document):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(document, stream)


def render_profiles(directory: Path) -> dict[str, Path]:
    spec = importlib.util.spec_from_file_location(
        "standard_compatibility", ROOT / "scripts/check-singbox-client-compatibility.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = module.fixture_document()
    document["client_registry"] = {"laptop": {"status": "active"}}
    secrets = directory / "secrets.json"
    private_json(secrets, document)
    environment = os.environ.copy()
    for name in ("SOPS_FILE", "SOPS_FILES", "PROVIDER", "ENV", "HOSTS", "COHORTS", "VPN_SECRETS_FILE"):
        environment.pop(name, None)
    environment.update(PATH=f"{ROOT / 'tests/stubs/bin'}:{environment.get('PATH', '')}",
                       VPN_SECRETS_FILE=str(secrets), HOSTS="upcloud:fixture", COHORTS="fullstack",
                       STUB_LOG=str(directory / "stub.log"))
    outputs = []
    for profile_format in ("sing-box", "ripdpi"):
        try:
            outputs.append(json.loads(run(["bash", str(ROOT / "scripts/emit-singbox.sh"),
                                           "laptop", "--profile-format", profile_format], environment)))
        except json.JSONDecodeError:
            raise CompatibilityError("emitter returned malformed JSON") from None

    def no_key(_value):
        raise CompatibilityError("unexpected AWG key derivation")

    profiles = directory / "profiles"
    profiles.mkdir(mode=0o700)
    built = build_profiles(outputs[0], outputs[1], document, "laptop",
                           ["p0-reality", "p1-xhttp", "p2-hysteria2"], None, None,
                           None, no_key, str(profiles), awg_defaults={}, awg_cohort={})
    paths = {}
    for name, profile in built["files"].items():
        paths[name] = profiles / name
        private_json(paths[name], profile)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sing-box", default="sing-box")
    parser.add_argument("--xray", default="xray")
    parser.add_argument("--sing-box-version", required=True)
    parser.add_argument("--xray-version", required=True)
    args = parser.parse_args()
    try:
        binaries = {}
        for name, executable, expected, flag, pattern in (
            ("sing-box", args.sing_box, args.sing_box_version, "version", r"sing-box version (\d+\.\d+\.\d+)\b"),
            ("xray", args.xray, args.xray_version, "version", r"Xray (\d+\.\d+\.\d+)\b"),
        ):
            binary = shutil.which(executable)
            if not binary:
                raise CompatibilityError(f"missing {name}")
            match = re.search(pattern, run([binary, flag]))
            if not match or match.group(1) != expected:
                raise CompatibilityError(f"{name} version mismatch")
            binaries[name] = binary
        with tempfile.TemporaryDirectory(prefix="liveness-parser-check-") as temporary:
            profiles = render_profiles(Path(temporary))
            run([binaries["sing-box"], "check", "-c", str(profiles["sing-box.json"])])
            run([binaries["xray"], "run", "-test", "-config", str(profiles["xray.json"])])
    except (CompatibilityError, ValueError, OSError):
        print("liveness parser compatibility: failed (emitter, runtime, or configuration)", file=sys.stderr)
        return 1
    print("liveness parser compatibility: PASS (canonical emitters, sing-box, Xray)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
