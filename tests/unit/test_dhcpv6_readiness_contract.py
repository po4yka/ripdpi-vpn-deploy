"""Real child refusals and closed readiness evidence; no Linux firewall claim."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_dhcpv6_receiver_contract import execute_input_admission, input_route

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'tests/native/transport_acceptance/test_dhcpv6.py'
spec = importlib.util.spec_from_file_location('readiness_native_controller', NATIVE)
native = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = native
spec.loader.exec_module(native)
PREFIX = 'dhcpv6-readiness:'


def encoded(stage='start', mask=0):
    return PREFIX + json.dumps({'stage': stage, 'authority_mismatch': mask}) + '\n'


@pytest.mark.parametrize('body,stage', [
    ('sys.exit(2)', 'exit'), ('print("private-secret")', 'json'),
    ('os.write(1,b"x"*4097)', 'oversize'), ('time.sleep(10)', 'read-deadline'),
])
def test_actual_route_child_refusal_has_only_closed_category(tmp_path, body, stage):
    result, _ = execute_input_admission(tmp_path, body)
    assert result.returncode != 0
    assert native.readiness_record(result.stderr) == {'stage': stage, 'authority_mismatch': 0}
    assert result.stdout == ''


def test_actual_missing_route_command_is_classified(tmp_path):
    result, _ = execute_input_admission(tmp_path, 'pass', available=False)
    assert native.readiness_record(result.stderr) == {'stage': 'start', 'authority_mismatch': 0}


@pytest.mark.parametrize('field,bit', [('type', 1), ('dev', 2), ('iif', 4),
                                     ('table', 8), ('dst', 16), ('from', 32)])
def test_actual_authority_mismatch_reports_only_exact_field_bit(tmp_path, field, bit):
    route = input_route()
    route[0][field] = 'private-secret'
    result, _ = execute_input_admission(tmp_path, 'print(' + repr(json.dumps(route)) + ')')
    assert native.readiness_record(result.stderr) == {'stage': 'authority', 'authority_mismatch': bit}
    assert 'private-secret' not in result.stderr


def test_actual_receiver_socket_setup_failure_is_classified_and_not_ready():
    result = subprocess.run([sys.executable, '-c', native.RECEIVER,
                             'not-a-real-device', '::', '547', 'yes'],
                            capture_output=True, text=True, timeout=3, check=False)
    assert result.returncode != 0 and not result.stdout
    assert native.readiness_record(result.stderr) == {'stage': 'bind-join', 'authority_mismatch': 0}


@pytest.mark.parametrize('stage', ['start', 'read-deadline', 'oversize', 'exit',
                                  'json', 'bind-join', 'unknown'])
def test_closed_non_authority_record_has_not_applicable_mask(stage):
    assert native.readiness_record('private stderr\n' + encoded(stage)) == {
        'stage': stage, 'authority_mismatch': 0}


@pytest.mark.parametrize('mask', [1, 63])
def test_authority_mask_accepts_exact_bounds(mask):
    assert native.readiness_record(encoded('authority', mask)) == {
        'stage': 'authority', 'authority_mismatch': mask}


@pytest.mark.parametrize('value', [
    {'stage': 'private-secret', 'authority_mismatch': 0},
    {'stage': 'authority', 'authority_mismatch': 0},
    {'stage': 'authority', 'authority_mismatch': 64},
    {'stage': 'authority', 'authority_mismatch': -1},
    {'stage': 'authority', 'authority_mismatch': True},
    {'stage': 'authority', 'authority_mismatch': 1.0},
    {'stage': 'authority', 'authority_mismatch': 'private-secret'},
    {'stage': 'start', 'authority_mismatch': 1},
    {'stage': [], 'authority_mismatch': 0},
    {'stage': 'start', 'authority_mismatch': 0, 'credential': 'private-secret'},
])
def test_unknown_values_or_fields_are_refused(value):
    assert native.readiness_record(PREFIX + json.dumps(value)) is None


@pytest.mark.parametrize('body', [
    PREFIX + 'broken', PREFIX + '[]', PREFIX + 'x' * 256,
    PREFIX + '{"stage":"private-secret","stage":"start","authority_mismatch":0}',
    encoded() * 2, 'private-secret' * 1000,
    '\ud800',
])
def test_malformed_duplicate_or_oversized_marker_is_refused(body):
    assert native.readiness_record(body) is None


def test_marker_byte_cap_is_exact():
    marker = encoded().rstrip('\n')
    bounded = marker + ' ' * (256 - len(marker.encode()))
    assert native.readiness_record(bounded) == {'stage': 'start', 'authority_mismatch': 0}
    assert native.readiness_record(bounded + ' ') is None


def test_actual_combined_authority_mask_has_all_six_bits(tmp_path):
    route = [{key: 'private-secret' for key in input_route()[0]}]
    result, _ = execute_input_admission(tmp_path, 'print(' + repr(json.dumps(route)) + ')')
    assert native.readiness_record(result.stderr) == {'stage': 'authority', 'authority_mismatch': 63}
    assert 'private-secret' not in result.stderr


@pytest.mark.parametrize('property_failure', [False, True])
@pytest.mark.parametrize('invalid_stderr', [False, True])
def test_actual_child_eof_keeps_original_ready_assert_and_never_launches_sender(monkeypatch, property_failure, invalid_stderr):
    real_popen = subprocess.Popen
    children, properties = [], []

    def listener(*_args, **kwargs):
        program = ('import os;os.write(2,bytes([255]))' if invalid_stderr else
                   'import sys;sys.stderr.write(' + repr(encoded('exit')) + ')')
        child = real_popen([sys.executable, '-c',
                            program + ';raise SystemExit(1)'],
                           stdin=kwargs['stdin'], stdout=kwargs['stdout'],
                           stderr=kwargs['stderr'], text=kwargs['text'])
        children.append(child)
        return child

    def run(*args, **_kwargs):
        assert '-c' not in args, 'sender-launched-after-readiness-refusal'
        return ''

    def record_property(name, value):
        if property_failure:
            raise ValueError('private-property-error')
        properties.append((name, json.loads(value)))

    monkeypatch.setattr(native.subprocess, 'Popen', listener)
    monkeypatch.setattr(native, 'run', run)
    with pytest.raises(AssertionError, match='^dhcpv6-receiver-not-ready$'):
        native.packet('sender', 'receiver', source='fe80::10', target='ff02::1:2',
                      sport=546, dport=547, send_interface='up0', receive_interface='peer0',
                      observe_multicast=True, record_property=record_property)
    assert children and all(child.poll() is not None for child in children)
    assert properties == ([] if property_failure or invalid_stderr else [
        ('dhcpv6-readiness', {'stage': 'exit', 'authority_mismatch': 0})])


def test_only_original_multicast_case_attaches_readiness_property():
    tree = ast.parse(NATIVE.read_text())
    cases = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
    attached = [(case.name, call) for case in cases for call in ast.walk(case)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == 'packet' and any(key.arg == 'record_property' for key in call.keywords)]
    assert len(attached) == 1
    name, call = attached[0]
    assert name == 'test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server'
    assert any(key.arg == 'observe_multicast' and ast.literal_eval(key.value) is True for key in call.keywords)
