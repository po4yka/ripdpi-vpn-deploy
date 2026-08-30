#!/usr/bin/env python3
"""Fixed-command sentinel probe for authenticated VPN data-plane liveness.

Usage:
    sudo /usr/local/sbin/vpn-protocol-liveness

The optional ``--config`` argument exists for hermetic tests and local verification; the installed sudoers interface permits only the fixed command above.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


DEFAULT_CONFIG = Path("/etc/vpn-liveness/config.json")
DEFAULT_LOCK = Path("/run/lock/vpn-protocol-liveness.lock")
NETWORK_FAILURE_CODES = {7, 28, 35, 52, 56}
AUTH_ERROR = re.compile(r"auth|credential|invalid user|rejected|bad certificate", re.IGNORECASE)
AWG_TOOLCHAIN_BASE = Path("/opt/ripdpi-real-vps-awg-nat/toolchains")
AWG_TOOLCHAIN_UID = 0
AWG_TOOLCHAIN_GID = 0
TARGET_IDENTITY_KEYS = {
    "inventory_alias", "public_service_address_sha256", "deployable_digest", "applied_at",
    "required_profiles", "source_revision", "runner_sha256", "public_profile_digest",
}


def validate_target_identity(config: dict) -> None:
    target = config.get("target_identity")
    provenance = config.get("provenance")
    profiles = sorted({profile for runtime in ("sing_box", "xray")
                       for profile in (config.get(runtime) or {}).get("profiles", {})}
                      | ({"p2-amneziawg"} if "amneziawg" in config else set()))
    if (
        config.get("schema_version") != 2
        or not isinstance(target, dict)
        or set(target) != TARGET_IDENTITY_KEYS
        or not isinstance(provenance, dict)
        or target.get("required_profiles") != profiles
        or target.get("source_revision") != provenance.get("controller_revision")
        or target.get("runner_sha256") != provenance.get("runner_sha256")
        or target.get("public_profile_digest") != provenance.get("public_profile_digest")
        or type(target.get("applied_at")) is not int
        or target["applied_at"] < 1
        or not isinstance(target.get("inventory_alias"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", target["inventory_alias"]) is None
        or any(not isinstance(target.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", target[key]) is None
               for key in ("public_service_address_sha256", "deployable_digest", "runner_sha256", "public_profile_digest"))
        or not isinstance(target.get("source_revision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", target["source_revision"]) is None
    ):
        raise ValueError("target identity invalid")


def validate_sing_box(config: dict) -> None:
    settings = config.get("sing_box")
    if settings is None:
        return
    if not isinstance(settings, dict):
        raise ValueError("sing-box settings invalid")
    profiles = settings.get("profiles")
    if (
        not isinstance(settings.get("config"), str)
        or not Path(settings["config"]).is_absolute()
        or not isinstance(profiles, dict)
        or any(profile not in {"p0-reality", "p1-xhttp", "p2-hysteria2"} for profile in profiles)
        or any(
            not isinstance(ports, list)
            or not ports
            or any(type(port) is not int or not 1 <= port <= 65535 for port in ports)
            or len(set(ports)) != len(ports)
            for ports in profiles.values()
        )
    ):
        raise ValueError("sing-box settings invalid")


def verify_awg_toolchain(expected_id: str) -> dict:
    """Verify the immutable installer's canonical input, tree and binary hashes."""
    if not isinstance(expected_id, str) or re.fullmatch(r"[0-9a-f]{64}", expected_id) is None:
        raise ValueError("toolchain pin invalid")
    root = AWG_TOOLCHAIN_BASE / expected_id
    for directory in root.parents:
        info = directory.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, AWG_TOOLCHAIN_UID}
                or info.st_mode & 0o022 and not sticky_root):
            raise ValueError("toolchain parent unsafe")
    entries = [root]
    for directory, dirs, files in os.walk(root, followlinks=False):
        entries.extend(Path(directory) / name for name in dirs + files)
        if len(entries) > 60000:
            raise ValueError("toolchain entry limit")
    for path in entries:
        info = path.lstat()
        if (info.st_uid != AWG_TOOLCHAIN_UID or info.st_gid != AWG_TOOLCHAIN_GID
                or (stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) != 0o500)
                or (stat.S_ISREG(info.st_mode) and (stat.S_IMODE(info.st_mode) not in {0o400, 0o500} or info.st_nlink != 1))
                or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
            raise ValueError("toolchain metadata invalid")
    manifest_path = root / "manifest.json"
    if manifest_path.stat().st_size > 65536:
        raise ValueError("toolchain manifest limit")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    canonical = lambda value: (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if (not isinstance(manifest, dict) or raw != canonical(manifest)
            or set(manifest) != {"schemaVersion", "inputs", "binaries", "treeSha256"}
            or type(manifest["schemaVersion"]) is not int or manifest["schemaVersion"] != 1):
        raise ValueError("toolchain manifest invalid")
    inputs = manifest["inputs"]
    fields = {"goBundleSha256": 64, "goCommit": 40, "toolsBundleSha256": 64, "toolsCommit": 40, "vendorSha256": 64}
    if (not isinstance(inputs, dict) or set(inputs) != set(fields)
            or any(not isinstance(inputs[k], str) or re.fullmatch(r"[0-9a-f]{" + str(n) + "}", inputs[k]) is None for k, n in fields.items())
            or hashlib.sha256(canonical(inputs)).hexdigest() != expected_id):
        raise ValueError("toolchain inputs invalid")
    names = {"amneziawg-go", "awg", "awg-quick"}
    if not isinstance(manifest["binaries"], dict) or set(manifest["binaries"]) != names:
        raise ValueError("toolchain binaries invalid")
    tree = hashlib.sha256()
    binaries = {}
    total = 0
    deadline = time.monotonic() + 30
    for path in sorted(entries[1:], key=lambda value: value.as_posix()):
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        metadata = f"{info.st_uid}:{info.st_gid}:{stat.S_IMODE(info.st_mode):04o}".encode()
        if stat.S_ISDIR(info.st_mode):
            tree.update(b"D\0" + relative.encode() + b"\0" + metadata + b"\0")
        elif path != manifest_path:
            tree.update(b"F\0" + relative.encode() + b"\0" + metadata + b"\0")
            digest = hashlib.sha256()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > 1024 * 1024 * 1024 or time.monotonic() > deadline:
                        raise ValueError("toolchain read limit")
                    tree.update(chunk)
                    digest.update(chunk)
            if relative in {f"bin/{name}" for name in names}:
                if stat.S_IMODE(info.st_mode) != 0o500 or manifest["binaries"][path.name] != digest.hexdigest():
                    raise ValueError("toolchain binary mismatch")
                binaries[path.name] = str(path)
    if set(binaries) != names or manifest["treeSha256"] != tree.hexdigest():
        raise ValueError("toolchain tree mismatch")
    return {"id": expected_id, "binaries": binaries}


def awg_probe_url(config: dict):
    url = config.get("probe_url")
    if not isinstance(url, str) or any(ord(c) <= 32 for c in url):
        raise ValueError("AWG URL invalid")
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443)
            or parsed.username is not None or parsed.password is not None or parsed.fragment
            or ":" in parsed.hostname):
        raise ValueError("AWG requires IPv4 HTTPS port 443")
    if ipaddress.ip_interface(config["amneziawg"]["address"]).version != 4:
        raise ValueError("AWG requires IPv4 client address")
    return parsed


def command_version(command: list[str]) -> str:
    for attempt in range(2):
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=5, check=False)
            if result.returncode != 0:
                return "unknown"
            match = re.search(r"v?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)", result.stdout)
            return match.group(1) if match else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            if attempt == 0:
                time.sleep(0.1)
    return "missing"


def xray_version() -> str:
    for attempt in range(2):
        try:
            result = subprocess.run(["xray", "version"], text=True, capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            if attempt == 0:
                time.sleep(0.1)
                continue
            return "missing"
        banner = re.search(r"(?m)^Xray\s+(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)(?:\s|$)", result.stdout)
        return banner.group(1) if result.returncode == 0 and banner else "unknown"
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
        return {"verdict": verdict, "duration_ms": duration_ms, "http_status": status, "payload_transport": "tcp-https"}
    if AUTH_ERROR.search(result.stderr):
        return {"verdict": "error", "duration_ms": duration_ms, "error_kind": "authentication", "payload_transport": "tcp-https"}
    if result.returncode in NETWORK_FAILURE_CODES:
        return {"verdict": "blocked", "duration_ms": duration_ms, "error_kind": "network", "payload_transport": "tcp-https"}
    return {"verdict": "error", "duration_ms": duration_ms, "error_kind": "unexpected_response", "payload_transport": "tcp-https"}


def curl_command(config: dict, extra: list[str] | None = None, prefix: list[str] | None = None) -> list[str]:
    command = list(prefix or []) + [
        "curl",
        "--disable",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code} %{time_total}",
        "--max-time",
        str(config["timeout_seconds"]),
    ]
    # An AWG namespace uses its own route, while a SOCKS request must never
    # honor a NO_PROXY bypass. Neither path may inherit an ambient proxy.
    if "--socks5-hostname" in (extra or []):
        command.extend(["--noproxy", ""])
    else:
        command.extend(["--proxy", "", "--noproxy", "*"])
    command.extend(extra or [])
    command.append(config["probe_url"])
    return command


def curl_probe(config: dict, extra: list[str] | None = None, prefix: list[str] | None = None) -> dict:
    command = curl_command(config, extra, prefix)
    try:
        result = subprocess.run(
            command, text=True, capture_output=True,
            timeout=config["timeout_seconds"] + 2, check=False,
            env={key: value for key, value in os.environ.items() if not key.lower().endswith("_proxy")},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"verdict": "error", "duration_ms": None, "error_kind": type(exc).__name__.lower(),
                **({"payload_transport": "tcp-https"} if isinstance(exc, subprocess.TimeoutExpired) else {})}
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
                    env={key: value for key, value in os.environ.items() if not key.lower().endswith("_proxy")},
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
                    "payload_transport": "tcp-https",
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
    return {"profile": profile, "payload_transport": "unknown", "target_address_family": "unknown",
            "dns_through_tunnel": False, "authenticated_handshake": False, **result}


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
                # Listener startup is asynchronous; retry until the bounded deadline.
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


def probe_runtime_profiles(runtime: str, settings: dict, config: dict, control_alive: bool) -> list[dict]:
    profile_ports = settings["profiles"]
    all_ports = [port for ports in profile_ports.values() for port in ports]
    reservations = []
    try:
        for port in all_ports:
            reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            reservations.append(reservation)
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            reservation.bind(("127.0.0.1", port))
            reservation.listen(1)
    except OSError:
        return [process_result(profile, {"verdict": "error", "duration_ms": None,
                                         "error_kind": "listener_in_use"}) for profile in sorted(profile_ports)]
    finally:
        for reservation in reservations:
            reservation.close()
    # Private per-run log file: a predictable name in a world-writable
    # directory lets a local user pre-plant a symlink that this (possibly
    # root-run) writer would follow.
    log_fd, log_name = tempfile.mkstemp(prefix=f"vpn-liveness-{runtime}-", suffix=".log")
    os.close(log_fd)
    log_path = Path(log_name)
    process: subprocess.Popen[str] | None = None
    try:
        command = [runtime, "run", "-config" if runtime == "xray" else "-c", settings["config"]]
        if runtime == "xray":
            validated = subprocess.run(
                [runtime, "run", "-test", "-config", settings["config"]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False,
            )
            if validated.returncode:
                return [process_result(profile, {"verdict": "error", "duration_ms": None,
                                                  "error_kind": "runtime_config"})
                        for profile in sorted(profile_ports)]
        with log_path.open("w", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=log_handle,
                text=True,
            )
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
            variants = [
                {
                    **result,
                    "dns_through_tunnel": result["verdict"] in {"ok", "throttled"},
                    "authenticated_handshake": result["verdict"] in {"ok", "throttled"},
                }
                for result in variants
            ]
            for index, result in enumerate(variants):
                if not control_alive and result["verdict"] == "blocked":
                    variants[index] = {
                        **result,
                        "verdict": "unknown",
                        "duration_ms": result.get("duration_ms"),
                        "error_kind": "control_unavailable",
                    }
            results.append(aggregate_variants(profile, variants))
        if process.poll() is not None:
            return [process_result(profile, {"verdict": "error", "duration_ms": None,
                                             "error_kind": "runtime_exited"}) for profile in sorted(profile_ports)]
        stop_process(process)
        if process.poll() is None:
            return [process_result(profile, {"verdict": "error", "duration_ms": None,
                                             "error_kind": "cleanup"}) for profile in sorted(profile_ports)]
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
    except (OSError, subprocess.TimeoutExpired) as exc:
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


def namespace_exists(name: str) -> bool:
    # iproute2's /var/run/netns resolves to /run/netns on the managed hosts.
    # Inspect only our generated name, never infer ownership from a broad list.
    return os.path.lexists(Path("/run/netns") / name)


def probe_awg(config: dict, control_alive: bool, toolchain: dict) -> dict:
    profile = "p2-amneziawg"
    namespace = f"vpn-live-{uuid4().hex}"
    interface = f"awglive{uuid4().hex[:8]}"
    awg_config = config["amneziawg"]["config"]
    created = False
    namespace_attempted = False
    address_family = "unknown"
    interface_location = None
    go_process: subprocess.Popen[str] | None = None
    result: dict
    cleanup_failed = False
    try:
        parsed = awg_probe_url(config)
        address_family = "ipv4"
        existing = subprocess.run(["ip", "link", "show", interface], timeout=2, check=False, capture_output=True)
        if existing.returncode != 1:
            raise RuntimeError("AWG interface is not available")
        if namespace_exists(namespace):
            raise RuntimeError("AWG namespace is not available")
        # The root-owned namespace directory and unguessable name were absent.
        # Remember the attempt before a timeout/signal can interrupt ip after
        # creating its mount, then reconcile that partial result in finally.
        namespace_attempted = True
        subprocess.run(["ip", "netns", "add", namespace], timeout=5, check=True, capture_output=True)
        created = True
        stripped = subprocess.run(
            [toolchain["binaries"]["awg-quick"], "strip", awg_config], text=True, capture_output=True, timeout=5, check=True
        )
        go_env = {key: value for key, value in os.environ.items() if key not in {"WG_TUN_FD", "WG_UAPI_FD", "WG_PROCESS_FOREGROUND", "LOG_LEVEL"}}
        go_env["LOG_LEVEL"] = "silent"
        go_process = subprocess.Popen(
            [toolchain["binaries"]["amneziawg-go"], "-f", interface],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=go_env,
        )
        interface_location = "host"
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
            [toolchain["binaries"]["awg"], "setconf", interface, "/dev/stdin"],
            input=stripped.stdout,
            text=True,
            timeout=5,
            check=True,
            capture_output=True,
        )
        # The interface is created in the host namespace so the userspace UDP socket keeps the sentinel's underlay after the interface moves; addresses and routes exist only in the disposable namespace.
        subprocess.run(["ip", "link", "set", interface, "netns", namespace], timeout=5, check=True, capture_output=True)
        interface_location = "namespace"
        subprocess.run(["ip", "-n", namespace, "address", "add", config["amneziawg"]["address"], "dev", interface], timeout=5, check=True, capture_output=True)
        subprocess.run(["ip", "-n", namespace, "link", "set", interface, "up"], timeout=5, check=True, capture_output=True)
        subprocess.run(["ip", "-n", namespace, "route", "add", "default", "dev", interface], timeout=5, check=True, capture_output=True)
        started = int(time.time())
        result = curl_probe(
            config,
            ["--ipv4"],
            ["ip", "netns", "exec", namespace],
        )
        handshake = subprocess.run(
            ["ip", "netns", "exec", namespace, toolchain["binaries"]["awg"], "show", interface, "latest-handshakes"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        fields = [line.split() for line in handshake.stdout.splitlines() if line.strip()]
        fresh = (handshake.returncode == 0 and len(fields) == 1 and len(fields[0]) == 2
                 and fields[0][1].isdigit() and started - 5 <= int(fields[0][1]) <= int(time.time()))
        if result["verdict"] in {"ok", "throttled"} and not fresh:
            result = {**result, "verdict": "error", "error_kind": "no_fresh_handshake"}
        elif result["verdict"] in {"ok", "throttled"}:
            result["fresh_handshake"] = True
            result["dns_through_tunnel"] = True
            result["authenticated_handshake"] = True
        if not control_alive and result["verdict"] == "blocked":
            result = {**result, "verdict": "unknown", "duration_ms": None, "error_kind": "control_unavailable"}
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        result = {"verdict": "error", "duration_ms": None, "error_kind": type(exc).__name__.lower()}
    finally:
        stop_process(go_process)
        if go_process is not None and go_process.poll() is None:
            cleanup_failed = True
        if created or (namespace_attempted and namespace_exists(namespace)):
            if interface_location is not None:
                try:
                    prefix = ["ip", "-n", namespace] if interface_location == "namespace" else ["ip"]
                    # Closing the foreground TUN owner may already remove it.
                    present = subprocess.run([*prefix, "link", "show", interface], timeout=5, check=False, capture_output=True)
                    if present.returncode == 0:
                        link = subprocess.run([*prefix, "link", "delete", interface], timeout=5, check=False, capture_output=True)
                        cleanup_failed |= link.returncode != 0
                    elif present.returncode != 1:
                        cleanup_failed = True
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_failed = True
            try:
                deleted = subprocess.run(["ip", "netns", "delete", namespace], timeout=5, check=False, capture_output=True)
                cleanup_failed |= deleted.returncode != 0
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
    if cleanup_failed:
        result = {**result, "verdict": "error", "duration_ms": None, "error_kind": "cleanup"}
    return process_result(profile, {**result, "target_address_family": address_family})


def error_profiles(config: dict, error_kind: str) -> list[dict]:
    profiles = sorted({profile for runtime in ("sing_box", "xray")
                       for profile in (config.get(runtime) or {}).get("profiles", {})})
    if "amneziawg" in config:
        profiles.append("p2-amneziawg")
    return [
        process_result(profile, {"verdict": "error", "duration_ms": None, "error_kind": error_kind})
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

    try:
        validate_sing_box(config)
    except (AttributeError, TypeError, ValueError):
        print("vpn-protocol-liveness: invalid sing-box profiles", file=sys.stderr)
        return 2

    if "p1-xhttp" in (config.get("sing_box") or {}).get("profiles", {}):
        print("vpn-protocol-liveness: migration required: p1-xhttp requires xray", file=sys.stderr)
        return 2
    if "xray" in config:
        settings = config["xray"]
        expected_xray = config.get("expected_runtime", {}).get("xray")
        if (not isinstance(settings, dict)
                or not isinstance(settings.get("config"), str) or not Path(settings["config"]).is_absolute()
                or not isinstance(settings.get("profiles"), dict) or set(settings["profiles"]) != {"p1-xhttp"}
                or not isinstance(settings["profiles"]["p1-xhttp"], list) or not settings["profiles"]["p1-xhttp"]
                or any(type(port) is not int or not 1 <= port <= 65535 for port in settings["profiles"]["p1-xhttp"])
                or len(set(settings["profiles"]["p1-xhttp"])) != len(settings["profiles"]["p1-xhttp"])
                or not isinstance(expected_xray, str)
                or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", expected_xray)):
            print("vpn-protocol-liveness: invalid xray profile or expected_runtime.xray pin", file=sys.stderr)
            return 2

    try:
        validate_target_identity(config)
    except (ValueError, TypeError):
        print("vpn-protocol-liveness: invalid target identity", file=sys.stderr)
        return 2

    toolchain = None
    if "amneziawg" in config:
        try:
            awg_probe_url(config)
            toolchain = verify_awg_toolchain(config.get("expected_runtime", {}).get("awg_toolchain"))
        except (OSError, ValueError, TypeError, KeyError):
            print("vpn-protocol-liveness: invalid AWG toolchain or IPv4 HTTPS profile", file=sys.stderr)
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
        runtime = {}
        if "sing_box" in config:
            runtime["sing_box"] = command_version(["sing-box", "version"])
        if "xray" in config:
            runtime["xray"] = xray_version()
        if toolchain is not None:
            runtime["awg"] = command_version([toolchain["binaries"]["awg"], "--version"])
            runtime["awg_toolchain"] = toolchain["id"]
        if runtime != config["expected_runtime"]:
            profiles = error_profiles(config, "runtime_mismatch")
        else:
            sing_box = config.get("sing_box") or {"config": "", "profiles": {}}
            profiles = probe_runtime_profiles("sing-box", sing_box, config, control_alive) if sing_box["profiles"] else []
            if "xray" in config:
                profiles.extend(probe_runtime_profiles("xray", config["xray"], config, control_alive))
            if "amneziawg" in config:
                profiles.append(probe_awg(config, control_alive, toolchain))
        payload = {
            "schema_version": 2,
            "sentinel": config["sentinel"],
            "observed_at": int(time.time()),
            "control": control,
            "profiles": profiles,
            "runtime": runtime,
            "provenance": config["provenance"],
            "target_identity": config["target_identity"],
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
