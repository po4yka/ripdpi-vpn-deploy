"""Add one selected hardware recipient without retiring recovery authority."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

import yaml
from encrypted_client_document import MAX_BYTES, identity, private_file, run_sops


class PrivateSource:
    """Retain the shared writer lock and original authority until publication."""

    def __init__(self, path):
        self.path = path
        self.source = self.lock = None
        self.before = None
        self.data = None

    def __enter__(self):
        try:
            self.lock = os.open(str(self.path) + '.new-client.lock',
                                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            self.lock_before = private_file(self.lock)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.source = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                return self
            self.before = private_file(self.source)
            if self.before.st_size > MAX_BYTES:
                raise ValueError('private-document-too-large')
            self.data = os.read(self.source, MAX_BYTES + 1)
            self.check()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def check(self):
        named_lock = self.path.with_name(self.path.name + '.new-client.lock').lstat()
        if (named_lock.st_dev, named_lock.st_ino) != (self.lock_before.st_dev, self.lock_before.st_ino):
            raise ValueError('private-lock-changed')
        if self.before is None:
            if self.path.exists() or self.path.is_symlink():
                raise ValueError('private-document-changed')
        elif (identity(self.path.lstat()) != identity(self.before)
              or identity(os.fstat(self.source)) != identity(self.before)
              or len(self.data) != self.before.st_size):
            raise ValueError('private-document-changed')

    def publish(self, data):
        self.check()
        if data == self.data:
            return
        descriptor, temporary = tempfile.mkstemp(prefix='.' + self.path.name + '.hardware.', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            self.check()
            os.replace(temporary, self.path)
            temporary = None
            parent = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            if temporary is not None:
                os.unlink(temporary)

    def __exit__(self, *_):
        if self.source is not None:
            os.close(self.source)
        if self.lock is not None:
            os.close(self.lock)


def parse_identity(data, serial, slot):
    text = data.decode('utf-8')
    selected = re.findall(r'^#\s*Serial:\s*(\d+),\s*Slot:\s*(\d+)\s*$', text, re.MULTILINE)
    recipients = re.findall(r'^#\s*Recipient:\s*(age1(?:yubikey1|tag1)[a-z0-9]+)\s*$', text, re.MULTILINE)
    stubs = re.findall(r'^AGE-PLUGIN-YUBIKEY-[A-Z0-9]+$', text, re.MULTILINE)
    if (selected != [(str(serial), str(slot))] or len(recipients) != 1 or len(stubs) != 1):
        raise ValueError('selected-hardware-identity-required')
    return recipients[0], stubs[0]


def operator_terminal():
    # Plugin setup can display a recovery management key on failure. Its PIN
    # prompts and diagnostics belong only to the operator's private terminal.
    return open('/dev/tty', 'r+b', buffering=0)


def plugin_identity(serial, slot, generate):
    argv = ['age-plugin-yubikey', '--generate' if generate else '--identity',
            '--serial', str(serial), '--slot', str(slot)]
    if generate:
        with operator_terminal() as terminal:
            result = subprocess.run(argv, stdin=terminal, stdout=subprocess.PIPE, stderr=terminal,
                                    check=False, timeout=180)
    else:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=180)
    if result.returncode or len(result.stdout) > 16384:
        raise ValueError('hardware-identity-operation-refused')
    parse_identity(result.stdout, serial, slot)
    return result.stdout


def age_recipients(value):
    recipients = value.split(',') if isinstance(value, str) else value
    if not isinstance(recipients, list) or not recipients or not all(
            isinstance(item, str) and re.fullmatch(r'age1[a-z0-9]+', item.strip()) for item in recipients):
        raise ValueError('age-only-recipient-policy-required')
    return [item.strip() for item in recipients]


def admit_rule(rule):
    if (not isinstance(rule, dict) or 'key_groups' in rule
            or any(rule.get(key) for key in ('pgp', 'kms', 'gcp_kms', 'azure_keyvault', 'hc_vault_transit_uri', 'hckms'))):
        raise ValueError('single-group-age-policy-required')
    age_recipients(rule.get('age'))


def additive_rule(encrypted, recipient):
    document = yaml.safe_load(encrypted)
    metadata = document.get('sops') if isinstance(document, dict) else None
    if (not isinstance(metadata, dict) or metadata.get('key_groups')
            or metadata.get('shamir_threshold', 0) not in (0, 1)
            or any(metadata.get(key) for key in ('pgp', 'kms', 'gcp_kms', 'azure_kv', 'hc_vault', 'hckms'))):
        raise ValueError('single-group-age-document-required')
    entries = metadata.get('age')
    if not isinstance(entries, list) or not entries or not all(isinstance(item, dict) for item in entries):
        raise ValueError('age-only-document-required')
    recipients = age_recipients([item.get('recipient') for item in entries])
    rule = {'age': list(dict.fromkeys([*recipients, recipient]))}
    for key in ('unencrypted_suffix', 'encrypted_suffix', 'unencrypted_regex',
                'encrypted_regex', 'unencrypted_comment_regex', 'encrypted_comment_regex',
                'mac_only_encrypted'):
        if metadata.get(key) is not None:
            rule[key] = metadata[key]
    return rule


def stage_update(path, encrypted, rule, runner=run_sops):
    """Real SOPS rewraps an encrypted sibling; plaintext stays only in memory."""
    expected = runner(['--decrypt', '--input-type', 'yaml', '--output-type', 'json', '/dev/stdin'], data=encrypted)
    with tempfile.TemporaryDirectory(prefix='.' + path.name + '.hardware.', dir=path.parent) as temporary:
        config = Path(temporary) / '.sops.yaml'
        config.write_text(yaml.safe_dump({'creation_rules': [rule]}))
        config.chmod(0o600)
        candidate = Path(temporary) / path.name
        candidate.write_bytes(encrypted)
        candidate.chmod(0o600)
        runner(['--config', str(config), 'updatekeys', '-y', str(candidate)])
        if candidate.stat().st_size > MAX_BYTES:
            raise ValueError('private-document-too-large')
        actual = candidate.read_bytes()
        verified = runner(['--decrypt', '--input-type', 'yaml', '--output-type', 'json', '/dev/stdin'], data=actual)
        if json.loads(expected) != json.loads(verified) or additive_rule(actual, rule['age'][-1]) != rule:
            raise ValueError('hardware-migration-verification-failed')
        return actual


def migrate(directory, recipient, runner=run_sops):
    with ExitStack() as stack:
        configuration = stack.enter_context(PrivateSource(directory / '.sops.yaml'))
        policy = yaml.safe_load(configuration.data) if configuration.data is not None else {'creation_rules': []}
        if (not isinstance(policy, dict) or not isinstance(policy.get('creation_rules'), list)):
            raise TypeError('invalid-sops-configuration')
        for rule in policy['creation_rules']:
            admit_rule(rule)
        files = sorted(directory.glob('*.secrets.sops.yaml'))
        if not files:
            raise ValueError('no-encrypted-documents-selected')
        candidates = []
        rules = []
        for path in files:
            source = stack.enter_context(PrivateSource(path))
            if source.data is None:
                raise ValueError('encrypted-document-missing')
            rule = additive_rule(source.data, recipient)
            staged = stage_update(path, source.data, rule, runner)
            candidates.append((source, staged))
            rules.append({'path_regex': '^' + re.escape(path.name) + '$', **rule})
        # Exact file rules retain each document's recovery recipients independently.
        # General rules remain unchanged. Repeated enrollment replaces our exact rules.
        exact = {rule['path_regex'] for rule in rules}
        policy['creation_rules'] = rules + [rule for rule in policy['creation_rules'] if rule.get('path_regex') not in exact]
        for source, _ in candidates:
            source.check()
        configuration.publish(yaml.safe_dump(policy, sort_keys=False).encode())
        for source, staged in candidates:
            source.publish(staged)
        return len(candidates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True, type=int)
    parser.add_argument('--slot', required=True, type=int)
    parser.add_argument('--generate', action='store_true', help='Create only if no saved identity exists.')
    parser.add_argument('--reencrypt', action='store_true', help='Add the recipient to every selected encrypted file.')
    arguments = parser.parse_args()
    try:
        if not 0 < arguments.serial < 2**32 or not 1 <= arguments.slot <= 20:
            raise ValueError('invalid-hardware-selector')
        directory = Path.home() / '.config/vpn-provision'
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = directory.lstat()
        if directory.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private-operator-directory-required')
        with PrivateSource(directory / 'yubikey-identity.txt') as saved:
            if saved.data is not None:
                expected = parse_identity(saved.data, arguments.serial, arguments.slot)
                if arguments.generate:
                    raise ValueError('existing-hardware-identity-resume-required')
                actual = plugin_identity(arguments.serial, arguments.slot, False)
                if parse_identity(actual, arguments.serial, arguments.slot) != expected:
                    raise ValueError('hardware-identity-changed')
            else:
                actual = plugin_identity(arguments.serial, arguments.slot, arguments.generate)
                saved.publish(actual)
            recipient, _ = parse_identity(actual, arguments.serial, arguments.slot)
            updated = migrate(directory, recipient) if arguments.reencrypt else 0
        print(json.dumps({'identity': 'ready', 'updated_files': updated}))
        print('Recovery recipients remain active. Verify hardware-only decryption before separate retirement.')
    except (OSError, TypeError, ValueError, yaml.YAMLError, subprocess.SubprocessError):
        print('Hardware enrollment refused; inspect selected identity, private authority and age-only policy. Prior recovery recipients remain active.', file=sys.stderr)
        return 1
    return 0


def interrupted(*_):
    raise KeyboardInterrupt


if __name__ == '__main__':
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        signal.signal(signum, interrupted)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Hardware enrollment interrupted; resume the same serial and slot.', file=sys.stderr)
        raise SystemExit(130)
