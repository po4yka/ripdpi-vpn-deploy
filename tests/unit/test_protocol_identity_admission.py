"""Admission rejects ambiguous wire identities without disclosing values."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest
import yaml

from transport_semantics import cohort_errors, mtg_errors

ROOT = Path(__file__).resolve().parents[2]


def clients(*values):
    return [{"name": f"device-{i}", "uuid": f"00000000-0000-4000-8000-{i+1:012x}", "short_id": value}
            for i, value in enumerate(values)]


@pytest.mark.parametrize("value", [None, "", "a", "abc", "aabbc", "ab" * 9, "zz", "aa\n"])
def test_short_id_requires_even_bounded_hex(value):
    errors = cohort_errors({"clients": clients(value)})
    assert errors == [("xray.clients.0.short_id", "must be nonempty even-length hex of at most eight bytes")]


@pytest.mark.parametrize("values", [("aa", "aa00"), ("AA", "aa"), ("00", "0000000000000000")])
@pytest.mark.parametrize("cohorts", [False, True])
def test_short_id_wire_aliases_are_global_across_cohorts(values, cohorts):
    raw = {"clients": clients(*values)}
    if cohorts:
        raw["cohorts"] = [{"name": str(i), "clients": [client["name"]]} for i, client in enumerate(raw["clients"])]
    assert cohort_errors(raw) == [("xray.clients", "duplicate short_id wire value")]


def test_short_id_valid_distinct_and_lenient_placeholders():
    assert not cohort_errors({"clients": clients("aa", "aa01", "BB")})
    example = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    raw = {"clients": clients(example["xray"]["clients"][0]["short_id"])}
    assert not cohort_errors(raw, allow_placeholders=True)
    assert cohort_errors(raw)


def test_schema_rejects_odd_short_id_before_semantics():
    schema = json.loads((ROOT / 'secrets/schema.json').read_text())
    document = yaml.safe_load((ROOT / 'secrets/prod.secrets.example.yaml').read_text())
    for value in ('abc', 'abcde', 'aa\n'):
        document['xray']['clients'] = clients(value)
        assert any(error.json_path.endswith('.short_id') for error in jsonschema.Draft202012Validator(schema).iter_errors(document))


def faketls(host=b'example.com', key=b'\xaa' * 16, prefix=b'\xee'):
    return prefix + key + host


@pytest.mark.parametrize('encode', [lambda raw: raw.hex(), lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip('=')])
def test_mtg_hex_and_unpadded_base64_are_accepted(encode):
    assert not mtg_errors({'mtproto_secret': encode(faketls())})


@pytest.mark.parametrize('raw', [b'', b'\xee', faketls(host=b''), faketls(prefix=b'\xdd'),
                                  faketls(key=b'\0'*16), faketls(host=b'bad/host'),
                                  faketls(host=b'127.0.0.1'), faketls(host=b'bad\n.example'),
                                  faketls(host=b'-bad.example'), faketls(host=b'\xff.example')])
def test_mtg_invalid_structure_has_only_categorical_diagnostics(raw):
    errors = mtg_errors({'mtproto_secret': raw.hex()})
    assert errors == [('probe_matrix_target_secrets.mtproto_secret',
                       'requires FakeTLS prefix, a nonzero sixteen-byte key and a valid hostname')]


def test_mtg_placeholder_requires_explicit_lenient_mode():
    example = yaml.safe_load((ROOT / "secrets/prod.secrets.example.yaml").read_text())
    doc = {"mtproto_secret": example["probe_matrix_target_secrets"]["mtproto_secret"]}
    assert mtg_errors(doc)
    assert not mtg_errors(doc, allow_placeholders=True)


@pytest.mark.parametrize('check_mode', [False, True])
def test_actual_mtg_controller_refuses_before_first_mutation(tmp_path, check_mode):
    source = yaml.safe_load((ROOT / 'ansible/roles/probe-matrix-target/tasks/enable.yml').read_text())
    marker = tmp_path / 'mutated'
    play = tmp_path / 'preflight.yml'
    secret = 'private-synthetic-marker'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'vars': {'role_path': str(ROOT / 'ansible/roles/probe-matrix-target'),
                 'ansible_python_interpreter': sys.executable,
                 'probe_matrix_target_secrets': {'mtproto_secret': secret}},
        'tasks': [source[0], {'ansible.builtin.copy': {'dest': str(marker), 'content': 'mutated'}}]}]))
    command = ['ansible-playbook', '-i', 'localhost,', str(play)] + (['--check'] if check_mode else [])
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and not marker.exists()
    assert secret not in result.stdout + result.stderr


def test_mtg_archive_and_native_admission_precede_runtime_publication():
    tasks = yaml.safe_load((ROOT / 'ansible/roles/probe-matrix-target/tasks/enable.yml').read_text())
    stage, publish = [task for task in tasks if task.get('ansible.builtin.include_role', {}).get('name') == 'runtime-release']
    render = next(task for task in tasks if task.get('ansible.builtin.template', {}).get('src') == 'mtg.toml.j2')
    revalidate = next(task for task in tasks if task['name'] == 'Validate mtg candidate even when configuration bytes are unchanged')
    assert tasks.index(stage) < tasks.index(render) < tasks.index(revalidate) < tasks.index(publish)
    assert revalidate['changed_when'] is False and revalidate['no_log'] is True
    assert revalidate['when'] == 'not ansible_check_mode'
    assert stage['vars']['runtime_release_stage_only'] is True
    assert publish['vars']['runtime_release_stage_only'] is False
    assert stage['vars']['runtime_release_artifact_type'] == 'archive'
    assert stage['vars']['runtime_release_version'] == '{{ probe_matrix_target_secrets.mtg_version }}+archive.1'
    assert publish['vars']['runtime_release_version'] == stage['vars']['runtime_release_version']
    validation = render['ansible.builtin.template']['validate']
    assert '/releases/{{ probe_matrix_target_secrets.mtg_version }}+archive.1/mtg' in validation
    assert '--version {{ probe_matrix_target_secrets.mtg_version }} --config' in validation
    assert all('+archive.1' not in member for member in stage['vars']['runtime_release_archive_members'].values())
    assert stage['vars']['runtime_release_archive_strip_components'] == 1
    assert set(stage['vars']['runtime_release_archive_members']) == {'amd64', 'arm64'}
    assert '--config %s' in render['ansible.builtin.template']['validate']
    assert render['no_log'] is True and render['diff'] is False
    assert tasks[0]['name'] == 'Validate FakeTLS authority before target mutation'


def test_native_mtg_wrapper_discards_credentials_from_both_streams(tmp_path, monkeypatch, capsys):
    import importlib.util
    helper = ROOT / 'ansible/roles/probe-matrix-target/files/validate_mtg.py'
    spec = importlib.util.spec_from_file_location('mtg_validator', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if '--version' in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=b'2.2.8 (build metadata)\n')
        return subprocess.CompletedProcess(argv, 1)
    monkeypatch.setattr(module.subprocess, 'run', run)
    candidate = tmp_path / 'candidate.toml'
    candidate.write_text('synthetic-private-marker')
    with pytest.raises(ValueError, match='native-config-refused'):
        module.validate('/owned/mtg', 'v2.2.8', str(candidate))
    assert calls[1][1]['stdout'] == subprocess.DEVNULL
    assert calls[1][1]['stderr'] == subprocess.DEVNULL
    assert capsys.readouterr().out == ''


def test_native_mtg_failure_context_exposes_only_static_task_and_category(monkeypatch):
    import importlib.util
    source = ROOT / 'tests/native/mtg_compatibility.py'
    spec = importlib.util.spec_from_file_location('mtg_native_diagnostics', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stdout = ('TASK [runtime-release : Preflight runtime release activation layout] ********\n'
              'fatal: unsafe-storage-ancestor synthetic-private-value /private/path\n')
    result = subprocess.CompletedProcess(['ansible-playbook'], 2, stdout=stdout, stderr='private-stderr')
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: result)
    with pytest.raises(RuntimeError) as raised:
        module.command(['ansible-playbook'])
    assert str(raised.value) == ('native-command-outcome-mismatch: rc=2; '
        'task=runtime-release : Preflight runtime release activation layout; categories=unsafe-storage-ancestor')
    assert 'private' not in str(raised.value)
