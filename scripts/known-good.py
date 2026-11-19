#!/usr/bin/env python3
"""Record per-node verification receipts and cut the fleet known-good tag.

`record` runs after a passing `make verify` (any limit) and writes one receipt
per selected `vpn` host for the checked-out source identity. `tag` creates a
`vpn-deploy-known-good-*` tag on HEAD only when every `vpn` host of every given
inventory has a fresh receipt for exactly that revision and deployable digest.
Each node keeps its own secrets and overrides, so no single unbounded verify
can cover the fleet; the tag is the conjunction of per-node results instead.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAG_PREFIX = "vpn-deploy-known-good-"
ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
SCHEMA_VERSION = 1


class Refusal(Exception):
    pass


def source_identity():
    out = subprocess.run([str(REPO_ROOT / "scripts/deploy-source-identity.sh"), "--identity"],
                         check=True, capture_output=True, text=True).stdout.split()
    if len(out) != 2:
        raise Refusal("cannot derive deploy source identity")
    return out[0], out[1]


def vpn_hosts(inventory, limit=""):
    argv = ["ansible-inventory", "-i", str(inventory), "--list"]
    if limit:
        argv += ["--limit", limit]
    result = subprocess.run(argv, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise Refusal(f"cannot list inventory {inventory}")
    hosts, pending, seen = set(), ["vpn"], set()
    try:
        document = json.loads(result.stdout)
        while pending:
            group = pending.pop()
            if group in seen:
                continue
            seen.add(group)
            entry = document.get(group, {})
            hosts.update(entry.get("hosts", []))
            pending.extend(entry.get("children", []))
    except (ValueError, AttributeError, TypeError):
        raise Refusal(f"unreadable inventory listing for {inventory}") from None
    for alias in hosts:
        if not ALIAS.fullmatch(alias):
            raise Refusal(f"inventory alias is not a plain name: {alias!r}")
    return sorted(hosts)


def receipt_path(receipts, revision, alias):
    return Path(receipts) / revision / f"{alias}.json"


def record(args):
    revision, digest = source_identity()
    hosts = vpn_hosts(args.inventory, args.limit)
    if not hosts:
        raise Refusal("verification selected no vpn hosts")
    folder = Path(args.receipts) / revision
    os.umask(0o077)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = int(time.time())
    for alias in hosts:
        body = {"schema_version": SCHEMA_VERSION, "alias": alias, "source_revision": revision,
                "deployable_digest": digest, "verified_at": now}
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{alias}.")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(body, handle, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, receipt_path(args.receipts, revision, alias))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        print(f"known-good receipt: {alias} at {revision[:12]}")


def tag(args):
    revision, digest = source_identity()
    existing = subprocess.run(["git", "-C", str(REPO_ROOT), "tag", "--points-at", revision,
                               "--list", TAG_PREFIX + "*"],
                              check=True, capture_output=True, text=True).stdout.split()
    if existing:
        print(f"already tagged: {existing[-1]}")
        return
    required = set()
    for inventory in args.inventories:
        hosts = vpn_hosts(inventory)
        if not hosts:
            raise Refusal(f"inventory {inventory} lists no vpn hosts")
        required.update(hosts)
    now = time.time()
    oldest = now - args.max_age_hours * 3600
    problems = []
    for alias in sorted(required):
        path = receipt_path(args.receipts, revision, alias)
        try:
            body = json.loads(path.read_text())
        except (OSError, ValueError):
            problems.append(f"{alias}: no verification receipt at {revision[:12]}")
            continue
        if (body.get("schema_version") != SCHEMA_VERSION or body.get("alias") != alias
                or body.get("source_revision") != revision):
            problems.append(f"{alias}: malformed receipt")
        elif body.get("deployable_digest") != digest:
            problems.append(f"{alias}: receipt digest differs from the checkout")
        elif not isinstance(body.get("verified_at"), int) or body["verified_at"] > now + 300:
            problems.append(f"{alias}: receipt time is missing or in the future")
        elif body["verified_at"] < oldest:
            problems.append(f"{alias}: receipt older than {args.max_age_hours}h; run make verify for it again")
    if problems:
        raise Refusal("known-good tag refused:\n  " + "\n  ".join(problems))
    name = TAG_PREFIX + time.strftime("%Y-%m-%d-%H%M", time.gmtime())
    nodes = ", ".join(sorted(required))
    created = subprocess.run(["git", "-C", str(REPO_ROOT), "tag", "-a", name, "-m",
                              f"verified nodes: {nodes}", revision],
                             check=False, capture_output=True, text=True)
    if created.returncode != 0:
        raise Refusal(f"git tag {name} failed: {created.stderr.strip()}")
    print(f"tagged: {name} ({len(required)} nodes: {nodes})")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--inventory", required=True)
    rec.add_argument("--limit", default="")
    rec.add_argument("--receipts", required=True)
    tg = sub.add_parser("tag")
    tg.add_argument("--inventory", dest="inventories", action="append", required=True)
    tg.add_argument("--receipts", required=True)
    tg.add_argument("--max-age-hours", type=int, default=24)
    args = parser.parse_args(argv)
    try:
        (record if args.command == "record" else tag)(args)
    except Refusal as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
