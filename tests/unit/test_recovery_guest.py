"""Recovery adapter with real encrypted migration and local publisher transactions."""
from __future__ import annotations

import json
import sys

import device_migration
import device_migration_io
import recovery_guest
from device_migration_errors import MigrationRefused
from test_device_migration import authorities as authorities  # noqa: PLC0414
from test_device_migration import migration as migration  # noqa: PLC0414
from test_device_migration import prepare, signed_receipt
from test_device_migration import service as service  # noqa: PLC0414


def bind_guest(instance, monkeypatch):
    plan = instance.plan
    manifest = {'environment': plan['target']['host'].split(':')[1],
                'sops_file': plan['target']['secrets_file'], 'known_hosts_file': plan['known_hosts'],
                'migration_plan': '/synthetic/migration.json'}
    monkeypatch.setattr(recovery_guest, 'load_manifest', lambda _: manifest)
    monkeypatch.setattr(device_migration_io, 'load_plan', lambda _: plan)
    monkeypatch.setattr(device_migration_io, 'LocalIO', lambda _: instance.io)
    monkeypatch.setattr(device_migration, 'Migration', lambda _plan, _io: instance)
    monkeypatch.setattr(sys, 'argv', ['recovery_guest', '--manifest', '/synthetic/recovery.json', '--action', 'ready'])


def test_real_migration_acceptance_maps_only_missing_device_evidence_to_pending(migration, monkeypatch, capsys):
    instance = prepare(migration)
    _, token, _ = migration
    instance.publish()
    bind_guest(instance, monkeypatch)
    assert recovery_guest.main() == 0
    result = capsys.readouterr()
    assert json.loads(result.out) == {'ready': False, 'reason': 'device-path-evidence-incomplete'}
    assert not result.err
    instance.evidence(signed_receipt(instance, token))
    assert recovery_guest.main() == 0
    result = capsys.readouterr()
    assert json.loads(result.out)['ready'] is True
    assert not result.err
    def changed_authority():
        raise MigrationRefused('source-authority-changed')
    monkeypatch.setattr(instance, 'ready', changed_authority)
    assert recovery_guest.main() == 2
    result = capsys.readouterr()
    assert result.out == '' and result.err.strip() == 'replacement-verification-unavailable'
