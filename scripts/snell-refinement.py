#!/usr/bin/env python3
"""Run a redacted Snell payload-size refinement evaluation from a client path."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import jsonschema
import yaml

DEFAULT_SIZES = [1024, 4096, 8192, 12288, 14336, 16384, 18432, 20480, 24576, 32768]
TECHNICAL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
AUTH_FAILURE = re.compile(r"auth(?:entication)?|credential|invalid user|psk|userkey", re.IGNORECASE)
SCHEMA = Path(__file__).resolve().parent.parent / "contract" / "snell-refinement-result.schema.json"


def median(values: list[int]) -> int | None:
    return int(statistics.median(values)) if values else None


def classify_profile(profile: str, sizes: list[int], repetitions: int, observations: list[dict]) -> dict:
    size_reports = []
    verdict = "ok"
    first_failure = None
    required = math.ceil(repetitions * 2 / 3)
    for size in sizes:
        rows = [row for row in observations if row["profile"] == profile and row["bytes"] == size]
        controls = [row for row in observations if row["profile"] == "direct" and row["bytes"] == size]
        control_healthy = len(controls) >= repetitions * 2 and all(row["completed"] for row in controls)
        completed = [row for row in rows if row["completed"]]
        elapsed = median([row["duration_ms"] for row in completed])
        control_elapsed = median([row["duration_ms"] for row in controls if row["completed"]])
        current = "ok"
        if not control_healthy:
            current = "unknown"
        elif len(completed) < required:
            current = "blocked"
        elif elapsed is not None and control_elapsed and elapsed >= 3 * control_elapsed:
            current = "throttled"
        if current == "unknown":
            verdict = "unknown"
        elif current == "blocked" and verdict != "unknown":
            verdict = "blocked"
        elif current == "throttled" and verdict == "ok":
            verdict = "throttled"
        if current in {"blocked", "throttled"} and first_failure is None:
            first_failure = size
        size_reports.append(
            {
                "bytes": size,
                "control_healthy": control_healthy,
                "completed": len(completed),
                "attempts": repetitions,
                "median_ms": elapsed,
                "control_median_ms": control_elapsed,
            }
        )
    return {"profile": profile, "verdict": verdict, "first_failure_bytes": first_failure, "sizes": size_reports}


def classify(profiles: list[str], sizes: list[int], repetitions: int, observations: list[dict]) -> list[dict]:
    return [classify_profile(profile, sizes, repetitions, observations) for profile in profiles]


def curl_probe(url: str, expected: int, timeout: int, port: int | None = None) -> dict:
    command = ["curl", "-sS", "-o", "/dev/null", "--max-time", str(timeout), "-w", "%{http_code} %{size_download} %{time_total}"]
    if port is not None:
        command += ["--socks5-hostname", f"127.0.0.1:{port}"]
    command.append(url)
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 2, check=False)
        status, downloaded, duration = process.stdout.strip().split()
        completed = process.returncode == 0 and int(status) == 200 and int(float(downloaded)) == expected
        return {"completed": completed, "duration_ms": round(float(duration) * 1000)}
    except (OSError, subprocess.TimeoutExpired, TypeError, ValueError):
        return {"completed": False, "duration_ms": None}


def snell_outbounds(bundle: dict) -> list[dict]:
    return [outbound for outbound in bundle.get("outbounds", []) if str(outbound.get("tag", "")).startswith("p3-snell-")]


def build_config(bundle: dict, path: Path) -> dict[str, int]:
    outbounds = snell_outbounds(bundle)
    if not outbounds:
        raise ValueError("bundle contains no Snell candidates")
    ports = {outbound["tag"]: 19000 + index for index, outbound in enumerate(outbounds)}
    document = {
        "log": {"level": "warn"},
        "inbounds": [
            {"type": "mixed", "tag": f"probe-{index}", "listen": "127.0.0.1", "listen_port": port}
            for index, port in enumerate(ports.values())
        ],
        "outbounds": outbounds,
        "route": {
            "rules": [
                {"inbound": [f"probe-{index}"], "outbound": tag}
                for index, tag in enumerate(ports)
            ],
            "auto_detect_interface": True,
        },
    }
    path.write_text(json.dumps(document, separators=(",", ":")) + "\n")
    os.chmod(path, 0o600)
    return ports


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def report_payload(vantage: str, config_bytes: bytes, verdict: str, profiles: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "observed_at": int(time.time()),
        "vantage": vantage,
        "verdict": verdict,
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "profiles": profiles,
    }


def error_profiles(bundle: dict) -> list[dict]:
    return [
        {"profile": outbound["tag"], "verdict": "error", "first_failure_bytes": None, "sizes": []}
        for outbound in snell_outbounds(bundle)
    ]


def mark_authentication_errors(reports: list[dict], observations: list[dict], runtime_log: str) -> None:
    if not AUTH_FAILURE.search(runtime_log):
        return
    failed_profiles = {
        report["profile"]
        for report in reports
        if not any(row["profile"] == report["profile"] and row["completed"] for row in observations)
    }
    for report in reports:
        if report["profile"] in failed_profiles:
            report["verdict"] = "error"
            report["first_failure_bytes"] = None


def emit_report(args: argparse.Namespace, payload: dict) -> None:
    jsonschema.validate(payload, json.loads(SCHEMA.read_text()))
    if args.state_dir:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(payload["observed_at"]))
        atomic_json(args.state_dir / args.vantage / f"{stamp}.json", payload)
    print(json.dumps(payload, sort_keys=True))


def load_inputs(args: argparse.Namespace) -> tuple[dict, bytes, dict, str, list[int], int, int]:
    bundle = json.loads(args.bundle.read_text())
    config_bytes = args.config.read_bytes()
    config = yaml.safe_load(config_bytes) or {}
    base_url = str(config["probe_base_url"]).rstrip("/")
    if not base_url.startswith("https://"):
        raise ValueError("probe_base_url must use https")
    sizes = [int(value) for value in config.get("sizes", DEFAULT_SIZES)]
    repetitions = int(config.get("repetitions", 3))
    timeout = int(config.get("timeout_seconds", 15))
    if repetitions < 3 or any(value < 1 for value in sizes):
        raise ValueError("invalid repetitions or sizes")
    return bundle, config_bytes, config, base_url, sizes, repetitions, timeout


def measure(base_url: str, sizes: list[int], repetitions: int, timeout: int, ports: dict[str, int], seed: object) -> list[dict]:
    observations = []
    randomizer = random.Random(seed)
    for size in sizes:
        url = f"{base_url}/{size}.bin"
        for _ in range(repetitions):
            observations.append({"profile": "direct", "bytes": size, **curl_probe(url, size, timeout)})
            candidates = list(ports.items())
            randomizer.shuffle(candidates)
            for profile, port in candidates:
                observations.append({"profile": profile, "bytes": size, **curl_probe(url, size, timeout, port)})
            observations.append({"profile": "direct", "bytes": size, **curl_probe(url, size, timeout)})
    return observations


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--vantage", required=True)
    parser.add_argument("--state-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not TECHNICAL_ID.fullmatch(args.vantage):
        print("invalid technical vantage id", file=sys.stderr)
        return 2

    bundle: dict = {}
    config_bytes = b""
    try:
        bundle, config_bytes, config, base_url, sizes, repetitions, timeout = load_inputs(args)
    except (OSError, KeyError, ValueError, json.JSONDecodeError, yaml.YAMLError):
        try:
            config_bytes = args.config.read_bytes()
        except OSError:
            # Preserve an empty hash input when the invalid config is unreadable.
            pass
        try:
            bundle = json.loads(args.bundle.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            # A malformed bundle cannot provide profile identifiers for the error report.
            pass
        emit_report(args, report_payload(args.vantage, config_bytes, "error", error_profiles(bundle)))
        return 1

    if not shutil.which("sing-box") or not shutil.which("curl"):
        emit_report(args, report_payload(args.vantage, config_bytes, "error", error_profiles(bundle)))
        return 1

    process = None
    payload = None
    with tempfile.TemporaryDirectory(prefix="snell-refinement-") as temporary:
        log_path = Path(temporary) / "sing-box.log"
        try:
            probe_config = Path(temporary) / "sing-box.json"
            ports = build_config(bundle, probe_config)
            check = subprocess.run(["sing-box", "check", "-c", str(probe_config)], capture_output=True, timeout=10, check=False)
            if check.returncode:
                raise RuntimeError("sing-box rejected probe configuration")
            with log_path.open("w+") as log_handle:
                process = subprocess.Popen(
                    ["sing-box", "run", "-c", str(probe_config)],
                    stdout=subprocess.DEVNULL,
                    stderr=log_handle,
                )
                time.sleep(0.25)
                if process.poll() is not None:
                    raise RuntimeError("sing-box stopped during startup")
                observations = measure(base_url, sizes, repetitions, timeout, ports, config.get("random_seed"))
                if process.poll() is not None:
                    raise RuntimeError("sing-box stopped during measurement")
                reports = classify(list(ports), sizes, repetitions, observations)
                log_handle.flush()
                log_handle.seek(0)
                runtime_log = log_handle.read()
            mark_authentication_errors(reports, observations, runtime_log)
            overall = next(
                (candidate for candidate in ("error", "unknown", "blocked", "throttled") if any(report["verdict"] == candidate for report in reports)),
                "ok",
            )
            payload = report_payload(args.vantage, config_bytes, overall, reports)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
            payload = report_payload(args.vantage, config_bytes, "error", error_profiles(bundle))
        finally:
            stop_process(process)

    emit_report(args, payload)
    return 1 if payload["verdict"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
