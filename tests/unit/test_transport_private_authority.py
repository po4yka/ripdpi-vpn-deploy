"""ACL shape tests are unit evidence; actual systemd credentials have native coverage."""
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

import transport_private_authority as authority

ACTOR = 65534
ROOT = Path(__file__).resolve().parents[2]


def metadata(mode, uid=0, directory=False):
    return SimpleNamespace(st_mode=(stat.S_IFDIR if directory else stat.S_IFREG) | mode, st_uid=uid)


def acl(directory=False):
    permission = 5 if directory else 4
    return [(1, permission, 0xFFFFFFFF), (2, permission, ACTOR), (4, 0, 0xFFFFFFFF),
            (16, permission, 0xFFFFFFFF), (32, 0, 0xFFFFFFFF)]


@pytest.mark.parametrize('directory', [False, True])
def test_observed_systemd_acl_admits_only_root_and_exact_actor(directory):
    authority._private_acl(metadata(0o550 if directory else 0o440, directory=directory),
                           acl(directory), ACTOR, directory=directory)


@pytest.mark.parametrize('mutation', ['user', 'named_group', 'group_read', 'other_read', 'actor_write',
                                     'mask_write', 'duplicate', 'missing_mask', 'mode', 'foreign_owner'])
def test_credential_acl_never_extends_authority_to_another_reader_or_writer(mutation):
    entries = acl()
    info = metadata(0o440)
    if mutation == 'user':entries[1] = (2, 4, ACTOR-1)
    elif mutation == 'named_group':entries[1] = (8, 4, ACTOR)
    elif mutation == 'group_read':entries[2] = (4, 4, 0xFFFFFFFF)
    elif mutation == 'other_read':entries[-1] = (32, 4, 0xFFFFFFFF);info = metadata(0o444)
    elif mutation == 'actor_write':entries[1] = (2, 6, ACTOR)
    elif mutation == 'mask_write':entries[3] = (16, 6, 0xFFFFFFFF);info = metadata(0o460)
    elif mutation == 'duplicate':entries.append(entries[1])
    elif mutation == 'missing_mask':entries.pop(3)
    elif mutation == 'mode':info = metadata(0o400)
    else:info = metadata(0o440, uid=ACTOR-1)
    with pytest.raises(authority.PrivateAuthorityError, match='^unsafe-private-authority$'):
        authority._private_acl(info, entries, ACTOR)


def test_acl_decoder_uses_observed_linux_wire_shape(monkeypatch):
    encoded = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in acl())
    monkeypatch.setattr(os, 'getxattr', lambda *args, **kwargs: encoded, raising=False)
    assert authority._acl('/unused') == acl()
    for value in (b'', struct.pack('<I', 3), encoded+b'x', encoded+encoded):
        monkeypatch.setattr(os, 'getxattr', lambda *args, value=value, **kwargs: value, raising=False)
        with pytest.raises(authority.PrivateAuthorityError):authority._acl('/unused')


def test_unavailable_acl_api_refuses_categorically(monkeypatch):
    monkeypatch.delattr(os, 'getxattr', raising=False)
    with pytest.raises(authority.PrivateAuthorityError, match='^unsafe-private-authority$'):
        authority._acl('/unused')


def test_private_unit_directory_requires_exact_canonical_env_and_readonly_mount(monkeypatch):
    directory = Path('/run/credentials/owned-test.service')
    path = directory/'config'
    monkeypatch.setenv('CREDENTIALS_DIRECTORY', str(directory))
    monkeypatch.setattr(Path, 'resolve', lambda self, **kwargs: self)
    monkeypatch.setattr(Path, 'lstat', lambda self: metadata(0o550, directory=True) if self == directory else metadata(0o755, directory=True))
    monkeypatch.setattr(os, 'statvfs', lambda value: SimpleNamespace(f_flag=os.ST_RDONLY))
    monkeypatch.setattr(authority, '_acl', lambda value: acl(True))
    assert authority._credential_directory(path, ACTOR)
    assert not authority._credential_directory(Path('/run/credentials/another.service/config'), ACTOR)
    monkeypatch.setattr(os, 'statvfs', lambda value: SimpleNamespace(f_flag=0))
    with pytest.raises(authority.PrivateAuthorityError):authority._credential_directory(path, ACTOR)
    monkeypatch.setattr(os, 'statvfs', lambda value: SimpleNamespace(f_flag=os.ST_RDONLY))
    monkeypatch.setattr(authority, '_acl', lambda value: [(1, 5, 0xFFFFFFFF), (4, 0, 0xFFFFFFFF), (32, 0, 0xFFFFFFFF)])
    with pytest.raises(authority.PrivateAuthorityError):authority._credential_directory(path, ACTOR)
    monkeypatch.setenv('CREDENTIALS_DIRECTORY', '/tmp/owned-test.service')
    with pytest.raises(authority.PrivateAuthorityError):authority._credential_directory(Path('/tmp/owned-test.service/config'), ACTOR)


def test_plain_private_files_keep_the_original_strict_permission_contract(tmp_path, monkeypatch):
    monkeypatch.delenv('CREDENTIALS_DIRECTORY', raising=False)
    path = tmp_path/'private-config'
    path.write_bytes(b'synthetic-private-authority-marker');path.chmod(0o600)
    assert authority.read_private_file(path, max_bytes=128) == path.read_bytes()
    for mode in (0o640, 0o644, 0o660, 0o444):
        path.chmod(mode)
        with pytest.raises(authority.PrivateAuthorityError):authority.read_private_file(path, max_bytes=128)
    path.chmod(0o600)
    with pytest.raises(authority.PrivateAuthorityError):authority.read_private_file(path, max_bytes=2)
    linked = tmp_path/'linked'
    os.link(path, linked)
    with pytest.raises(authority.PrivateAuthorityError):authority.read_private_file(path, max_bytes=128)
    linked.unlink();linked.symlink_to(path)
    with pytest.raises(authority.PrivateAuthorityError):authority.read_private_file(linked, max_bytes=128)
    with pytest.raises(authority.PrivateAuthorityError):authority.read_private_file(tmp_path/'absent', max_bytes=128)


def test_nonregular_files_are_refused_without_waiting_for_fifo_input(tmp_path):
    fifo = tmp_path/'fifo'
    os.mkfifo(fifo, 0o600)
    with pytest.raises(authority.PrivateAuthorityError):authority.read_private_file(fifo, max_bytes=128)


def test_plain_group_readable_config_remains_redacted_in_actual_normalizer_cli(tmp_path):
    from test_transport_destination_boundary import config
    path = tmp_path/'config.json'
    candidate = config()
    marker = 'synthetic-private-authority-marker'
    candidate['listeners'][0]['password'] = marker+'0'*8
    path.write_text(json.dumps(candidate));path.chmod(0o640)
    result = subprocess.run([sys.executable, str(ROOT/'scripts/transport_egress_normalizer.py'),
                             '--validate', '--config', str(path)], capture_output=True, text=True)
    assert result.returncode == 1 and result.stdout == ''
    assert marker not in result.stderr and str(path) not in result.stderr
