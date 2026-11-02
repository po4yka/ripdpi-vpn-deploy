"""Native failures retain only bounded categories after private fixture cleanup."""
import importlib.util
import hashlib
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('runtime_fixture_categories_test',
    ROOT / 'tests/integration/transport_runtime_acceptance/fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_rebuilt_hysteria_cache_uses_immutable_release_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(fixture, 'ARCH', 'amd64')
    monkeypatch.setattr(fixture, 'XRAY_PINS', {})
    monkeypatch.setattr(fixture, 'HYSTERIA_PINS', {'v2.13.0': hashlib.sha256(b'rebuilt').hexdigest()})
    cache = tmp_path / 'amd64'
    cache.mkdir()
    (cache / 'hysteria-v2.13.0-go1.27.3').write_bytes(b'rebuilt')
    (cache / 'hysteria-v2.13.0').write_bytes(b'old-upstream-binary')
    def no_download(*args, **kwargs):
        raise AssertionError('the admitted rebuilt bytes must be reused')
    monkeypatch.setattr(fixture, 'command', no_download)
    assert fixture.artifacts(tmp_path) == cache
    assert (cache / 'hysteria-v2.13.0-go1.27.3').stat().st_mode & 0o777 == 0o755


def test_owned_canary_bind_never_requires_reverse_dns(monkeypatch):
    spec = importlib.util.spec_from_file_location('owned_canary_bind_test',
        ROOT / 'tests/integration/transport_runtime_acceptance/molecule_canary.py')
    canary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canary)
    def refuse_dns(*_args):
        raise AssertionError('owned numeric canary attempted reverse DNS')
    monkeypatch.setattr(socket, 'getfqdn', refuse_dns)
    with canary.CanaryServer(('127.0.0.1', 0), canary.Canary) as server:
        assert server.server_name == '127.0.0.1'
        assert server.server_port > 0


def test_failure_diagnostics_exclude_private_result_payload(tmp_path):
    lab = fixture.Lab.__new__(fixture.Lab)
    lab.log = tmp_path/'ansible.log'
    lab.log.write_text('TASK [hysteria : Report only bounded categorical consumer refusal] ***\n'
        'fatal: [localhost]: FAILED! => {"private":"synthetic-private-password",'
        '"msg":["transport-runtime-refused:native-command-refused",'
        '"transport-runtime-frame:validate_hysteria:87"]}\n')
    result = lab.failure_categories()
    assert result['categories'] == ['transport-runtime-refused:native-command-refused',
                                    'transport-runtime-frame:validate_hysteria:87']
    assert result['failed_tasks'] == ['hysteria : Report only bounded categorical consumer refusal']
    assert result['last_task'] == 'hysteria : Report only bounded categorical consumer refusal'
    assert 'synthetic-private-password' not in str(result)


def test_failure_diagnostics_are_bounded(tmp_path):
    lab = fixture.Lab.__new__(fixture.Lab)
    lab.log = tmp_path/'ansible.log'
    lab.log.write_text('\n'.join('transport-runtime-frame:ready:1' for _ in range(100)))
    assert len(lab.failure_categories()['categories']) == 9


def test_native_lab_origin_is_admitted_without_hidden_normalization():
    from transport_semantics import origin_valid
    assert origin_valid(fixture.OWNED_ORIGIN)


@pytest.mark.parametrize('failed', [False, True])
def test_retirement_forgets_only_stopped_owned_unit_failures(monkeypatch, failed):
    events = []
    state = {'LoadState': 'error' if failed else 'not-found',
             'ActiveState': 'failed' if failed else 'inactive', 'MainPID': '0'}

    def command(argv):
        events.append(argv)
        if argv[1] == 'show':
            assert argv[2] == 'owned.service'
            return '\n'.join(key + '=' + value for key, value in state.items())
        if argv[1] == 'reset-failed':
            assert argv[2] == 'owned.service'
            state.update(LoadState='not-found', ActiveState='inactive')
        return ''

    monkeypatch.setattr(fixture, 'command', command)
    fixture.forget_retired_units(('owned.service',))
    assert [row[1] for row in events] == (
        ['show', 'reset-failed', 'daemon-reload', 'show'] if failed
        else ['show', 'daemon-reload', 'show'])


@pytest.mark.parametrize('state', [
    {'LoadState': 'loaded', 'ActiveState': 'active', 'MainPID': '12'},
    {'LoadState': 'loaded', 'ActiveState': 'inactive', 'MainPID': '12'},
    {'LoadState': 'error', 'ActiveState': 'activating', 'MainPID': '0'},
    {'LoadState': 'masked', 'ActiveState': 'failed', 'MainPID': '0'},
])
def test_retirement_refuses_unconfirmed_stop_without_reset(monkeypatch, state):
    events = []

    def command(argv):
        events.append(argv)
        return '\n'.join(key + '=' + value for key, value in state.items())

    monkeypatch.setattr(fixture, 'command', command)
    with pytest.raises(RuntimeError, match='native-fixture-unit-retirement-unconfirmed'):
        fixture.forget_retired_units(('owned.service',))
    assert [row[1] for row in events] == ['show']


@pytest.mark.parametrize('reset_refused', [False, True])
def test_retirement_requires_confirmed_absence_after_reset(monkeypatch, reset_refused):
    events = []

    def command(argv):
        events.append(argv)
        if argv[1] == 'reset-failed' and reset_refused:
            raise RuntimeError('reset-refused')
        return 'LoadState=error\nActiveState=failed\nMainPID=0\n'

    monkeypatch.setattr(fixture, 'command', command)
    with pytest.raises(RuntimeError, match=(
            'reset-refused' if reset_refused else 'native-fixture-unit-retirement-unconfirmed')):
        fixture.forget_retired_units(('owned.service',))
    assert [row[1] for row in events] == (
        ['show', 'reset-failed'] if reset_refused
        else ['show', 'reset-failed', 'daemon-reload', 'show'])
