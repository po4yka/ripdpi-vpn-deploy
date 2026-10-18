"""Hardware output admission plus real SOPS additive recipient transactions."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('hardware_age', ROOT / 'scripts/setup_yubikey_age.py')
hardware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hardware)


def identity_text(serial=1234, slot=2, recipient='age1yubikey1testrecipient', stub='AGE-PLUGIN-YUBIKEY-1TEST'):
    return f'# Serial: {serial}, Slot: {slot}\n# Recipient: {recipient}\n{stub}\n'.encode()


def test_released_commented_recipient_selects_one_exact_identity():
    assert hardware.parse_identity(identity_text(), 1234, 2) == ('age1yubikey1testrecipient', 'AGE-PLUGIN-YUBIKEY-1TEST')


@pytest.mark.parametrize('data', [identity_text(serial=777), identity_text(slot=1), identity_text() * 2,
                                 b'age1yubikey1testrecipient\nAGE-PLUGIN-YUBIKEY-1TEST\n',
                                 identity_text().replace(b'# Recipient:', b'# unrelated:')])
def test_ambiguous_or_different_identity_refuses(data):
    with pytest.raises(ValueError, match='selected-hardware-identity-required'):
        hardware.parse_identity(data, 1234, 2)


@pytest.fixture
def authority(tmp_path, monkeypatch):
    directory = tmp_path / 'operator'
    directory.mkdir(mode=0o700)
    recipients = []
    identities = []
    for index in range(3):
        key = tmp_path / f'key-{index}'
        subprocess.run(['age-keygen', '-o', str(key)], capture_output=True, check=True)
        identities.append(key)
        recipients.append(subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip())
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(identities[0]))
    monkeypatch.delenv('SOPS_CONFIG', raising=False)
    return directory, recipients, identities


def encrypted_file(directory, name, recipient, payload=None):
    data = json.dumps(payload or {'secret': 'synthetic-value', 'public_unencrypted': 'kept-public'}).encode()
    raw = subprocess.run(['sops', '--encrypt', '--input-type', 'json', '--output-type', 'yaml',
                          '--age', recipient, '/dev/stdin'], input=data, capture_output=True, check=True).stdout
    target = directory / name
    target.write_bytes(raw)
    target.chmod(0o600)
    return target


def decrypt(path, key):
    result = subprocess.run(['sops', '--decrypt', '--output-type', 'json', str(path)],
                            env={**os.environ, 'SOPS_AGE_KEY_FILE': str(key)}, check=False, capture_output=True)
    assert result.returncode == 0, 'synthetic SOPS roundtrip refused'
    return json.loads(result.stdout)


def test_real_sops_explicit_additive_migration_preserves_each_recovery_path(authority, tmp_path, monkeypatch):
    directory, recipients, identities = authority
    first = encrypted_file(directory, 'first.secrets.sops.yaml', recipients[0])
    second = encrypted_file(directory, 'second.secrets.sops.yaml', recipients[1])
    keys = tmp_path / 'both.keys'
    keys.write_bytes(identities[0].read_bytes() + b'\n' + identities[1].read_bytes())
    keys.chmod(0o600)
    monkeypatch.setenv('SOPS_AGE_KEY_FILE', str(keys))
    config = directory / '.sops.yaml'
    original_rule = {'path_regex': '.*', 'age': recipients[0], 'unencrypted_suffix': '_unencrypted'}
    config.write_text(yaml.safe_dump({'creation_rules': [original_rule]}))
    config.chmod(0o600)
    monkeypatch.chdir(tmp_path)  # No implicit lookup of the operator config.
    assert hardware.migrate(directory, recipients[2]) == 2
    for path, prior in [(first, identities[0]), (second, identities[1])]:
        assert decrypt(path, prior) == decrypt(path, identities[2])
        assert path.stat().st_mode & 0o777 == 0o600
    first_recipients = hardware.additive_rule(first.read_bytes(), recipients[2])['age']
    second_recipients = hardware.additive_rule(second.read_bytes(), recipients[2])['age']
    assert recipients[1] not in first_recipients and recipients[0] not in second_recipients
    policy = yaml.safe_load(config.read_text())
    assert policy['creation_rules'][-1] == original_rule
    assert len(policy['creation_rules']) == 3
    hardware.migrate(directory, recipients[2])
    assert yaml.safe_load(config.read_text()) == policy
    # The canonical config can update the original named documents explicitly.
    subprocess.run(['sops', '--config', str(config), 'updatekeys', '-y', str(first)], capture_output=True, check=True)
    assert decrypt(first, identities[0]) == decrypt(first, identities[2])


@pytest.mark.parametrize('failure', ['update', 'verification'])
def test_real_candidates_are_not_published_when_any_stage_fails(authority, failure):
    directory, recipients, _ = authority
    paths = [encrypted_file(directory, f'{name}.secrets.sops.yaml', recipients[0]) for name in ('a', 'b')]
    before = {path: path.read_bytes() for path in paths}
    calls = 0

    def runner(arguments, *, data=None):
        nonlocal calls
        if 'updatekeys' in arguments:
            calls += 1
            if calls == 2 and failure == 'update':
                raise ValueError('synthetic-update-refused')
        result = hardware.run_sops(arguments, data=data)
        if failure == 'verification' and calls == 2 and '--decrypt' in arguments:
            return b'{"secret":"different synthetic plaintext"}'
        return result

    with pytest.raises(ValueError):
        hardware.migrate(directory, recipients[2], runner)
    assert {path: path.read_bytes() for path in paths} == before
    assert not (directory / '.sops.yaml').exists()
    assert not list(directory.glob('.*.hardware.*'))


def test_existing_writer_lock_prevents_hardware_migration(authority):
    directory, recipients, _ = authority
    path = encrypted_file(directory, 'a.secrets.sops.yaml', recipients[0])
    before = path.read_bytes()
    with hardware.PrivateSource(path), pytest.raises(BlockingIOError):
        hardware.migrate(directory, recipients[2])
    assert path.read_bytes() == before


@pytest.mark.parametrize('where', ['document', 'configuration'])
def test_grouped_policy_refuses_before_replacing_authority(authority, where):
    directory, recipients, _ = authority
    path = encrypted_file(directory, 'a.secrets.sops.yaml', recipients[0])
    if where == 'document':
        document = yaml.safe_load(path.read_bytes())
        document['sops']['key_groups'] = [{'age': document['sops'].pop('age')}]
        path.write_text(yaml.safe_dump(document))
    else:
        config = directory / '.sops.yaml'
        config.write_text(yaml.safe_dump({'creation_rules': [{'key_groups': [{'age': [recipients[0]]}]}]}))
        config.chmod(0o600)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='single-group-age'):
        hardware.migrate(directory, recipients[2])
    assert path.read_bytes() == before


def test_resume_keeps_identity_and_never_generates(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    directory = home / '.config/vpn-provision'
    directory.mkdir(parents=True, mode=0o700)
    saved = directory / 'yubikey-identity.txt'
    saved.write_bytes(identity_text())
    saved.chmod(0o600)
    original = saved.stat()
    calls = []

    def plugin(serial, slot, generate):
        calls.append((serial, slot, generate))
        return identity_text()

    monkeypatch.setattr(hardware, 'plugin_identity', plugin)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setattr(sys, 'argv', ['setup-yubikey-age', '--serial', '1234', '--slot', '2'])
    assert hardware.main() == 0
    assert calls == [(1234, 2, False)]
    assert saved.read_bytes() == identity_text() and saved.stat().st_ino == original.st_ino
    monkeypatch.setattr(sys, 'argv', ['setup-yubikey-age', '--serial', '1234', '--slot', '2', '--generate'])
    assert hardware.main() == 1
    assert calls == [(1234, 2, False)]


def test_compromise_runbook_rotates_data_key_before_new_credentials():
    text = (ROOT / 'docs/AGE-RECOVERY.md').read_text().split('## Rotating the age key', 1)[1]
    assert text.index('sops updatekeys') < text.index('sops rotate --in-place') < text.index('application credentials')


def test_real_sops_compromise_sequence_replaces_the_exposed_data_key(authority):
    directory, recipients, identities = authority
    path = encrypted_file(directory, 'compromise.secrets.sops.yaml', recipients[0])

    def unwrap(key):
        wrapped = yaml.safe_load(path.read_bytes())['sops']['age'][0]['enc'].encode()
        result = subprocess.run(['age', '--decrypt', '-i', str(key)], input=wrapped, capture_output=True, check=True)
        return result.stdout

    exposed = unwrap(identities[0])
    config = directory / '.sops.yaml'
    config.write_text(yaml.safe_dump({'creation_rules': [{'age': recipients[1]}]}))
    environment = {**os.environ, 'SOPS_AGE_KEY_FILE': str(identities[0])}
    subprocess.run(['sops', '--config', str(config), 'updatekeys', '-y', str(path)],
                   env=environment, capture_output=True, check=True)
    assert unwrap(identities[1]) == exposed  # Recipient retirement alone retains the compromised key.
    environment['SOPS_AGE_KEY_FILE'] = str(identities[1])
    subprocess.run(['sops', 'rotate', '--in-place', str(path)], env=environment, capture_output=True, check=True)
    assert unwrap(identities[1]) != exposed
    subprocess.run(['sops', 'set', '--value-stdin', str(path), '["secret"]'],
                   env=environment, input=b'"replacement-synthetic-credential"', capture_output=True, check=True)
    assert decrypt(path, identities[1])['secret'] == 'replacement-synthetic-credential'
    refused = subprocess.run(['sops', '--decrypt', str(path)], env={**environment, 'SOPS_AGE_KEY_FILE': str(identities[0])},
                             check=False, capture_output=True)
    assert refused.returncode != 0


def test_real_restic_password_change_keeps_the_prior_snapshot(tmp_path):
    repository = tmp_path / 'prior-generation'
    original = tmp_path / 'original-password'
    replacement = tmp_path / 'replacement-password'
    for path, data in [(original, 'synthetic-original-password'), (replacement, 'synthetic-replacement-password')]:
        path.write_text(data)
        path.chmod(0o600)
    content = tmp_path / 'configuration'
    content.write_text('synthetic-backup-content')
    base = ['restic', '-r', str(repository), '--no-cache']
    subprocess.run([*base, '--password-file', str(original), 'init'], capture_output=True, check=True)
    subprocess.run([*base, '--password-file', str(original), 'backup', str(content)], capture_output=True, check=True)
    before = subprocess.check_output([*base, '--password-file', str(original), 'snapshots', '--json'])
    subprocess.run([*base, '--password-file', str(original), 'key', 'passwd', '--new-password-file', str(replacement)],
                   capture_output=True, check=True)
    after = subprocess.check_output([*base, '--password-file', str(replacement), 'snapshots', '--json'])
    assert json.loads(before) == json.loads(after)
    restored = tmp_path / 'restore'
    subprocess.run([*base, '--password-file', str(replacement), 'restore', 'latest', '--target', str(restored)],
                   capture_output=True, check=True)
    assert (restored / content.relative_to('/')).read_text() == content.read_text()
    text = (ROOT / 'docs/RUNBOOK-rotate.md').read_text().split('## 4. Restic password', 1)[1].split('## 5.', 1)[0]
    assert 'rm -rf' not in text
    assert 'distinct local `restic_repo_dir`' in text and 'distinct `backup.remote.rclone_path`' in text


@pytest.mark.parametrize('selected', ['configuration', 'document'])
def test_linked_authority_refuses_without_replacing_source(authority, selected):
    directory, recipients, _ = authority
    document = encrypted_file(directory, 'a.secrets.sops.yaml', recipients[0])
    if selected == 'document':
        source = document
    else:
        source = directory / '.sops.yaml'
        source.write_text(yaml.safe_dump({'creation_rules': [{'age': recipients[0]}]}))
        source.chmod(0o600)
    target = source.with_suffix('.original')
    source.rename(target)
    source.symlink_to(target)
    before = target.read_bytes()
    with pytest.raises(OSError):
        hardware.migrate(directory, recipients[2])
    assert source.is_symlink() and target.read_bytes() == before


@pytest.mark.parametrize('generate', [False, True])
def test_plugin_binds_exact_selection_and_keeps_setup_prompts_on_private_terminal(monkeypatch, tmp_path, generate):
    terminal = tmp_path / 'private-terminal'
    calls = []
    monkeypatch.setattr(hardware, 'operator_terminal', lambda: terminal.open('w+b'))

    def run(argv, **options):
        calls.append((argv, options))
        if generate:
            assert options['stdin'] is options['stderr']
            options['stderr'].write(b'synthetic PIN prompt')
        else:
            assert options['stderr'] == subprocess.PIPE
        return subprocess.CompletedProcess(argv, 0, stdout=identity_text())

    monkeypatch.setattr(subprocess, 'run', run)
    assert hardware.plugin_identity(1234, 2, generate) == identity_text()
    argv, options = calls[0]
    assert argv == ['age-plugin-yubikey', '--generate' if generate else '--identity', '--serial', '1234', '--slot', '2']
    assert '--force' not in argv and options['stdout'] == subprocess.PIPE
    assert terminal.read_bytes() == b'synthetic PIN prompt' if generate else not terminal.exists()
