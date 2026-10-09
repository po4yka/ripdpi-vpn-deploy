#!/usr/bin/env python3
"""Validate supplied TLS authority without persistent candidate files."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def openssl(*arguments: str, content: str | None = None, descriptors=()) -> str:
    result = subprocess.run(
        ["openssl", *arguments],
        input=content,
        text=True,
        capture_output=True,
        timeout=10,
        pass_fds=descriptors,
    )
    if result.returncode:
        raise ValueError("invalid authority")
    return result.stdout.strip()


def validate(value: dict) -> None:
    expected = {"certificate", "private_key", "ca", "purpose", "identity"}
    if (
        not isinstance(value, dict)
        or set(value) not in (expected, expected | {"crl"})
        or any(
            not isinstance(item, str) or len(item) > 65536 for item in value.values()
        )
        or any(
            not value[field] for field in ("certificate", "ca", "purpose", "identity")
        )
        or ("crl" in value and not value["crl"])
    ):
        raise ValueError("invalid request")
    if value["purpose"] not in ("sslclient", "sslclient_public", "sslserver"):
        raise ValueError("invalid purpose")
    if value["purpose"] != "sslclient_public":
        if not value["private_key"]:
            raise ValueError("missing key")
        certificate_key = openssl(
            "x509", "-noout", "-pubkey", content=value["certificate"]
        )
        private_key = openssl("pkey", "-pubout", content=value["private_key"])
        if certificate_key != private_key:
            raise ValueError("mismatched key")
    elif value["private_key"]:
        raise ValueError("public identity cannot contain a key")
    descriptors = []
    try:
        for field in ("ca", "certificate", *(("crl",) if "crl" in value else ())):
            descriptor = os.memfd_create("observability-tls", os.MFD_CLOEXEC)
            descriptors.append(descriptor)
            with os.fdopen(os.dup(descriptor), "wb") as output:
                output.write(value[field].encode())
            os.lseek(descriptor, 0, os.SEEK_SET)
        arguments = [
            "verify",
            "-no-CAfile",
            "-no-CApath",
            "-no-CAstore",
            "-trusted",
            f"/proc/self/fd/{descriptors[0]}",
            "-purpose",
            "sslclient" if value["purpose"] == "sslclient_public" else value["purpose"],
        ]
        if "crl" in value:
            arguments += [
                "-crl_check_all",
                "-CRLfile",
                f"/proc/self/fd/{descriptors[2]}",
            ]
        if value["purpose"] == "sslserver":
            arguments += ["-verify_ip", value["identity"]]
        else:
            subject = openssl(
                "x509",
                "-noout",
                "-subject",
                "-nameopt",
                "RFC2253",
                content=value["certificate"],
            )
            if subject != "subject=CN=" + value["identity"]:
                raise ValueError("identity mismatch")
        openssl(
            *arguments,
            f"/proc/self/fd/{descriptors[1]}",
            descriptors=tuple(descriptors),
        )
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def main() -> int:
    try:
        validate(json.loads(sys.stdin.read(262145)))
    except (ValueError, OSError, AttributeError, subprocess.TimeoutExpired):
        print("TLS authority preflight rejected", file=sys.stderr)
        return 2
    print("TLS authority preflight accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
