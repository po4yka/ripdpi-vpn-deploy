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
    assert "command -v cloud-init" in target
    assert "command -v docker" in target
    assert "cloud-init schema --config-file /dev/stdin" in target
    assert "missing: cloud-init (or docker fallback)" in target
    assert "set -eu" in target


def test_inventory_uses_the_local_fleet_profile_when_present():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("inventory:", 1)[1].split("\n\nwait:", 1)[0]

    assert "-include .fleet.mk" in makefile
    assert 'HOSTS="$(HOSTS)"' in target
    assert 'COHORTS="$(COHORTS)"' in target


def test_client_emitters_receive_the_local_fleet_profile():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()

    for target in ("emit-singbox", "emit-bundle"):
        body = makefile.split(f"{target}:", 1)[1].split("\n\n", 1)[0]
        for variable in ("HOSTS", "COHORTS", "SOPS_FILE", "SOPS_FILES"):
            assert f'{variable}="$({variable})"' in body
        assert "\n\t@HOSTS=" in body

    awg = makefile.split("emit-awg:", 1)[1].split("\n\n", 1)[0]
    assert 'SOPS_FILE="$(SOPS_FILE)"' in awg
    assert "\n\t@SOPS_FILE=" in awg


def test_subscription_issuers_honor_the_explicit_sops_file():
    root = Path(__file__).resolve().parents[2]
    for script in ("issue-bootstrap.sh", "issue-sub-token.sh"):
        source = (root / "scripts" / script).read_text()
        assert 'sops_file="${SOPS_FILE:-' in source


def test_yamllint_excludes_git_ignored_local_state():
    root = Path(__file__).resolve().parents[2]
    config = (root / ".yamllint.yml").read_text()

    assert "  secrets/local/\n" in config
    assert "  state-backups/\n" in config


def test_check_prereqs_rejects_terraform_older_than_project_floor():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("check-prereqs:", 1)[1].split("\n\ninit:", 1)[0]

    assert "terraform version -json" in target
    assert "Terraform >= 1.15 required" in target


def test_live_ansible_targets_require_a_nonempty_generated_inventory():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    guard = makefile.split("require-inventory:", 1)[1].split(
        "\n\npre-deploy-check:", 1
    )[0]

    assert 'test -s "$(ANSIBLE_DIR)/inventory/generated.ini"' in guard
    assert 'document.get("vpn", {}).get("hosts", [])' in guard
    for target in (
        "dry-run",
        "deploy",
        "verify",
        "security-verify",
        "xray-diagnostics",
    ):
        declaration = next(
            line for line in makefile.splitlines() if line.startswith(f"{target}:")
        )
        assert "require-inventory" in declaration


def test_xray_diagnostics_rejects_unsafe_extra_vars_files():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("validate-ansible-extra-vars:", 1)[1].split(
        "\n\npre-deploy-check", 1
    )[0]

    assert "follow_symlinks=False" in target
    assert "s.st_uid == os.geteuid()" in target
    assert "stat.S_IMODE(s.st_mode) == 0o600" in target

    for live_target in (
        "dry-run",
        "deploy",
        "verify",
        "security-verify",
        "xray-diagnostics",
    ):
        declaration = next(
            line for line in makefile.splitlines() if line.startswith(f"{live_target}:")
        )
        assert "validate-ansible-extra-vars" in declaration


def test_live_ansible_targets_forward_limit_and_extra_vars():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()

    for target_name, following in (
        ("dry-run", "deploy:"),
        ("deploy", "deploy-canary:"),
        ("verify", "security-verify:"),
        ("security-verify", "security-audit:"),
        ("xray-diagnostics", "awg-evidence-provision:"),
    ):
        target = makefile.split(f"{target_name}:", 1)[1].split(f"\n\n{following}", 1)[0]
        assert "ANSIBLE_LIMIT" in target
        assert "ANSIBLE_EXTRA_VARS_FILE" in target


def test_partial_verify_cannot_create_a_fleet_known_good_tag():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    target = makefile.split("verify:", 1)[1].split("\n\nsecurity-verify:", 1)[0]

    assert '"$(TAG_ON_SUCCESS)" = "1"' in target
    assert '"$(ANSIBLE_LIMIT)"' in target
    assert "requires an unbounded fleet verification" in target
