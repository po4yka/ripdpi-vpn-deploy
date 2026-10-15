"""Baseline runtime sysctls must recover after an interrupted play."""

from pathlib import Path
import os
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_baseline_reconciles_sysctls_without_change_notifications():
    tasks = (ROOT / "ansible/roles/baseline/tasks/main.yml").read_text()
    handlers = (ROOT / "ansible/roles/baseline/handlers/main.yml").read_text()
    assert "ansible.builtin.import_tasks: forwarding.yml" in tasks
    tasks = (ROOT / "ansible/roles/baseline/tasks/forwarding.yml").read_text()

    assert "name: Reconcile effective sysctl values on every converge" in tasks
    assert "cmd: /usr/local/libexec/vpn-baseline-sysctl" in tasks
    assert "notify: Apply sysctl" not in tasks
    assert "name: Apply sysctl" not in handlers


def test_only_explicit_optional_performance_settings_can_ignore_native_failure():
    config = (ROOT / "ansible/roles/baseline/templates/sysctl-vpn.conf.j2").read_text()
    tasks = (ROOT / "ansible/roles/baseline/tasks/forwarding.yml").read_text()
    optional = [line for line in config.splitlines() if line.startswith("-")]
    assert optional == [
        "-net.core.default_qdisc = fq",
        "-net.ipv4.tcp_congestion_control = bbr",
        "-net.core.rmem_max = {{ baseline_udp_receive_buffer_max }}",
        "-net.core.wmem_max = {{ baseline_udp_send_buffer_max }}",
    ]
    assert "failed_when:" not in tasks
    assert "/usr/local/libexec/vpn-baseline-sysctl" in tasks


@pytest.mark.parametrize("receive,send,accepted", [
    (1048576, 1048576, True), (67108864, 67108864, True),
    (1048575, 7500000, False), (7500000, 67108865, False),
    (True, 7500000, False), ("7500000", 7500000, False),
])
def test_udp_resource_admission_precedes_mutating_tasks(tmp_path, receive, send, accepted):
    first = yaml.safe_load((ROOT / "ansible/roles/baseline/tasks/main.yml").read_text())[0]
    marker = tmp_path / "admitted"
    play = [{"hosts":"localhost", "connection":"local", "gather_facts":False, "become":False,
             "vars":{"ansible_python_interpreter":sys.executable,
                     "baseline_udp_receive_buffer_max":receive,
                     "baseline_udp_send_buffer_max":send},
             "tasks":[first, {"name":"Observe admitted mutation boundary",
                               "ansible.builtin.copy":{"dest":str(marker), "content":"admitted", "mode":"0600"}}]}]
    path = tmp_path / "admission.yml"
    path.write_text(yaml.safe_dump(play))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
        env={**os.environ,"ANSIBLE_CONFIG":str(ROOT / "ansible/ansible.cfg")},
        capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    assert marker.exists() is accepted
    if not accepted:
        assert "UDP socket ceilings must be integers" in result.stdout
