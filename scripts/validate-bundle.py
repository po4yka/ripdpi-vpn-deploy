#!/usr/bin/env python3
"""Validate a RIPDPI bundle's `ripdpi` object against the formal schema.

The schema (contract/ripdpi-bundle.schema.json) is the cross-repo contract
between this server and the RIPDPI Android client: the server emits the
`ripdpi` object, the client parses it. Today a typo or a dropped field in
emit-bundle.sh surfaces only as a silent handshake/subscription failure on a
real device. This script catches that drift at PR time, and the client repo
runs an equivalent contract test against a vendored copy of the same schema.

Two checks:
  1. jsonschema validation against contract/ripdpi-bundle.schema.json.
  2. cohort_fingerprint correctness — every amneziawg[] entry that carries a
     cohort_fingerprint must match the fingerprint recomputed from its own
     resolved params (catches an emit-side hash bug the schema cannot see).

Input may be a full RIPDPI profile (the `ripdpi` key is extracted) or a bare
`ripdpi` object. Default target: contract/ripdpi-bundle.example.json.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
import ipaddress
import json
import os
import re
import stat
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ripdpi_cohort_fingerprint import ORDER, cohort_fingerprint  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "contract" / "ripdpi-bundle.schema.json"
DEFAULT_TARGET = REPO_ROOT / "contract" / "ripdpi-bundle.example.json"


def _read_runtime_materialized(path: Path) -> str:
    """Read a private bundle only through an owner-controlled path."""
    target = path.absolute()
    owner = os.geteuid()
    for parent in reversed(target.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("runtime bundle path contains a symlink")
        writable = info.st_mode & 0o022
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if info.st_uid not in {0, owner} or (writable and not sticky_root):
            raise ValueError("runtime bundle path ancestry is not owner-controlled")

    before = target.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("runtime bundle must be a regular non-symlink file")
    if before.st_uid != owner or stat.S_IMODE(before.st_mode) != 0o600:
        raise ValueError("runtime bundle must be owned by the current user with mode 0600")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("runtime bundle changed while it was being opened")
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _extract_ripdpi(doc: dict) -> dict:
    """Return the ripdpi object: doc['ripdpi'] if present, else doc itself."""
    if isinstance(doc, dict) and isinstance(doc.get("ripdpi"), dict):
        return doc["ripdpi"]
    return doc


def _fingerprint_errors(ripdpi: dict) -> list[str]:
    errors: list[str] = []
    for i, entry in enumerate(ripdpi.get("amneziawg") or []):
        if not isinstance(entry, dict) or "cohort_fingerprint" not in entry:
            continue
        params = {k: entry.get(k) for k in ORDER if entry.get(k) is not None}
        expected = cohort_fingerprint(params)
        actual = entry["cohort_fingerprint"]
        if actual != expected:
            errors.append(
                f"amneziawg[{i}].cohort_fingerprint: does not match resolved parameters"
            )
    return errors


def _address_errors(ripdpi: dict) -> list[str]:
    errors = []
    for index, entry in enumerate(ripdpi.get("amneziawg") or []):
        try:
            addresses = entry["address"]
            if not isinstance(addresses, list) or len(addresses) != 2:
                raise ValueError
            for value, version, prefix in zip(addresses, (4, 6), (32, 128)):
                address = ipaddress.ip_interface(value)
                if (not isinstance(value, str) or str(address) != value or address.version != version
                        or address.network.prefixlen != prefix or address.ip.is_multicast
                        or address.ip.is_unspecified or address.ip.is_loopback or address.ip.is_link_local):
                    raise ValueError
        except (KeyError, ValueError, TypeError):
            errors.append(f"amneziawg[{index}].address: requires canonical IPv4 and IPv6 unicast host identities")
    return errors


def _canonical_key(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        return False
    return len(decoded) == 32 and base64.b64encode(decoded).decode("ascii") == value


def _valid_host(value: str) -> bool:
    if not value or len(value) > 253 or "%" in value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        if re.fullmatch(r"[0-9.]+", value):
            return False
    return all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
               for label in value.removesuffix(".").split("."))


def _valid_endpoint(value: str) -> bool:
    if value.startswith("["):
        match = re.fullmatch(r"\[([^]]+)\]:([0-9]{1,5})", value)
        if match is None:
            return False
        host, port = match.groups()
        try:
            if ipaddress.ip_address(host).version != 6 or "%" in host:
                return False
        except ValueError:
            return False
    else:
        match = re.fullmatch(r"([^:]+):([0-9]{1,5})", value)
        if match is None:
            return False
        host, port = match.groups()
    return _valid_host(host) and 1 <= int(port) <= 65535


def _semantic_errors(ripdpi: dict) -> list[str]:
    errors = []
    for index, entry in enumerate(ripdpi["amneziawg"]):
        prefix = f"amneziawg[{index}]"
        for name in ("public_key", "preshared_key"):
            if not _canonical_key(entry["peer"][name]):
                errors.append(f"{prefix}.peer.{name}: requires canonical base64 of 32 bytes")
        if not _valid_endpoint(entry["peer"]["endpoint"]):
            errors.append(f"{prefix}.peer.endpoint: requires a valid host and port")
        for value in entry["peer"]["allowed_ips"]:
            try:
                if "/" not in value:
                    raise ValueError
                network = ipaddress.ip_network(value, strict=True)
                if str(network) != value:
                    raise ValueError
            except ValueError:
                errors.append(f"{prefix}.peer.allowed_ips: requires canonical network CIDRs")
                break
        for value in entry["dns"]:
            try:
                address = ipaddress.ip_address(value)
                if address.is_unspecified or address.is_multicast:
                    raise ValueError
            except ValueError:
                errors.append(f"{prefix}.dns: requires literal unicast IP addresses")
                break
        if entry["jmin"] > entry["jmax"]:
            errors.append(f"{prefix}: junk bounds must be ordered")
        if len({entry[name] for name in ("h1", "h2", "h3", "h4")}) != 4:
            errors.append(f"{prefix}: headers must be pairwise distinct")
    for index, extra in enumerate(ripdpi["hysteria_extras"].values()):
        hopping = extra.get("port_hopping")
        if hopping is not None:
            bounds = re.split(r"[:-]", hopping["ports"])
            lower, upper = (map(int, bounds) if all(len(value) <= 5 for value in bounds) else (0, 0))
            if not 1 <= lower <= upper <= 65535:
                errors.append(f"hysteria_extras[{index}].port_hopping: invalid port range")
            if len(hopping["interval"]) > 10 or int(hopping["interval"][:-1]) < 1:
                errors.append(f"hysteria_extras[{index}].port_hopping: interval must be positive")
    if "expires" in ripdpi:
        try:
            value = ripdpi["expires"]
            if "T" in value:
                datetime.fromisoformat(value)
            else:
                date.fromisoformat(value)
        except ValueError:
            errors.append("expires: requires a valid calendar instant")
    return errors


def _normalize_runtime_materialized(ripdpi: dict) -> tuple[dict, list[str]]:
    """Return a redacted in-memory copy of a locally materialized bundle."""
    normalized = copy.deepcopy(ripdpi)
    errors: list[str] = []
    if not isinstance(normalized, dict):
        return normalized, errors
    entries = normalized.get("amneziawg")
    if not isinstance(entries, list):
        return normalized, errors

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        has_key = "private_key" in entry
        has_placeholder = "private_key_placeholder" in entry
        if not has_key or has_placeholder:
            errors.append(
                f"amneziawg[{i}]: runtime materialization requires private_key "
                "and forbids private_key_placeholder"
            )
            entry.pop("private_key", None)
            continue

        private_key = entry.pop("private_key")
        if not isinstance(private_key, str):
            errors.append(f"amneziawg[{i}].private_key: must be canonical base64")
            continue
        try:
            decoded = base64.b64decode(private_key, validate=True)
        except (binascii.Error, ValueError):
            errors.append(f"amneziawg[{i}].private_key: must be canonical base64")
            continue
        if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != private_key:
            errors.append(
                f"amneziawg[{i}].private_key: must encode exactly 32 bytes "
                "using canonical base64"
            )
            continue
        entry["private_key_placeholder"] = True

    return normalized, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "bundle_file",
        nargs="?",
        help="A RIPDPI bundle JSON (or bare ripdpi object). "
        "Defaults to contract/ripdpi-bundle.example.json.",
    )
    ap.add_argument(
        "--runtime-materialized",
        action="store_true",
        help="Validate a local runtime bundle containing inline AmneziaWG "
        "private keys after redacting them in memory. The default remains the "
        "strict distribution contract.",
    )
    args = ap.parse_args()

    target = Path(args.bundle_file) if args.bundle_file else DEFAULT_TARGET
    if not target.is_file():
        print(f"validate-bundle: not a file: {target}", file=sys.stderr)
        return 2

    try:
        import jsonschema
    except ImportError:
        print(
            "validate-bundle: missing 'jsonschema' — `pip install jsonschema`",
            file=sys.stderr,
        )
        return 2

    try:
        source = (
            _read_runtime_materialized(target)
            if args.runtime_materialized
            else target.read_text()
        )
    except (OSError, ValueError) as exc:
        print(f"validate-bundle: unsafe runtime input: {exc}", file=sys.stderr)
        return 2

    schema = json.loads(SCHEMA.read_text())
    try:
        doc = json.loads(source)
    except (ValueError, RecursionError):
        print("validate-bundle: malformed JSON input", file=sys.stderr)
        return 1

    ripdpi = _extract_ripdpi(doc)
    runtime_errors: list[str] = []
    if args.runtime_materialized:
        ripdpi, runtime_errors = _normalize_runtime_materialized(ripdpi)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ripdpi), key=lambda e: list(e.absolute_path))

    fp_errors = ([] if errors else _fingerprint_errors(ripdpi) + _address_errors(ripdpi) + _semantic_errors(ripdpi))

    if errors or fp_errors or runtime_errors:
        print(
            "validate-bundle: "
            f"{len(errors) + len(fp_errors) + len(runtime_errors)} violation(s) "
            f"in {target}:",
            file=sys.stderr,
        )
        for e in errors:
            print(f"  schema: {e.validator} constraint failed", file=sys.stderr)
        for msg in fp_errors:
            print(f"  {msg}", file=sys.stderr)
        for msg in runtime_errors:
            print(f"  {msg}", file=sys.stderr)
        return 1

    print(f"validate-bundle: OK — {target} conforms to ripdpi-bundle.schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
