#!/usr/bin/env python3
"""Install SSH recovery on one explicit node; never activate an SSH migration."""
from __future__ import annotations

import json
import hashlib
import stat
import os
from pathlib import Path
import re
import shlex
import tempfile

import fleet_inspection as inspection

ROOT = Path(__file__).resolve().parents[1]
TARGET = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')


class InstallError(ValueError):
    """Redacted controller failure, never raw Ansible output."""


def portable_ssh_arguments(command):
    """Ansible shares these options with scp/sftp, whose -l/-p differ."""
    result = []
    options = iter(command[1:-2])
    for flag in options:
        value = next(options)
        if flag in {'-i', '-l', '-p'}:
            value = {'-i': 'IdentityFile', '-l': 'User', '-p': 'Port'}[flag] + '=' + value
            flag = '-o'
        if flag not in {'-F', '-o'}:
            raise InstallError('unsupported-ssh-option')
        if flag == '-o' and value.startswith(('IdentityFile=', 'UserKnownHostsFile=')):
            name, path = value.split('=', 1)
            if any(c in path for c in '\r\n\x00'):
                raise InstallError('unsafe-ssh-path')
            # -o values have OpenSSH configuration quoting in addition to the
            # outer shell quoting consumed by Ansible's shlex.split.
            value = name + '="' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'
        result.extend((flag, value))
    return shlex.join(result)


def bundle_manifest():
    source = ROOT / 'ansible/roles/baseline'
    names = ('sshd_migrate.py', 'sshd_transaction.py', 'sshd_ownership.py',
             'units/vpn-sshd-boot-recover.service', 'units/vpn-sshd-recover.service',
             'units/vpn-sshd-recover.timer')
    hashes = {}
    for name in names:
        path = source / ('templates' if name.startswith('units/') else 'files') / Path(name).name
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                    or info.st_mode & 0o022 or info.st_size > 256*1024):
                raise InstallError('source-file-unsafe')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                content = stream.read(256*1024+1)
            if len(content) > 256*1024:
                raise InstallError('source-file-too-large')
            hashes[name] = hashlib.sha256(content).hexdigest()
        finally:
            os.close(fd)
    manifest = json.dumps({'schema_version':1,'files':hashes},sort_keys=True,separators=(',',':'))+'\n'
    return hashlib.sha256(manifest.encode()).hexdigest(), manifest


def build_invocation(environment):
    target = environment.get('SSH_RECOVERY_TARGET', '')
    if not TARGET.fullmatch(target) or target in {'all', 'vpn', 'ungrouped'}:
        raise InstallError('exact-node-required')
    if environment.get('SSH_RECOVERY_WINDOW') != '1':
        raise InstallError('exclusive-window-required')
    debug = environment.get('ANSIBLE_DEBUG', '').lower().strip()
    if debug not in {'', 'false', 'no', '0', 'off'}:
        raise InstallError('ansible-debug-forbidden')
    inventory = Path(environment.get('SSH_RECOVERY_INVENTORY') or ROOT/'ansible/inventory/generated.ini').expanduser().absolute()
    known_hosts = Path(environment.get('SSH_RECOVERY_KNOWN_HOSTS') or Path.home()/'.ssh/known_hosts').expanduser().absolute()
    hosts = inspection.select_hosts(inventory, [target])
    host = hosts[0]
    # Reuse the established strict SSH identity boundary, including custom-port
    # aliases, no agent, no inherited proxy, and no multiplexed connection.
    ssh = inspection.ssh_command(host, known_hosts)
    generation, manifest = bundle_manifest()
    extra_vars = {
        'ssh_recovery_generation': generation, 'ssh_recovery_manifest': manifest,
        'ssh_recovery_exclusive_window': True,
        'ansible_host': host['transport'], 'ansible_user': host['user'], 'ansible_port': host['port'],
        'ansible_ssh_private_key_file': host['key'], 'ansible_python_interpreter': '/usr/bin/python3',
        'ansible_connection': 'ssh', 'ansible_become_method': 'sudo', 'ansible_become_flags': '-n',
    }
    argv = ['ansible-playbook', '-i', '<private-inventory>', str(ROOT/'ansible/playbooks/install-sshd-recovery.yml'),
            '--limit', target, '--extra-vars', json.dumps(extra_vars, sort_keys=True)]
    # Do not forward provider credentials, Git routing, plugin overrides, or
    # tags which can turn an apparently successful installation into a no-op.
    child = {key: environment[key] for key in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE') if key in environment}
    child.update(ANSIBLE_CONFIG=str(ROOT/'ansible/ansible.cfg'), ANSIBLE_DEBUG='false',
                 ANSIBLE_HOST_KEY_CHECKING='true', ANSIBLE_SSH_ARGS=portable_ssh_arguments(ssh),
                 ANSIBLE_SSH_COMMON_ARGS='', ANSIBLE_SSH_EXTRA_ARGS='', ANSIBLE_INVENTORY_ENABLED='ini',
                 ANSIBLE_VARS_ENABLED='', ANSIBLE_VARS_PLUGINS=os.devnull,
                 ANSIBLE_LOG_PATH=os.devnull, ANSIBLE_DISPLAY_ARGS_TO_STDOUT='false')
    return argv, child, '[vpn]\n' + target + '\n'


def _clean_source(environment):
    dirty = inspection.bounded_command(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=normal'],
                                       timeout=10, environment=environment)
    if dirty.strip():
        raise InstallError('clean-source-required')
    for flag, size in (('--revision', 40), ('--digest', 64)):
        result = inspection.bounded_command([str(ROOT/'scripts/deploy-source-identity.sh'), flag],
                                            timeout=10, environment=environment).decode().strip()
        if re.fullmatch('[0-9a-f]{'+str(size)+'}', result) is None:
            raise InstallError('source-identity-required')


def main():
    try:
        argv, environment, inventory = build_invocation(dict(os.environ))
        _clean_source(environment)
        # Capture/discard both streams: no_log alone cannot protect values from
        # Ansible's own debug internals. An uncertain install stays journaled.
        # Never let Ansible discover unvalidated sibling host_vars/group_vars
        # beside the operator's original inventory.
        with tempfile.TemporaryDirectory(prefix='vpn-sshd-install-') as directory:
            path = Path(directory) / 'inventory.ini'
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(inventory)
            argv[argv.index('-i') + 1] = str(path)
            inspection.bounded_command(argv, timeout=600, limit=1024*1024, environment=environment)
        print(json.dumps({'status':'installed', 'migration':'not-applied'}))
        return 0
    except (InstallError, inspection.InspectionError, OSError, ValueError):
        print(json.dumps({'status':'error', 'reason':'ssh-recovery-install-failed',
                          'action':'inspect-install-journal-before-retrying'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
