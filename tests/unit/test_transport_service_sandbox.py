"""Internet-facing transport units must carry the uniform sandbox baseline."""
from __future__ import annotations

from pathlib import Path


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
