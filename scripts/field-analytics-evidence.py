#!/usr/bin/env python3
"""Check exported evidence of one field-analytics acceptance run.

The run itself is manual (docs/how-to/field-analytics-acceptance.md). Each
subcommand reads one artifact the operator saved during the run and prints one
verdict line, so the verification file can quote the same check for every run:

  bundle  BUNDLE.json  --server-ref REF       the endpoint is degraded or down and its health is fresh
  ingest  QUERY.json   --protocol P --stage S  Prometheus shows the failure series for P and S
  alert   ALERTS.json  --protocol P --asn N    FieldReportNetworkBlocked is active (firing) for P and N

QUERY.json is a Prometheus /api/v1/query response for
vpn_field_report_failures_total; ALERTS.json is an Alertmanager /api/v2/alerts
list or a Prometheus /api/v1/alerts document. --at sets the instant the artifact was captured (default: now). Exit 0
means the claim holds, 1 that it does not, 2 an unusable artifact. Values from
the artifacts are printed only when they match a plain pattern.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAIN = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
ALLOWED_INGEST_LABELS = {"__name__", "environment", "node", "job", "instance", "protocol", "failure_stage", "asn"}


class Unusable(Exception):
    pass


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError, RecursionError):
        raise Unusable(f"{path.name}: not a readable JSON document") from None


def _instant(text: str) -> datetime:
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise Unusable("--at needs an RFC 3339 instant") from None
    if moment.tzinfo is None:
        raise Unusable("--at needs an explicit offset")
    return moment


def check_bundle(path: Path, server_ref: str, at: datetime) -> tuple[bool, str]:
    validation = subprocess.run([sys.executable, str(REPO_ROOT / "scripts/validate-bundle.py"), str(path)],
                                capture_output=True, text=True, check=False)
    if validation.returncode != 0:
        return False, "bundle does not validate as ripdpi-bundle v3"
    document = _load(path)
    ripdpi = document.get("ripdpi", document) if isinstance(document, dict) else {}
    health = ((ripdpi.get("endpoints") or {}).get(server_ref) or {}).get("health")
    if not isinstance(health, dict):
        return False, "bundle has no health for that endpoint"
    observed = _instant(health["observed_at"])
    expires = observed + timedelta(seconds=health["ttl_seconds"])
    if health["status"] not in ("degraded", "down"):
        return False, f"endpoint health is {health['status']}, not degraded or down"
    if not observed <= at < expires:
        return False, "endpoint health was not fresh at the capture instant"
    return True, f"endpoint health is {health['status']} until {expires.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def _looks_like_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def check_ingest(path: Path, protocol: str, stage: str) -> tuple[bool, str]:
    document = _load(path)
    data = document.get("data") if isinstance(document, dict) else None
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, list) or not all(isinstance(item, dict) and isinstance(item.get("metric"), dict)
                                               for item in result):
        raise Unusable(f"{path.name}: not a Prometheus instant-query vector")
    matching = []
    for item in result:
        labels = item["metric"]
        extra = set(labels) - ALLOWED_INGEST_LABELS
        if extra or any(_looks_like_address(str(value)) for value in labels.values()):
            return False, "a field-report series carries a label outside the contract or an address"
        if labels.get("protocol") == protocol and labels.get("failure_stage") == stage:
            matching.append(item)
    if not matching:
        return False, "no failure series for that protocol and stage"
    if not all(labels.get("node") for labels in (item["metric"] for item in matching)):
        return False, "a matching series has no node label"
    try:
        total = sum(float(item["value"][1]) for item in matching)
    except (KeyError, IndexError, TypeError, ValueError):
        raise Unusable(f"{path.name}: a sample has no numeric value") from None
    if total <= 0:
        return False, "the failure series exist but count no failures"
    return True, f"{len(matching)} failure series for {protocol} {stage}, {total:.0f} failures"


def check_alert(path: Path, protocol: str, asn: str) -> tuple[bool, str]:
    document = _load(path)
    data = document.get("data") if isinstance(document, dict) else None
    alerts = data.get("alerts") if isinstance(data, dict) else document
    if not isinstance(alerts, list):
        raise Unusable(f"{path.name}: not an Alertmanager or Prometheus alert list")
    for alert in alerts:
        labels = alert.get("labels") if isinstance(alert, dict) else None
        if not isinstance(labels, dict):
            raise Unusable(f"{path.name}: an alert has no labels")
        status = alert.get("status")
        # Alertmanager reports status.state "active"; Prometheus reports state "firing" once the hold has passed.
        state = status.get("state") if isinstance(status, dict) else alert.get("state")
        if (labels.get("alertname") == "FieldReportNetworkBlocked" and labels.get("protocol") == protocol
                and labels.get("asn") == asn and state in ("active", "firing")):
            country = labels.get("country")
            shown = country if isinstance(country, str) and PLAIN.match(country) else "unprintable"
            return True, f"FieldReportNetworkBlocked is active for {protocol} AS{asn} ({shown})"
    return False, "no active FieldReportNetworkBlocked alert for that protocol and ASN"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="kind", required=True)
    bundle = sub.add_parser("bundle")
    bundle.add_argument("artifact", type=Path)
    bundle.add_argument("--server-ref", required=True)
    bundle.add_argument("--at")
    ingest = sub.add_parser("ingest")
    ingest.add_argument("artifact", type=Path)
    ingest.add_argument("--protocol", required=True)
    ingest.add_argument("--stage", required=True)
    alert = sub.add_parser("alert")
    alert.add_argument("artifact", type=Path)
    alert.add_argument("--protocol", required=True)
    alert.add_argument("--asn", required=True)
    args = parser.parse_args(argv)
    for value in (getattr(args, name, None) for name in ("server_ref", "protocol", "stage", "asn")):
        if value is not None and not PLAIN.match(value):
            print("field-analytics-evidence: arguments must be plain identifiers", file=sys.stderr)
            return 2
    try:
        if args.kind == "bundle":
            at = _instant(args.at) if args.at else datetime.now(timezone.utc)
            held, message = check_bundle(args.artifact, args.server_ref, at)
        elif args.kind == "ingest":
            held, message = check_ingest(args.artifact, args.protocol, args.stage)
        else:
            held, message = check_alert(args.artifact, args.protocol, args.asn)
    except Unusable as error:
        print(f"field-analytics-evidence: {error}", file=sys.stderr)
        return 2
    print(f"{'PASS' if held else 'FAIL'} {args.kind}: {message}")
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
