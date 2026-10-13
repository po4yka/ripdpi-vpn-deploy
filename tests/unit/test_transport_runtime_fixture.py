"""Native failures retain only bounded categories after private fixture cleanup."""
import importlib.util
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('runtime_fixture_categories_test',
    ROOT / 'tests/integration/transport_runtime_acceptance/fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


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
    assert 'synthetic-private-password' not in str(result)


def test_failure_diagnostics_are_bounded(tmp_path):
    lab = fixture.Lab.__new__(fixture.Lab)
    lab.log = tmp_path/'ansible.log'
    lab.log.write_text('\n'.join('transport-runtime-frame:ready:1' for _ in range(100)))
    assert len(lab.failure_categories()['categories']) == 9
