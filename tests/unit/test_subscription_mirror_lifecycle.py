"""Mirror retirement selection preserves data authority and administrative masks."""
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
