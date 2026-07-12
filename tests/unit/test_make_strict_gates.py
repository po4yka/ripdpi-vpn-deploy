"""ci-fast and validate must not silently reduce their promised coverage."""

from pathlib import Path


def test_validate_checks_every_provider_and_ci_fast_has_no_tool_skips():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    ci = (root / ".github" / "workflows" / "ci.yml").read_text()
    for provider in ("upcloud", "hetzner", "vultr", "scaleway"):
        assert provider in makefile
    assert "skipped: ansible-playbook" not in makefile
    assert "skipped: cargo" not in makefile

    ci_fast = makefile.split("ci-fast:", 1)[1].split("\n\n# Union gate", 1)[0]
    for target in (
        "actionlint-check",
        "cloud-init-schema",
        "tf-test",
        "yamllint-check",
        "shellcheck",
        "vpnd-deny",
        "vpnd-msrv",
    ):
        assert f"$(MAKE) {target}" in ci_fast
    assert "python3 scripts/render-cloud-init-ci.py" in ci


def test_cloud_init_schema_has_a_pinned_container_fallback():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("cloud-init-schema:", 1)[1].split("\n\ntf-test:", 1)[0]

    assert "CLOUD_INIT_IMAGE ?= ubuntu:24.04@sha256:" in makefile
    assert 'command -v cloud-init' in target
    assert 'command -v docker' in target
    assert 'cloud-init schema --config-file /dev/stdin' in target
    assert 'missing: cloud-init (or docker fallback)' in target


def test_inventory_uses_the_local_fleet_profile_when_present():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("inventory:", 1)[1].split("\n\nwait:", 1)[0]

    assert "-include .fleet.mk" in makefile
    assert 'HOSTS="$(HOSTS)"' in target
    assert 'COHORTS="$(COHORTS)"' in target


def test_check_prereqs_rejects_terraform_older_than_project_floor():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("check-prereqs:", 1)[1].split("\n\ninit:", 1)[0]

    assert "terraform version -json" in target
    assert "Terraform >= 1.15 required" in target
