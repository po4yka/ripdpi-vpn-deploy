#!/usr/bin/env python3
"""Observe an explicit inventory subset without deployment prerequisites."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

import fleet_inspection as inspection


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hosts", default=os.environ.get("INSPECT_HOSTS", ""), help="Exact comma-separated inventory names; no wildcard or default fleet")
    parser.add_argument("--inventory", default=os.environ.get("INSPECT_INVENTORY", "ansible/inventory/generated.ini"))
    parser.add_argument("--known-hosts", default=os.environ.get("INSPECT_KNOWN_HOSTS", "~/.ssh/known_hosts"))
    args = parser.parse_args(argv)
    try:
        hosts = inspection.select_hosts(Path(args.inventory), args.hosts.split(",") if args.hosts else [])
        # Validate every local input before contacting the first selected host.
        commands = [inspection.ssh_command(host, Path(args.known_hosts)) for host in hosts]
        source = Path(inspection.__file__).read_bytes()
    except (inspection.InspectionError, OSError) as exc:
        category = str(exc) if isinstance(exc, inspection.InspectionError) else "collector-unavailable"
        print(json.dumps({"error": category}), file=sys.stderr)
        return 2
    results = []
    failed = False
    for host, command in zip(hosts, commands):
        try:
            raw = inspection.bounded_command(command, timeout=30, input_bytes=source)
            report = inspection.validate_report(inspection.decode_json(raw), dt.datetime.now(dt.timezone.utc))
            status = inspection.observation_status(report, dt.datetime.now(dt.timezone.utc))
            results.append({"name": host["name"], "status": status, "observation": report})
            failed |= status != "observed"
        except inspection.InspectionError as exc:
            results.append({"name": host["name"], "status": "unknown", "error": str(exc)})
            failed = True
    print(json.dumps({"schema_version": 1, "hosts": results}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
