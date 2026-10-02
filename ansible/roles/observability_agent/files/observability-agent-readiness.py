#!/usr/bin/env python3
"""Require the managed sender process itself to own its ready HTTP listener."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

PROC = Path("/proc")
BIN = Path("/usr/local/bin")


def identity() -> tuple[int, str]:
    result = subprocess.run(
        [
            "/usr/bin/systemctl",
            "show",
            "observability-agent.service",
            "--property=ActiveState",
            "--property=MainPID",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    )
    properties = dict(line.split("=", 1) for line in result.stdout.splitlines())
    pid = int(properties["MainPID"])
    if properties["ActiveState"] != "active" or pid <= 0:
        raise ValueError("sender_not_active")
    # The start-time field prevents a recycled PID from passing the second check.
    start = (PROC / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19]
    return pid, start


def owns_listener(pid: int, runtime: str, port: int) -> None:
    process = PROC / str(pid)
    if not os.path.samefile(process / "exe", BIN / f"{runtime}-observability-agent"):
        raise ValueError("sender_executable_mismatch")
    sockets = set()
    with os.scandir(process / "fd") as entries:
        for count, entry in enumerate(entries, 1):
            if count > 65536:
                raise ValueError("sender_fd_bound_exceeded")
            try:
                target = os.readlink(entry.path)
            except FileNotFoundError:
                continue
            match = re.fullmatch(r"socket:\[(\d+)\]", target)
            if match:
                sockets.add(match[1])
    # net/tcp includes all namespace sockets, so its inode MUST also be held by
    # this exact MainPID. Namespace membership alone is not ownership proof.
    with (process / "net/tcp").open() as stream:
        table = stream.read(4 * 1024 * 1024 + 1)
    if len(table) > 4 * 1024 * 1024:
        raise ValueError("sender_socket_table_bound_exceeded")
    address = f"0100007F:{port:04X}"
    for row in table.splitlines()[1:]:
        columns = row.split()
        if len(columns) >= 10 and columns[1] == address and columns[3] == "0A":
            if columns[9] in sockets:
                return
    raise ValueError("sender_does_not_own_listener")


def ready(listener: str, runtime: str) -> None:
    if runtime not in ("vmagent", "prometheus"):
        raise ValueError("unsupported_sender_runtime")
    if not re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", listener):
        raise ValueError("sender_listener_not_loopback")
    port = int(listener.rsplit(":", 1)[1])
    if not 0 < port <= 65535:
        raise ValueError("sender_listener_port_invalid")
    before = identity()
    owns_listener(before[0], runtime, port)
    endpoint = "/ready" if runtime == "vmagent" else "/-/ready"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://{listener}{endpoint}", timeout=2) as response:
        if response.status != 200:
            raise ValueError("sender_not_ready")
    if identity() != before:
        raise ValueError("sender_changed_during_readiness")
    owns_listener(before[0], runtime, port)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("invalid_readiness_arguments")
        ready(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        # No command arguments, process environment, or response body is logged.
        raise SystemExit("managed_sender_not_ready") from None
