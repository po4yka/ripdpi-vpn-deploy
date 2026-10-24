"""Real child refusals and closed readiness evidence; no Linux firewall claim."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_dhcpv6_receiver_contract import setup_branch_source

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'tests/native/transport_acceptance/test_dhcpv6.py'
spec = importlib.util.spec_from_file_location('readiness_native_controller', NATIVE)
native = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = native
spec.loader.exec_module(native)
PREFIX = 'dhcpv6-readiness:'


def encoded(stage='bind-join', mask=0):
    return PREFIX + json.dumps({'stage': stage, 'authority_mismatch': mask}) + '\n'


def test_actual_receiver_socket_setup_failure_is_classified_and_not_ready():
    result = subprocess.run([sys.executable, '-c', native.RECEIVER,
                             'not-a-real-device', '::', '547', 'yes'],
                            capture_output=True, text=True, timeout=3, check=False)
    assert result.returncode != 0 and not result.stdout
    assert native.readiness_record(result.stderr) == {'stage': 'bind-join', 'authority_mismatch': 0}


def test_closed_bind_join_record_has_not_applicable_mask():
    assert native.readiness_record('private stderr\n' + encoded('bind-join')) == {
        'stage': 'bind-join', 'authority_mismatch': 0}


@pytest.mark.parametrize('stage', ['start', 'read-deadline', 'oversize', 'exit', 'json',
                                  'authority', 'unknown', 'exit-network-unreachable',
                                  'exit-invalid-argument', 'exit-operation-not-permitted',
                                  'exit-permission-denied', 'exit-operation-not-supported', 'exit-protocol'])
def test_obsolete_route_readiness_stages_are_refused(stage):
    assert native.readiness_record(encoded(stage)) is None


@pytest.mark.parametrize('value', [
    {'stage': 'private-secret', 'authority_mismatch': 0},
    {'stage': 'authority', 'authority_mismatch': 0},
    {'stage': 'authority', 'authority_mismatch': 64},
    {'stage': 'authority', 'authority_mismatch': -1},
    {'stage': 'authority', 'authority_mismatch': True},
    {'stage': 'authority', 'authority_mismatch': 1.0},
    {'stage': 'authority', 'authority_mismatch': 'private-secret'},
    {'stage': 'bind-join', 'authority_mismatch': 1},
    {'stage': [], 'authority_mismatch': 0},
    {'stage': 'bind-join', 'authority_mismatch': 0, 'credential': 'private-secret'},
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
    assert native.readiness_record(bounded) == {'stage': 'bind-join', 'authority_mismatch': 0}
    assert native.readiness_record(bounded + ' ') is None


@pytest.mark.parametrize('child_exits', [True, False], ids=['exited', 'unreaped'])
@pytest.mark.parametrize('property_failure', [False, True])
@pytest.mark.parametrize('invalid_stderr', [False, True])
def test_actual_child_eof_keeps_original_ready_assert_and_never_launches_sender(
        monkeypatch, property_failure, invalid_stderr, child_exits):
    real_popen = subprocess.Popen
    children, properties = [], []

    def listener(*_args, **kwargs):
        program = ('import os;os.write(2,bytes([255]))' if invalid_stderr else
                   'import sys;sys.stderr.write(' + repr(encoded('bind-join')) + ')')
        # An unreaped receiver closes stdout but keeps running, so cleanup takes the kill path.
        ending = (';raise SystemExit(1)' if child_exits else
                  ';import os,sys,time;sys.stderr.flush();os.close(1);time.sleep(30)')
        child = real_popen([sys.executable, '-c',
                            program + ending],
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
        ('dhcpv6-readiness', {'stage': 'bind-join', 'authority_mismatch': 0})])


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


@pytest.mark.parametrize('changes', [
    {'bound': 'other0'}, {'join_error': True}, {'unreadable': True}, {'groups': ''},
    {'groups': '7 other0 ff020000000000000000000000010002 1 0\n'},
    {'groups': '7 peer0 ff020000000000000000000000000002 1 0\n'},
])
def test_actual_setup_refusal_keeps_sender_blocked_and_child_reaped(tmp_path, monkeypatch, changes):
    membership = tmp_path / 'igmp6'
    if not changes.get('unreadable'):
        membership.write_text(changes.get('groups', '7 peer0 ff020000000000000000000000010002 1 0\n'))
    source = setup_branch_source(membership, bound=changes.get('bound', 'peer0'),
                                 join_error=changes.get('join_error', False))
    real_popen = subprocess.Popen
    children, properties = [], []

    def listener(*_args, **kwargs):
        child = real_popen([sys.executable, '-c', source, 'peer0', 'yes'],
                           stdin=kwargs['stdin'], stdout=kwargs['stdout'],
                           stderr=kwargs['stderr'], text=kwargs['text'])
        children.append(child)
        return child

    def run(*args, **_kwargs):
        assert '-c' not in args, 'sender-launched-after-setup-refusal'
        return ''

    monkeypatch.setattr(native.subprocess, 'Popen', listener)
    monkeypatch.setattr(native, 'run', run)
    with pytest.raises(AssertionError, match='^dhcpv6-receiver-not-ready$'):
        native.packet('sender', 'receiver', source='fe80::10', target='ff02::1:2',
                      sport=546, dport=547, send_interface='up0', receive_interface='peer0',
                      observe_multicast=True,
                      record_property=lambda name, value: properties.append((name, json.loads(value))))
    assert children and all(child.poll() is not None for child in children)
    assert properties == [('dhcpv6-readiness', {'stage': 'bind-join', 'authority_mismatch': 0})]
