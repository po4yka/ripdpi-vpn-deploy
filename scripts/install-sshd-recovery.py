#!/usr/bin/env python3
"""Install SSH recovery on one explicit node; never activate an SSH migration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

import fleet_inspection as inspection
from sshd_bundle_source import BundleSourceError, bundle_manifest

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


def build_invocation(environment):
    target = environment.get('SSH_RECOVERY_TARGET', '')
    if not TARGET.fullmatch(target) or target in {'all', 'vpn', 'ungrouped'}:
        raise InstallError('exact-node-required')
    if environment.get('SSH_RECOVERY_WINDOW') != '1':
        raise InstallError('exclusive-window-required')
    debug = environment.get('ANSIBLE_DEBUG', '').lower().strip()
    if debug not in {'', 'false', 'no', '0', 'off'}:
        raise InstallError('ansible-debug-forbidden')
    section = environment.get('SSH_RECOVERY_INVENTORY_SECTION')
    if section not in {'vpn', 'observability-kuma'}:
        raise InstallError('inventory-section-required')
    inventory = Path(environment.get('SSH_RECOVERY_INVENTORY') or ROOT/'ansible/inventory/generated.ini').expanduser().absolute()
    known_hosts = Path(environment.get('SSH_RECOVERY_KNOWN_HOSTS') or Path.home()/'.ssh/known_hosts').expanduser().absolute()
    hosts = inspection.select_hosts(inventory, [target], primary_section=section)
    host = hosts[0]
    # Reuse the established strict SSH identity boundary, including custom-port
    # aliases, no agent and no inherited proxy. main() swaps only the three
    # multiplexing options for one run-owned master.
    ssh = inspection.ssh_command(host, known_hosts)
    # A disposable node can transiently drop a TCP SYN while Ansible opens its
    # SSH session. Retry transport establishment only; every attempt still
    # uses the same pinned identity.
    ssh[ssh.index('ConnectionAttempts=1')] = 'ConnectionAttempts=3'
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


MULTIPLEX_OPTIONS = ('ControlPath=none', 'ControlMaster=no', 'ControlPersist=no')


def shared_master_arguments(arguments, sockets):
    """Share one run-owned master across this playbook's tasks.

    The playbook installs recovery code and starts its recovery units, which do
    nothing without an open transaction. It never changes sshd or the firewall,
    so a master cannot hide a refused login. Every other strict option stays.
    """
    words = shlex.split(arguments)
    if any(words.count(option) != 1 for option in MULTIPLEX_OPTIONS):
        raise InstallError('unsupported-ssh-option')
    replaced = dict(zip(MULTIPLEX_OPTIONS, ('ControlPath=' + str(sockets / '%C'), 'ControlMaster=auto',
                                            'ControlPersist=60')))
    return shlex.join(replaced.get(word, word) for word in words)


def close_master(arguments, host, sockets, environment):
    # Called while another error may propagate: never raise.
    try:
        if any(sockets.iterdir()):
            # The same PATH as Ansible, so the same ssh resolves the same %C socket.
            subprocess.run(['ssh', *shlex.split(arguments), '-O', 'exit', host], env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        # Best effort: ControlPersist still ends an unclosed master, and the run removes its socket.
        pass


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
        # Control sockets live under a short 0700 /tmp path: macOS limits socket paths to 104 bytes.
        with tempfile.TemporaryDirectory(prefix='vpn-sshd-install-') as directory, \
                tempfile.TemporaryDirectory(prefix='vs-ssh-', dir='/tmp') as control:
            path = Path(directory) / 'inventory.ini'
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(inventory)
            argv[argv.index('-i') + 1] = str(path)
            sockets = Path(control).resolve()
            shared = shared_master_arguments(environment['ANSIBLE_SSH_ARGS'], sockets)
            environment['ANSIBLE_SSH_ARGS'] = shared
            host = json.loads(argv[argv.index('--extra-vars') + 1])['ansible_host']
            try:
                inspection.bounded_command(argv, timeout=600, limit=1024*1024, environment=environment)
            finally:
                close_master(shared, host, sockets, environment)
        print(json.dumps({'status':'installed', 'migration':'not-applied'}))
        return 0
    except (InstallError, BundleSourceError, inspection.InspectionError, OSError, ValueError):
        print(json.dumps({'status':'error', 'reason':'ssh-recovery-install-failed',
                          'action':'inspect-install-journal-before-retrying'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
