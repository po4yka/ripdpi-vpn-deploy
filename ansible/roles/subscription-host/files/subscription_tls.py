#!/usr/bin/env python3
"""Validate independent delivery TLS bytes in memory before nginx publication."""

from __future__ import annotations
import json
import os
import re
import subprocess
import sys


def invoke(*arguments, content=None, descriptors=()):
    result = subprocess.run(
        ["openssl", *arguments],
        input=content,
        text=True,
        capture_output=True,
        timeout=10,
        pass_fds=descriptors,
    )
    if result.returncode:
        raise ValueError("invalid TLS")
    return result.stdout.strip()


def validate(value, minimum_lifetime=0):
    if (
        not isinstance(value, dict)
        or set(value) != {"certificate", "private_key", "hostname"}
        or any(
            not isinstance(item, str) or not item or len(item) > 65536
            for item in value.values()
        )
        or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", value["hostname"]
        )
    ):
        raise ValueError("invalid request")
    public = invoke("x509", "-pubkey", "-noout", content=value["certificate"])
    if public != invoke("pkey", "-pubout", content=value["private_key"]):
        raise ValueError("key mismatch")
    invoke(
        "x509",
        "-checkend",
        str(minimum_lifetime),
        "-noout",
        content=value["certificate"],
    )
    descriptor = os.memfd_create("subscription-tls", os.MFD_CLOEXEC)
    try:
        with os.fdopen(os.dup(descriptor), "wb") as output:
            output.write(value["certificate"].encode())
        os.lseek(descriptor, 0, os.SEEK_SET)
        # Trust the explicitly supplied leaf for the identity/date/EKU check;
        # external certificate issuance remains operator-owned. Unlike x509
        # -checkhost (which returns zero on mismatch), verify rejects mismatch.
        path = "/proc/self/fd/" + str(descriptor)
        invoke(
            "verify",
            "-no-CAfile",
            "-no-CApath",
            "-no-CAstore",
            "-trusted",
            path,
            "-partial_chain",
            "-purpose",
            "sslserver",
            "-verify_hostname",
            value["hostname"],
            path,
            descriptors=(descriptor,),
        )
    finally:
        os.close(descriptor)


def main():
    try:
        minimum_lifetime = int(sys.argv[1]) if len(sys.argv) == 2 else 0
        if not 0 <= minimum_lifetime <= 604800 or len(sys.argv) > 2:
            raise ValueError("invalid lifetime policy")
        validate(json.loads(sys.stdin.read(196609)), minimum_lifetime)
    except (ValueError, OSError, subprocess.SubprocessError):
        print("subscription TLS preflight rejected", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
