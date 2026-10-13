"""Private origin projection, real CLI refusal and rendered consumer contract."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'ansible/roles/hysteria/files/masquerade_hosts.py'
spec = importlib.util.spec_from_file_location('hysteria_hosts', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def request():
    return {'origin': 'https://owned.example.test:8443', 'server_name': 'owned.example.test',
            'nginx_enabled': True, 'service_address': '203.0.113.50'}


@pytest.mark.parametrize('enabled,origin,name,mapped', [
    (True, 'https://owned.example.test:8443', 'owned.example.test', True),
    (True, 'https://owned.example.test', 'OWNED.EXAMPLE.TEST', True),
    (False, 'https://owned.example.test', 'owned.example.test', False),
    (True, 'https://external.example.test', 'owned.example.test', False),
])
def test_only_the_matching_enabled_local_origin_is_mapped(enabled, origin, name, mapped):
    value = module.build({**request(), 'nginx_enabled': enabled, 'origin': origin, 'server_name': name})
    assert value['enabled'] is mapped
    assert ('203.0.113.50 owned.example.test\n' in value['content']) is mapped
    assert '127.0.0.1 localhost\n' in value['content']


@pytest.mark.parametrize('field,value', [
    ('service_address', '999.0.0.1'), ('service_address', '203.0.113.50\nforeign'),
    ('nginx_enabled', 'true'), ('server_name', []), ('origin', 'http://owned.example.test'),
    ('origin', 'https://user:private-marker@owned.example.test'),
])
def test_bad_projection_refuses_before_publication_without_values(field, value):
    result = subprocess.run([sys.executable, str(SOURCE)], input=json.dumps({**request(), field: value}),
                            text=True, capture_output=True, timeout=5)
    assert result.returncode == 1 and result.stdout == ''
    assert result.stderr == 'masquerade-hosts-invalid\n'


@pytest.mark.parametrize('enabled', [True, False])
def test_actual_unit_binds_private_hosts_only_for_local_origin(enabled):
    values = merge_render_vars()
    values['hysteria_masquerade_hosts'] = {'enabled': enabled, 'content': ''}
    unit = render_template(ROOT / 'ansible/roles/hysteria/templates/hysteria-server.service.j2', values)
    assert ('BindReadOnlyPaths=/etc/hysteria/masquerade-hosts:/etc/hosts' in unit) is enabled
    tasks = yaml.safe_load((ROOT / 'ansible/roles/hysteria/tasks/enable.yml').read_text())
    detect = next(task for task in tasks if task['name'] == 'Detect private masquerade hosts change before publication')
    staged = next(task for task in tasks if task['name'] == 'Stage complete Hysteria authority for guarded consumer acceptance')
    assert detect['check_mode'] is True and detect['no_log'] is True
    assert tasks.index(detect) < tasks.index(staged)
    plan = staged['ansible.builtin.set_fact']['transport_runtime_candidates']
    assert 'masquerade-hosts' in plan and 'hysteria_masquerade_hosts.content | b64encode' in plan
    assert staged['no_log'] is True and staged['diff'] is False
    snapshot = (ROOT / 'ansible/roles/transport-egress/files/snapshot.py').read_text()
    assert "Path('/etc/hysteria/masquerade-hosts')" in snapshot
