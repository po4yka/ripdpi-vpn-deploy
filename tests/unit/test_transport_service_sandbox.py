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


@pytest.mark.parametrize("shared_tls", [False, True])
def test_realm_user_group_arguments_match_the_tls_ownership_mode(shared_tls) -> None:
    tasks = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/hysteria-realm/tasks/main.yml").read_text()
    )
    task = next(task for task in tasks if task.get("name") == "Ensure system user")
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    omitted = object()
    values = {}
    for name in ("groups", "append"):
        value = task["ansible.builtin.user"][name]
        if isinstance(value, str) and value.startswith("{{"):
            value = environment.compile_expression(value[2:-2].strip())(
                hysteria_realm={"share_hysteria_tls": shared_tls}, omit=omitted
            )
        values[name] = value

    if shared_tls:
        assert values["groups"] == ["hysteria"]
        assert values["append"] is True  # preserve unrelated supplementary groups
    else:
        assert values["groups"] is omitted
        # ansible.builtin.user rejects append=true when groups is omitted.
        assert values["append"] is False or values["append"] is omitted
