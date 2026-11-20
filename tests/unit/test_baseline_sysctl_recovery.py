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
        "-net.netfilter.nf_conntrack_buckets = {{ (baseline_conntrack_max // 4) }}",
        "-net.netfilter.nf_conntrack_max = {{ baseline_conntrack_max }}",
        "-net.netfilter.nf_conntrack_udp_timeout = {{ baseline_conntrack_udp_timeout }}",
        "-net.netfilter.nf_conntrack_udp_timeout_stream = {{ baseline_conntrack_udp_timeout_stream }}",
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


@pytest.mark.parametrize("present", [False, True])
def test_mptcp_disable_is_mandatory_only_on_supported_kernels(present):
    from scripts.template_render import render_template

    template = ROOT / "ansible/roles/baseline/templates/sysctl-vpn.conf.j2"
    rendered = render_template(template, {"_baseline_mptcp_sysctl": {"stat": {"exists": present}},
        "baseline_udp_receive_buffer_max": 7500000, "baseline_udp_send_buffer_max": 7500000,
        "baseline_conntrack_max": 131072, "baseline_conntrack_udp_timeout": 60,
        "baseline_conntrack_udp_timeout_stream": 180})
    assert ("net.mptcp.enabled = 0" in rendered) is present
    assert "-net.mptcp.enabled" not in rendered
    tasks = yaml.safe_load((ROOT / "ansible/roles/baseline/tasks/main.yml").read_text())
    check = next(task for task in tasks if task.get("name") == "Require disabled MPTCP on supported kernels")
    assert check["ansible.builtin.assert"]["that"] == ["_baseline_mptcp_effective.stdout == '0'"]


@pytest.mark.parametrize("present", [False, True])
def test_bpf_jit_hardening_is_mandatory_only_where_the_kernel_exposes_it(present):
    from scripts.template_render import render_template

    template = ROOT / "ansible/roles/baseline/templates/sysctl-vpn.conf.j2"
    rendered = render_template(template, {"_baseline_bpf_jit_sysctl": {"stat": {"exists": present}},
        "baseline_udp_receive_buffer_max": 7500000, "baseline_udp_send_buffer_max": 7500000,
        "baseline_conntrack_max": 131072, "baseline_conntrack_udp_timeout": 60,
        "baseline_conntrack_udp_timeout_stream": 180})
    settings = [line for line in rendered.splitlines() if line and not line.startswith("#")]
    assert ("net.core.bpf_jit_harden = 2" in settings) is present
    assert not any(line.startswith("-net.core.bpf_jit_harden") for line in settings)
    for mandatory in (
        "net.ipv6.conf.all.accept_redirects = 0",
        "net.ipv6.conf.default.accept_redirects = 0",
        "kernel.kexec_load_disabled = 1",
    ):
        assert mandatory in settings


def test_security_verification_requires_disabled_mptcp_only_where_supported():
    tasks = yaml.safe_load((ROOT / "ansible/playbooks/security-verify.yml").read_text())[0]["tasks"]
    check = next(t for t in tasks if t.get("name") == "Verify MPTCP is disabled when the kernel provides it")
    assert check["when"] == "security_mptcp_control.stat.exists"
    assert check["failed_when"] == "security_mptcp_value.stdout != '0'"
    assert check["ansible.builtin.command"]["argv"] == ["sysctl", "-n", "net.mptcp.enabled"]
