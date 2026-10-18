"""Exercise AWG unit inspection at the systemctl output boundary."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

FILES = Path(__file__).resolve().parents[2] / 'ansible/roles'


@pytest.fixture
def consumer(monkeypatch):
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    load('transport_runtime_transaction', FILES / 'runtime-release/files/transport_runtime_transaction.py')
    load('firewall_consumer', FILES / 'firewall/files/firewall_consumer.py')
    module = load('awg_unit_state_consumer', FILES / 'amneziawg/files/consumer.py')
    monkeypatch.setattr(module, 'record', lambda: {
        'schema': 1, 'config_dir': '/etc/amnezia/amneziawg', 'instances': [],
    })
    return module


def systemctl_output(consumer, monkeypatch, selected, stdout, returncode=0):
    def run(argv, **kwargs):
        assert argv == ['systemctl', 'show', selected, '--property=LoadState,ActiveState,UnitFileState,MainPID']
        assert kwargs == {'stdout': consumer.subprocess.PIPE, 'stderr': consumer.subprocess.PIPE,
                          'timeout': 30, 'check': False}
        return SimpleNamespace(returncode=returncode, stdout=stdout.encode(), stderr=b'')

    monkeypatch.setattr(consumer.subprocess, 'run', run)


@pytest.mark.parametrize(('load', 'active', 'enabled', 'returncode'), [
    ('loaded', 'active', 'enabled', 0),
    ('loaded', 'inactive', 'disabled', 0),
    ('not-found', 'inactive', '', 1),
])
def test_target_without_service_pid_is_valid(consumer, monkeypatch, load, active, enabled, returncode):
    systemctl_output(consumer, monkeypatch, 'awg-quick.target',
                     f'LoadState={load}\nActiveState={active}\nUnitFileState={enabled}\n', returncode)
    actual = consumer.fields('awg-quick.target')
    assert actual == {'LoadState': load, 'ActiveState': active, 'UnitFileState': enabled, 'MainPID': '0'}
    consumer.Adapter().validate_units({'awg-quick.target': actual})


@pytest.mark.parametrize('selected', ['awg-quick@a0.service', 'other.target'])
def test_missing_pid_remains_invalid_outside_exact_awg_target(consumer, monkeypatch, selected):
    systemctl_output(consumer, monkeypatch, selected,
                     'LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n')
    with pytest.raises(consumer.Refusal, match='awg-unit-state-invalid'):
        consumer.fields(selected)


def test_service_retains_reported_pid(consumer, monkeypatch):
    systemctl_output(consumer, monkeypatch, 'awg-quick@a0.service',
                     'LoadState=loaded\nActiveState=active\nUnitFileState=enabled\nMainPID=1234\n')
    actual = consumer.fields('awg-quick@a0.service')
    assert actual['MainPID'] == '1234'
    consumer.Adapter().validate_units({'awg-quick@a0.service': actual})


@pytest.mark.parametrize(('stdout', 'returncode'), [
    ('LoadState=loaded\nUnitFileState=disabled\n', 0),
    ('LoadState=loaded\nActiveState=inactive\nUnitFileState=disabled\nUnexpected=1\n', 0),
    ('LoadState=loaded\nActiveState=inactive\nUnitFileState=disabled\n', 1),
])
def test_target_still_requires_complete_successful_unit_response(consumer, monkeypatch, stdout, returncode):
    systemctl_output(consumer, monkeypatch, 'awg-quick.target', stdout, returncode)
    with pytest.raises(consumer.Refusal, match='awg-unit-state-invalid'):
        consumer.fields('awg-quick.target')


@pytest.mark.parametrize(('field', 'value'), [
    ('LoadState', 'error'), ('ActiveState', 'activating'),
    ('UnitFileState', 'masked'), ('MainPID', '-1'),
])
def test_target_state_values_remain_strict(consumer, monkeypatch, field, value):
    values = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'UnitFileState': 'disabled'}
    values[field] = value
    systemctl_output(consumer, monkeypatch, 'awg-quick.target',
                     ''.join(f'{key}={item}\n' for key, item in values.items()))
    with pytest.raises(consumer.Refusal, match='awg-unit-state-invalid'):
        consumer.Adapter().validate_units({'awg-quick.target': consumer.fields('awg-quick.target')})
