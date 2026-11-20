#!/usr/bin/env python3
"""Compute the RIPDPI AWG cohort fingerprint.

The fingerprint is a stable SHA-256 over the resolved AmneziaWG obfuscation
parameter set (jc, jmin, jmax, s1, s2, h1..h4, i1..i5). emit-bundle.sh stamps
it into each `ripdpi.amneziawg[]` entry; the client recomputes it from the
parsed params and compares. A mismatch means the bundle's params drifted from
the cohort the fingerprint was minted for — the client can then say "profile
outdated, refresh subscription" instead of letting the handshake stall.

The algorithm is the cross-language contract (bash emit-side calls this file;
the Kotlin client reimplements it). Keep it byte-for-byte identical to the
`cohort_fingerprint` $defs note in contract/ripdpi-bundle.schema.json:

  preimage = "wire_profile=awg-3.1-ranges-v1&jc=<jc>&jmin=<jmin>&jmax=<jmax>&s1=<s1>&s2=<s2>"
             "&h1=<h1>&h2=<h2>&h3=<h3>&h4=<h4>"
             "&i1=<i1>&i2=<i2>&i3=<i3>&i4=<i4>&i5=<i5>"
  fingerprint = "sha256:" + hex(sha256(preimage.encode("utf-8")))

Each scalar is base-10 with no leading zeros; headers are canonical range
strings and each i-value is its canonical tag program or "" when absent.

Usage:
  python3 scripts/ripdpi_cohort_fingerprint.py --jc 4 --jmin 10 ... --h4 4
  echo '{"jc":4,"jmin":10,...}' | python3 scripts/ripdpi_cohort_fingerprint.py -
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

ORDER = ["wire_profile", "jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4",
         "i1", "i2", "i3", "i4", "i5"]
# The contract fixes this preimage prefix; only i1..i5 may be absent.
WIRE_PROFILE = "awg-3.1-ranges-v1"
REQUIRED = ORDER[1:10]


def cohort_fingerprint(params: dict) -> str:
    """Return 'sha256:<hex>' for the resolved AWG parameter set in `params`.

    An absent i-value renders as the empty string (the emit side omits it from
    the bundle). An absent wire_profile is the contract constant; any other
    absent value has no defined preimage and raises ValueError.
    """
    params = {"wire_profile": WIRE_PROFILE, **{k: v for k, v in params.items() if v is not None}}
    missing = [key for key in REQUIRED if key not in params]
    if missing:
        raise ValueError("missing AWG params: " + ", ".join(missing))
    parts = []
    for key in ORDER:
        value = params.get(key)
        parts.append(f"{key}={'' if value is None else value}")
    preimage = "&".join(parts)
    return "sha256:" + hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "stdin_json",
        nargs="?",
        help="Pass '-' to read a JSON object of params from stdin.",
    )
    for key in ORDER:
        ap.add_argument(f"--{key}")
    args = ap.parse_args()

    if args.stdin_json == "-":
        params = json.load(sys.stdin)
    else:
        params = {k: getattr(args, k) for k in ORDER if getattr(args, k) is not None}

    try:
        print(cohort_fingerprint(params))
    except ValueError as error:
        print(f"ripdpi_cohort_fingerprint: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
