#!/usr/bin/env python3
"""Read-only observer admission; never install a runtime or change authority."""

import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys


def private_directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('backup-path-boundary')
    for component in [*reversed(path.parents), path]:
        info = component.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError('backup-path-boundary')
        if component == path and stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('private-backup-storage')
    return path


def local_address(address):
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            listener.bind((str(address), 0))
    except OSError:
        raise ValueError('local-private-address') from None


def check(config, *, proc=Path('/proc/meminfo'), usage=shutil.disk_usage, run=subprocess.run, bind=local_address):
    address = ipaddress.ip_address(config['bind_address'])
    if not (address.is_private or address in ipaddress.ip_network('100.64.0.0/10')) or address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
        raise ValueError('private-ingress')
    bind(address)
    if not 1 <= len(config['allowed_sources']) <= 10:
        raise ValueError('source-allowlist')
    for source in config['allowed_sources']:
        peer = ipaddress.ip_network(source, strict=True)
        if peer.num_addresses != 1 or peer.network_address == address or not (peer.network_address.is_private or peer.network_address in ipaddress.ip_network('100.64.0.0/10')) or peer.network_address.is_loopback or peer.network_address.is_unspecified or peer.network_address.is_link_local:
            raise ValueError('source-allowlist')
    memory = re.search(r'^MemAvailable:\s+(\d+) kB$', proc.read_text(), re.M)
    if memory is None or int(memory[1]) * 1024 < config['minimum_available_memory_bytes']:
        raise ValueError('memory-reserve')
    data = Path(config['data_dir'])
    ancestor = data if data.exists() else data.parent
    if ancestor.is_symlink() or not ancestor.is_dir():
        raise ValueError('local-data-path')
    disk = usage(ancestor)
    reserve = max(config['reserve_minimum_bytes'], disk.total // 5)
    if disk.free < config['data_allowance_bytes'] + reserve:
        raise ValueError('disk-reserve')
    filesystem = run(['/usr/bin/findmnt', '-n', '-o', 'FSTYPE', '-T', str(ancestor)], capture_output=True, text=True, check=True).stdout.strip()
    if filesystem not in {'ext4', 'xfs', 'btrfs'}:
        raise ValueError('local-filesystem')
    backup = private_directory(config['backup_directory'])
    if not backup.is_absolute() or backup.is_symlink() or not backup.is_dir() or os.stat(backup).st_dev == os.stat(ancestor).st_dev:
        raise ValueError('separate-existing-backup-storage')
    info = backup.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('private-backup-storage')
    if usage(backup).free < config['data_allowance_bytes']:
        raise ValueError('backup-capacity')
    # These are existing-runtime checks, not package installation authority.
    for command in (['/usr/bin/docker', 'info', '--format', '{{.ServerVersion}}'], ['/usr/sbin/nginx', '-v'], ['/usr/bin/age', '--version']):
        run(command, capture_output=True, check=True, timeout=10)


if __name__ == '__main__':
    try:
        check(json.load(sys.stdin))
    except Exception as error:
        categories = {'private-ingress', 'local-private-address', 'source-allowlist', 'memory-reserve', 'local-data-path', 'disk-reserve', 'local-filesystem', 'separate-existing-backup-storage', 'private-backup-storage', 'backup-path-boundary', 'backup-capacity'}
        reason = str(error) if type(error) is ValueError and str(error) in categories else 'existing-runtime-or-path-unavailable'
        print('observer admission failed: ' + reason, file=sys.stderr)
        raise SystemExit(1) from None
