"""Baseline runtime sysctls must recover after an interrupted play."""

from pathlib import Path

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


def test_only_optional_congestion_control_can_ignore_native_setting_failure():
    config = (ROOT / "ansible/roles/baseline/templates/sysctl-vpn.conf.j2").read_text()
    tasks = (ROOT / "ansible/roles/baseline/tasks/forwarding.yml").read_text()
    optional = [line for line in config.splitlines() if line.startswith("-")]
    assert optional == ["-net.ipv4.tcp_congestion_control = bbr"]
    assert "failed_when:" not in tasks
    assert "/usr/local/libexec/vpn-baseline-sysctl" in tasks
