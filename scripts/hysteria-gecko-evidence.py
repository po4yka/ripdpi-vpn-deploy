#!/usr/bin/env python3
"""Capture, evaluate, and validate redacted Hysteria2 Gecko evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PHASES = (("salamander-a1", "salamander"), ("gecko-b", "gecko"), ("salamander-a2", "salamander"))
IDENTITY_FIELDS = (
    "scope",
    "vantage_id",
    "canary_id",
    "client_version",
    "client_sha256",
    "canary_endpoint_hmac_sha256",
    "control_endpoint_hmac_sha256",
    "target_endpoint_hmac_sha256",
    "client_transport_hmac_sha256",
    "obfs_password_hmac_sha256",
)
HASH_IDENTITY_FIELDS = (
    "client_sha256",
    "canary_endpoint_hmac_sha256",
    "control_endpoint_hmac_sha256",
    "target_endpoint_hmac_sha256",
    "client_transport_hmac_sha256",
    "obfs_password_hmac_sha256",
)
AUTH_FAILURE_MARKERS = ("authentication failed", "auth failed", "unauthorized")
TLS_FAILURE_MARKERS = ("certificate", "tls", "x509")
CONFIG_FAILURE_MARKERS = ("config error", "invalid config", "missing", "parse error", "unknown obfs")
LOCAL_FAILURE_MARKERS = ("permission denied", "no such file", "exec format")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def keyed_identity(key: bytes, label: str, value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hmac.new(key, label.encode("utf-8") + b"\0" + payload, hashlib.sha256).hexdigest()


def load_or_create_identity_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(os.urandom(32))
    path.chmod(0o600)
    key = path.read_bytes()
    if len(key) < 32:
        raise ValueError("evidence identity key must contain at least 32 bytes")
    return key


def inspect_client_config(path: Path, expected_obfs_type: str, identity_key: bytes) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("client config must be a YAML object")
    server = value.get("server")
    obfs = value.get("obfs")
    actual_obfs_type = obfs.get("type") if isinstance(obfs, dict) else None
    if not isinstance(server, str) or not server.strip():
        raise ValueError("client config must contain a server endpoint")
    if actual_obfs_type != expected_obfs_type:
        raise ValueError(f"client config obfs type is {actual_obfs_type!r}, expected {expected_obfs_type!r}")
    obfs_settings = obfs.get(expected_obfs_type) if isinstance(obfs, dict) else None
    if not isinstance(obfs_settings, dict):
        raise ValueError(f"client config must contain obfs.{expected_obfs_type} settings")
    password = obfs_settings.get("password")
    if not isinstance(password, str) or not password:
        raise ValueError("client config obfuscation password must be non-empty")
    gecko_min = gecko_max = None
    if expected_obfs_type == "gecko":
        gecko_min = obfs_settings.get("minPacketSize")
        gecko_max = obfs_settings.get("maxPacketSize")
        if not isinstance(gecko_min, int) or not isinstance(gecko_max, int) or not 1 <= gecko_min <= gecko_max <= 2048:
            raise ValueError("client config Gecko bounds must satisfy 1 <= minPacketSize <= maxPacketSize <= 2048")
    transport = dict(value)
    transport.pop("obfs", None)
    return {
        "canary_endpoint_hmac_sha256": keyed_identity(identity_key, "canary-endpoint", server.strip()),
        "client_config_hmac_sha256": keyed_identity(identity_key, "client-config", path.read_bytes()),
        "client_transport_hmac_sha256": keyed_identity(identity_key, "client-transport", json.dumps(transport, sort_keys=True, separators=(",", ":"))),
        "obfs_password_hmac_sha256": keyed_identity(identity_key, "obfs-password", password),
        "gecko_min_packet_size": gecko_min,
        "gecko_max_packet_size": gecko_max,
    }


def evaluate_documents(phases: list[dict[str, Any]]) -> dict[str, Any]:
    if len(phases) != 3:
        raise ValueError("evaluate requires exactly three phase reports")
    reasons: set[str] = set()
    for phase, (expected_phase, expected_obfs) in zip(phases, PHASES, strict=True):
        if phase.get("schema_version") != 1:
            reasons.add("unsupported_phase_schema")
        if phase.get("phase") != expected_phase or phase.get("obfs_type") != expected_obfs:
            reasons.add("phase_order_mismatch")
        if phase.get("attempts") != 10:
            reasons.add("attempt_count_mismatch")
        control_successes = phase.get("control_successes")
        if not isinstance(control_successes, int) or not 9 <= control_successes <= 10:
            reasons.add("control_unhealthy")
        if phase.get("invalid_failures", 0) != 0:
            reasons.add("invalid_failure_class")
        failure_classes = phase.get("failure_classes")
        if not isinstance(failure_classes, dict) or set(failure_classes) != {"network", "authentication", "tls", "malformed_config", "local_process"}:
            reasons.add("invalid_failure_classes")
        elif any(not isinstance(count, int) or count < 0 for count in failure_classes.values()):
            reasons.add("invalid_failure_classes")
        elif failure_classes["network"] != phase.get("network_failures") or sum(failure_classes[key] for key in ("authentication", "tls", "malformed_config", "local_process")) != phase.get("invalid_failures"):
            reasons.add("invalid_failure_classes")
        successes = phase.get("hysteria_successes")
        failures = phase.get("network_failures")
        invalid_count = phase.get("invalid_failures")
        if not all(isinstance(count, int) for count in (successes, failures, invalid_count)) or successes + failures + invalid_count != 10:
            reasons.add("invalid_counts")
        config_hash = phase.get("client_config_hmac_sha256")
        if (
            not isinstance(config_hash, str)
            or len(config_hash) != 64
            or any(character not in "0123456789abcdef" for character in config_hash)
        ):
            reasons.add("invalid_config_identity")
    if phases[0].get("client_config_hmac_sha256") != phases[2].get("client_config_hmac_sha256"):
        reasons.add("salamander_config_mismatch")
    gecko_min = phases[1].get("gecko_min_packet_size")
    gecko_max = phases[1].get("gecko_max_packet_size")
    if not isinstance(gecko_min, int) or not isinstance(gecko_max, int) or not 1 <= gecko_min <= gecko_max <= 2048:
        reasons.add("invalid_gecko_bounds")
    if any(len({phase.get(field) for phase in phases}) != 1 for field in IDENTITY_FIELDS):
        reasons.add("identity_mismatch")
    if any(
        not isinstance(phases[0].get(field), str)
        or len(phases[0][field]) != 64
        or any(character not in "0123456789abcdef" for character in phases[0][field])
        for field in HASH_IDENTITY_FIELDS
    ):
        reasons.add("invalid_identity_hash")
    try:
        starts = [parse_timestamp(str(phase["started_at"])) for phase in phases]
        finishes = [parse_timestamp(str(phase["finished_at"])) for phase in phases]
        if any(start >= finish for start, finish in zip(starts, finishes, strict=True)) or not (finishes[0] <= starts[1] and finishes[1] <= starts[2]):
            reasons.add("phase_order_mismatch")
        if (finishes[2] - starts[0]).total_seconds() > 86400:
            reasons.add("measurement_window_exceeded")
    except (KeyError, TypeError, ValueError):
        reasons.add("invalid_time_window")
    if isinstance(phases[0].get("hysteria_successes"), int) and phases[0]["hysteria_successes"] > 2:
        reasons.add("salamander_a1_not_blocked")
    if isinstance(phases[1].get("hysteria_successes"), int) and phases[1]["hysteria_successes"] < 8:
        reasons.add("gecko_not_effective")
    if isinstance(phases[2].get("hysteria_successes"), int) and phases[2]["hysteria_successes"] > 2:
        reasons.add("salamander_a2_not_blocked")
    summary_fields = ("phase", "obfs_type", "client_config_hmac_sha256", "gecko_min_packet_size", "gecko_max_packet_size", "started_at", "finished_at", "attempts", "hysteria_successes", "control_successes", "network_failures", "invalid_failures", "failure_classes", "latency_ms")
    return {"schema_version": 1, **{field: phases[0].get(field) for field in IDENTITY_FIELDS}, "gecko_min_packet_size": gecko_min, "gecko_max_packet_size": gecko_max, "verdict": "confirmed" if not reasons else "rejected", "reason_codes": sorted(reasons), "phases": [{field: phase.get(field) for field in summary_fields} for phase in phases]}


def evaluate(paths: list[Path]) -> dict[str, Any]:
    return evaluate_documents([load_json(path) for path in paths])


def command_evaluate(args: argparse.Namespace) -> int:
    try:
        report = evaluate([Path(path) for path in args.phases])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"hysteria-gecko-evidence: {exc}", file=sys.stderr)
        return 2
    write_json(Path(args.output), report)
    if report["verdict"] != "confirmed":
        print("hysteria-gecko-evidence: rejected: " + ", ".join(report["reason_codes"]), file=sys.stderr)
        return 1
    print(f"hysteria-gecko-evidence: confirmed: {args.output}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    path = Path(args.report)
    try:
        raw = path.read_bytes()
        report = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"hysteria-gecko-evidence: cannot read report: {exc}", file=sys.stderr)
        return 1
    errors = []
    if hashlib.sha256(raw).hexdigest() != args.sha256.lower():
        errors.append("sha256_mismatch")
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        errors.append("unsupported_report_schema")
    elif report.get("verdict") != "confirmed" or report.get("reason_codes") != []:
        errors.append("report_not_confirmed")
    elif not all(isinstance(report.get(field), str) and report[field] for field in IDENTITY_FIELDS):
        errors.append("invalid_identity")
    else:
        phase_summaries = report.get("phases")
        if not isinstance(phase_summaries, list):
            errors.append("invalid_phases")
        else:
            phase_documents = [
                {"schema_version": 1, **{field: report[field] for field in IDENTITY_FIELDS}, **phase}
                for phase in phase_summaries
                if isinstance(phase, dict)
            ]
            if len(phase_documents) != len(phase_summaries):
                errors.append("invalid_phases")
            else:
                try:
                    recomputed = evaluate_documents(phase_documents)
                except (TypeError, ValueError):
                    errors.append("invalid_phases")
                else:
                    if recomputed["verdict"] != "confirmed" or recomputed["reason_codes"]:
                        errors.append("report_not_confirmed")
    if isinstance(report, dict):
        if report.get("scope") != args.scope:
            errors.append("scope_mismatch")
        if getattr(args, "gecko_min_packet_size", None) is not None and report.get("gecko_min_packet_size") != args.gecko_min_packet_size:
            errors.append("gecko_bounds_mismatch")
        if getattr(args, "gecko_max_packet_size", None) is not None and report.get("gecko_max_packet_size") != args.gecko_max_packet_size:
            errors.append("gecko_bounds_mismatch")
    if errors:
        print("hysteria-gecko-evidence: invalid: " + ", ".join(errors), file=sys.stderr)
        return 1
    print(f"hysteria-gecko-evidence: valid: {path}")
    return 0


def command_validate_config(args: argparse.Namespace) -> int:
    merged: dict[str, Any] = {}

    def merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value

    try:
        for raw_path in args.group_vars:
            value = yaml.safe_load(Path(raw_path).read_text(encoding="utf-8")) or {}
            if not isinstance(value, dict):
                raise ValueError(f"{raw_path}: expected a YAML object")
            merge(merged, value)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"hysteria-gecko-evidence: {exc}", file=sys.stderr)
        return 2
    if merged.get("hysteria_obfs_type") != "gecko":
        print("hysteria-gecko-evidence: Gecko disabled; no evidence required")
        return 0
    report = str(Path(args.repo_root) / str(merged.get("hysteria_gecko_evidence_report", "")))
    return command_validate(
        argparse.Namespace(
            report=report,
            scope=str(merged.get("hysteria_gecko_evidence_scope", "")),
            sha256=str(merged.get("hysteria_gecko_evidence_sha256", "")),
            gecko_min_packet_size=int(merged.get("hysteria_gecko_min_packet_size", 512)),
            gecko_max_packet_size=int(merged.get("hysteria_gecko_max_packet_size", 1200)),
        )
    )


def command_probe(args: argparse.Namespace) -> int:
    if dict(PHASES).get(args.phase) != args.obfs_type:
        print("hysteria-gecko-evidence: phase and obfs type do not match", file=sys.stderr)
        return 2
    binary_text = args.hysteria_binary or shutil.which("hysteria")
    binary = Path(binary_text) if binary_text else Path()
    config = Path(args.client_config)
    if not binary.is_file() or not config.is_file():
        print("hysteria-gecko-evidence: binary or client config not found", file=sys.stderr)
        return 2
    try:
        socks_host, socks_port_text = args.socks_address.rsplit(":", 1)
        socks_port = int(socks_port_text)
    except ValueError:
        print("hysteria-gecko-evidence: invalid SOCKS address", file=sys.stderr)
        return 2
    try:
        with socket.create_connection((socks_host, socks_port), timeout=0.2):
            print("hysteria-gecko-evidence: SOCKS address is already in use", file=sys.stderr)
            return 2
    except OSError:
        pass
    version = subprocess.run([str(binary), "version"], capture_output=True, text=True, timeout=10)
    version_lines = (version.stdout or version.stderr).strip().splitlines()
    if version.returncode != 0 or not version_lines:
        print("hysteria-gecko-evidence: unable to identify client binary", file=sys.stderr)
        return 2
    raw_dir = Path(args.raw_log_dir).expanduser()
    raw_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity_key_path = Path(args.identity_key_file).expanduser() if args.identity_key_file else raw_dir / "identity.key"
    try:
        identity_key = load_or_create_identity_key(identity_key_path)
    except (OSError, ValueError) as exc:
        print(f"hysteria-gecko-evidence: invalid identity key: {exc}", file=sys.stderr)
        return 2
    cached_config = raw_dir / f"{args.phase}-client-config{config.suffix or '.yaml'}"
    shutil.copyfile(config, cached_config)
    cached_config.chmod(0o600)
    try:
        config_identity = inspect_client_config(cached_config, args.obfs_type, identity_key)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"hysteria-gecko-evidence: invalid client config: {exc}", file=sys.stderr)
        return 2
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    hysteria_successes = control_successes = network_failures = invalid_failures = 0
    failure_classes = {"network": 0, "authentication": 0, "tls": 0, "malformed_config": 0, "local_process": 0}
    latencies: list[int] = []
    for attempt in range(1, 11):
        control = subprocess.run(["curl", "-fsS", "--max-time", str(args.timeout), "-o", "/dev/null", args.control_url], capture_output=True, text=True)
        control_successes += int(control.returncode == 0)
        log_path = raw_dir / f"{args.phase}-{attempt:02d}.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen([str(binary), "client", "-c", str(cached_config)], stdout=log, stderr=subprocess.STDOUT, text=True)
            ready = False
            for _ in range(50):
                if process.poll() is not None:
                    break
                try:
                    with socket.create_connection((socks_host, socks_port), timeout=0.1):
                        ready = True
                        break
                except OSError:
                    time.sleep(0.1)
            before = time.monotonic()
            proxy = subprocess.run(["curl", "-fsS", "--max-time", str(args.timeout), "--proxy", f"socks5h://{args.socks_address}", "-o", "/dev/null", args.target_url], capture_output=True, text=True) if ready else None
            elapsed_ms = int((time.monotonic() - before) * 1000)
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        log_path.chmod(0o600)
        log_text = log_path.read_text(encoding="utf-8", errors="replace").lower()
        combined_error = "\n".join((log_text, proxy.stderr.lower() if proxy is not None else ""))
        classification = "success"
        if proxy is not None and proxy.returncode == 0:
            hysteria_successes += 1
            latencies.append(elapsed_ms)
        elif any(marker in combined_error for marker in AUTH_FAILURE_MARKERS):
            classification = "authentication"
            failure_classes[classification] += 1
            invalid_failures += 1
        elif any(marker in combined_error for marker in TLS_FAILURE_MARKERS):
            classification = "tls"
            failure_classes[classification] += 1
            invalid_failures += 1
        elif any(marker in combined_error for marker in CONFIG_FAILURE_MARKERS):
            classification = "malformed_config"
            failure_classes[classification] += 1
            invalid_failures += 1
        elif any(marker in combined_error for marker in LOCAL_FAILURE_MARKERS) or (not ready and process.returncode not in (0, -15)):
            classification = "local_process"
            failure_classes[classification] += 1
            invalid_failures += 1
        else:
            classification = "network"
            failure_classes[classification] += 1
            network_failures += 1
        attempt_record = {
            "attempt": attempt,
            "phase": args.phase,
            "client_config": str(cached_config),
            "control_url": args.control_url,
            "target_url": args.target_url,
            "control_returncode": control.returncode,
            "control_error": control.stderr,
            "proxy_returncode": proxy.returncode if proxy is not None else None,
            "proxy_error": proxy.stderr if proxy is not None else None,
            "client_returncode": process.returncode,
            "classification": classification,
            "latency_ms": elapsed_ms,
        }
        attempt_path = raw_dir / f"{args.phase}-{attempt:02d}.attempt.json"
        write_json(attempt_path, attempt_record)
        attempt_path.chmod(0o600)
    latency_summary = {"min": min(latencies), "median": int(statistics.median(latencies)), "max": max(latencies)} if latencies else None
    report = {"schema_version": 1, "phase": args.phase, "obfs_type": args.obfs_type, "scope": args.scope, "vantage_id": args.vantage_id, "canary_id": args.canary_id, "client_version": version_lines[0], "client_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), **config_identity, "control_endpoint_hmac_sha256": keyed_identity(identity_key, "control-endpoint", args.control_url), "target_endpoint_hmac_sha256": keyed_identity(identity_key, "target-endpoint", args.target_url), "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "attempts": 10, "hysteria_successes": hysteria_successes, "control_successes": control_successes, "network_failures": network_failures, "invalid_failures": invalid_failures, "failure_classes": failure_classes, "latency_ms": latency_summary}
    write_json(Path(args.output), report)
    print(json.dumps({"phase": args.phase, "hysteria_successes": hysteria_successes, "control_successes": control_successes, "invalid_failures": invalid_failures}))
    return 0 if invalid_failures == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("phases", nargs=3)
    evaluate_parser.add_argument("--output", required=True)
    evaluate_parser.set_defaults(func=command_evaluate)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("report")
    validate_parser.add_argument("--scope", required=True)
    validate_parser.add_argument("--sha256", required=True)
    validate_parser.add_argument("--gecko-min-packet-size", type=int)
    validate_parser.add_argument("--gecko-max-packet-size", type=int)
    validate_parser.set_defaults(func=command_validate)
    config_parser = subparsers.add_parser("validate-config")
    config_parser.add_argument("group_vars", nargs="+")
    config_parser.add_argument("--repo-root", default=".")
    config_parser.set_defaults(func=command_validate_config)
    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("--phase", choices=[phase for phase, _ in PHASES], required=True)
    probe_parser.add_argument("--obfs-type", choices=["salamander", "gecko"], required=True)
    probe_parser.add_argument("--client-config", required=True)
    probe_parser.add_argument("--hysteria-binary")
    probe_parser.add_argument("--socks-address", default="127.0.0.1:31081")
    probe_parser.add_argument("--control-url", required=True)
    probe_parser.add_argument("--target-url", required=True)
    probe_parser.add_argument("--scope", required=True)
    probe_parser.add_argument("--vantage-id", required=True)
    probe_parser.add_argument("--canary-id", required=True)
    probe_parser.add_argument("--timeout", type=int, default=15)
    probe_parser.add_argument("--raw-log-dir", default="~/.cache/vpn-deploy/hysteria-gecko")
    probe_parser.add_argument("--identity-key-file")
    probe_parser.add_argument("--output", required=True)
    probe_parser.set_defaults(func=command_probe)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
