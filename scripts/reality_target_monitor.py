#!/usr/bin/env python3
"""State/report engine for monitor-reality-target.sh."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
import sys
import re
import signal
from typing import Any


def atomic_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".reality-target-monitor-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        pathlib.Path(tmp_name).unlink(missing_ok=True)


def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def read_reasons(path: pathlib.Path) -> list[str]:
    try:
        return list(dict.fromkeys(line.strip() for line in path.read_text().splitlines() if line.strip()))
    except OSError:
        return []


def read_observations(path: pathlib.Path) -> list[dict[str, Any]]:
    observations = []
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except OSError:
        lines = []
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 5:
            continue
        ip, asn, prefix, checked, failed = fields
        observations.append({
            "ip": ip,
            "asn": asn or None,
            "prefix": prefix or None,
            "checks": int(checked),
            "failed_checks": int(failed),
        })
    return observations


def next_strike(previous_day: str | None, current_day: str, previous_count: int) -> tuple[int, bool]:
    if previous_day == current_day:
        return previous_count, False
    if previous_day:
        try:
            previous = dt.date.fromisoformat(previous_day)
            current = dt.date.fromisoformat(current_day)
            if current == previous + dt.timedelta(days=1):
                return previous_count + 1, True
        except ValueError:
            # Invalid persisted dates intentionally restart the strike sequence.
            pass
    return 1, True


def evaluate(args: argparse.Namespace) -> int:
    target = os.environ["TARGET"]
    server_names = os.environ["SERVER_NAMES"]
    target += "\0" + os.environ.get("TARGET_MODE", "borrowed") + "\0" + os.environ.get("PUBLIC_ENDPOINT", "")
    fingerprint = hashlib.sha256((target + "\0" + server_names).encode()).hexdigest()
    reasons = read_reasons(args.reasons)
    observations = read_observations(args.observations)
    asns = sorted({row["asn"] for row in observations if row["asn"]})
    prefixes = sorted({row["prefix"] for row in observations if row["prefix"]})
    blocked_reasons = {"tls_handshake_failed", "certificate_validation_failed", "h2_unavailable", "certificate_san_mismatch", "https_no_response", "tls_failed", "http_failed", "http_status_failed", "client_failed"}
    verdict = "blocked" if any(reason in blocked_reasons for reason in reasons) else "unknown" if reasons else "ok"
    captured_at = args.captured_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    report = {
        "schema_version": 1,
        "captured_at": captured_at,
        "vantage": args.vantage,
        "target_fingerprint": fingerprint,
        "verdict": verdict,
        "asns": asns,
        "prefixes": prefixes,
        "reason_codes": reasons,
        "observations": observations,
    }

    state = read_json(args.state)
    same_target = state.get("target_fingerprint") == fingerprint
    previous_alert = bool(state.get("alert_active", False)) if same_target else False
    previous_count = int(state.get("consecutive_unhealthy", 0)) if same_target else 0
    previous_day = state.get("last_unhealthy_day") if same_target else None
    accepted_asns = list(state.get("accepted_asns", [])) if same_target else []
    accepted_prefixes = list(state.get("accepted_prefixes", [])) if same_target else []
    base_healthy = verdict == "ok"
    baseline_created = False
    baseline_accepted = False
    alert_event = "none"
    accept_failed = False

    if base_healthy and (not same_target or not accepted_asns or not accepted_prefixes):
        accepted_asns, accepted_prefixes = asns, prefixes
        baseline_created = True
    if args.accept_baseline:
        if base_healthy:
            accepted_asns, accepted_prefixes = asns, prefixes
            baseline_accepted = True
            if previous_alert:
                alert_event = "recovery"
        else:
            accept_failed = True
            reasons.append("accept_requires_healthy_path")
    if base_healthy and accepted_asns and asns != accepted_asns and not baseline_accepted:
        reasons.append("asn_set_changed")
    if base_healthy and accepted_prefixes and prefixes != accepted_prefixes and not baseline_accepted:
        reasons.append("prefix_set_changed")
    reasons = sorted(set(reasons))
    if base_healthy and reasons:
        verdict = "unknown"

    unhealthy = verdict != "ok"
    current_day = captured_at[:10]
    if baseline_accepted:
        consecutive, last_unhealthy_day = 0, None
        alert_active = alert_event == "recovery"
    elif unhealthy:
        consecutive, new_day = next_strike(previous_day, current_day, previous_count)
        last_unhealthy_day = current_day
        alert_active = previous_alert
        if new_day and (consecutive >= 2 or previous_alert):
            alert_event, alert_active = "alert", True
    else:
        consecutive, last_unhealthy_day = 0, None
        alert_event = "recovery" if previous_alert else "none"
        alert_active = previous_alert

    report.update({
        "verdict": verdict,
        "reason_codes": reasons,
        "alert_event": alert_event,
        "alert_delivery": "not_requested",
        "baseline_accepted": baseline_accepted,
        "baseline_created": baseline_created,
        "consecutive_unhealthy": consecutive,
    })
    atomic_json(args.state, {
        "schema_version": 1,
        "target_fingerprint": fingerprint,
        "accepted_asns": accepted_asns,
        "accepted_prefixes": accepted_prefixes,
        "consecutive_unhealthy": consecutive,
        "last_unhealthy_day": last_unhealthy_day,
        "alert_active": alert_active,
        "last_report": report,
    })
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 3 if accept_failed else 0


def record_delivery(args: argparse.Namespace) -> int:
    report = read_json(args.report)
    report["alert_delivery"] = args.delivery
    state = read_json(args.state)
    state["last_report"] = report
    if args.recovery_delivered:
        state["alert_active"] = False
    atomic_json(args.state, state)
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--observations", type=pathlib.Path, required=True)
    evaluate_parser.add_argument("--reasons", type=pathlib.Path, required=True)
    evaluate_parser.add_argument("--state", type=pathlib.Path, required=True)
    evaluate_parser.add_argument("--vantage", required=True)
    evaluate_parser.add_argument("--captured-at", default="")
    evaluate_parser.add_argument("--accept-baseline", action="store_true")
    delivery_parser = subparsers.add_parser("record-delivery")
    delivery_parser.add_argument("--state", type=pathlib.Path, required=True)
    delivery_parser.add_argument("--report", type=pathlib.Path, required=True)
    delivery_parser.add_argument("--delivery", choices=("not_requested", "sent", "failed"), required=True)
    delivery_parser.add_argument("--recovery-delivered", action="store_true")
    return parser.parse_args()


def probe(arguments: list[str]) -> int:
    from bootstrap_readiness import run_command, ReadinessError, cancellation
    try:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", os.environ.get("ENV", "prod")):
            raise ValueError
        budget = int(os.environ.get("REALITY_MONITOR_BUDGET", "120"))
        if not 1 <= budget <= 120:
            raise ValueError
    except ValueError:
        print(json.dumps({"schema_version": 1, "verdict": "error", "reason_codes": ["invalid_monitor_budget"]}))
        return 2
    failure = {"schema_version": 1, "verdict": "error", "reason_codes": ["monitor_deadline_or_process_refused"],
               "captured_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()}
    try:
        with tempfile.TemporaryDirectory(prefix="reality-monitor-owner-", dir=os.environ.get("TMPDIR")) as temporary:
            environment = {**os.environ, "TMPDIR": temporary}
            with cancellation(signals=(signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)):
                code, output = run_command(["bash", str(pathlib.Path(__file__).with_name("reality-target-monitor-probe.sh")), *arguments],
                    timeout=budget, environment=environment, capture=True, output_limit=65536, forward_stderr=True)
        if output:
            sys.stdout.buffer.write(output)
        return code
    except (ReadinessError, SystemExit) as error:
        # Preserve accepted ASN/prefix and alert budgets; replace only the
        # observation so a killed run cannot retain a healthy last report.
        state_home = pathlib.Path(os.environ.get("XDG_STATE_HOME", str(pathlib.Path.home() / ".local/state")))
        state_path = state_home / "vpn-deploy/reality-target-monitor" / (os.environ.get("ENV", "prod") + ".json")
        if state_path.is_file():
            state = read_json(state_path)
            if state:
                state["last_report"] = failure
                atomic_json(state_path, state)
        print(json.dumps(failure, sort_keys=True))
        return int(error.code) if isinstance(error, SystemExit) else 2


def main() -> int:
    if sys.argv[1:2] == ["probe"]:
        return probe(sys.argv[2:])
    args = parse_args()
    return evaluate(args) if args.command == "evaluate" else record_delivery(args)


if __name__ == "__main__":
    raise SystemExit(main())
