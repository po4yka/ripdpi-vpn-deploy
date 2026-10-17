"""Fresh protocol dry-runs plan authority and do not activate runtime."""

import copy
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_fresh_hysteria_unit_is_planned_before_service_activation():
    tasks = yaml.safe_load((ROOT / 'ansible/roles/hysteria/tasks/enable.yml').read_text())
    by_name = {task['name']: task for task in tasks}
    unit_path = '/etc/systemd/system/hysteria-server.service'
    predictive = by_name['Detect Hysteria frontend authority change before publication']
    unit = next(item for item in predictive['loop'] if item['destination'] == unit_path)
    assert unit['group'] == 'root' and unit['mode'] == '0644'
    assert predictive['check_mode'] is True and predictive['register'] == '_hysteria_frontend_change'
    staged = by_name['Stage complete Hysteria authority for guarded consumer acceptance']
    service = by_name['Activate guarded standalone frontend generation']
    assert tasks.index(predictive) < tasks.index(staged) < tasks.index(service)
    assert 'not (transport_egress_fresh_check_mode' in staged['when']
    assert unit_path in staged['ansible.builtin.set_fact']['transport_runtime_candidates']
    assert staged['no_log'] is True and staged['diff'] is False
    activation = next(task for task in yaml.safe_load(
        (ROOT / 'ansible/roles/transport-egress/tasks/activate.yml').read_text())
        if task['name'] == 'Activate only a ready guarded generation after frontend staging')
    assert activation['when'] == 'not ansible_check_mode'
    assert activation['block'][0]['ansible.builtin.systemd_service']['name'] == 'ripdpi-transport-generation.service'


def test_fresh_awg_plans_complete_unit_and_acquisition_before_deferring_acceptance():
    role = ROOT / 'ansible/roles/amneziawg'
    enable = yaml.safe_load((role / 'tasks/enable.yml').read_text())
    configure = yaml.safe_load((role / 'tasks/configure.yml').read_text())
    acquire = next(task for task in enable if task['name'] == 'Converge pinned AmneziaWG source builds')
    assert acquire['ansible.builtin.include_role']['tasks_from'] == 'source-build'
    assert next(task for task in enable if task.get('ansible.builtin.import_tasks') == 'configure.yml')
    units = next(task for task in configure if task['name'] == 'Stage shared units and the complete AWG membership receipt')
    candidates = units['ansible.builtin.set_fact']['_awg_consumer_candidates']
    assert '/etc/systemd/system/awg-quick@.service' in candidates
    assert '/etc/systemd/system/awg-quick.target' in candidates
    assert units['no_log'] is True
    prediction = next(task for task in configure if task['name'] == 'Predict fresh AmneziaWG acquisition and complete consumer publication')
    accept = next(task for task in configure if task['name'] == 'Accept complete AmneziaWG runtime and firewall together')
    assert configure.index(units) < configure.index(prediction) < configure.index(accept)
    assert prediction['changed_when'] is True
    assert accept['check_mode'] is False and accept['no_log'] is True
    assert "'check': ansible_check_mode" in accept['ansible.builtin.command']['stdin']
    assert yaml.safe_load((role / 'handlers/main.yml').read_text()) == []


@pytest.mark.parametrize('acquired,helper_planned', [(False, False), (True, True), (True, False)])
def test_actual_fresh_awg_check_mode_plans_or_inspects_without_publication(private_authority_path, acquired, helper_planned):
    """Run actual role decision tasks and the real consumer with absent runtime state."""
    root = private_authority_path
    state = root / 'not-created/runtime'
    helper = root / 'fresh_consumer.py'
    helper.write_text('''import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]); source=Path(sys.argv[2]); state=Path(sys.argv[3])
sys.path[:0]=[str(root/'ansible/roles/runtime-release/files'),str(root/'ansible/roles/firewall/files')]
spec=importlib.util.spec_from_file_location('fresh_awg',source)
consumer=importlib.util.module_from_spec(spec); spec.loader.exec_module(consumer)
consumer.STATE=state
# An absent check-only consumer must not construct any lifecycle adapter.
def forbidden(*args,**kwargs): raise AssertionError('fresh-check-runtime-mutation')
consumer.Adapter=forbidden
payload=json.load(sys.stdin)
assert payload['check'] is True
print(json.dumps(consumer.operate('apply',payload)))
''')
    configure = yaml.safe_load((ROOT / 'ansible/roles/amneziawg/tasks/configure.yml').read_text())
    selected = copy.deepcopy([task for task in configure if task['name'] in {
        'Predict fresh AmneziaWG acquisition and complete consumer publication',
        'Accept complete AmneziaWG runtime and firewall together'}])
    assert len(selected) == 2
    selected[1]['ansible.builtin.command']['argv'] = [sys.executable, str(helper), str(ROOT),
        str(ROOT / 'ansible/roles/amneziawg/files/consumer.py'), str(state)]
    deferred = not acquired or helper_planned
    selected.append({'name': 'Require the actual fresh-host decision', 'ansible.builtin.assert': {'that': [
        f"(_awg_consumer_publication.skipped | default(false) | bool) == {str(deferred).lower()}",
        '_awg_consumer_publication is skipped' if deferred else '_awg_consumer_publication.changed | bool']}})
    play = [{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': False,
             'vars': {'ansible_python_interpreter': sys.executable,
                      '_awg_acquired': {'results': [{'stat': {'exists': acquired}}]},
                      '_awg_consumer_install': {'changed': helper_planned}, '_awg_consumer_candidates': []},
             'tasks': selected}]
    path = root / 'check.yml'
    path.write_text(yaml.safe_dump(play))
    before = {str(path): (path.read_bytes(), path.stat().st_ino) for path in root.rglob('*') if path.is_file()}
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path), '--check'], capture_output=True,
        text=True, timeout=30, env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'fresh-check-runtime-mutation' not in result.stdout + result.stderr
    assert not state.parent.exists()
    assert {str(path): (path.read_bytes(), path.stat().st_ino) for path in root.rglob('*') if path.is_file()} == before
