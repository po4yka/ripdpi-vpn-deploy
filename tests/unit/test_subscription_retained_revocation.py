"""Retained publisher admission and unchanged-process HTTP revocation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from jinja2 import Environment
import pytest
import yaml

from test_subscription_document import delivery, envelope
from test_subscription_retention import service as service  # noqa: PLC0414

ROLE = Path(__file__).resolve().parents[2] / 'ansible/roles/subscription-host'
TASKS = yaml.safe_load((ROLE / 'tasks/revoke-grants.yml').read_text())
ADMISSION = next(task for task in TASKS if task['name'].startswith('Admit retained'))
PUBLICATION = yaml.safe_load((ROLE / 'tasks/revoked-hashes.yml').read_text())[0]


def admit(service, tokens, **overrides):
    source = ADMISSION['ansible.builtin.command']['argv'][-1]
    # Test the shipped admission program against the rendered installed helper.
    source = source.replace("'/usr/local/bin/vpn-bootstrap.py'", repr(service.__file__))
    request = {'directory': str(service.SUBSCRIPTION_DIR), 'revoked_file': str(service.REVOKED_FILE),
               'revoked_tokens': tokens} | overrides
    return subprocess.run([sys.executable, '-I', '-B', '-S', '-c', source],
                          input=json.dumps(request).encode(), capture_output=True, timeout=10, check=False)


def publish(service, tokens):
    task = PUBLICATION['ansible.builtin.copy']
    content = Environment().from_string(task['content']).render(subscription={'revoked_tokens': tokens})
    replacement = service.REVOKED_FILE.with_suffix('.next')
    replacement.write_text(content)
    replacement.chmod(int(task['mode'], 8))
    os.replace(replacement, service.REVOKED_FILE)


def test_shared_denylist_changes_real_running_reader_without_restart(service):
    preserved = service._hash('already-revoked-grant')
    publish(service, [preserved])
    with delivery(service) as (token, get):
        service._publish_subscription(token, envelope(b'{"owned":"payload"}'))
        assert get() == (200, b'{"owned":"payload"}')
        admitted = admit(service, [preserved, token])
        assert admitted.returncode == 0, admitted.stderr
        assert admitted.stdout == b'retained-publisher-authority-v1\n'
        publish(service, [preserved, token])
        assert get()[0] == 410
        assert service._migration_revocations() == {preserved, token}
        assert admit(service, [preserved, token]).returncode == 0


@pytest.mark.parametrize('invalid', ['missing-lock', 'missing-denylist', 'symlink-denylist',
                                   'malformed-denylist', 'remove-existing', 'invalid-new-hash',
                                   'different-namespace', 'different-denylist'])
def test_retained_authority_refuses_before_denylist_publication(service, tmp_path, invalid):
    retained = service._hash('already-revoked-grant')
    publish(service, [retained])
    desired, overrides = [retained, service._hash('new-revocation')], {}
    if invalid == 'missing-lock':
        (service.SUBSCRIPTION_DIR / service.STATE_LOCK_NAME).unlink()
    elif invalid == 'missing-denylist':
        service.REVOKED_FILE.unlink()
    elif invalid == 'symlink-denylist':
        alternate = tmp_path / 'alternate'
        alternate.write_bytes(service.REVOKED_FILE.read_bytes())
        alternate.chmod(0o600)
        service.REVOKED_FILE.unlink()
        service.REVOKED_FILE.symlink_to(alternate)
    elif invalid == 'malformed-denylist':
        service.REVOKED_FILE.write_text('invalid\n')
    elif invalid == 'remove-existing':
        desired = []
    elif invalid == 'invalid-new-hash':
        desired.append('invalid')
    elif invalid == 'different-namespace':
        overrides['directory'] = str(tmp_path)
    else:
        overrides['revoked_file'] = str(tmp_path / 'elsewhere')
    before = service.REVOKED_FILE.read_bytes() if service.REVOKED_FILE.exists() else None
    result = admit(service, desired, **overrides)
    assert result.returncode == 2
    assert result.stdout == b''
    assert result.stderr == b'retained-publisher-authority-refused\n'
    assert (service.REVOKED_FILE.read_bytes() if service.REVOKED_FILE.exists() else None) == before
    assert retained.encode() not in result.stderr


def test_retained_task_has_no_runtime_activation_and_shares_normal_publication():
    normal = yaml.safe_load((ROLE / 'tasks/enable.yml').read_text())
    assert any(task.get('ansible.builtin.import_tasks') == 'revoked-hashes.yml' for task in normal)
    assert TASKS[-1]['ansible.builtin.import_tasks'] == 'revoked-hashes.yml'
    assert all(not any(key in task for key in ('ansible.builtin.systemd_service', 'ansible.builtin.template',
                                             'ansible.builtin.apt', 'ansible.builtin.service')) for task in TASKS)
    assert ADMISSION['check_mode'] is False and ADMISSION['no_log'] is True and ADMISSION['diff'] is False
    assert ADMISSION['become_user'] == 'vpn-bootstrap'
    assert PUBLICATION['no_log'] is True and PUBLICATION['diff'] is False
    assert PUBLICATION['ansible.builtin.copy']['mode'] == '0600'
    guards = [task['ansible.builtin.assert']['that'] for task in TASKS if 'ansible.builtin.assert' in task]
    assert 'vpn_device_retained_publisher is boolean' in guards[0]
    assert any('MainPID=[1-9]' in str(guard) for guard in guards)
