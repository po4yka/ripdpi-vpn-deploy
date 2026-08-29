#!/usr/bin/env python3
"""Schedule-safe authenticated protocol monitor with transition alerts.

The evaluator owns probe collection and quorum semantics. This wrapper owns
durable redacted evidence, alert/recovery transitions, and ntfy delivery.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from liveness_generation import JOB_TIMEOUT_SECONDS


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVALUATOR = REPO_ROOT / "scripts" / "protocol-liveness.py"
DECRYPT_SECRETS = REPO_ROOT / "scripts" / "decrypt-secrets.sh"
DECISIONS = {"healthy", "degraded", "unknown", "rotation_candidate"}
REMINDER_SECONDS = 24 * 60 * 60
EVALUATOR_TIMEOUT_SECONDS = JOB_TIMEOUT_SECONDS


class MonitorError(RuntimeError):
    """The monitor cannot produce trustworthy evidence."""


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def evaluate(config: Path, state_dir: Path) -> dict:
    evaluator = Path(os.environ.get("PROTOCOL_LIVENESS", str(DEFAULT_EVALUATOR)))
    try:
        result = subprocess.run(
            [str(evaluator), "--config", str(config), "--state-dir", str(state_dir)],
            text=True,
            capture_output=True,
            timeout=EVALUATOR_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MonitorError(f"evaluator unavailable: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise MonitorError(f"evaluator exited {result.returncode}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MonitorError("evaluator returned malformed JSON") from exc
    if (not isinstance(report, dict) or report.get("schema_version") != 2
            or report.get("decision") not in DECISIONS):
        raise MonitorError("evaluator returned an unsupported decision")
    return report


def credentials_from_file(path: Path) -> tuple[str, str]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            metadata = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077
            ):
                return "", ""
            value = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return "", ""
    if not isinstance(value, dict) or not isinstance(value.get("watchdog_secrets"), dict):
        return "", ""
    watchdog = value["watchdog_secrets"]
    return str(watchdog.get("ntfy_topic") or ""), str(watchdog.get("ntfy_token") or "")


def notification_credentials() -> tuple[str, str]:
    topic = os.environ.get("NTFY_TOPIC", "")
    token = os.environ.get("NTFY_TOKEN", "")
    if topic:
        return topic, token
    materialized = os.environ.get("VPN_SECRETS_FILE", "")
    if materialized:
        return credentials_from_file(Path(materialized))
    sops_file = os.environ.get("SOPS_FILE", "")
    if not sops_file or not Path(sops_file).is_file():
        return "", ""
    with tempfile.TemporaryDirectory(prefix="vpn-liveness-secrets-") as directory:
        secrets_file = Path(directory) / "secrets.yaml"
        environment = os.environ.copy()
        environment.update(
            {
                "VPN_RUNTIME_DIR": directory,
                "SECRETS_FILE": str(secrets_file),
                "SOPS_FILE": sops_file,
            }
        )
        try:
            result = subprocess.run(
                [str(DECRYPT_SECRETS)],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "", ""
        if result.returncode != 0:
            return "", ""
        return credentials_from_file(secrets_file)


def evidence_summary(report: dict) -> str:
    rows: list[str] = []
    for item in report.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        profiles = item.get("profiles") or {}
        profile_text = ",".join(f"{key}={profiles[key]}" for key in sorted(profiles))
        rows.append(f"{item.get('sentinel', 'unknown')}:{profile_text}")
    errors = "; ".join(str(value) for value in report.get("monitoring_errors") or [])
    return f"evidence={'; '.join(rows) or 'none'} errors={errors or 'none'}"


def send_notification(event: str, report: dict) -> str:
    topic, token = notification_credentials()
    if not topic:
        return "failed"
    decision = report["decision"]
    if event == "recovery":
        title = "VPN VLESS user path recovered"
        priority = "default"
        tags = "white_check_mark,vpn,vless"
    else:
        title = f"VPN VLESS user path {decision.replace('_', ' ')}"
        priority = "urgent" if decision == "rotation_candidate" else "high"
        tags = "warning,vpn,vless,protocol-liveness"
    base_url = os.environ.get("NTFY_URL", "https://ntfy.sh").rstrip("/")
    url = f"{base_url}/{urllib.parse.quote(topic, safe='')}"
    request = urllib.request.Request(
        url,
        data=evidence_summary(report).encode(),
        method="POST",
        headers={"Title": title, "Priority": priority, "Tags": tags},
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                return "failed"
    except (OSError, urllib.error.URLError):
        return "failed"
    return "sent"


def choose_event(report: dict, previous: dict, now: int) -> str:
    decision = report["decision"]
    previous_decision = previous.get("decision")
    alert_active = bool(previous.get("alert_active"))
    if decision == "healthy":
        return "recovery" if alert_active else "none"
    last_delivery = previous.get("alert_delivery")
    last_notified_at = previous.get("last_notified_at")
    reminder_due = not isinstance(last_notified_at, int) or now - last_notified_at >= REMINDER_SECONDS
    if previous_decision != decision or last_delivery != "sent" or reminder_due:
        return "alert"
    return "none"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--state-dir", type=Path)
    args = parser.parse_args()
    state_dir = args.state_dir or Path(
        os.environ.get(
            "PROTOCOL_LIVENESS_STATE_DIR",
            str(Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "vpn-deploy/protocol-liveness"),
        )
    )
    now = int(time.time())
    try:
        report = evaluate(args.config, state_dir)
    except MonitorError as exc:
        report = {
            "schema_version": 2,
            "evaluated_at": now,
            "decision": "unknown",
            "candidate_policies": [],
            "failed_vantages": {},
            "monitoring_errors": [f"evaluator: {exc}"],
            "evidence": [],
        }
    state_path = state_dir / "monitor-state.json"
    previous = read_json(state_path)
    event = choose_event(report, previous, now)
    delivery = send_notification(event, report) if event != "none" else "not_requested"
    last_delivery = previous.get("alert_delivery", "not_requested")
    if event != "none":
        last_delivery = delivery
    last_notified_at = previous.get("last_notified_at")
    if delivery == "sent":
        last_notified_at = now
    alert_active = report["decision"] != "healthy"
    if event == "recovery" and delivery != "sent":
        alert_active = True
    state = {
        "schema_version": 1,
        "decision": report["decision"],
        "alert_active": alert_active,
        "alert_delivery": last_delivery,
        "last_evaluated_at": now,
        "last_notified_at": last_notified_at,
    }
    report.update({"monitor_event": event, "alert_delivery": delivery})
    atomic_json(state_path, state)
    atomic_json(state_dir / "last-evidence.json", report)
    print(json.dumps(report, sort_keys=True))
    return 4 if event != "none" and delivery != "sent" else 0


if __name__ == "__main__":
    raise SystemExit(main())
