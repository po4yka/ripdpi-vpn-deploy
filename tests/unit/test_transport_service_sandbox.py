"""Internet-facing transport units must carry the uniform sandbox baseline."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined


REPO_ROOT = Path(__file__).resolve().parents[2]

BASELINE = (
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "ProtectHome=true",
    "ProtectSystem=strict",
    "ProtectKernelTunables=yes",
    "ProtectKernelModules=yes",
    "ProtectControlGroups=yes",
    "RestrictNamespaces=yes",
    "MemoryDenyWriteExecute=yes",
    "LockPersonality=yes",
    "RestrictRealtime=",
    "RestrictSUIDSGID=",
    "SystemCallArchitectures=native",
    "SystemCallFilter=@system-service",
    "SystemCallFilter=~@privileged @resources",
    "CapabilityBoundingSet=CAP_NET_BIND_SERVICE",
)

UNITS = (
    "ansible/roles/hysteria/templates/hysteria-server.service.j2",
    "ansible/roles/hysteria-realm/templates/hysteria-realm.service.j2",
    "ansible/roles/snell/templates/snell.service.j2",
)


def test_transport_units_carry_the_sandbox_baseline() -> None:
    for rel in UNITS:
        unit = (REPO_ROOT / rel).read_text()
        for directive in BASELINE:
            assert directive in unit, f"{rel} lacks {directive}"


def test_transport_units_run_as_dedicated_non_root_users() -> None:
    for rel in UNITS:
        unit = (REPO_ROOT / rel).read_text()
        assert "User=root" not in unit
        assert "\nUser=" in unit and "\nGroup=" in unit, rel


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
