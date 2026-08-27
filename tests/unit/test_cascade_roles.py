"""Structural contracts for inert cascade roles and their deploy guards."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"


def test_roles_have_required_scaffold_and_distinct_namespaces() -> None:
    for role in ("cascade-ingress", "cascade-egress"):
        root = ANSIBLE / "roles" / role
        for relative in ("CLAUDE.md", "tasks/main.yml", "defaults/main.yml", "handlers/main.yml"):
            assert (root / relative).is_file()
        assert list((root / "templates").glob("*.j2"))

    ingress_policy = (ANSIBLE / "roles/cascade-ingress/templates/cascade-ingress.nft.j2").read_text()
    egress_policy = (ANSIBLE / "roles/cascade-egress/templates/cascade-egress.nft.j2").read_text()
    assert "cascade_ingress" in ingress_policy
    assert "cascade_egress" in egress_policy
    assert "split_hop" not in ingress_policy + egress_policy


def test_ingress_preflights_dataset_before_serving_configuration() -> None:
    tasks = (ANSIBLE / "roles/cascade-ingress/tasks/main.yml").read_text()

    assert tasks.index("Preflight classifier dataset") < tasks.index("Render disabled classifier integration contract")
    assert tasks.index("Preflight classifier dataset") < tasks.index("Render cascade ingress tunnel")
    assert "--check-dataset" in tasks
    assert "systemd_service" not in tasks


def test_ingress_installs_concrete_proxy_but_unit_is_repository_disabled() -> None:
    role = ANSIBLE / "roles/cascade-ingress"
    tasks = (role / "tasks/main.yml").read_text()
    unit = (role / "templates/cascade-classifier-proxy.service.j2").read_text()

    assert "cascade-classifier-proxy.py" in tasks
    assert "cascade_classifier_lib.py" in tasks
    assert "classifier_proxy_password" in tasks
    assert "ExecCondition=/usr/bin/false" in unit
    assert "cascade-classifier-proxy.py" in unit
    assert "systemd_service" not in tasks


def test_ingress_installs_probe_machinery_but_cannot_schedule_it() -> None:
    role = ANSIBLE / "roles/cascade-ingress"
    tasks = (role / "tasks/main.yml").read_text()
    service = (role / "templates/cascade-leg-probe.service.j2").read_text()
    timer = (role / "templates/cascade-leg-probe.timer.j2").read_text()

    assert "cascade-leg-probe.py" in tasks
    assert "cascade-leg-probe-config.schema.json" in tasks
    assert "python3-jsonschema" in tasks
    assert "ExecCondition=/usr/bin/false" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "systemd_service" not in tasks


def test_neither_role_has_an_operator_service_activation_switch() -> None:
    for role in ("cascade-ingress", "cascade-egress"):
        root = ANSIBLE / "roles" / role
        content = "\n".join(path.read_text() for path in root.rglob("*.yml"))

        assert "manage_service" not in content
        assert "systemd_service" not in (root / "tasks/main.yml").read_text()


def test_each_role_starts_with_direct_execution_colocation_guard() -> None:
    for role in ("cascade-ingress", "cascade-egress"):
        tasks = yaml.safe_load((ANSIBLE / "roles" / role / "tasks/main.yml").read_text())
        assert tasks[0]["name"] == "Assert cascade and split-hop role families are not co-located"
        assert tasks[0]["tags"] == ["always"]


@pytest.mark.parametrize(
    ("cascade_role", "split_toggle"),
    [
        ("cascade-ingress", "enable_split_hop_ingress"),
        ("cascade-ingress", "enable_split_hop_egress"),
        ("cascade-egress", "enable_split_hop_ingress"),
        ("cascade-egress", "enable_split_hop_egress"),
    ],
)
def test_direct_role_guard_covers_every_cross_family_pairing(cascade_role: str, split_toggle: str) -> None:
    first = yaml.safe_load((ANSIBLE / "roles" / cascade_role / "tasks/main.yml").read_text())[0]
    guard = str(first)

    assert split_toggle in guard
    assert "not split_hop_role_family_enabled" in guard
    assert "cascade_role_family_enabled" not in guard


def test_egress_has_no_classifier_or_geodata_knowledge() -> None:
    role = ANSIBLE / "roles/cascade-egress"
    egress = "\n".join(
        path.read_text()
        for subtree in ("tasks", "defaults", "handlers", "templates")
        for path in (role / subtree).rglob("*")
        if path.is_file()
    )

    assert "classifier" not in egress.lower()
    assert "geoip" not in egress.lower()
    assert "geodata" not in egress.lower()


def test_cascade_roles_are_exception_tier_and_disabled_in_family_profiles() -> None:
    manifest = yaml.safe_load((ANSIBLE / "role-tiers.yml").read_text())
    assert manifest["tiers"]["cascade-ingress"] == "exception"
    assert manifest["tiers"]["cascade-egress"] == "exception"
    assert manifest["cascade_governance_status"] == "implementation-only"

    for relative in manifest["family_profiles"]:
        text = (ANSIBLE / relative).read_text()
        profile = yaml.safe_load(text)
        # Canonical defaults declare the complete toggle surface explicitly;
        # absent per-cohort overrides and literal false must both stay inert.
        for toggle in ("enable_cascade_ingress", "enable_cascade_egress"):
            assert profile.get("vpn", {}).get(toggle, False) is False
        assert "allow_exception_roles" not in text


def test_site_has_attestation_and_colocation_guards_before_roles() -> None:
    site = (ANSIBLE / "playbooks/site.yml").read_text()
    first_role = site.index("  roles:")

    assert site.index("verify cascade ASN attestation") < first_role
    assert site.index("verify fresh cascade per-leg protocol completion") < first_role
    assert site.index("implementation-only governance") < first_role
    assert "lookup('file', playbook_dir ~ '/../role-tiers.yml')" in site
    assert ".cascade_governance_status == 'live-authorized'" in site
    assert site.index("mutually exclusive") < first_role
    assert site.index("classifier owns every egress decision") < first_role
    assert "enable_cascade_ingress" in site[site.index("classifier owns every egress decision") : site.index("verify cascade ASN attestation")]
    assert "enable_warp_outbound" in site[site.index("classifier owns every egress decision") : site.index("verify cascade ASN attestation")]
    assert site.index("role: cascade-ingress") > first_role
    assert site.index("role: cascade-egress") > first_role
