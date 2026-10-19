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



@pytest.mark.parametrize('error,stage', [
    (b'RTNETLINK answers: Network is unreachable\n', 'exit-network-unreachable'),
    (b'RTNETLINK answers: Invalid argument\n', 'exit-invalid-argument'),
    (b'RTNETLINK answers: Operation not permitted\n', 'exit-operation-not-permitted'),
    (b'RTNETLINK answers: Permission denied\n', 'exit-permission-denied'),
    (b'RTNETLINK answers: Operation not supported\n', 'exit-operation-not-supported'),
    (b'Error: argument "udp" is wrong: Invalid "ipproto" value\n\n', 'exit-protocol'),
])
def test_actual_route_exit_keeps_only_exact_known_stderr_category(tmp_path, error, stage):
    result, _ = execute_input_admission(tmp_path, 'os.write(2,' + repr(error) + ');sys.exit(2)')
    assert native.readiness_record(result.stderr) == {'stage': stage, 'authority_mismatch': 0}
    assert error.decode().strip() not in result.stderr


@pytest.mark.parametrize('error', [
    b'RTNETLINK answers: Network is unreachable\nprivate-secret',
    b'private-secret\nRTNETLINK answers: Network is unreachable\n',
    b'RTNETLINK answers: Network is unreachable\n' * 2,
    b'RTNETLINK answers: private-secret\n', b'\xff', b'',
])
def test_actual_unknown_or_modified_stderr_remains_unclassified_private_exit(tmp_path, error):
    result, _ = execute_input_admission(tmp_path, 'os.write(2,' + repr(error) + ');sys.exit(2)')
    assert native.readiness_record(result.stderr) == {'stage': 'exit', 'authority_mismatch': 0}
    assert 'private-secret' not in result.stderr


@pytest.mark.parametrize('size,stage', [(4096, 'exit'), (4097, 'oversize')])
def test_actual_route_stderr_shares_the_original_total_output_cap(tmp_path, size, stage):
    body = "os.write(1,b'x'*2000);os.write(2,b'y'*" + str(size - 2000) + ");sys.exit(2)"
    result, _ = execute_input_admission(tmp_path, body)
    assert native.readiness_record(result.stderr) == {'stage': stage, 'authority_mismatch': 0}



@pytest.mark.parametrize('size,accepted', [(4096, True), (4097, False)])
def test_successful_route_stderr_cannot_bypass_combined_cap_or_leak(tmp_path, size, accepted):
    document = json.dumps(input_route()).encode()
    body = 'os.write(1,' + repr(document) + ");os.write(2,b'x'*" + str(size - len(document)) + ')'
    result, _ = execute_input_admission(tmp_path, body)
    assert (result.returncode == 0) is accepted
    if accepted:
        assert result.stdout == 'ready\n' and result.stderr == ''
    else:
        assert native.readiness_record(result.stderr) == {'stage': 'oversize', 'authority_mismatch': 0}


@pytest.mark.parametrize('body', [
    "os.write(2,b'x');time.sleep(10)",
    "while True:os.write(2,b'x'*1024)",
    "os.close(1);os.write(2,b'x');time.sleep(10)",
])
def test_actual_stderr_writer_keeps_original_deadline_and_is_reaped(tmp_path, body):
    result, _ = execute_input_admission(tmp_path, body)
    assert native.readiness_record(result.stderr)['stage'] in {'read-deadline', 'oversize'}


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
                                  'json', 'bind-join', 'unknown', 'exit-network-unreachable',
                                  'exit-invalid-argument', 'exit-operation-not-permitted',
                                  'exit-permission-denied', 'exit-operation-not-supported', 'exit-protocol'])
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


@pytest.mark.parametrize('body,status', [
    ("sys.stderr.write('private-refusal');sys.exit(71)", 71),
    ('os.kill(os.getpid(),15)', -15),
])
def test_real_route_child_status_does_not_capture_unverified_command(tmp_path, monkeypatch, body, status):
    import base64

    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    monkeypatch.setenv('DHCPV6_ROUTE_DIAGNOSTIC_DIR', str(private))
    monkeypatch.setenv('DHCPV6_ROUTE_IP_SHA256', '0' * 64)
    result, _ = execute_input_admission(tmp_path, body)
    retained = json.loads((private / 'dhcpv6-route.json').read_text())
    assert retained == {'returncode': status, 'command_authority': 'unverified', 'stderr_base64': None}
    assert native.readiness_record(result.stderr) == {'stage': 'exit', 'authority_mismatch': 0}
    assert 'private-refusal' not in result.stderr
    assert (private / 'dhcpv6-route.json').stat().st_mode & 0o777 == 0o600
    assert base64.b64decode(retained['stderr_base64'] or '') == b''


def test_real_route_child_receives_only_minimal_locale_and_path(tmp_path, monkeypatch):
    observed = tmp_path / 'child-environment.json'
    monkeypatch.setenv('PRIVATE_OPERATOR_SENTINEL', 'must-not-reach-route-child')
    body = 'open(' + repr(str(observed)) + ",'w').write(json.dumps(sorted(os.environ)));sys.exit(2)"
    result, _ = execute_input_admission(tmp_path, body)
    assert result.returncode != 0
    expected = ['LANG', 'LC_ALL', 'PATH']
    if sys.platform == 'darwin':
        # Darwin's C runtime injects its own encoding variable after exec.
        expected.append('__CF_USER_TEXT_ENCODING')
    assert json.loads(observed.read_text()) == expected


def route_writer(tmp_path):
    """Exercise real file guards; only canonical path and root UID are relocated."""
    import os

    tree = ast.parse(native.RECEIVER)
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'retain_route_refusal')
    executable = tmp_path / 'canonical-ip'

    class FixtureAuthority(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value in ('/usr/sbin/ip', '/usr/bin/ip'):
                return ast.copy_location(ast.Constant(str(executable)), node)
            return node

        def visit_Compare(self, node):
            if (isinstance(node.left, ast.Attribute) and node.left.attr == 'st_uid'
                    and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)
                    and node.comparators[0].value == 0):
                node.comparators[0] = ast.Constant(os.geteuid())
            return self.generic_visit(node)

    program = ast.fix_missing_locations(ast.Module(body=[FixtureAuthority().visit(helper)], type_ignores=[]))
    namespace = {'os': os, 'json': json}
    exec(compile(program, str(NATIVE), 'exec'), namespace)  # noqa: S102 - trusted repository helper
    return namespace['retain_route_refusal'], executable


def prepared_writer(tmp_path, monkeypatch):
    import hashlib
    import shutil

    writer, executable = route_writer(tmp_path)
    executable.write_bytes(b'\x7fELF' + b'synthetic-authority-fixture')
    executable.chmod(0o755)
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    monkeypatch.setattr(shutil, 'which', lambda name: str(executable))
    monkeypatch.setenv('DHCPV6_ROUTE_DIAGNOSTIC_DIR', str(private))
    monkeypatch.setenv('DHCPV6_ROUTE_IP_SHA256', hashlib.sha256(executable.read_bytes()).hexdigest())
    return writer, executable, private


def test_verified_writer_preserves_exact_bounded_bytes_in_private_file(tmp_path, monkeypatch):
    import base64

    writer, _executable, private = prepared_writer(tmp_path, monkeypatch)
    error = b'\xff' + b'x' * 4095
    writer(2, error)
    record = json.loads((private / 'dhcpv6-route.json').read_text())
    assert record['command_authority'] == 'verified' and record['returncode'] == 2
    assert base64.b64decode(record['stderr_base64'], validate=True) == error
    assert (private / 'dhcpv6-route.json').stat().st_size <= 8192
    assert (private / 'dhcpv6-route.json').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('change', ['hash', 'writable', 'non-elf', 'foreign-path'])
def test_command_authority_mismatch_never_retains_raw_bytes(tmp_path, monkeypatch, change):
    import shutil

    writer, executable, private = prepared_writer(tmp_path, monkeypatch)
    if change == 'hash':
        monkeypatch.setenv('DHCPV6_ROUTE_IP_SHA256', '0' * 64)
    elif change == 'writable':
        executable.chmod(0o777)
    elif change == 'non-elf':
        executable.write_bytes(b'#!/bin/sh\n')
    else:
        monkeypatch.setattr(shutil, 'which', lambda name: '/unknown/wrapper')
    writer(255, b'private-secret')
    assert json.loads((private / 'dhcpv6-route.json').read_text()) == {
        'returncode': 255, 'command_authority': 'unverified', 'stderr_base64': None}


@pytest.mark.parametrize('kind', ['file', 'symlink', 'unsafe-parent', 'symlink-parent'])
def test_private_diagnostic_refuses_foreign_authority_without_mutation(tmp_path, monkeypatch, kind):
    writer, _executable, private = prepared_writer(tmp_path, monkeypatch)
    target = tmp_path / 'foreign'
    target.write_bytes(b'foreign-bytes')
    before = (target.stat().st_ino, target.read_bytes())
    destination = private / 'dhcpv6-route.json'
    if kind == 'file':
        destination.write_bytes(b'prior-diagnostic')
    elif kind == 'symlink':
        destination.symlink_to(target)
    elif kind == 'unsafe-parent':
        private.chmod(0o755)
    else:
        alias = tmp_path / 'alias'
        alias.symlink_to(private, target_is_directory=True)
        monkeypatch.setenv('DHCPV6_ROUTE_DIAGNOSTIC_DIR', str(alias))
    prior = (destination.lstat().st_ino, destination.read_bytes()) if destination.exists() else None
    writer(2, b'private-secret')
    assert (target.stat().st_ino, target.read_bytes()) == before
    if prior:
        assert (destination.lstat().st_ino, destination.read_bytes()) == prior
    else:
        assert not destination.exists()


@pytest.mark.parametrize('status,error', [(0, b'x'), (True, b'x'), (256, b'x'), (-129, b'x'), (2, b'x' * 4097)])
def test_non_failure_or_unbounded_diagnostic_is_absent(tmp_path, monkeypatch, status, error):
    writer, _executable, private = prepared_writer(tmp_path, monkeypatch)
    writer(status, error)
    assert not (private / 'dhcpv6-route.json').exists()


@pytest.mark.parametrize('collision', [False, True])
def test_optional_diagnostic_failure_keeps_actual_original_refusal(tmp_path, monkeypatch, collision):
    private = tmp_path / 'private'
    private.mkdir(mode=0o700 if collision else 0o755)
    destination = private / 'dhcpv6-route.json'
    if collision:
        destination.write_bytes(b'foreign-bytes')
    monkeypatch.setenv('DHCPV6_ROUTE_DIAGNOSTIC_DIR', str(private))
    result, _ = execute_input_admission(tmp_path, 'sys.exit(71)')
    assert native.readiness_record(result.stderr) == {'stage': 'exit', 'authority_mismatch': 0}
    if collision:
        assert destination.read_bytes() == b'foreign-bytes'
    else:
        assert not destination.exists()
