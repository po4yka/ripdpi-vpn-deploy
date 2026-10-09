#!/usr/bin/env python3
"""Own one pinned loopback OpenSSH sentinel on an ephemeral Linux CI runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import subprocess
import sys
import time
from uuid import uuid4


class SentinelError(ValueError):
    """Categorical failure only; subprocess output stays private."""


def run(argv, *, timeout=30, reason='sentinel-command-failed'):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode:
        raise SentinelError(reason)
    return result.stdout


def write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def private_root(path):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve() or any(c in str(path) for c in '\r\n\x00\"\\'):
        raise SentinelError('sentinel-root-invalid')
    info = path.lstat()
    if not path.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o777 != 0o700:
        raise SentinelError('sentinel-root-invalid')
    return path


def prepare(root):
    if sys.platform != 'linux' or os.getuid() == 0:
        raise SentinelError('ephemeral-linux-runner-required')
    root = private_root(root)
    user = pwd.getpwuid(os.getuid()).pw_name
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', user):
        raise SentinelError('sentinel-user-invalid')
    ssh = Path.home() / '.ssh'
    ssh.mkdir(mode=0o700, exist_ok=True)
    config_path = ssh / 'config'
    # This helper owns a disposable runner. Do not alter an operator SSH config.
    if os.path.lexists(config_path) or any(root.iterdir()):
        raise SentinelError('fresh-runner-inputs-required')
    # Hosted images can precreate an owner-controlled .ssh with mode 0755.
    # Tighten it before writing private configuration, without following links.
    fd = os.open(ssh, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise SentinelError('sentinel-ssh-directory-invalid')
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)
    private_root(ssh)
    run(['sudo', '-n', 'true'], reason='sentinel-sudo-unavailable')
    key, hostkey = root / 'identity', root / 'host-key'
    for path in (key, hostkey):
        run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(path)],
            reason='sentinel-key-generation-failed')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    unit = 'vpn-ci-liveness-' + uuid4().hex
    server_config = root / 'sshd-config'
    server = f'''Port {port}
ListenAddress 127.0.0.1
HostKey "{hostkey}"
PidFile "{root / 'sshd.pid'}"
AuthorizedKeysFile "{key}.pub"
AllowUsers {user}
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin no
UsePAM yes
StrictModes yes
AllowTcpForwarding no
AllowAgentForwarding no
X11Forwarding no
PermitTunnel no
Subsystem sftp internal-sftp
'''
    write(server_config, server.encode())
    public = hostkey.with_suffix('.pub').read_text().split()
    pins = root / 'known-hosts'
    write(pins, ('ci-liveness ' + ' '.join(public[:2]) + '\n').encode())
    config = f'''Host ci-liveness
  HostName 127.0.0.1
  HostKeyAlias ci-liveness
  Port {port}
  User {user}
  IdentityFile "{key}"
  IdentitiesOnly yes
  IdentityAgent none
  UserKnownHostsFile "{pins}"
  GlobalKnownHostsFile /dev/null
  StrictHostKeyChecking yes
  UpdateHostKeys no
  BatchMode yes
  ControlMaster no
  ControlPath none
'''.encode()
    manifest = {'schema_version': 1, 'unit': unit, 'ssh_config_sha256': hashlib.sha256(config).hexdigest(),
                'ssh_config': str(config_path), 'root': str(root)}
    # Publish exact cleanup ownership before starting the unit.
    write(root / 'owner.json', json.dumps(manifest, sort_keys=True).encode())
    write(config_path, config)
    # The package can be installed with its ordinary service disabled. OpenSSH
    # still requires this root-owned privilege-separation directory for -t.
    run(['sudo', '-n', 'install', '-d', '-m', '0755', '/run/sshd'],
        reason='sentinel-runtime-directory-failed')
    run(['sudo', '-n', '/usr/sbin/sshd', '-t', '-f', str(server_config)],
        reason='sentinel-sshd-config-invalid')
    run(['sudo', '-n', 'systemd-run', '--quiet', '--unit=' + unit,
         '--property=KillMode=control-group', '--property=Restart=no',
         '/usr/sbin/sshd', '-D', '-e', '-f', str(server_config)],
        reason='sentinel-service-start-failed')
    for _ in range(20):
        try:
            if run(['ssh', 'ci-liveness', 'id', '-un'], timeout=5).decode().strip() == user:
                run(['ssh', 'ci-liveness', 'sudo', '-n', 'true'])
                return
        except (SentinelError, subprocess.TimeoutExpired):
            time.sleep(0.25)
    raise SentinelError('sentinel-readiness-failed')


def stop(root):
    root = private_root(root)
    owner = root / 'owner.json'
    if not os.path.lexists(owner):
        # Preparation has not acquired a daemon or SSH-config ownership yet.
        return
    fd = os.open(owner, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_mode & 0o777 != 0o600):
            raise SentinelError('sentinel-owner-invalid')
        value = json.loads(stream.read(8192))
    if (set(value) != {'schema_version', 'unit', 'ssh_config_sha256', 'ssh_config', 'root'}
            or value['schema_version'] != 1 or value['root'] != str(root)
            or not re.fullmatch(r'vpn-ci-liveness-[0-9a-f]{32}', value['unit'])
            or value['ssh_config'] != str(Path.home() / '.ssh/config')):
        raise SentinelError('sentinel-owner-invalid')
    config = Path(value['ssh_config'])
    if os.path.lexists(config) and (config.is_symlink() or not config.is_file()
            or hashlib.sha256(config.read_bytes()).hexdigest() != value['ssh_config_sha256']):
        raise SentinelError('sentinel-config-changed')
    # Unit name is a private per-run random capability; never stop generic sshd.
    state = run(['sudo', '-n', 'systemctl', 'show', value['unit'], '--property=LoadState', '--value'],
                reason='sentinel-service-state-failed').strip()
    if state != b'not-found':
        run(['sudo', '-n', 'systemctl', 'stop', value['unit']], reason='sentinel-service-stop-failed')
    config.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('verb', choices=('prepare', 'stop'))
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    try:
        (prepare if args.verb == 'prepare' else stop)(args.root)
        print(json.dumps({'status': 'ready' if args.verb == 'prepare' else 'stopped'}))
    except SentinelError as exc:
        print(json.dumps({'status': 'error', 'reason': str(exc)}))
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({'status': 'error', 'reason': 'ci-sentinel-operation-failed'}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
