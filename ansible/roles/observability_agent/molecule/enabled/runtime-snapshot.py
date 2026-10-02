"""Capture non-secret identities for real sender cutover/rollback assertions."""

import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


unit = Path("/etc/systemd/system/observability-agent.service")
old_binary = Path("/usr/local/bin/prometheus-observability-agent")
queue = Path("/var/lib/observability-agent/queue")
pid = subprocess.check_output(
    ["systemctl", "show", "observability-agent", "-p", "MainPID", "--value"], text=True
).strip()
subprocess.run(["systemctl", "is-active", "--quiet", "observability-agent"], check=True)
assert int(pid) > 1
executable = Path("/proc", pid, "cmdline").read_bytes().split(b"\0", 1)[0].decode()
version = subprocess.check_output([str(old_binary), "--version"], text=True)
assert version.startswith("prometheus, version 3.14.0 ")
print(
    json.dumps(
        {
            "unit_sha256": digest(unit),
            "generation": os.readlink("/etc/observability-agent/credentials/current"),
            "queue_inode": queue.stat().st_ino if queue.exists() else None,
            "wal_inode": Path("/var/lib/observability-agent/wal").stat().st_ino,
            "previous_binary": str(old_binary.resolve(strict=True)),
            "previous_binary_sha256": digest(old_binary),
            "previous_current": os.readlink("/opt/observability-agent/current"),
            "running_binary": executable,
        },
        sort_keys=True,
    )
)
