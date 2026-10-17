"""Warm fixture diagnostics expose only admitted scalar observations."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from test_topology_awg_warm_native import warm_startup_diagnostics

PRIVATE = 'fixture-private-value-never-render'


def runner_for(properties='', ipv6='0\n1\n', journal='', *, code=0):
    def run(argv, **kwargs):
        assert kwargs == {'capture_output': True, 'text': True, 'timeout': 10}
        assert argv[0] in {'systemctl', 'ip', 'journalctl'}
        text = properties if argv[0] == 'systemctl' else ipv6 if argv[0] == 'ip' else journal
        return subprocess.CompletedProcess(argv, code, text, PRIVATE)
    return run


def evidence(tmp_path, **kwargs):
    return warm_startup_diagnostics('awg-quick@fixture.service', 'fixture', tmp_path, **kwargs)


def test_unknown_and_private_property_values_never_render(tmp_path):
    observed = evidence(tmp_path, runner=runner_for(
        f'LoadState=loaded\nActiveState=active\nSubState=running\nResult={PRIVATE}\n'
        f'ExecMainCode={PRIVATE}\nExecMainStatus=999999\nUnknown={PRIVATE}\n',
        journal=PRIVATE + '\nFailed at step EXEC\nPermission denied\n'))
    assert PRIVATE not in json.dumps(observed)
    assert observed['unit']['LoadState'] == 'loaded'
    assert observed['unit']['Result'] == 'unavailable'
    assert observed['unit']['ExecMainCode'] == 'unavailable'
    assert observed['unit']['ExecMainStatus'] == 'unavailable'
    assert observed['journal_flags']['exec_failure'] is True
    assert observed['journal_flags']['permission_denied'] is True
    assert observed['ipv6'] == {'all_disabled': 0, 'default_disabled': 1}


@pytest.mark.parametrize('properties,ipv6', [
    ('Result=exit-code\nExecMainCode=1\nExecMainStatus=203\n', '1\n0\n'),
    ('Result=success\nExecMainCode=0\nExecMainStatus=0\n', '0\n0\n'),
])
def test_known_unit_exit_properties_and_numeric_ipv6_remain_useful(tmp_path, properties, ipv6):
    observed = evidence(tmp_path, runner=runner_for(properties, ipv6))
    assert observed['unit']['Result'] in {'exit-code', 'success'}
    assert isinstance(observed['unit']['ExecMainCode'], int)
    assert observed['unit']['ExecMainStatus'] in {0, 203}
    assert set(observed['parents']['private']) == {'uid', 'gid', 'mode', 'nlink', 'issym', 'isdir'}
    assert observed['parents']['private']['isdir'] is True


def test_failed_queries_and_exception_strings_never_render(tmp_path):
    failed = evidence(tmp_path, runner=runner_for(PRIVATE, PRIVATE, PRIVATE, code=1))
    assert PRIVATE not in json.dumps(failed)
    assert set(failed['journal_flags'].values()) == {False}

    def raises(argv, **kwargs):
        raise OSError(PRIVATE)
    observed = evidence(tmp_path, runner=raises)
    assert PRIVATE not in json.dumps(observed)
    assert observed['unit']['LoadState'] == 'unavailable'


def test_timeout_command_and_output_never_render(tmp_path):
    def raises(argv, **kwargs):
        raise subprocess.TimeoutExpired([PRIVATE], 10, output=PRIVATE, stderr=PRIVATE)
    observed = evidence(tmp_path, runner=raises)
    assert PRIVATE not in json.dumps(observed)
    assert set(observed['journal_flags'].values()) == {False}


def test_parent_metadata_errors_never_render_paths_or_exception_strings(tmp_path, monkeypatch):
    def raises(path):
        raise OSError('/outside/' + PRIVATE)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'lstat', raises)
        observed = evidence(tmp_path, runner=runner_for())
    assert PRIVATE not in json.dumps(observed)
    assert '/outside/' not in json.dumps(observed)
    assert all(set(values.values()) == {'unavailable'} for values in observed['parents'].values())


def test_duplicate_and_non_ascii_unit_numbers_are_not_admitted(tmp_path):
    observed = evidence(tmp_path, runner=runner_for(
        f'Result={PRIVATE}\nResult=success\nExecMainCode=-1\nExecMainStatus=１２\n'))
    assert observed['unit']['Result'] == 'unavailable'
    assert observed['unit']['ExecMainCode'] == 'unavailable'
    assert observed['unit']['ExecMainStatus'] == 'unavailable'
    assert PRIVATE not in json.dumps(observed)


@pytest.mark.parametrize('ipv6', [PRIVATE, '2\n0\n', '0\n1\n0\n'])
def test_ipv6_accepts_only_exact_two_boolean_numbers(tmp_path, ipv6):
    observed = evidence(tmp_path, runner=runner_for(ipv6=ipv6))
    assert observed['ipv6'] == {'all_disabled': 'unavailable', 'default_disabled': 'unavailable'}
    assert PRIVATE not in json.dumps(observed)
