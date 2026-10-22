"""Empty private authority retires transports without reusing shared auth."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from device_runtime_context import project

ROOT = Path(__file__).resolve().parents[2]


def test_last_device_disables_only_selected_empty_transport_authority():
    context = {'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': True, 'enable_hysteria': True,
                       'enable_snell': True, 'enable_amneziawg': True, 'enable_naive': True},
               'snell': {'variants': [{'id': 'one'}, {'id': 'two'}]}}
    source = {'xray': {'clients': []}, 'hysteria': {'clients': []},
              'snell_secrets': {'variants': [{'id': 'one', 'users': []}, {'id': 'two', 'users': []}]}}
    before = copy.deepcopy(context)
    actual, cohorts, variants = project(source, context)
    assert context == before
    assert actual['vpn'] == dict.fromkeys(('enable_xray_reality', 'enable_nginx_xhttp', 'enable_hysteria', 'enable_snell'), False) | {
        'enable_amneziawg': True, 'enable_naive': True}
    assert actual['snell']['variants'] == [] and variants == [] and cohorts == []


def test_partial_cohorts_and_variants_preserve_survivors():
    doc = {'xray': {'clients': [{'name': 'survivor'}], 'cohorts': [
        {'name': 'empty', 'clients': []}, {'name': 'active', 'clients': ['survivor']}]},
        'snell_secrets': {'variants': [{'id': 'a', 'users': []}, {'id': 'b', 'users': [{'name': 'survivor'}]}]}}
    ctx = {'vpn': {'enable_xray_reality': True, 'enable_snell': True}, 'snell': {'variants': [{'id': 'a'}, {'id': 'b'}]}}
    result, cohorts, variants = project(doc, ctx)
    assert cohorts == ['active'] and variants == ['b']
    assert result['vpn'] == ctx['vpn'] and result['snell']['variants'] == [{'id': 'b'}]
    assert project(doc, result)[0] == result


def test_empty_named_cohorts_cannot_fall_back_to_implicit_all_client_listener():
    result, _, _ = project({'xray': {'clients': [{'name': 'unassigned'}], 'cohorts': [{'name': 'empty', 'clients': []}]}},
                           {'vpn': {'enable_xray_reality': True, 'enable_nginx_xhttp': True}})
    assert result['vpn'] == {'enable_xray_reality': False, 'enable_nginx_xhttp': True}


@pytest.mark.parametrize('value', [None, '', {}, False])
def test_missing_or_malformed_authority_never_counts_as_explicit_empty(value):
    ctx = {'vpn': {'enable_hysteria': True}}
    assert project({'hysteria': {'clients': value}}, ctx)[0] == ctx


def test_cli_does_not_export_private_values_and_refuses_incomplete_variants():
    request = {'secrets': {'xray': {'clients': [], 'private': 'test-secret-omitted'}}, 'context': {'vpn': {}}}
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/device_runtime_context.py')],
                         input=json.dumps(request), capture_output=True, text=True, check=False)
    assert run.returncode == 0 and 'test-secret-omitted' not in run.stdout + run.stderr
    request['secrets']['snell_secrets'] = {'variants': [{'id': 'bad', 'users': 'not-a-list'}]}
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/device_runtime_context.py')],
                         input=json.dumps(request), capture_output=True, text=True, check=False)
    assert run.returncode == 2 and run.stderr.strip() == 'device-runtime-context-refused'


@pytest.mark.parametrize('all_empty', [False, True])
@pytest.mark.parametrize('check_mode', [False, True])
def test_real_ansible_projects_public_and_private_snell_variants_together(tmp_path, all_empty, check_mode):
    expected = [] if all_empty else ['v6-default']
    play = tmp_path / 'projection.yml'
    play.write_text(yaml.safe_dump([{
        'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'vars': {'ansible_python_interpreter': sys.executable,
                 'role_path': str(ROOT / 'ansible/roles/snell'),
                 'vpn': {'enable_snell': True}, 'snell': {'listen_addr': '127.0.0.2'},
                 'snell_secrets': {'variants': [
                     {'id': 'v4-stream', 'users': [], 'psk': 'retired-variant'},
                     {'id': 'v6-default', 'users': [] if all_empty else [{'name': 'survivor'}], 'psk': 'STUB_RETAINED_VARIANT_KEY'},
                     {'id': 'v6-unshaped', 'users': [], 'psk': 'retired-variant'}]}},
        'tasks': [{'ansible.builtin.import_tasks': str(ROOT / 'ansible/playbooks/tasks/device-runtime-context.yml')},
                  {'ansible.builtin.assert': {'that': [
                      "snell.variants | map(attribute='id') | list == " + repr(expected),
                      "snell_secrets.variants | map(attribute='id') | list == " + repr(expected),
                      "vpn.enable_snell == " + str(not all_empty).lower(),
                      "snell.listen_addr == '127.0.0.2'", "snell.version == 'v1.14.3'",
                      "snell.config_dir == '/etc/snell'"]}}],
    }]))
    argv = ['ansible-playbook', '-i', 'localhost,', str(play)] + (['--check'] if check_mode else [])
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_duplicate_retired_cohort_authority_remains_invalid():
    with pytest.raises(ValueError, match='runtime-cohorts'):
        project({'xray': {'clients': [], 'cohorts': [{'name': 'same', 'clients': []}, {'name': 'same', 'clients': []}]}}, {})
