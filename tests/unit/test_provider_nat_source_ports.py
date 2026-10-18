"""Provider return-port authority refuses malformed direct role inputs."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
NAT_TASK = "Validate provider NAT source-port range before mutation"


def role_tasks(role):
    filename = "enable.yml" if role == "split-hop-egress" else "main.yml"
    return yaml.safe_load((ROOT / f"ansible/roles/{role}/tasks/{filename}").read_text())


def nat_validation_task(tasks, role):
    matches = [task for task in tasks if task.get("name") == NAT_TASK]
    assert len(matches) == 1
    task = matches[0]
    assert "ansible.builtin.assert" in task
    permitted_prefix = [{
        "name": "Admit scoped DHCPv6 prerequisites before firewall mutation",
        "ansible.builtin.import_tasks": "dhcpv6-admission.yml",
    }] if role == "firewall" else []
    assert tasks[:tasks.index(task)] == permitted_prefix
    return task


@pytest.mark.parametrize("role", ["firewall", "split-hop-egress"])
@pytest.mark.parametrize("fault", ["missing", "duplicate", "after-consumer", "unexpected-prefix"])
def test_nat_guard_selection_refuses_ambiguous_or_late_guards(role, fault):
    tasks = role_tasks(role)
    guard = next(task for task in tasks if task.get("name") == NAT_TASK)
    if fault == "missing":
        tasks.remove(guard)
    elif fault == "duplicate":
        tasks.append(guard.copy())
    else:
        name = ({
            "firewall": "Prepare retained firewall consumer authority",
            "split-hop-egress": "Install WireGuard tooling",
        } if fault == "after-consumer" else {
            "firewall": "Admit AmneziaWG dual-stack forwarding prerequisites before mutation",
            "split-hop-egress": "Pre-flight — egress secrets must be set",
        })[role]
        prefix = next(task for task in tasks if task.get("name") == name)
        tasks.remove(prefix)
        tasks.insert(tasks.index(guard), prefix)
    with pytest.raises(AssertionError):
        nat_validation_task(tasks, role)


def test_firewall_nat_guard_requires_the_exact_dhcp_preflight_import():
    tasks = role_tasks("firewall")
    tasks[0]["ansible.builtin.import_tasks"] = "consumer-prepare.yml"
    with pytest.raises(AssertionError):
        nat_validation_task(tasks, "firewall")


@pytest.mark.parametrize("role", ["firewall", "split-hop-egress"])
@pytest.mark.parametrize("value,ssh_port,valid", [
    ("32768-60999", 22, True),
    ("40000-45000", 2222, True),
    ("40000-40000", 22, True),
    (True, 22, False),
    (32768, 22, False),
    (None, 22, False),
    ("", 22, True),
    ("032768-60999", 22, False),
    ("1023-60999", 22, False),
    ("32768-65536", 22, False),
    ("60999-32768", 22, False),
    ("32768-60999", 40000, False),
    ("32768-60999 extra=unsafe", 22, False),
])
def test_role_refuses_unsafe_source_range_before_mutation(tmp_path, role, value, ssh_port, valid):
    task = nat_validation_task(role_tasks(role), role)
    play = [{"hosts": "localhost", "gather_facts": False, "vars": {
        "terraform_nat_source_port_range": value, "ansible_port": ssh_port,
    }, "tasks": [task]}]
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run([shutil.which("ansible-playbook"), "-i", "localhost,", "-c", "local", str(path)],
        text=True, capture_output=True, timeout=25,
        env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg"), "ANSIBLE_NOCOLOR": "1"})
    assert (result.returncode == 0) is valid, result.stdout + result.stderr
    if not valid:
        assert "provider-nat-source-port-range-invalid" in result.stdout
