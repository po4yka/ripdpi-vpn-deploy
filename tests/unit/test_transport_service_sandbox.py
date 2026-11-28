"""Internet-facing transport units must carry the uniform sandbox baseline."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parents[2]

BOOLEAN_BASELINE = (
    "NoNewPrivileges",
    "PrivateTmp",
    "ProtectHome",
    "ProtectKernelTunables",
    "ProtectKernelModules",
    "ProtectControlGroups",
    "RestrictNamespaces",
    "MemoryDenyWriteExecute",
    "LockPersonality",
    "RestrictRealtime",
    "RestrictSUIDSGID",
)

SCALAR_BASELINE = (
    "ProtectSystem=strict",
    "SystemCallArchitectures=native",
    "SystemCallFilter=@system-service",
)

UNITS = {
    "ansible/roles/hysteria/templates/hysteria-server.service.j2": "CAP_NET_BIND_SERVICE",
    "ansible/roles/xray/templates/xray.service.j2": "CAP_NET_BIND_SERVICE",
    "ansible/roles/hysteria-realm/templates/hysteria-realm.service.j2": "CAP_NET_BIND_SERVICE",
    "ansible/roles/snell/templates/snell.service.j2": "CAP_NET_BIND_SERVICE",
    "ansible/roles/probe-matrix-target/templates/probe-matrix-xray.service.j2": "CAP_NET_BIND_SERVICE",
    "ansible/roles/probe-matrix-target/templates/probe-matrix-mtg.service.j2": "CAP_NET_BIND_SERVICE",
    "ansible/roles/real-vps-awg-nat/templates/server-awg.service.j2": "CAP_NET_ADMIN",
    "ansible/roles/real-vps-awg-nat/templates/echo.service.j2": "",
    "ansible/roles/real-vps-awg-nat/templates/firewall.service.j2": "CAP_NET_ADMIN",
}


def test_transport_units_carry_the_sandbox_baseline() -> None:
    for rel, capability in UNITS.items():
        unit = (REPO_ROOT / rel).read_text()
        for name in BOOLEAN_BASELINE:
            assert any(
                line in unit for line in (f"{name}=true", f"{name}=yes")
            ), f"{rel} lacks enabled {name}"
        for directive in SCALAR_BASELINE:
            assert directive in unit, f"{rel} lacks {directive}"
        if capability:
            assert f"CapabilityBoundingSet={capability}" in unit
            assert f"AmbientCapabilities={capability}" in unit
        else:
            assert "CapabilityBoundingSet=" not in unit
            assert "AmbientCapabilities=" not in unit


def test_public_proxy_units_restrict_socket_families() -> None:
    for rel in ("ansible/roles/xray/templates/xray.service.j2",
                "ansible/roles/hysteria/templates/hysteria-server.service.j2"):
        unit = (REPO_ROOT / rel).read_text().splitlines()
        assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK" in unit, rel


def test_xray_unit_hides_host_state_and_stays_below_the_host_file_table() -> None:
    unit = (REPO_ROOT / "ansible/roles/xray/templates/xray.service.j2").read_text().splitlines()
    for directive in ("ProtectProc=invisible", "PrivateDevices=yes", "ProtectClock=yes",
                      "ProtectKernelLogs=yes", "ProtectHostname=yes", "UMask=0077"):
        assert directive in unit, directive
    sysctl = (REPO_ROOT / "ansible/roles/baseline/templates/sysctl-vpn.conf.j2").read_text()
    file_max = next(int(line.split("=")[1]) for line in sysctl.splitlines() if line.startswith("fs.file-max"))
    limit = next(int(line.split("=")[1]) for line in unit if line.startswith("LimitNOFILE="))
    assert limit < file_max


def test_public_tls_coordinator_can_inspect_cross_uid_nginx_workers():
    unit = (REPO_ROOT / 'ansible/roles/nginx-xhttp/templates/vpn-public-tls.service.j2').read_text()
    capabilities = next(line.split('=', 1)[1].split() for line in unit.splitlines()
                        if line.startswith('CapabilityBoundingSet='))
    assert set(capabilities) == {
        'CAP_CHOWN', 'CAP_DAC_OVERRIDE', 'CAP_FOWNER', 'CAP_NET_BIND_SERVICE',
        'CAP_SYS_ADMIN', 'CAP_SYS_CHROOT', 'CAP_SYS_PTRACE',
    }


@pytest.mark.parametrize('sharing', [False, True])
def test_direct_realm_refuses_native_acme_before_mutation(sharing):
    tasks = yaml.safe_load((REPO_ROOT / 'ansible/roles/hysteria-realm/tasks/enable.yml').read_text())
    guard = tasks[0]['ansible.builtin.assert']['that'][0]
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    evaluate = environment.compile_expression(guard)
    assert evaluate(hysteria={'cert_pem': 'owned'}, hysteria_realm={'share_hysteria_tls': sharing})
    assert not evaluate(hysteria={'acme': {}}, hysteria_realm={'share_hysteria_tls': sharing})


def test_non_net_admin_units_exclude_privileged_and_resource_syscalls() -> None:
    for rel, capability in UNITS.items():
        if capability == "CAP_NET_ADMIN":
            continue
        unit = (REPO_ROOT / rel).read_text()
        assert "SystemCallFilter=~@privileged @resources" in unit, rel


def test_net_admin_units_document_the_privileged_syscall_filter_exemption() -> None:
    for rel, capability in UNITS.items():
        if capability != "CAP_NET_ADMIN":
            continue
        unit = (REPO_ROOT / rel).read_text()
        assert "CAP_NET_ADMIN workload: do not deny @privileged" in unit, rel


def test_transport_units_run_as_dedicated_non_root_users() -> None:
    non_root_units = {
        rel for rel, capability in UNITS.items() if capability != "CAP_NET_ADMIN"
    }
    for rel in non_root_units:
        unit = (REPO_ROOT / rel).read_text()
        assert "User=root" not in unit
        assert (
            "\nUser=" in unit and "\nGroup=" in unit
        ) or "\nDynamicUser=true" in unit, rel


def test_realm_identity_and_tls_copy_exclude_hysteria_group() -> None:
    tasks = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/hysteria-realm/tasks/enable.yml").read_text()
    )
    user = next(task["ansible.builtin.user"] for task in tasks if "ansible.builtin.user" in task)
    assert user["group"] == "hysteria-realm" and user["groups"] == "" and user["append"] is False
    tls_tasks = [task for task in tasks if task.get("ansible.builtin.copy", {}).get("group") == "hysteria-realm"]
    assert len(tls_tasks) == 2
    assert all(task["notify"] == "Restart hysteria-realm" and task["no_log"] for task in tls_tasks)
    for task in tls_tasks:
        copy = task["ansible.builtin.copy"]
        assert copy["owner"] == "root" and copy["mode"] == "0640" and copy["follow"] is False
    unit = (REPO_ROOT / "ansible/roles/hysteria-realm/templates/hysteria-realm.service.j2").read_text()
    assert "InaccessiblePaths=" in unit and "/config.yaml" in unit
    assert "IPAddressDeny=localhost" in unit


def test_hysteria_unit_keeps_connection_records_out_of_the_journal() -> None:
    unit = (REPO_ROOT / "ansible/roles/hysteria/templates/hysteria-server.service.j2").read_text()
    assert "Environment=HYSTERIA_LOG_LEVEL=warn" in unit
