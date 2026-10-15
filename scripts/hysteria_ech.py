#!/usr/bin/env python3
"""Issue an exact-runtime ECH generation through the existing SOPS transaction."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile

from encrypted_client_document import CommittedPublication, operate
from transport_semantics import ech_keys_config, hostname_valid, hysteria_errors

ROOT = Path(__file__).resolve().parent.parent
PINS = json.loads((ROOT / "scripts/hysteria-runtimes.json").read_text())


def verified_binary(binary):
    path = Path(binary).resolve(strict=True)
    architecture = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64"}.get(
        platform.machine()
    )
    digest = PINS["hysteria"]["sha256"].get(sys.platform + "-" + str(architecture))
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 50000000:
            raise ValueError("unverified-hysteria-runtime")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            data = source.read(50000001)
    finally:
        os.close(descriptor)
    if digest is None or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("unverified-hysteria-runtime")
    return data


def generate(binary, public_name, inner_name):
    if (
        not hostname_valid(public_name)
        or not hostname_valid(inner_name)
        or public_name == inner_name
    ):
        raise ValueError("invalid-ech-identities")
    executable = verified_binary(binary)
    with tempfile.TemporaryDirectory(prefix="hysteria-ech-") as temporary:
        binary = Path(temporary) / "hysteria"
        binary.write_bytes(executable)
        binary.chmod(0o700)
        private = Path(temporary) / "ech.pem"
        result = subprocess.run(
            [
                str(binary),
                "ech",
                "--public-name",
                public_name,
                "--output",
                str(private),
            ],
            capture_output=True,
            timeout=15,
        )
        if result.returncode:
            raise ValueError("ech-generation-refused")
        if private.stat().st_mode & 0o077:
            raise ValueError("unsafe-generated-ech-authority")
        pem = private.read_text()
        config = ech_keys_config(pem)
    return {
        "profile": "ech-required",
        "generation": hashlib.sha256(base64.b64decode(config)).hexdigest(),
        "public_name": public_name,
        "inner_name": inner_name,
        "config_list": config,
        "keys_pem": pem,
    }


def issue(path, binary, public_name, inner_name):
    def transform(document):
        hysteria = document.get("hysteria")
        if (
            not isinstance(hysteria, dict)
            or hysteria.get("version") != PINS["hysteria"]["version"]
        ):
            raise ValueError("exact-hysteria-runtime-required")
        hysteria["ech"] = generate(binary, public_name, inner_name)
        if hysteria_errors(hysteria):
            raise ValueError("invalid-coordinated-ech-profile")
        # Only public generation identity is returned to the operator.
        return document, {
            "generation": hysteria["ech"]["generation"],
            "profile": "ech-required",
        }

    return operate(path, transform)


def main():
    try:
        source = os.environ["SOPS_FILE"]
        binary = os.environ.get("HYSTERIA_BINARY") or shutil.which("hysteria")
        if not binary:
            raise ValueError("exact-hysteria-runtime-required")
        metadata = issue(
            source,
            binary,
            os.environ["HYSTERIA_ECH_PUBLIC_NAME"],
            os.environ["HYSTERIA_ECH_INNER_NAME"],
        )
        print(json.dumps(metadata))
    except CommittedPublication:
        print(
            "ECH ciphertext committed; storage durability is uncertain; inspect before retrying",
            file=sys.stderr,
        )
        return 2
    except (KeyError, OSError, ValueError, subprocess.SubprocessError):
        print(
            "ECH authority issuance refused; verify exact binary, identities and private SOPS authority",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
