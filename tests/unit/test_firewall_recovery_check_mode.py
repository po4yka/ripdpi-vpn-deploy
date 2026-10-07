"""Recovery activation follows systemd load state for services and timers."""

from pathlib import Path

from ansible.plugins.filter.core import FilterModule
from jinja2 import Environment, StrictUndefined
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
TASKS = yaml.safe_load(
    (ROOT / "ansible/roles/firewall/tasks/main.yml").read_text()
)
GUARD = next(task for task in TASKS if task["name"] ==
             "Require planned Tailnet recovery units when check mode lacks them")
ACTIVATE = next(task for task in TASKS if task["name"] ==
                "Enable persistent Tailnet firewall recovery")
UNITS = [item["name"] for item in ACTIVATE["loop"]]
ENVIRONMENT = Environment(undefined=StrictUndefined)
ENVIRONMENT.filters.update(FilterModule().filters())


def evaluate(expression, variables):
    return ENVIRONMENT.compile_expression(expression, undefined_to_none=False)(variables)


def selected(task, variables):
    return all(evaluate(condition, variables) for condition in task["when"])


def context(unit, *, loaded, planned, check_mode=True):
    return {
        "ansible_facts": {"virtualization_type": "kvm", "services": {}},
        "_firewall_effective_check_mode": check_mode,
        "_firewall_tailnet_existing_units": {"results": [
            {"item": name, "stdout": "loaded" if loaded else "not-found"}
            for name in UNITS
        ]},
        "_firewall_tailnet_recovery_units": {"results": [
            {"item": name, "changed": planned} for name in UNITS
        ]},
        "item": {"name": unit, "state": "started"},
    }


@pytest.mark.parametrize("unit", UNITS)
def test_loaded_unit_is_checked_even_without_a_service_fact(unit):
    variables = context(unit, loaded=True, planned=False)
    assert not selected(GUARD, variables)
    assert selected(ACTIVATE, variables)


@pytest.mark.parametrize("planned", [True, False])
@pytest.mark.parametrize("unit", UNITS)
def test_absent_unit_requires_its_own_planned_copy_and_defers_activation(unit, planned):
    variables = context(unit, loaded=False, planned=planned)
    assert selected(GUARD, variables)
    assert all(evaluate(condition, variables)
               for condition in GUARD["ansible.builtin.assert"]["that"]) is planned
    assert not selected(ACTIVATE, variables)


def test_real_convergence_does_not_depend_on_check_mode_discovery():
    variables = context(UNITS[1], loaded=False, planned=False, check_mode=False)
    del variables["_firewall_tailnet_existing_units"]
    assert not selected(GUARD, variables)
    assert selected(ACTIVATE, variables)


@pytest.mark.parametrize(("status", "code", "refused"), [
    ("loaded", 0, False), ("not-found", 0, False), ("not-found", 1, False),
    ("loaded", 1, True), ("error", 0, True), ("", 1, True),
    ("not-found", 2, True), ("not-found", 255, True),
])
def test_load_state_probe_refuses_ambiguous_or_failed_discovery(status, code, refused):
    probe = next(task for task in TASKS if task.get("register") ==
                 "_firewall_tailnet_existing_units")
    variables = {"_firewall_tailnet_existing_units": {"stdout": status, "rc": code}}
    assert evaluate(probe["failed_when"], variables) is refused
