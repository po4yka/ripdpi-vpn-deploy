"""Warm fixture diagnostics expose only admitted scalar observations."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_topology_awg_warm_native import (
    HELPER_FILES, ROOT, last_known_role_task, literal_refusal_codes,
    readonly_consumer_diagnostics, warm_startup_diagnostics,
)

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


def install_helpers(directory):
    directory.mkdir()
    sources = ('amneziawg/files/consumer.py', 'runtime-release/files/transport_runtime_transaction.py',
               'firewall/files/firewall_consumer.py', 'runtime-release/files/runtime_build_receipt.py')
    for source, target in zip(sources, HELPER_FILES):
        shutil.copyfile(ROOT / 'ansible/roles' / source, directory / target)
    return directory


def test_only_literal_known_task_names_can_enter_diagnostics():
    known = 'Accept complete AmneziaWG runtime and firewall together'
    text = f'TASK [amneziawg : {known}] ***\nTASK [amneziawg : {PRIVATE}] ***\n{PRIVATE}'
    assert last_known_role_task(text) == known
    assert last_known_role_task(PRIVATE) == 'unavailable'


@pytest.mark.parametrize('output', [PRIVATE, json.dumps({
    'transaction_validate': PRIVATE, 'adapter_validate': 'refusal:' + PRIVATE,
    'adapter_inspect': {'private': PRIVATE}}), json.dumps({'unexpected': PRIVATE})])
def test_child_output_is_filtered_against_actual_literal_categories(tmp_path, output):
    helpers = install_helpers(tmp_path / 'helpers')
    assert 'unsafe-parent' in literal_refusal_codes(helpers)
    def run(argv, **kwargs):
        assert argv[1:3] == ['-B', '-Es']
        return subprocess.CompletedProcess(argv, 0, output, PRIVATE)
    observed = readonly_consumer_diagnostics({'candidates': []}, helpers, runner=run)
    assert PRIVATE not in json.dumps(observed)
    assert set(observed.values()) == {'unavailable'}


def test_actual_readonly_transaction_child_censors_faults_without_writes(private_authority_path):
    helpers = install_helpers(private_authority_path / 'helpers')
    state = private_authority_path / 'absent-runtime'
    # Fault-only adapter canaries test disclosure boundaries. The transaction
    # class and its check-mode admission remain the actual copied production code.
    (helpers / 'amneziawg_consumer.py').write_text(
        'from pathlib import Path\nfrom transport_runtime_transaction import Transaction, Refusal\n'
        f'STATE = Path({str(state)!r})\n'
        'class Adapter:\n'
        '    def __init__(self, *args): pass\n'
        '    def validate(self): raise Refusal("fixture-" + "private-value-never-render")\n'
        f'    def inspect(self): raise OSError({PRIVATE!r})\n')
    before = {path.name: (path.stat().st_ino, path.stat().st_mode, path.read_bytes()) for path in helpers.iterdir()}
    observed = readonly_consumer_diagnostics({'candidates': []}, helpers)
    assert observed == {'transaction_validate': 'refusal:candidate-invalid',
                        'adapter_validate': 'Refusal', 'adapter_inspect': 'OSError'}
    assert PRIVATE not in json.dumps(observed)
    assert not state.exists()
    assert {path.name: (path.stat().st_ino, path.stat().st_mode, path.read_bytes()) for path in helpers.iterdir()} == before


def test_source_metadata_and_additional_unit_properties_are_bounded(tmp_path):
    source = tmp_path / 'private-source'
    source.write_text(PRIVATE)
    acquired = [{'path': '/usr/local/bin/amneziawg-go', 'source': str(source)}]
    observed = warm_startup_diagnostics('fixture.service', 'fixture', tmp_path, sources=acquired,
        runner=runner_for(f'UnitFileState={PRIVATE}\nMainPID=2147483648\n'))
    assert observed['unit']['UnitFileState'] == 'unavailable'
    assert observed['unit']['MainPID'] == 'unavailable'
    assert observed['parents']['source_go']['isdir'] is False
    assert observed['parents']['source_go_parent']['isdir'] is True
    assert {'opt', 'awg_acquisitions', 'awg_releases', 'local_libexec', 'consumer_helpers'} <= set(observed['parents'])
    assert PRIVATE not in json.dumps(observed)
    assert str(source) not in json.dumps(observed)
