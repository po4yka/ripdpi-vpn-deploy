#!/usr/bin/env python3
"""Fail-closed reserve guard; a durable latch requires explicit operator recovery.

Retention-size is not a quota. Admission binds the polling/stop delay to measured
peak writes; the operator must repeat that measurement on the actual filesystem.
"""

import argparse
import errno
import ipaddress
import os
from pathlib import Path
import socket
import stat
import sys
import time

GIB = 1024**3
AGENT_QUEUE = Path("/var/lib/observability-agent/queue")


def private_address(value):
    address = ipaddress.ip_address(value)
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
    if address.version != 4 or not any(
        address in ipaddress.ip_network(n) for n in networks
    ):
        raise ValueError("private_ipv4_required")
    return str(address)


def allocated_bytes(root, *, allow_missing=False):
    """Account allocated blocks including WAL/head, without following links."""
    try:
        root_metadata = root.lstat()
    except FileNotFoundError:
        if allow_missing:
            return 0
        raise
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError("unsafe_data_root")

    def scan_error(error):
        # Compaction may remove a child after walk discovered it. All other
        # scan failures, including disappearance of the root, remain fatal.
        if error.errno != errno.ENOENT or Path(error.filename) == root:
            raise error

    total = 0
    count = 0
    for parent, directories, files in os.walk(
        root, followlinks=False, onerror=scan_error
    ):
        for name in [*directories, *files]:
            count += 1
            if count > 100000:
                raise ValueError("unsafe_data_tree")
            try:
                item = (Path(parent) / name).lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(item.st_mode):
                raise ValueError("unsafe_data_tree")
            total += item.st_blocks * 512
    final_root = root.lstat()
    if (final_root.st_dev, final_root.st_ino) != (
        root_metadata.st_dev,
        root_metadata.st_ino,
    ):
        raise ValueError("unsafe_data_root")
    return total


def inspect(args):
    root = Path(args.data_dir)
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    fs = os.statvfs(ancestor)
    reserve = max(
        args.reserve_bytes, fs.f_blocks * fs.f_frsize * args.reserve_percent // 100
    )
    queue_ancestor = AGENT_QUEUE
    while not queue_ancestor.exists():
        queue_ancestor = queue_ancestor.parent
    if queue_ancestor.stat().st_dev == ancestor.stat().st_dev:
        queue_used = allocated_bytes(AGENT_QUEUE, allow_missing=True)
        if queue_used > args.agent_queue_allowance_bytes:
            raise ValueError("agent_queue_allocation_exceeded")
        reserve += args.agent_queue_allowance_bytes - queue_used
    used = allocated_bytes(root, allow_missing=getattr(args, "preflight", False))
    available = fs.f_bavail * fs.f_frsize
    if used + args.headroom_bytes >= args.high_water_bytes:
        raise ValueError("data_high_water")
    if available <= reserve + args.headroom_bytes:
        raise ValueError("filesystem_reserve")
    return available, reserve, used


def validate_measurement(args):
    if args.agent_queue_allowance_bytes != 2 * GIB:
        raise ValueError("invalid_agent_queue_allowance")
    if args.peak_bytes_per_second <= 0 or not 1 <= args.stop_seconds <= 30:
        raise ValueError("disk_write_measurement_required")
    if not 1 <= args.interval_seconds <= 5:
        raise ValueError("guard_interval_exceeded")
    # Two times the measured poll+stop window leaves explicit burst headroom.
    if args.headroom_bytes < 2 * args.peak_bytes_per_second * (10 + args.stop_seconds):
        raise ValueError("insufficient_measured_headroom")
    if (
        not 0 < args.headroom_bytes < args.high_water_bytes
        or args.high_water_bytes != 2 * GIB
    ):
        raise ValueError("invalid_data_budget")
    if args.reserve_bytes < 5 * GIB or args.reserve_percent < 20:
        raise ValueError("invalid_reserve")


def latch(state_dir):
    """Persist before stopping writes; never clear an existing latch."""
    directory = Path(state_dir)
    metadata = directory.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o022:
        raise ValueError("unsafe_latch_directory")
    descriptor = os.open(
        directory / "latched",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.write(descriptor, b"disk_guard_latched\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def notify(message):
    address = os.environ["NOTIFY_SOCKET"]
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
        channel.connect(address)
        channel.sendall(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--state-dir", default="/var/lib/observability-disk-guard")
    parser.add_argument("--high-water-bytes", type=int, default=2 * GIB)
    parser.add_argument("--reserve-bytes", type=int, default=5 * GIB)
    parser.add_argument("--reserve-percent", type=int, default=20)
    parser.add_argument("--agent-queue-allowance-bytes", type=int, default=2 * GIB)
    parser.add_argument("--headroom-bytes", type=int, required=True)
    parser.add_argument("--peak-bytes-per-second", type=int, required=True)
    parser.add_argument("--stop-seconds", type=int, required=True)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--ingress-address", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    try:
        private_address(args.ingress_address)
        validate_measurement(args)
        if Path(args.state_dir, "latched").exists():
            raise ValueError("manual_disk_recovery_required")
        available, reserve, _ = inspect(args)
        if args.preflight:
            memory = dict(
                line.split(":", 1)
                for line in Path("/proc/meminfo").read_text().splitlines()
            )
            if int(memory["MemAvailable"].split()[0]) * 1024 < GIB:
                raise ValueError("memory_admission_failed")
            if available <= reserve + args.high_water_bytes + args.headroom_bytes:
                raise ValueError("disk_admission_failed")
            with socket.socket() as probe:
                probe.bind((args.ingress_address, 0))
            print("capacity_admitted")
            return 0
        notify(b"READY=1\nWATCHDOG=1")
        while True:
            time.sleep(args.interval_seconds)
            inspect(args)
            notify(b"WATCHDOG=1")
    except (OSError, ValueError, KeyError):
        if not args.preflight:
            try:
                latch(args.state_dir)
            except FileExistsError:
                # An existing durable latch already prevents receiver restart.
                pass
            except (OSError, ValueError):
                # Service exit also stops its BindsTo receiver on latch I/O failure.
                print("disk_guard_latch_failed", file=sys.stderr)
        print("observability_capacity_refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
