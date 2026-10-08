"""First dry-run defers only an absent service with a real installation plan."""

from pathlib import Path

from jinja2 import Environment, StrictUndefined
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/subscription-host"
TASKS = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
BY_NAME = {task["name"]: task for task in TASKS}
GUARD = BY_NAME["Require planned subscription unit on a fresh check-mode host"]
PROBE = BY_NAME["Inspect subscription unit load state in check mode"]
ACTIVATE = BY_NAME["Enable + start service"]
HANDLER = next(task for task in yaml.safe_load((ROLE / "handlers/main.yml").read_text())
               if task["name"] == "Restart vpn-bootstrap")
ENVIRONMENT = Environment(undefined=StrictUndefined)


def evaluate(expression, variables):
    return ENVIRONMENT.compile_expression(expression, undefined_to_none=False)(variables)


def context(*, loaded=False, planned=False, check=True):
    return {
        "ansible_check_mode": check,
        "_subscription_unit_existing": {"stdout": "loaded" if loaded else "not-found"},
        "_subscription_unit_plan": {"changed": planned},
    }


@pytest.mark.parametrize("planned", [True, False])
def test_fresh_unit_requires_installation_plan_and_defers_activation(planned):
    variables = context(planned=planned)
    assert all(evaluate(value, variables) for value in GUARD["when"])
    assert evaluate(GUARD["ansible.builtin.assert"]["that"], variables) is planned
    assert not evaluate(ACTIVATE["when"], variables)
    assert not evaluate(HANDLER["when"], variables)


def test_loaded_unit_retains_activation_and_handler_checks():
    variables = context(loaded=True)
    assert not all(evaluate(value, variables) for value in GUARD["when"])
    assert evaluate(ACTIVATE["when"], variables)
    assert evaluate(HANDLER["when"], variables)


def test_real_deployment_has_no_check_mode_discovery_dependency():
    variables = {"ansible_check_mode": False}
    assert not all(evaluate(value, variables) for value in GUARD["when"])
    assert evaluate(ACTIVATE["when"], variables)
    assert evaluate(HANDLER["when"], variables)


@pytest.mark.parametrize(("status", "code", "refused"), [
    ("loaded", 0, False), ("not-found", 0, False), ("not-found", 1, False),
    ("loaded", 1, True), ("error", 0, True), ("", 1, True),
    ("not-found", 2, True), ("not-found", 255, True),
])
def test_load_state_discovery_refuses_unknown_or_failed_results(status, code, refused):
    variables = {"_subscription_unit_existing": {"stdout": status, "rc": code}}
    assert evaluate(PROBE["failed_when"], variables) is refused


def test_probe_is_read_only_and_template_plan_precedes_guard():
    unit = BY_NAME["Install systemd unit"]
    assert unit["register"] == "_subscription_unit_plan"
    assert PROBE["ansible.builtin.command"]["argv"] == [
        "systemctl", "show", "vpn-bootstrap.service", "--property=LoadState", "--value",
    ]
    assert PROBE["check_mode"] is False
    assert PROBE["changed_when"] is False
    assert TASKS.index(unit) < TASKS.index(PROBE) < TASKS.index(GUARD) < TASKS.index(ACTIVATE)
