#!/usr/bin/env python3
"""Deep probe-matrix driver module behind the Make/JSON interface.

Usage:
  probe-matrix-driver.py control --config /absolute/matrix.yaml
  probe-matrix-driver.py cell --config /absolute/matrix.yaml --target-id ID --protocol PROTOCOL --control-verdict VERDICT
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml


NETWORK_FAILURE_CODES = {5, 6, 7, 28, 35, 52, 55, 56}
XRAY_PROTOCOLS = {"xhttp-vless", "xhttp-trojan", "tcp-trojan"}
PROTOCOLS = XRAY_PROTOCOLS | {"mtproto", "tls-non-443"}


class DriverError(Exception):
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def verdict(name: str, rtt_ms: int | None = None, error_kind: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"verdict": name, "rtt_ms": rtt_ms}
    if error_kind is not None:
        result["error_kind"] = error_kind
    return result


def load_matrix(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DriverError("config-invalid") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        raise DriverError("config-invalid")
    control = data.get("control")
    targets = data.get("targets")
    if not isinstance(control, dict) or not isinstance(targets, list):
        raise DriverError("config-invalid")
    return data


def secure_profile(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise DriverError("profile-missing") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise DriverError("profile-permissions")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise DriverError("profile-permissions")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DriverError("profile-invalid") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise DriverError("profile-invalid")
    if not isinstance(data.get("protocols"), dict) or not isinstance(data.get("endpoint"), str):
        raise DriverError("profile-invalid")
    return data


def target_profile(matrix: dict[str, Any], target_id: str) -> dict[str, Any]:
    matches = [target for target in matrix["targets"] if isinstance(target, dict) and target.get("id") == target_id]
    if len(matches) != 1:
        raise DriverError("target-unknown")
    profile_path = matches[0].get("profile_file")
    if not isinstance(profile_path, str) or not Path(profile_path).is_absolute():
        raise DriverError("profile-invalid")
    profile = secure_profile(Path(profile_path))
    if profile.get("target_id") != target_id:
        raise DriverError("profile-target-mismatch")
    return profile


def checked_control(matrix: dict[str, Any]) -> tuple[str, int, int, int]:
    control = matrix["control"]
    url = control.get("url")
    expected = control.get("expected_status")
    timeout = control.get("timeout_seconds")
    degraded = control.get("degraded_after_ms")
    if (
        not isinstance(url, str)
        or not url.startswith("https://")
        or not isinstance(expected, int)
        or not 100 <= expected <= 599
        or not isinstance(timeout, int)
        or not 1 <= timeout <= 60
        or not isinstance(degraded, int)
        or degraded < 1
    ):
        raise DriverError("config-invalid")
    return url, expected, timeout, degraded


def curl_probe(matrix: dict[str, Any], proxy_port: int | None = None) -> dict[str, Any]:
    url, expected, timeout, degraded = checked_control(matrix)
    if shutil.which("curl") is None:
        return verdict("error", error_kind="dependency-missing")
    command = [
        "curl",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code} %{time_total}",
        "--max-time",
        str(timeout),
    ]
    if proxy_port is not None:
        command.extend(["--socks5-hostname", f"127.0.0.1:{proxy_port}"])
    command.append(url)
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout + 2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return verdict("error", error_kind="control-timeout" if proxy_port is None else "runtime-timeout")
    parts = result.stdout.strip().split()
    rtt_ms = None
    status_code = 0
    if len(parts) == 2:
        try:
            status_code = int(parts[0])
            rtt_ms = round(float(parts[1]) * 1000)
        except ValueError:
            pass
    if result.returncode == 0 and status_code == expected and rtt_ms is not None:
        return verdict("throttled" if rtt_ms > degraded else "ok", rtt_ms=rtt_ms)
    if result.returncode in NETWORK_FAILURE_CODES:
        return verdict("error", rtt_ms=rtt_ms, error_kind="network")
    return verdict("error", rtt_ms=rtt_ms, error_kind="unexpected-response")


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def xray_outbound(protocol: str, endpoint: str, settings: dict[str, Any]) -> dict[str, Any]:
    port = settings.get("port")
    server_name = settings.get("server_name")
    if not isinstance(port, int) or not 1 <= port <= 65535 or not isinstance(server_name, str):
        raise DriverError("profile-invalid")
    stream: dict[str, Any] = {
        "network": "xhttp" if protocol.startswith("xhttp-") else "tcp",
        "security": "tls",
        "tlsSettings": {"serverName": server_name, "allowInsecure": False},
    }
    if protocol.startswith("xhttp-"):
        path = settings.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            raise DriverError("profile-invalid")
        stream["xhttpSettings"] = {"path": path, "host": server_name}
    if protocol == "xhttp-vless":
        uuid = settings.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            raise DriverError("profile-invalid")
        return {
            "protocol": "vless",
            "settings": {"vnext": [{"address": endpoint, "port": port, "users": [{"id": uuid, "encryption": "none"}]}]},
            "streamSettings": stream,
        }
    password = settings.get("password")
    if not isinstance(password, str) or not password:
        raise DriverError("profile-invalid")
    return {
        "protocol": "trojan",
        "settings": {"servers": [{"address": endpoint, "port": port, "password": password}]},
        "streamSettings": stream,
    }


def map_network_result(result: dict[str, Any], control_verdict: str) -> dict[str, Any]:
    if result.get("error_kind") == "network":
        return filtering_verdict(control_verdict, result.get("rtt_ms"))
    return result


def filtering_verdict(control_verdict: str, rtt_ms: int | None = None) -> dict[str, Any]:
    return verdict("blocked" if control_verdict == "ok" else "unknown", rtt_ms=rtt_ms)


def xray_probe(matrix: dict[str, Any], profile: dict[str, Any], protocol: str, control_verdict: str) -> dict[str, Any]:
    binary = shutil.which("xray")
    if binary is None:
        return verdict("error", error_kind="dependency-missing")
    expected_version = profile.get("expected_xray_version")
    if not isinstance(expected_version, str) or not expected_version:
        return verdict("error", error_kind="profile-invalid")
    try:
        version = subprocess.run([binary, "version"], text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return verdict("error", error_kind="dependency-missing")
    if version.returncode != 0 or expected_version not in version.stdout + version.stderr:
        return verdict("error", error_kind="version-mismatch")
    settings = profile["protocols"].get(protocol)
    if not isinstance(settings, dict):
        return verdict("error", error_kind="profile-invalid")
    try:
        port = free_port()
        outbound = xray_outbound(protocol, profile["endpoint"], settings)
    except DriverError as exc:
        return verdict("error", error_kind=exc.kind)
    runtime: subprocess.Popen[str] | None = None
    cleanup_failed = False
    try:
        with tempfile.TemporaryDirectory(prefix="probe-matrix-") as directory:
            os.chmod(directory, 0o700)
            config_path = Path(directory) / "xray.json"
            error_log = Path(directory) / "xray-error.log"
            config_path.write_text(
                json.dumps(
                    {
                        "log": {"error": str(error_log), "loglevel": "warning"},
                        "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks", "settings": {"udp": False}}],
                        "outbounds": [outbound],
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            config_path.chmod(0o600)
            validated = subprocess.run(
                [binary, "run", "-test", "-config", str(config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if validated.returncode != 0:
                return verdict("error", error_kind="runtime-config")
            runtime = subprocess.Popen(
                [binary, "run", "-config", str(config_path)],
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if runtime.poll() is not None:
                    return verdict("error", error_kind="runtime-start")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.025)
            else:
                return verdict("error", error_kind="runtime-start")
            result = curl_probe(matrix, proxy_port=port)
            if result.get("error_kind") == "network" and error_log.exists():
                diagnostic = error_log.read_text(encoding="utf-8", errors="replace").lower()
                if any(marker in diagnostic for marker in ("authentication", "invalid account", "invalid user", "invalid password", "rejected")):
                    return verdict("error", rtt_ms=result.get("rtt_ms"), error_kind="authentication")
                if any(marker in diagnostic for marker in ("connection refused", "no route to host", "network is unreachable")):
                    return verdict("error", rtt_ms=result.get("rtt_ms"), error_kind="target-unavailable")
            return map_network_result(result, control_verdict)
    except (OSError, subprocess.TimeoutExpired):
        return verdict("error", error_kind="runtime-start")
    finally:
        if runtime is not None and runtime.poll() is None:
            try:
                runtime.terminate()
                runtime.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    runtime.kill()
                    runtime.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_failed = True
        if cleanup_failed:
            return verdict("error", error_kind="cleanup-failed")


def mtproto_probe(matrix: dict[str, Any], profile: dict[str, Any], control_verdict: str) -> dict[str, Any]:
    settings = profile["protocols"].get("mtproto")
    if not isinstance(settings, dict) or not isinstance(settings.get("port"), int) or not isinstance(settings.get("secret"), str):
        return verdict("error", error_kind="profile-invalid")
    binary = os.environ.get("PROBE_MATRIX_MTPROTO_BIN") or str(
        Path(__file__).resolve().parent.parent / "tools" / "probe-matrix-mtproto" / "probe-matrix-mtproto"
    )
    if not Path(binary).is_file() or not os.access(binary, os.X_OK):
        return verdict("error", error_kind="dependency-missing")
    expected_helper = profile.get("expected_mtproto_helper_version")
    if profile.get("expected_mtg_version") != "v2.2.8" or not isinstance(expected_helper, str):
        return verdict("error", error_kind="profile-invalid")
    try:
        version = subprocess.run([binary, "--version"], text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return verdict("error", error_kind="dependency-missing")
    if version.returncode != 0 or version.stdout.strip() != expected_helper:
        return verdict("error", error_kind="version-mismatch")
    _, _, timeout, degraded = checked_control(matrix)
    request = {
        "endpoint": profile["endpoint"],
        "port": settings["port"],
        "secret": settings["secret"],
        "timeout_seconds": timeout,
    }
    started = time.monotonic()
    try:
        result = subprocess.run(
            [binary],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=timeout + 2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return filtering_verdict(control_verdict)
    elapsed = round((time.monotonic() - started) * 1000)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return verdict("error", error_kind="invalid-output")
    if result.returncode == 0 and payload.get("ok") is True:
        return verdict("throttled" if elapsed > degraded else "ok", rtt_ms=elapsed)
    kind = payload.get("error_kind")
    if kind in {"authentication", "request-invalid", "target-unavailable"}:
        return verdict("error", rtt_ms=elapsed, error_kind=str(kind))
    return filtering_verdict(control_verdict, elapsed)


def tls_probe(matrix: dict[str, Any], profile: dict[str, Any], control_verdict: str) -> dict[str, Any]:
    settings = profile["protocols"].get("tls-non-443")
    if not isinstance(settings, dict) or not isinstance(settings.get("port"), int) or not isinstance(settings.get("server_name"), str):
        return verdict("error", error_kind="profile-invalid")
    if shutil.which("openssl") is None:
        return verdict("error", error_kind="dependency-missing")
    _, _, timeout, degraded = checked_control(matrix)
    started = time.monotonic()
    try:
        result = subprocess.run(
            [
                "openssl",
                "s_client",
                "-connect",
                f"{profile['endpoint']}:{settings['port']}",
                "-servername",
                settings["server_name"],
                "-verify_hostname",
                settings["server_name"],
                "-verify_return_error",
                "-brief",
            ],
            input="",
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return filtering_verdict(control_verdict)
    elapsed = round((time.monotonic() - started) * 1000)
    if result.returncode == 0:
        return verdict("throttled" if elapsed > degraded else "ok", rtt_ms=elapsed)
    lowered = result.stderr.lower()
    if "verify error" in lowered or "certificate" in lowered:
        return verdict("error", rtt_ms=elapsed, error_kind="tls-validation")
    if any(marker in lowered for marker in ("connection refused", "errno=61", "errno=111", "no route to host", "network is unreachable")):
        return verdict("error", rtt_ms=elapsed, error_kind="target-unavailable")
    return filtering_verdict(control_verdict, elapsed)


def cell(matrix: dict[str, Any], target_id: str, protocol: str, control_verdict: str) -> dict[str, Any]:
    if protocol not in PROTOCOLS or control_verdict not in {"ok", "throttled", "blocked", "unknown", "error"}:
        raise DriverError("request-invalid")
    profile = target_profile(matrix, target_id)
    if protocol not in profile["protocols"]:
        raise DriverError("profile-invalid")
    if protocol in XRAY_PROTOCOLS:
        return xray_probe(matrix, profile, protocol, control_verdict)
    if protocol == "mtproto":
        return mtproto_probe(matrix, profile, control_verdict)
    return tls_probe(matrix, profile, control_verdict)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    control_parser = subparsers.add_parser("control")
    control_parser.add_argument("--config", required=True, type=Path)
    cell_parser = subparsers.add_parser("cell")
    cell_parser.add_argument("--config", required=True, type=Path)
    cell_parser.add_argument("--target-id", required=True)
    cell_parser.add_argument("--protocol", required=True)
    cell_parser.add_argument("--control-verdict", required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        matrix = load_matrix(args.config)
        result = curl_probe(matrix) if args.command == "control" else cell(
            matrix, args.target_id, args.protocol, args.control_verdict
        )
    except DriverError as exc:
        result = verdict("error", error_kind=exc.kind)
    except Exception:
        result = verdict("error", error_kind="internal")
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
