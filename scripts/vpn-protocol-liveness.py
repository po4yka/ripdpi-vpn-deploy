#!/usr/bin/env python3
"""Fixed-command sentinel probe for authenticated VPN data-plane liveness.

Usage:
    sudo /usr/local/sbin/vpn-protocol-liveness

The optional ``--config`` argument exists for hermetic tests and local verification; the installed sudoers interface permits only the fixed command above.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_CONFIG = Path("/etc/vpn-liveness/config.json")
DEFAULT_LOCK = Path("/run/lock/vpn-protocol-liveness.lock")
NETWORK_FAILURE_CODES = {7, 28, 35, 52, 56}
AUTH_ERROR = re.compile(r"auth|credential|invalid user|rejected|bad certificate", re.IGNORECASE)


def command_version(command: list[str]) -> str:
    for attempt in range(2):
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=5, check=False)
            match = re.search(r"v?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)", result.stdout + result.stderr)
            return match.group(1) if match else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            if attempt == 0:
                time.sleep(0.1)
    return "missing"


def classify_curl(result: subprocess.CompletedProcess[str], config: dict) -> dict:
    duration_ms = None
    status = 0
    parts = result.stdout.strip().split()
    if len(parts) == 2:
        try:
            status = int(parts[0])
            duration_ms = round(float(parts[1]) * 1000)
        except ValueError:
            # Malformed curl write-out stays an unexpected response below.
            pass
    if result.returncode == 0 and status == config["expected_status"] and duration_ms is not None:
        verdict = "throttled" if duration_ms > config["degraded_after_ms"] else "ok"
        return {"verdict": verdict, "duration_ms": duration_ms, "http_status": status}
    if AUTH_ERROR.search(result.stderr):
        return {"verdict": "error", "duration_ms": duration_ms, "error_kind": "authentication"}
    if result.returncode in NETWORK_FAILURE_CODES:
        return {"verdict": "blocked", "duration_ms": duration_ms, "error_kind": "network"}
    return {"verdict": "error", "duration_ms": duration_ms, "error_kind": "unexpected_response"}


def curl_command(config: dict, extra: list[str] | None = None, prefix: list[str] | None = None) -> list[str]:
    command = list(prefix or []) + [
        "curl",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code} %{time_total}",
        "--max-time",
        str(config["timeout_seconds"]),
    ]
    command.extend(extra or [])
    command.append(config["probe_url"])
    return command


def curl_probe(config: dict, extra: list[str] | None = None, prefix: list[str] | None = None) -> dict:
    command = curl_command(config, extra, prefix)
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=config["timeout_seconds"] + 2, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"verdict": "error", "duration_ms": None, "error_kind": type(exc).__name__.lower()}
    return classify_curl(result, config)


def parallel_curl_probes(config: dict, extras: list[list[str]]) -> list[dict]:
    processes: list[subprocess.Popen[str] | None] = []
    results: list[dict | None] = []
    deadline = time.monotonic() + config["timeout_seconds"] + 2
    try:
        for extra in extras:
            try:
                process = subprocess.Popen(
                    curl_command(config, extra),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except OSError as exc:
                processes.append(None)
                results.append(
                    {"verdict": "error", "duration_ms": None, "error_kind": type(exc).__name__.lower()}
                )
            else:
                processes.append(process)
                results.append(None)
        for index, process in enumerate(processes):
            if process is None:
                continue
            try:
                stdout, stderr = process.communicate(timeout=max(0.01, deadline - time.monotonic()))
                completed = subprocess.CompletedProcess(
                    process.args,
                    process.returncode,
                    stdout=stdout,
                    stderr=stderr,
                )
                results[index] = classify_curl(completed, config)
            except subprocess.TimeoutExpired:
                stop_process(process)
                results[index] = {
                    "verdict": "error",
                    "duration_ms": None,
                    "error_kind": "timeoutexpired",
                }
    finally:
        for process in processes:
            stop_process(process)
    return [
        result
        if result is not None
        else {"verdict": "error", "duration_ms": None, "error_kind": "missing_result"}
        for result in results
    ]


def process_result(profile: str, result: dict) -> dict:
    return {"profile": profile, **result}


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2)
        return
    except (OSError, subprocess.TimeoutExpired):
        # Escalate to SIGKILL when graceful termination cannot be confirmed.
        pass
    try:
        process.kill()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        # Cleanup is best-effort; the probe process is already unusable here.
        pass


def wait_for_ports(process: subprocess.Popen[str], ports: list[int], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    pending = set(ports)
    while pending and time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        for port in list(pending):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    pending.remove(port)
            except OSError:
                pass
        if pending:
            time.sleep(0.05)
    return not pending


def aggregate_variants(profile: str, variants: list[dict]) -> dict:
    evidence = [
        {
            "variant": index,
            "verdict": item["verdict"],
            "duration_ms": item.get("duration_ms"),
            **({"error_kind": item["error_kind"]} if item.get("error_kind") else {}),
        }
        for index, item in enumerate(variants, start=1)
    ]
    for verdict in ("ok", "throttled"):
        matching = [item for item in variants if item["verdict"] == verdict]
        if matching:
            best = min(matching, key=lambda item: item.get("duration_ms") or sys.maxsize)
            return {**process_result(profile, best), "variants": evidence}
    if variants and all(item["verdict"] == "blocked" for item in variants):
        best = min(variants, key=lambda item: item.get("duration_ms") or sys.maxsize)
        return {**process_result(profile, best), "variants": evidence}
    for verdict in ("error", "unknown", "blocked"):
        matching = [item for item in variants if item["verdict"] == verdict]
        if matching:
            return {**process_result(profile, matching[0]), "variants": evidence}
    return {
        **process_result(profile, {"verdict": "error", "duration_ms": None, "error_kind": "no_variants"}),
        "variants": evidence,
    }


def probe_sing_box_profiles(sing_box: dict, config: dict, control_alive: bool) -> list[dict]:
    profile_ports = sing_box["profiles"]
    log_path = Path(f"/tmp/vpn-liveness-{os.getpid()}-sing-box.log")
    process: subprocess.Popen[str] | None = None
    try:
        with log_path.open("w", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                ["sing-box", "run", "-c", sing_box["config"]],
                stdout=log_handle,
                stderr=log_handle,
                text=True,
            )
        all_ports = [port for ports in profile_ports.values() for port in ports]
        if not wait_for_ports(process, all_ports):
            return [
                process_result(profile, {"verdict": "error", "duration_ms": None, "error_kind": "runtime_start"})
                for profile in sorted(profile_ports)
            ]
        results: list[dict] = []
        for profile, ports in sorted(profile_ports.items()):
            variants = parallel_curl_probes(
                config,
                [["--socks5-hostname", f"127.0.0.1:{port}"] for port in ports],
            )
            for index, result in enumerate(variants):
                if not control_alive and result["verdict"] == "blocked":
                    variants[index] = {
                        "verdict": "unknown",
                        "duration_ms": result.get("duration_ms"),
                        "error_kind": "control_unavailable",
                    }
            results.append(aggregate_variants(profile, variants))
        stop_process(process)
        if any(item["verdict"] == "blocked" for item in results):
            try:
                if AUTH_ERROR.search(log_path.read_text(encoding="utf-8", errors="replace")):
                    results = [
                        {
                            **item,
                            "verdict": "error",
                            "error_kind": "authentication",
                            "variants": [
                                {
                                    **variant,
                                    "verdict": "error",
                                    "error_kind": "authentication",
                                }
                                if variant["verdict"] == "blocked"
                                else variant
                                for variant in item.get("variants") or []
                            ],
                        }
                        if item["verdict"] == "blocked"
                        else item
                        for item in results
                    ]
            except OSError:
                # Diagnostic loss must not turn a network result into an auth claim.
                pass
        return results
    except OSError as exc:
        return [
            process_result(profile, {"verdict": "error", "duration_ms": None, "error_kind": type(exc).__name__.lower()})
            for profile in sorted(profile_ports)
        ]
    finally:
        stop_process(process)
        try:
            log_path.unlink()
        except OSError:
            # Failure to remove this private temporary diagnostic is non-fatal.
            pass


def probe_awg(config: dict, control_alive: bool) -> dict:
    profile = "p2-amneziawg"
    namespace = f"vpn-live-{os.getpid()}"
    interface = f"awglive{os.getpid() % 10000}"
    awg_config = config["amneziawg"]["config"]
    created = False
    go_process: subprocess.Popen[str] | None = None
    result: dict
    cleanup_failed = False
    try:
        subprocess.run(["ip", "netns", "add", namespace], timeout=5, check=True, capture_output=True)
        created = True
        stripped = subprocess.run(
            ["awg-quick", "strip", awg_config], text=True, capture_output=True, timeout=5, check=True
        )
        go_process = subprocess.Popen(
            ["amneziawg-go", interface],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        startup_timeout = max(5.0, min(float(config["timeout_seconds"]), 10.0))
        startup_deadline = time.monotonic() + startup_timeout
        while time.monotonic() < startup_deadline:
            if go_process.poll() is not None:
                raise RuntimeError("amneziawg-go stopped during startup")
            link = subprocess.run(["ip", "link", "show", interface], timeout=2, check=False, capture_output=True)
            if link.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("amneziawg-go interface startup timed out")
        subprocess.run(
            ["awg", "setconf", interface, "/dev/stdin"],
            input=stripped.stdout,
            text=True,
            timeout=5,
            check=True,
            capture_output=True,
        )
        # The interface is created in the host namespace so the userspace UDP socket keeps the sentinel's underlay after the interface moves; addresses and routes exist only in the disposable namespace.
        subprocess.run(["ip", "link", "set", interface, "netns", namespace], timeout=5, check=True, capture_output=True)
        subprocess.run(["ip", "-n", namespace, "address", "add", config["amneziawg"]["address"], "dev", interface], timeout=5, check=True, capture_output=True)
        subprocess.run(["ip", "-n", namespace, "link", "set", interface, "up"], timeout=5, check=True, capture_output=True)
        subprocess.run(["ip", "-n", namespace, "route", "add", "default", "dev", interface], timeout=5, check=True, capture_output=True)
        parsed = urlparse(config["probe_url"])
        if not parsed.hostname:
            raise ValueError("probe_url has no hostname")
        target_ip = socket.getaddrinfo(parsed.hostname, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)[0][4][0]
        started = int(time.time())
        result = curl_probe(
            config,
            ["--resolve", f"{parsed.hostname}:443:{target_ip}"],
            ["ip", "netns", "exec", namespace],
        )
        handshake = subprocess.run(
            ["ip", "netns", "exec", namespace, "awg", "show", interface, "latest-handshakes"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        epochs = [int(value) for value in re.findall(r"\b\d{9,}\b", handshake.stdout)]
        if result["verdict"] in {"ok", "throttled"} and not any(epoch >= started - 5 for epoch in epochs):
            result = {"verdict": "error", "duration_ms": result.get("duration_ms"), "error_kind": "no_fresh_handshake"}
        if not control_alive and result["verdict"] == "blocked":
            result = {"verdict": "unknown", "duration_ms": None, "error_kind": "control_unavailable"}
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        result = {"verdict": "error", "duration_ms": None, "error_kind": type(exc).__name__.lower()}
    finally:
        if created:
            try:
                route = subprocess.run(["ip", "-n", namespace, "route", "delete", "default"], timeout=5, check=False, capture_output=True)
                cleanup_failed |= route.returncode not in {0, 1, 2}
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
            try:
                link = subprocess.run(["ip", "-n", namespace, "link", "delete", interface], timeout=5, check=False, capture_output=True)
                cleanup_failed |= link.returncode not in {0, 1, 2}
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
            try:
                deleted = subprocess.run(["ip", "netns", "delete", namespace], timeout=5, check=False, capture_output=True)
                cleanup_failed |= deleted.returncode != 0
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
        stop_process(go_process)
    if cleanup_failed:
        result = {"verdict": "error", "duration_ms": None, "error_kind": "cleanup"}
    return process_result(profile, result)


def error_profiles(config: dict, error_kind: str) -> list[dict]:
    profiles = sorted((config.get("sing_box") or {}).get("profiles", {}))
    if "amneziawg" in config:
        profiles.append("p2-amneziawg")
    return [
        {"profile": profile, "verdict": "error", "duration_ms": None, "error_kind": error_kind}
        for profile in profiles
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"vpn-protocol-liveness: invalid config: {exc}", file=sys.stderr)
        return 2

    lock_path = Path(os.environ.get("VPN_LIVENESS_LOCK", DEFAULT_LOCK))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("vpn-protocol-liveness: another probe is active", file=sys.stderr)
            return 75

        control = curl_probe(config)
        control_alive = control["verdict"] in {"ok", "throttled"}
        runtime = {
            "sing_box": command_version(["sing-box", "version"]),
            "awg": command_version(["awg", "--version"]),
        }
        if runtime != config["expected_runtime"]:
            profiles = error_profiles(config, "runtime_mismatch")
        else:
            sing_box = config.get("sing_box") or {"config": "", "profiles": {}}
            profiles = probe_sing_box_profiles(sing_box, config, control_alive) if sing_box["profiles"] else []
            if "amneziawg" in config:
                profiles.append(probe_awg(config, control_alive))
        payload = {
            "schema_version": 1,
            "sentinel": config["sentinel"],
            "observed_at": int(time.time()),
            "control": control,
            "profiles": profiles,
            "runtime": runtime,
        }
        print(json.dumps(payload, sort_keys=True))
    return 0


def terminate_on_signal(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate_on_signal)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
