#!/usr/bin/env python3
"""Fail closed unless systemd exposes exactly one effective SSH TCP port."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence


SYSTEMCTL = "/usr/bin/systemctl"
SYSTEMCTL_TIMEOUT_SECONDS = 5.0
MAX_SYSTEMCTL_STDOUT = 4096

Runner = Callable[[tuple[str, ...]], str]


class VerificationError(Exception):
    """A categorical, safe-to-print verification refusal."""


def run_bounded(
    command: Sequence[str], *, timeout: float = SYSTEMCTL_TIMEOUT_SECONDS
) -> str:
    """Run a fixed inspection command with bounded time and captured stdout."""
    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    completed = False
    try:
        process = subprocess.Popen(
            tuple(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if process.stdout is None:
            raise VerificationError("systemctl-query-failed")
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        reached_eof = False
        while not reached_eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VerificationError("systemctl-query-failed")
            events = selector.select(remaining)
            if not events:
                raise VerificationError("systemctl-query-failed")
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), MAX_SYSTEMCTL_STDOUT + 1 - len(output))
                if not chunk:
                    reached_eof = True
                    break
                output.extend(chunk)
                if len(output) > MAX_SYSTEMCTL_STDOUT:
                    raise VerificationError("systemctl-query-failed")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise VerificationError("systemctl-query-failed")
        if process.wait(timeout=remaining) != 0:
            raise VerificationError("systemctl-query-failed")
        try:
            decoded = output.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise VerificationError("systemctl-query-failed") from exc
        completed = True
        return decoded
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError("systemctl-query-failed") from exc
    finally:
        selector.close()
        if process is not None and not completed:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                if process.poll() is None:
                    process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.SubprocessError:
                    pass
        if process is not None and process.stdout is not None:
            process.stdout.close()


def _properties(
    output: str,
    allowed: frozenset[str],
    category: str,
    *,
    required: frozenset[str] | None = None,
    repeated: frozenset[str] = frozenset(),
) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in allowed or (key in values and key not in repeated):
            raise VerificationError(category)
        values[key] = f"{values[key]} {value}".strip() if key in values else value
    if not (required or allowed).issubset(values):
        raise VerificationError(category)
    return values


def _service_state(output: str) -> str:
    values = _properties(
        output,
        frozenset({"LoadState", "ActiveState"}),
        "invalid ssh.service state",
    )
    if values["LoadState"] != "loaded" or values["ActiveState"] not in {
        "active",
        "inactive",
    }:
        raise VerificationError("invalid ssh.service state")
    return values["ActiveState"]


def _socket_state(output: str) -> tuple[str, str]:
    properties = frozenset(
        {"LoadState", "ActiveState", "Listen", "Triggers", "Accept"}
    )
    values = _properties(
        output,
        properties,
        "invalid ssh.socket state",
        required=frozenset({"LoadState", "ActiveState"}),
        repeated=frozenset({"Listen"}),
    )
    load_state = values["LoadState"]
    active_state = values["ActiveState"]
    if (
        load_state == "not-found"
        and active_state == "inactive"
        and not values.get("Listen", "")
        and not values.get("Triggers", "")
        and values.get("Accept", "") in {"", "no"}
    ):
        return "missing", ""
    if (
        load_state != "loaded"
        or active_state not in {"active", "inactive"}
        or not properties.issubset(values)
    ):
        raise VerificationError("invalid ssh.socket state")
    if active_state == "active" and (
        values["Triggers"].split() != ["ssh.service"] or values["Accept"] != "no"
    ):
        raise VerificationError("invalid ssh.socket state")
    return active_state, values["Listen"]


def _endpoint_port(endpoint: str) -> int:
    host: str
    raw_port: str
    if endpoint.isdecimal():
        raw_port = endpoint
    elif endpoint.startswith("["):
        match = re.fullmatch(r"\[([^]]+)]:(\d+)", endpoint)
        if match is None:
            raise ValueError
        host, raw_port = match.groups()
        if ipaddress.ip_address(host).version != 6:
            raise ValueError
    else:
        match = re.fullmatch(r"([^:]+):(\d+)", endpoint)
        if match is None:
            raise ValueError
        host, raw_port = match.groups()
        if host != "*" and ipaddress.ip_address(host).version != 4:
            raise ValueError
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ValueError
    return port


def _stream_ports(listen: str) -> set[int]:
    if not listen:
        raise VerificationError("active ssh.socket has no valid Stream listener")
    entries: list[tuple[str, str]] = []
    position = 0
    pattern = re.compile(r"(\S+)\s+\(([^()\s]+)\)")
    for match in pattern.finditer(listen):
        if listen[position : match.start()].strip():
            raise VerificationError("active ssh.socket has no valid Stream listener")
        entries.append((match.group(1), match.group(2)))
        position = match.end()
    if listen[position:].strip() or not entries or len(entries) != len(set(entries)):
        raise VerificationError("active ssh.socket has no valid Stream listener")
    ports: set[int] = set()
    try:
        for endpoint, kind in entries:
            if kind != "Stream":
                raise ValueError
            ports.add(_endpoint_port(endpoint))
    except (ValueError, ipaddress.AddressValueError) as exc:
        raise VerificationError("active ssh.socket has no valid Stream listener") from exc
    if not ports:
        raise VerificationError("active ssh.socket has no valid Stream listener")
    return ports


def verify(expected_port: int, *, run: Runner = run_bounded) -> None:
    """Verify effective SSH listener ownership from bounded systemd state."""
    if isinstance(expected_port, bool) or not isinstance(expected_port, int) or not 1 <= expected_port <= 65535:
        raise VerificationError("invalid sshd port")
    service = _service_state(
        run(
            (
                SYSTEMCTL,
                "show",
                "ssh.service",
                "--all",
                "--property=LoadState",
                "--property=ActiveState",
            )
        )
    )
    socket, listen = _socket_state(
        run(
            (
                SYSTEMCTL,
                "show",
                "ssh.socket",
                "--all",
                "--property=LoadState",
                "--property=ActiveState",
                "--property=Listen",
                "--property=Triggers",
                "--property=Accept",
            )
        )
    )
    effective = {expected_port} if service == "active" else set()
    if socket == "active":
        effective.update(_stream_ports(listen))
    if effective != {expected_port}:
        rendered = ",".join(f"tcp/{port}" for port in sorted(effective))
        raise VerificationError(
            f"expected tcp/{expected_port} only; service={service} socket={socket} "
            f"effective=[{rendered}]"
        )


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Verify one effective systemd-owned SSH listener",
        exit_on_error=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    parser.add_argument("--sshd-port", required=True)
    try:
        args = parser.parse_args(argv)
        expected_port = int(args.sshd_port)
        verify(expected_port)
    except (argparse.ArgumentError, ValueError):
        print("verification error: invalid sshd port", file=sys.stderr)
        return 2
    except VerificationError as exc:
        print(f"verification error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
