"""Mirror retirement selection preserves data authority and administrative masks."""
import copy
import json
from pathlib import Path

from jinja2 import Environment, StrictUndefined
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/subscription-host'
TASKS = yaml.safe_load((ROLE / 'tasks/mirror-disable.yml').read_text())
ENV = Environment(undefined=StrictUndefined, autoescape=True)


def evaluate(expression, values):
    return ENV.compile_expression(expression, undefined_to_none=False)(values)


@pytest.mark.parametrize(('state', 'code', 'refuse'), [
    ('loaded', 0, False), ('masked', 0, False), ('not-found', 0, False), ('not-found', 1, False),
    ('loaded', 1, True), ('masked', 1, True), ('error', 0, True), ('', 0, True), ('not-found', 2, True),
])
def test_retirement_refuses_uncertain_discovery(state, code, refuse):
    probe = TASKS[0]
    assert evaluate(probe['failed_when'], {'_subscription_mirror_units': {'stdout': state, 'rc': code}}) is refuse
    assert probe['check_mode'] is False
    assert probe['changed_when'] is False


def test_exact_timer_stops_before_service_and_only_loaded_units_are_disabled():
    assert TASKS[0]['loop'] == ['vpn-sub-mirror.timer', 'vpn-sub-mirror.service']
    loaded, masked = TASKS[1:]
    for state in ('loaded', 'masked', 'not-found'):
        item = {'item': {'stdout': state}}
        assert bool(evaluate(loaded['when'], item)) is (state == 'loaded')
        assert bool(evaluate(masked['when'], item)) is (state == 'masked')
    assert loaded['ansible.builtin.systemd_service']['enabled'] is False
    assert 'enabled' not in masked['ansible.builtin.systemd_service']
    assert all(task['ansible.builtin.systemd_service']['state'] == 'stopped' for task in TASKS[1:])
    assert all('check_mode' not in task for task in TASKS[1:])
    assert all('ansible.builtin.file' not in task for task in TASKS)


def test_retirement_precedes_payload_mutation_and_queued_handler_cannot_restart():
    enabled = yaml.safe_load((ROLE / 'tasks/enable.yml').read_text())
    retirement = next(task for task in enabled if task.get('ansible.builtin.import_tasks') == 'mirror-disable.yml')
    assert all('ansible.builtin.assert' in task for task in enabled[:enabled.index(retirement)])
    handler = next(task for task in yaml.safe_load((ROLE / 'handlers/main.yml').read_text())
                   if task['name'] == 'Restart vpn-sub-mirror timer')
    # Default-false behavior is also retained for fresh hosts with no mirror map.
    assert 'default(false)' in retirement['when']
    assert 'default(false)' in handler['when']
    for selected in (False, True):
        values = {'subscription': {'mirror': {'enabled': selected}}}
        assert bool(evaluate(retirement['when'], values)) is (not selected)
        assert bool(evaluate(handler['when'], values)) is selected


def test_molecule_drains_scheduled_writers_before_baseline_without_stopping_timers():
    tasks = yaml.safe_load((ROLE / 'molecule/default/verify.yml').read_text())[0]['tasks']
    named = {task['name']: task for task in tasks}
    ordered = [
        'Defer independent fixture writers beyond the verification window',
        'Keep fixture timers enabled and active with deferred scheduling',
        'Drain independent fixture writers before the authority baseline',
        'Capture retained delivery authority before mirror retirement',
        'Predict mirror retirement without changing running units',
        'Check mode retains the enabled active mirror timer',
        'Retire mirror execution while preserving accepted authority',
        'Capture retained delivery authority after mirror retirement',
        'Retired mirror preserves accepted payload and replay authority',
    ]
    positions = [tasks.index(named[name]) for name in ordered]
    assert positions == sorted(positions)
    override = named[ordered[0]]['ansible.builtin.copy']
    assert override['dest'] == '/run/systemd/system/{{ item }}.d/molecule-retirement.conf'
    assert override['content'].splitlines() == [
        '[Timer]', 'OnCalendar=', 'OnBootSec=', 'OnUnitActiveSec=',
        'OnActiveSec=365d', 'RandomizedDelaySec=0', 'Persistent=false',
    ]
    timers = ['vpn-sub-mirror.timer', 'vpn-subscription-maintenance.timer']
    assert named[ordered[0]]['loop'] == timers
    assert named[ordered[1]]['loop'] == timers
    assert named[ordered[1]]['ansible.builtin.systemd_service'] == {
        'name': '{{ item }}', 'enabled': True, 'state': 'restarted', 'daemon_reload': True,
    }
    assert named[ordered[2]]['loop'] == ['vpn-sub-mirror.service', 'vpn-subscription-maintenance.service']
    assert named[ordered[2]]['ansible.builtin.systemd_service']['state'] == 'stopped'
    assert named[ordered[8]]['ansible.builtin.assert']['that'] == '_mirror_authority_after.stdout == _mirror_authority_before.stdout'
    assert all(named[name]['no_log'] is True for name in (ordered[3], ordered[7], ordered[8]))


@pytest.mark.parametrize('changed', ['pointer', 'revoked', 'fence', 'lock', 'payload', 'credential', 'consumed'])
def test_molecule_authority_diagnostics_expose_only_fixed_component_booleans(changed):
    tasks = yaml.safe_load((ROLE / 'molecule/default/verify.yml').read_text())[0]['tasks']
    classification = next(task for task in tasks if task['name'] == 'Classify retained authority differences without private values')
    report = next(task for task in tasks if task['name'] == 'Report only changed retained authority categories')
    files = {
        'revoked': 'revoked', 'fence': '.vpn-bootstrap-retired-before',
        'lock': '.vpn-bootstrap-state.lock',
        'payload': '.vpn-sub-mirror-current/sub/' + 'a' * 64,
        'credential': '/etc/vpn-subscription/mirror_ssh_key',
    }
    before = {'pointer': 'synthetic-generation', 'files': {name: 'synthetic-digest' for name in files.values()}, 'consumed': ['synthetic-consumption']}
    after = copy.deepcopy(before)
    if changed in files:
        after['files'][files[changed]] = 'changed-synthetic-digest'
    elif changed == 'pointer':
        after['pointer'] = 'changed-synthetic-generation'
    else:
        after['consumed'].append('changed-synthetic-consumption')
    environment = Environment(undefined=StrictUndefined, autoescape=True)
    environment.filters['from_json'] = json.loads
    predicates = classification['ansible.builtin.set_fact']['_mirror_authority_changed']
    result = {
        component: environment.compile_expression(expression[2:-2].strip())(
            _mirror_authority_before={'stdout': json.dumps(before)},
            _mirror_authority_after={'stdout': json.dumps(after)},
        ) for component, expression in predicates.items()
    }
    assert result == {component: component == changed for component in ['pointer', *files, 'consumed']}
    assert all(type(value) is bool for value in result.values())
    assert classification['no_log'] is True
    assert report['ansible.builtin.debug'] == {'var': '_mirror_authority_changed'}
    assert report['when'] == '_mirror_authority_after.stdout != _mirror_authority_before.stdout'
