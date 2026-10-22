#!/usr/bin/env python3
"""Summarize inventory-bound observations without claiming client-path health."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

import fleet_inspection as inspection

WATCHDOG_MAX_AGE_SECONDS = 300


def watchdog_health(report, now):
    """Evaluate validated passive evidence; success is only a local watchdog result."""
    try:
        observed = inspection.parse_time(report["observed_at"])
        if observed > now:
            return {"status": "unknown", "reason": "future-observation"}
        if now - observed > dt.timedelta(seconds=WATCHDOG_MAX_AGE_SECONDS):
            return {"status": "stale", "reason": "stale-observation"}
        service = report["services"]["vpn-watchdog.service"]
        timer = report["services"]["vpn-watchdog.timer"]
        if service.get("status") != "observed" or service.get("load_state") != "loaded":
            return {"status": "unknown", "reason": "service-unobserved"}
        if service.get("active_state") not in ("inactive", "failed"):
            return {"status": "unknown", "reason": "invocation-incomplete"}
        if (service.get("active_state") == "failed"
                or service.get("result") not in ("", "success")
                or service.get("exec_main_status") not in (None, 0)):
            return {"status": "unhealthy", "reason": "invocation-failed"}
        if (service.get("sub_state") != "dead"
                or service.get("result") != "success" or service.get("exec_main_status") != 0
                or service.get("exec_main_exit_timestamp") is None):
            return {"status": "unknown", "reason": "invocation-incomplete"}
        completed = inspection.parse_time(service["exec_main_exit_timestamp"])
        if completed > observed:
            return {"status": "unknown", "reason": "future-completion"}
        if now - completed > dt.timedelta(seconds=WATCHDOG_MAX_AGE_SECONDS):
            return {"status": "stale", "reason": "stale-completion"}
        if timer.get("status") != "observed" or timer.get("load_state") != "loaded":
            return {"status": "unknown", "reason": "timer-unobserved"}
        if timer.get("active_state") != "active":
            return {"status": "unhealthy", "reason": "timer-inactive"}
        if timer.get("sub_state") not in ("waiting", "elapsed"):
            return {"status": "unknown", "reason": "timer-unobserved"}
        return {"status": "healthy", "reason": "recent-success"}
    except (inspection.InspectionError, KeyError, TypeError):
        return {"status": "unknown", "reason": "invalid-observation"}


def collect_status(hosts, known_hosts):
    """Admit every local command before contacting the first selected host."""
    commands = [inspection.ssh_command(host, known_hosts) for host in hosts]
    source = Path(inspection.__file__).read_bytes()
    results = []
    for host, command in zip(hosts, commands):
        row = {"name": host["name"], "provider": host["variables"]["provider"],
               "environment": host["variables"]["env"], "source_revision": None,
               "watchdog_local": {"status": "unknown", "reason": "collection-failed"},
               "client_path": "unknown", "observation": None}
        try:
            raw = inspection.bounded_command(command, timeout=30, input_bytes=source)
            now = dt.datetime.now(dt.timezone.utc)
            report = inspection.validate_report(inspection.decode_json(raw), now)
            row.update(source_revision=report["manifest"].get("source_revision"),
                       watchdog_local=watchdog_health(report, now), observation=report)
        except inspection.InspectionError as exc:
            row["error"] = str(exc)
        results.append(row)
    return {"schema_version": 1, "hosts": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default_pair = os.environ.get("PROVIDER", "upcloud") + ":" + os.environ.get("ENV", "prod")
    parser.add_argument("--hosts", default=os.environ.get("HOSTS") or default_pair,
                        help="Exact comma-separated provider:environment inventory pairs")
    default_inventory = Path(__file__).resolve().parent.parent / "ansible/inventory/generated.ini"
    parser.add_argument("--inventory", default=os.environ.get("FLEET_INVENTORY", str(default_inventory)))
    parser.add_argument("--known-hosts", default=os.environ.get("FLEET_KNOWN_HOSTS", "~/.ssh/known_hosts"))
    parser.add_argument("--json", action="store_true", help="Emit validated passive observations as JSON")
    args = parser.parse_args(argv)
    try:
        hosts = inspection.select_hosts(Path(args.inventory), args.hosts.split(","),
                                        selection_kind="provider-env", include_variables=True)
        result = collect_status(hosts, Path(args.known_hosts))
    except (inspection.InspectionError, OSError) as exc:
        category = str(exc) if isinstance(exc, inspection.InspectionError) else "collector-unavailable"
        print(json.dumps({"error": category}), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        columns = "{:<10} {:<14} {:<24} {:<12} {:<14} {}"
        print(columns.format("PROVIDER", "ENV", "HOST", "SOURCE_REV", "WATCHDOG_LOCAL", "CLIENT_PATH"))
        for row in result["hosts"]:
            print(columns.format(row["provider"], row["environment"], row["name"],
                                 (row["source_revision"] or "unknown")[:12],
                                 row["watchdog_local"]["status"], row["client_path"]))
    return int(any(row["watchdog_local"]["status"] != "healthy" for row in result["hosts"]))


if __name__ == "__main__":
    sys.exit(main())
