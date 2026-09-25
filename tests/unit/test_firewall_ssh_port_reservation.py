"""The firewall role rejects public listeners on the effective SSH port.

Evaluates the real task from ansible/roles/firewall/tasks/main.yml with the
pinned ansible-core templar, so the test and the deploy share one expression.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ansible.errors import AnsibleTemplateError
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "ansible" / "roles" / "firewall" / "tasks" / "main.yml"
TASK_NAME = "Reject public listeners on the effective SSH port"


def _tasks() -> list[dict]:
    return yaml.safe_load(TASKS.read_text())


def _task() -> dict:
    return next(task for task in _tasks() if task["name"] == TASK_NAME)


def _listener(name: str, protocol: str, port: int | None = None, port_range: str | None = None) -> dict:
    return {"name": name, "protocol": protocol, "port": port, "port_range": port_range}


def _evaluate(contract: list[dict], ssh_port: int) -> tuple[bool, list[str]]:
    task = _task()
    variables = {
        "public_listener_contract": contract,
        "firewall_effective_ssh_ports": [ssh_port],
    }
    templar = Templar(loader=DataLoader(), variables=variables)
    names = templar.template(trust_as_template(task["vars"]["_firewall_ssh_port_listeners"]))
    templar.available_variables = {**variables, "_firewall_ssh_port_listeners": names}
    passed = all(
        templar.template(trust_as_template("{{ " + condition + " }}"))
        for condition in task["ansible.builtin.assert"]["that"]
    )
    return passed, names


@pytest.mark.parametrize(
    ("contract", "expected"),
    [
        ([_listener("honeypot", "tcp", 2222)], ["honeypot"]),
        ([_listener("probe-hops", "tcp", port_range="2000-3000")], ["probe-hops"]),
        ([_listener("edge", " TCP", 2222), _listener("low", "tcp", port_range="2222-2222")], ["edge", "low"]),
        # nftables.conf.j2 renders `port` whenever it is set, so it wins here too.
        ([_listener("both", "tcp", 2222, port_range="4000-5000")], ["both"]),
    ],
)
def test_tcp_listener_on_ssh_port_fails(contract: list[dict], expected: list[str]) -> None:
    assert _evaluate(contract, 2222) == (False, expected)


@pytest.mark.parametrize(
    "contract",
    [
        [],
        [_listener("honeypot", "tcp", 4443), _listener("xray", "tcp", 443)],
        [_listener("hysteria", "udp", 2222), _listener("hops", "udp", port_range="2000-3000")],
        [_listener("below", "tcp", port_range="2000-2221"), _listener("above", "tcp", port_range="2223-3000")],
    ],
)
def test_contract_without_tcp_ssh_claim_passes(contract: list[dict]) -> None:
    assert _evaluate(contract, 2222) == (True, [])


def test_tcp_listener_without_port_fails_closed() -> None:
    with pytest.raises(AnsibleTemplateError):
        _evaluate([_listener("broken", "tcp")], 2222)


def test_failure_message_names_listener_and_port() -> None:
    task = _task()
    variables = {
        "firewall_effective_ssh_ports": [2222],
        "_firewall_ssh_port_listeners": ["honeypot"],
    }
    message = Templar(loader=DataLoader(), variables=variables).template(
        trust_as_template(task["ansible.builtin.assert"]["fail_msg"])
    )
    assert "honeypot" in message
    assert "tcp/2222" in message


def test_check_precedes_firewall_mutation() -> None:
    names = [task["name"] for task in _tasks()]
    check = names.index(TASK_NAME)
    assert names.index("Require one effective SSH listener port") < check
    assert check < names.index("Disable provider-image UFW firewall")
    assert check < names.index("Render nftables config")
    # Nothing may skip the check: no condition, tag or check-mode override.
    assert not {"when", "tags", "check_mode"} & _task().keys()
