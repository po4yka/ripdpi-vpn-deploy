"""Console lease authority and policy normalization, never live proof."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def guest():
    spec = importlib.util.spec_from_file_location('console_guest', ROOT/'scripts/console_bootstrap_guest.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def request_data():
    return {'schema_version': 1, 'nonce': 'a'*32, 'hostname': 'node-one',
            'root_filesystem_uuid': '00000000-0000-0000-0000-000000000001',
            'host_key_sha256': 'b'*64, 'inventory_alias': 'node-one',
            'public_address': '192.0.2.10', 'ssh_port': 22,
            'public_sources': ['198.51.100.10'], 'source_revision': 'c'*40,
            'deployable_digest': 'd'*64, 'expires_at': int(time.time())+600}


def test_exact_source_bounded_lease(guest, request_data):
    guest.validate(request_data)
    rule = guest.rule(request_data, request_data['public_sources'][0])
    assert 'ip saddr 198.51.100.10 tcp dport 22' in rule
    assert 'vpn-console-lease:'+request_data['nonce'] in rule
    assert 'flush' not in rule


@pytest.mark.parametrize('change', [
    {'expires_at': 1}, {'expires_at': int(time.time())+1200},
    {'ssh_port': True}, {'ssh_port': 0}, {'public_sources': ['0.0.0.0']},
    {'public_sources': ['198.51.100.10/32']}, {'public_sources': ['198.51.100.10']*2},
    {'source_revision': 'wrong'}, {'nonce': 'wrong'}, {'schema_version': True},
])
def test_invalid_authority_refuses(guest, request_data, change):
    with pytest.raises((guest.Refusal, ValueError)):
        guest.validate({**request_data, **change})


def test_normalization_preserves_quota_and_expressions(guest):
    document = {'nftables': [{'metainfo': {'version': 'test'}},
                           {'rule': {'handle': 3, 'expr': [{'counter': {'packets': 4, 'bytes': 5}},
                                                         {'quota': {'bytes': 1024}}, {'accept': None}]}}]}
    value = guest.normalized(document)
    assert value == [{'rule': {'expr': [{'counter': {}}, {'quota': {'bytes': 1024}}, {'accept': None}]}}]


def test_renderer_and_guest_are_syntax_valid():
    for name in ['render-console-bootstrap.py', 'console_bootstrap_guest.py']:
        ast.parse((ROOT/'scripts'/name).read_text())


def test_make_renderer_rejects_other_capabilities():
    result = subprocess.run(['make', '-n', 'render-console-bootstrap', 'ANSIBLE_LIMIT=all'],
                            cwd=ROOT, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert b'accepts only CONSOLE_BOOTSTRAP_CONFIG' in result.stderr


def lease_rule(request, address, handle):
    return {'family': 'inet', 'table': 'filter', 'chain': 'input', 'handle': handle,
            'comment': 'vpn-console-lease:'+request['nonce'],
            'expr': [{'match': {'op': '==', 'left': {'payload': {'protocol': 'ip6' if ':' in address else 'ip', 'field': 'saddr'}}, 'right': address}},
                     {'match': {'op': '==', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}}, 'right': request['ssh_port']}},
                     {'counter': {'packets': 4, 'bytes': 20}}, {'accept': None}]}


def test_retirement_validates_all_rules_before_atomic_write(guest, request_data, monkeypatch):
    request_data['public_sources'].append('198.51.100.11')
    rules = [lease_rule(request_data, address, index+1) for index, address in enumerate(request_data['public_sources'])]
    rules[-1]['expr'][-1] = {'drop': None}
    from contextlib import nullcontext
    monkeypatch.setattr(guest, 'coordination_lock', nullcontext)
    mutations = []
    monkeypatch.setattr(guest, 'private_read', lambda _: json.dumps({'request': request_data}).encode())
    def run(argv, *, payload=None):
        if payload is not None:
            mutations.append(payload)
        return json.dumps({'nftables': [{'rule': row} for row in rules]}).encode()
    monkeypatch.setattr(guest, 'command', run)
    with pytest.raises(guest.Refusal, match='rule-drift'):
        guest.revoke()
    assert mutations == []


def test_retirement_deletes_exact_nonce_rules_in_one_batch(guest, request_data, monkeypatch):
    request_data['public_sources'].append('2001:db8::11')
    rules = [lease_rule(request_data, address, index+1) for index, address in enumerate(request_data['public_sources'])]
    foreign = lease_rule(request_data, request_data['public_sources'][0], 10)
    foreign['comment'] = 'another-owner'
    from contextlib import nullcontext
    monkeypatch.setattr(guest, 'coordination_lock', nullcontext)
    mutations = []
    monkeypatch.setattr(guest, 'private_read', lambda _: json.dumps({'request': request_data}).encode())
    def run(argv, *, payload=None):
        if payload is not None:
            mutations.append((argv, payload))
            return b''
        return json.dumps({'nftables': [{'rule': row} for row in [*rules, foreign]]}).encode()
    monkeypatch.setattr(guest, 'command', run)
    guest.revoke()
    assert mutations == [(['nft', '-f', '-'], b'delete rule inet filter input handle 1\ndelete rule inet filter input handle 2\n')]


def test_retirement_after_candidate_replacement_is_idempotent(guest, request_data, monkeypatch):
    from contextlib import nullcontext
    monkeypatch.setattr(guest, 'coordination_lock', nullcontext)
    calls = []
    monkeypatch.setattr(guest, 'private_read', lambda _: json.dumps({'request': request_data}).encode())
    def run(argv, *, payload=None):
        calls.append((argv, payload))
        return b'{"nftables": []}'
    monkeypatch.setattr(guest, 'command', run)
    guest.revoke()
    assert len(calls) == 1
    assert calls[0][1] is None


def test_shared_systemd_directories_are_not_made_private(guest, tmp_path, monkeypatch):
    import os
    import stat
    path = tmp_path/'systemd'
    path.mkdir(mode=0o755)
    path.chmod(0o755)
    real_lstat = guest.Path.lstat
    def root_owner(value):
        original = real_lstat(value)
        return os.stat_result((original.st_mode, original.st_ino, original.st_dev, original.st_nlink, 0, original.st_gid,
                               original.st_size, original.st_atime, original.st_mtime, original.st_ctime))
    monkeypatch.setattr(guest.Path, 'lstat', root_owner)
    guest.safe_directory(path, 0o755, create=True)
    assert stat.S_IMODE(real_lstat(path).st_mode) == 0o755
    path.chmod(0o700)
    with pytest.raises(guest.Refusal, match='directory-refused'):
        guest.safe_directory(path, 0o755, create=True)
    assert stat.S_IMODE(real_lstat(path).st_mode) == 0o700
