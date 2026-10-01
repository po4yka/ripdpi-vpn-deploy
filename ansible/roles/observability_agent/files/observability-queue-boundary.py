#!/usr/bin/env python3
"""Refuse implicit receiver changes or unsafe namespaces around retained queues."""

import errno
import os
from pathlib import Path
import pwd
import shlex
import stat
import sys

QUEUE = Path("/var/lib/observability-agent/queue")
BINDING = Path("/etc/observability-agent/queue-receiver.url")
DISK_ALLOWANCE = 2 * 1024**3
GUARD_UNIT = Path("/etc/systemd/system/observability-disk-guard.service")
COLLECTOR = Path("/var/lib/observability-prometheus")


def allocated_bytes(queue):
    def walk_error(error):
        if error.errno != errno.ENOENT or Path(error.filename) == queue:
            raise error

    metadata = queue.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("unsafe_queue_root")
    total = metadata.st_blocks * 512
    count = 0
    for root, directories, files in os.walk(queue, onerror=walk_error):
        for name in directories + files:
            count += 1
            if count > 100000:
                raise ValueError("unsafe_queue_tree")
            try:
                entry = (Path(root) / name).lstat()
            except FileNotFoundError:
                continue
            if not (stat.S_ISREG(entry.st_mode) or stat.S_ISDIR(entry.st_mode)):
                raise ValueError("unsafe_queue_entry")
            total += entry.st_blocks * 512
    final = queue.lstat()
    if (final.st_dev, final.st_ino) != (metadata.st_dev, metadata.st_ino):
        raise ValueError("unsafe_queue_root")
    return total


def ancestor(path):
    while not path.exists():
        path = path.parent
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise ValueError("unsafe_capacity_root")
    return path


def collector_allowance(queue_device):
    try:
        descriptor = os.open(GUARD_UNIT, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return 0
    with os.fdopen(descriptor) as source:
        metadata = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o644
            or metadata.st_nlink != 1
        ):
            raise ValueError("unsafe_collector_guard")
        contents = source.read(16385)
    commands = [
        line.removeprefix("ExecStart=")
        for line in contents.splitlines()
        if line.startswith("ExecStart=")
    ]
    if len(contents) > 16384 or len(commands) != 1:
        raise ValueError("invalid_collector_guard")
    command = shlex.split(commands[0])
    if (
        not command
        or command[0] != "/usr/local/libexec/observability-disk-guard.py"
        or len(command) % 2 != 1
    ):
        raise ValueError("invalid_collector_guard")
    flags = dict(zip(command[1::2], command[2::2]))
    if len(flags) != (len(command) - 1) // 2:
        raise ValueError("invalid_collector_guard")
    if flags.get("--data-dir") != str(COLLECTOR) or flags.get(
        "--agent-queue-allowance-bytes"
    ) != str(DISK_ALLOWANCE):
        raise ValueError("collector_shared_reserve_unproven")
    headroom = int(flags.get("--headroom-bytes", "0"))
    if not 0 < headroom < DISK_ALLOWANCE:
        raise ValueError("invalid_collector_headroom")
    if ancestor(COLLECTOR).stat().st_dev != queue_device:
        return 0
    used = allocated_bytes(COLLECTOR) if COLLECTOR.exists() else 0
    if used + headroom >= DISK_ALLOWANCE:
        raise ValueError("collector_allocation_exceeded")
    return DISK_ALLOWANCE - used + headroom


def capacity(queue):
    present = queue.exists()
    allocated = allocated_bytes(queue) if present else 0
    if allocated > DISK_ALLOWANCE:
        raise ValueError("queue_allocation_exceeds_admission")
    parent = ancestor(queue)
    fs = os.statvfs(parent)
    reserve = max(5 * 1024**3, fs.f_blocks * fs.f_frsize // 5)
    combined = collector_allowance(parent.stat().st_dev)
    if fs.f_bavail * fs.f_frsize <= reserve + DISK_ALLOWANCE - allocated + combined:
        raise ValueError("queue_filesystem_reserve")


def inspect(queue, binding, receiver, *, agent_uid, root_uid=0):
    for path in (queue, binding):
        for parent in reversed(path.parents):
            try:
                entry = parent.lstat()
            except FileNotFoundError:
                continue
            trusted_sticky = bool(entry.st_mode & stat.S_ISVTX) and entry.st_uid == 0
            if (
                not stat.S_ISDIR(entry.st_mode)
                or (entry.st_mode & 0o022 and not trusted_sticky)
                or entry.st_uid not in (0, root_uid, agent_uid)
            ):
                raise ValueError("unsafe_queue_ancestor")
    try:
        metadata = queue.lstat()
    except FileNotFoundError:
        present = False
    else:
        present = True
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != agent_uid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ValueError("unsafe_queue_directory")
    try:
        descriptor = os.open(binding, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        if present and any(queue.iterdir()):
            raise ValueError("unbound_retained_queue")
        return
    with os.fdopen(descriptor) as source:
        metadata = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != root_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("unsafe_queue_binding")
        saved = source.read(1025)
    if len(saved) > 1024:
        raise ValueError("invalid_queue_binding")
    if present and saved != receiver + "\n":
        raise ValueError("retained_queue_receiver_changed")


def main():
    try:
        try:
            owner = pwd.getpwnam("observability-agent").pw_uid
        except KeyError:
            owner = -1
        inspect(QUEUE, BINDING, sys.argv[1], agent_uid=owner)
        capacity(QUEUE)
    except (IndexError, OSError, ValueError):
        print("observability_queue_boundary_refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
