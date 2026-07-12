#!/usr/bin/env python3
"""Produce redacted cascade leg health evidence from authenticated HTTPS completion."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CONFIG_SCHEMA = Path(os.environ.get("CASCADE_LEG_PROBE_SCHEMA", ROOT / "contract" / "cascade-leg-probe-config.schema.json"))


class ProbeBlocked(ValueError):
    """The probe cannot make a trustworthy health claim."""


def _timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def _read_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProbeBlocked(f"probe config missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        import jsonschema
    except (OSError, json.JSONDecodeError, ImportError) as exc:
        raise ProbeBlocked(f"probe config unavailable: {exc}") from exc
    schema = json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        raise ProbeBlocked("probe config invalid: " + "; ".join(error.message for error in errors))
    if value["leg_interface"] == value["direct_interface"]:
        raise ProbeBlocked("leg and direct-control interfaces must be distinct")
    return value


def _read_token(path: Path) -> str:
    if not path.is_file():
        raise ProbeBlocked(f"probe token missing: {path}")
    if path.stat().st_mode & 0o077:
        raise ProbeBlocked("probe token permissions must exclude group and other access")
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\n" in token or "\r" in token or '"' in token:
        raise ProbeBlocked("probe token is empty or contains unsafe characters")
    return token


def _curl_config(url: str, token: str) -> str:
    if '"' in url or "\n" in url or "\r" in url:
        raise ProbeBlocked("probe URL contains unsafe characters")
    return f'url = "{url}"\nheader = "Authorization: Bearer {token}"\nrequest = "GET"\n'


def _probe(curl_bin: str, config: dict[str, Any], token: str, interface: str) -> tuple[bool, str, bool]:
    with tempfile.NamedTemporaryFile() as response:
        completed = subprocess.run(
            [
                curl_bin,
                "--silent",
                "--show-error",
                "--fail-with-body",
                "--max-time",
                str(config["timeout_seconds"]),
                "--interface",
                interface,
                "--config",
                "-",
                "--output",
                response.name,
                "--write-out",
                "%{http_code}",
            ],
            input=_curl_config(config["probe_url"], token),
            text=True,
            capture_output=True,
            check=False,
        )
        body_sha256 = hashlib.sha256(Path(response.name).read_bytes()).hexdigest()
    status = completed.stdout.strip()
    body_matches = body_sha256 == config["expected_body_sha256"]
    ok = completed.returncode == 0 and status == str(config["expected_status"]) and body_matches
    return ok, status if status.isdigit() else "unavailable", body_matches


def _load_failures(path: Path) -> int:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        failures = int(value["consecutive_failures"])
        return max(0, failures)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return 0


def _atomic_json(path: Path, value: dict[str, Any]) -> bytes:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return payload


def run(args: argparse.Namespace) -> int:
    config = _read_config(args.config)
    token = _read_token(args.token_file)
    control_ok, control_status, control_body = _probe(args.curl_bin, config, token, config["direct_interface"])
    leg_ok, leg_status, leg_body = _probe(args.curl_bin, config, token, config["leg_interface"])

    if control_ok and leg_ok:
        failures = 0
        status = "healthy"
    elif control_ok:
        failures = _load_failures(args.state_file) + 1
        status = "far-leg-down" if failures >= config["failure_threshold"] else "degraded"
    else:
        failures = 1
        status = "degraded"

    checked_at = args.now.astimezone(dt.timezone.utc)
    timestamp = checked_at.strftime("%Y%m%dt%H%M%Sz")
    report_id = f"{config['host_id']}-{config['leg_id']}-{timestamp}"
    report = {
        "schema_version": 1,
        "report_id": report_id,
        "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "leg_probe": {"completed": leg_ok, "http_status": leg_status, "body_matched": leg_body},
        "direct_control": {"completed": control_ok, "http_status": control_status, "body_matched": control_body},
    }
    report_path = args.evidence_dir / f"{report_id}.json"
    report_payload = _atomic_json(report_path, report)
    record = {
        "schema_version": 1,
        "host_id": config["host_id"],
        "leg_id": config["leg_id"],
        "checked_at": report["checked_at"],
        "signal_class": "authenticated-protocol-completion",
        "status": status,
        "consecutive_failures": failures,
        "ingress_local_control": "healthy" if control_ok else "unhealthy",
        "protocol_completed": control_ok and leg_ok,
        "evidence": {"report_id": report_id, "report_sha256": hashlib.sha256(report_payload).hexdigest()},
    }
    _atomic_json(args.state_file, {"consecutive_failures": failures})
    _atomic_json(args.health_record, record)
    print(json.dumps({"status": status, "report_id": report_id}, sort_keys=True))
    return 0 if status == "healthy" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--health-record", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--curl-bin", default="curl")
    parser.add_argument("--now", type=_timestamp, default=dt.datetime.now(dt.timezone.utc))
    return parser.parse_args()


def main() -> int:
    try:
        return run(parse_args())
    except (ProbeBlocked, OSError, subprocess.SubprocessError) as exc:
        print(f"cascade leg probe blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
