"""Actual private inventory publication; Terraform rendering is isolated."""
from __future__ import annotations

from pathlib import Path

import device_migration_inventory as inventory
import pytest
from fleet_inspection import select_hosts
from test_device_migration_io import plan as plan  # noqa: PLC0414


@pytest.fixture(autouse=True)
def operator_key(plan, monkeypatch):
    monkeypatch.setenv('ANSIBLE_SSH_PRIVATE_KEY_FILE', str(Path(plan[0]['inventory']).parent / 'key'))


def setup(plan):
    document, _ = plan
    path = Path(document['inventory'])
    raw = path.read_text().replace('\n[vpn-test]\nnode-b\n', '').replace('[vpn-test]\nnode-a', '[vpn-test]\nnode-a\nnode-b')
    raw = raw.replace('[vpn-test]',
        'publisher provider=hetzner env=delivery ansible_host=100.64.0.9 vpn_service_address=192.0.2.9 '
        'ansible_user=deploy ansible_port=2202\n'
        'alternate provider=vultr env=alternate ansible_host=192.0.2.8 ansible_user=deploy ansible_port=22\n'
        '[vpn-delivery]\npublisher\n[vpn-p0-minimal]\nalternate\n[vpn-test]')
    path.write_text(raw)
    document['publication'].update(source_alias='publisher', target_alias='publisher')
    fresh = raw.replace('ansible_host=192.0.2.2', 'ansible_host=100.64.0.2 vpn_service_address=192.0.2.2')
    fresh = '\n'.join(line for line in fresh.splitlines() if not line.startswith(('publisher', 'alternate', '[vpn-delivery]', '[vpn-p0-minimal]'))) + '\n'
    return document, path, fresh


def test_pair_render_preserves_dedicated_publisher_and_alternate_exactly(plan, monkeypatch):
    document, path, fresh = setup(plan)
    before = select_hosts(path, ['publisher', 'alternate'], include_variables=True, include_cohorts=True)
    def run(argv, **kwargs):
        assert argv[0] == 'bash' and argv[1].endswith('/render-inventory.sh')
        Path(kwargs['environment']['INVENTORY_OUTPUT']).write_text(fresh)
        return 0, b'private rendering output'
    monkeypatch.setattr(inventory, 'run_command', run)
    inventory.render(document)
    after = select_hosts(path, ['publisher', 'alternate'], include_variables=True, include_cohorts=True)
    assert after == before
    assert select_hosts(path, ['node-b'])[0]['transport'] == '100.64.0.2'
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(path.parent.glob('.migration-inventory.*'))
    # The second ownership render preserves the same unrelated authority.
    inventory.render(document)
    assert select_hosts(path, ['publisher', 'alternate'], include_variables=True, include_cohorts=True) == before


@pytest.mark.parametrize('fault', ['failed-render', 'global-key', 'missing-target', 'unrelated-new-host', 'concurrent-edit'])
def test_refused_render_preserves_prior_or_concurrently_changed_inventory(plan, monkeypatch, fault):
    document, path, fresh = setup(plan)
    original = path.read_bytes()
    concurrent = original + b'# independent operator edit\n'
    def run(argv, **kwargs):
        candidate = fresh
        if fault == 'global-key':
            key = path.parent / 'other-key'
            key.write_text('synthetic other key')
            key.chmod(0o600)
            candidate = candidate.replace(str(path.parent / 'key'), str(key))
        elif fault == 'missing-target':
            candidate = '\n'.join(line for line in candidate.splitlines() if not line.startswith('node-b'))
        elif fault == 'unrelated-new-host':
            candidate = candidate.replace('[vpn]', '[vpn]\nnew-host ansible_host=192.0.2.7 ansible_user=deploy ansible_port=22')
        elif fault == 'concurrent-edit':
            path.write_bytes(concurrent)
        Path(kwargs['environment']['INVENTORY_OUTPUT']).write_text(candidate)
        return (1 if fault == 'failed-render' else 0), b''
    monkeypatch.setattr(inventory, 'run_command', run)
    with pytest.raises(Exception):
        inventory.render(document)
    assert path.read_bytes() == (concurrent if fault == 'concurrent-edit' else original)
    assert not list(path.parent.glob('.migration-inventory.*'))


def test_missing_dedicated_publisher_refuses_before_renderer(plan, monkeypatch):
    document, _, _ = setup(plan)
    document['publication'].update(source_alias='missing', target_alias='missing')
    def unexpected(*args, **kwargs):
        pytest.fail('renderer ran before publisher admission')
    monkeypatch.setattr(inventory, 'run_command', unexpected)
    with pytest.raises(ValueError, match='publisher-inventory-unavailable'):
        inventory.render(document)


def test_global_key_change_refuses_before_renderer(plan, monkeypatch):
    document, path, _ = setup(plan)
    original = path.read_bytes()
    monkeypatch.setenv('ANSIBLE_SSH_PRIVATE_KEY_FILE', '/different/reviewed/key')
    def unexpected(*args, **kwargs):
        pytest.fail('renderer ran with changed inherited SSH authority')
    monkeypatch.setattr(inventory, 'run_command', unexpected)
    with pytest.raises(ValueError, match='global-authority-changed'):
        inventory.render(document)
    assert path.read_bytes() == original
