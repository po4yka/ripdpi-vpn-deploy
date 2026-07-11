"""Regression coverage for state-bound, fail-closed destruction."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_RESOURCES = {
    "upcloud": ("upcloud_server.vpn", "hostname"),
    "hetzner": ("hcloud_server.vpn", "name"),
    "vultr": ("vultr_instance.vpn", "hostname"),
}
ALLOWED_EXTRAS = {
    "upcloud": ["upcloud_firewall_rules.vpn"],
    "hetzner": [
        "hcloud_ssh_key.admin",
        "hcloud_firewall.vpn",
        "hcloud_firewall_attachment.vpn",
        "hcloud_floating_ip.honeypot_ipv4[0]",
    ],
    "vultr": [
        "vultr_ssh_key.admin",
        "vultr_firewall_group.vpn",
        "vultr_instance_ipv4.honeypot[0]",
        'vultr_firewall_rule.icmp["allow"]',
        'vultr_firewall_rule.ssh["admin"]',
        'vultr_firewall_rule.tcp_public["443"]',
    ],
}


def _test_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in ("destroy.sh", "terraform-env.sh"):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts / name)
    for provider in SERVER_RESOURCES:
        (root / f"terraform/providers/{provider}/environments").mkdir(parents=True)
    return root


def _terraform_stub(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    stub = tmp_path / "terraform"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$STUB_LOG\"\n"
        "while [[ \"${1:-}\" == -chdir=* ]]; do shift; done\n"
        "if [[ \"${1:-}\" == plan && -n \"${OVERRIDE_PATH:-}\" ]]; then cat \"$OVERRIDE_PATH\" >> \"$STUB_LOG\"; fi\n"
        "if [[ \"${1:-}\" == show ]]; then cat \"$PLAN_JSON_FILE\"; exit \"${SHOW_EXIT:-0}\"; fi\n"
        "if [[ \"${1:-}\" == apply && \"${FAIL_APPLY:-false}\" == true ]]; then exit 1; fi\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _change(
    address: str,
    *,
    actions: list[str] | None = None,
    before: object | None = None,
) -> dict[str, object]:
    return {
        "address": address,
        "change": {
            "actions": actions if actions is not None else ["delete"],
            "before": before if before is not None else {},
        },
    }


def _server_change(
    provider: str,
    *,
    identity: str = "vpn-ci.test",
    resource_id: object = "server-123",
    actions: list[str] | None = None,
    identity_field: str | None = None,
) -> dict[str, object]:
    address, expected_field = SERVER_RESOURCES[provider]
    return _change(
        address,
        actions=actions,
        before={(identity_field or expected_field): identity, "id": resource_id},
    )


def _run(
    root: Path,
    stub_dir: Path,
    env_name: str,
    *,
    provider: str = "upcloud",
    changes: list[dict[str, object]] | None = None,
    desired_hostname: str = "vpn-ci.test",
    non_interactive: bool = True,
    input_text: str | None = None,
    fail_apply: bool = False,
    show_exit: int = 0,
    raw_plan: str | None = None,
) -> subprocess.CompletedProcess[str]:
    tfvars = root / f"terraform/providers/{provider}/environments/{env_name}.tfvars"
    tfvars.write_text(f'server_name = "{desired_hostname}"\n')
    plan_json = stub_dir / "plan.json"
    plan_json.write_text(raw_plan if raw_plan is not None else json.dumps({"resource_changes": changes if changes is not None else [_server_change(provider)]}))
    temp_dir = stub_dir / "tmp"
    temp_dir.mkdir(exist_ok=True)
    env = os.environ | {
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "PROVIDER": provider,
        "ENV": env_name,
        "STUB_LOG": str(stub_dir / "terraform.log"),
        "OVERRIDE_PATH": str(root / f"terraform/providers/{provider}/_destroy_override.tf"),
        "PLAN_JSON_FILE": str(plan_json),
        "FAIL_APPLY": str(fail_apply).lower(),
        "SHOW_EXIT": str(show_exit),
        "TMPDIR": str(temp_dir),
    }
    command = ["bash", str(root / "scripts/destroy.sh")]
    if non_interactive:
        command.append("--non-interactive")
    return subprocess.run(
        command,
        cwd=root,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=10,
    )


def _log(stub_dir: Path) -> str:
    path = stub_dir / "terraform.log"
    return path.read_text() if path.exists() else ""


def _assert_no_apply(stub_dir: Path) -> None:
    assert not any(" apply " in f" {line} " for line in _log(stub_dir).splitlines())


@pytest.mark.parametrize("provider", SERVER_RESOURCES)
def test_ci_destroy_accepts_state_identity_for_each_provider(tmp_path: Path, provider: str) -> None:
    root = _test_repo(tmp_path)
    env_name = f"ci-123-{provider}"
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name, provider=provider)

    assert result.returncode == 0, result.stderr
    assert "CI destroy authorization accepted" in result.stdout
    assert f"address={SERVER_RESOURCES[provider][0]}" in result.stdout
    assert "planned_identity=vpn-ci.test" in result.stdout
    assert "id=server-123" in result.stdout
    assert f'resource "{SERVER_RESOURCES[provider][0].split(".")[0]}" "vpn"' in _log(stub.parent)
    assert " apply " in f" {_log(stub.parent)} "


def test_ci_destroy_cleans_inventory_override_and_temp_json_after_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-123-cleanup"
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\n")
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name)

    assert result.returncode == 0, result.stderr
    assert not inventory.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert not list((stub.parent / "tmp").iterdir())


def test_noninteractive_destroy_rejects_non_ci_environment(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "prod")

    assert result.returncode == 2
    assert "restricted to validated ci-* environments" in result.stderr
    assert not (stub.parent / "terraform.log").exists()


def test_failed_ci_destroy_keeps_inventory_for_diagnosis(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\n")
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-failure", fail_apply=True)

    assert result.returncode != 0
    assert inventory.exists()


def test_destroy_rejects_unknown_provider_before_writing_override(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)
    env = os.environ | {"PATH": f"{stub.parent}:{os.environ['PATH']}", "PROVIDER": "unknown", "ENV": "ci-123-unknown"}

    result = subprocess.run(
        ["bash", str(root / "scripts/destroy.sh"), "--non-interactive"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert "unsupported PROVIDER for destroy" in result.stderr


def test_ci_mismatch_refuses_apply_and_cleans_temporary_files(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-mismatch", desired_hostname="desired.test")

    assert result.returncode != 0
    assert "does not match planned state identity" in result.stderr
    _assert_no_apply(stub.parent)
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert not list((stub.parent / "tmp").iterdir())


@pytest.mark.parametrize("resource_id", ["__missing__", None, "", {}, [], "(known after apply)"])
def test_missing_null_empty_or_structured_id_refuses_apply(tmp_path: Path, resource_id: object) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)
    change = _server_change("upcloud", resource_id=resource_id)
    if resource_id == "__missing__":
        before = change["change"]["before"]  # type: ignore[index]
        assert isinstance(before, dict)
        before.pop("id")

    result = _run(root, stub.parent, "ci-123-id", changes=[change])

    assert result.returncode != 0
    assert "no usable immutable id" in result.stderr
    _assert_no_apply(stub.parent)


def test_wrong_provider_identity_field_refuses_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-field", changes=[_server_change("upcloud", identity_field="name")])

    assert result.returncode != 0
    assert "no usable state identity field hostname" in result.stderr
    _assert_no_apply(stub.parent)


def test_duplicate_server_change_refuses_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-duplicate", changes=[_server_change("upcloud"), _server_change("upcloud")])

    assert result.returncode != 0
    assert "exactly one change" in result.stderr
    _assert_no_apply(stub.parent)


def test_destroy_refuses_apply_when_plan_lacks_expected_server_address(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-no-server", changes=[_change("upcloud_firewall_rules.vpn")])

    assert result.returncode != 0
    assert "exactly one change for upcloud_server.vpn; found 0" in result.stderr
    _assert_no_apply(stub.parent)


def test_server_change_without_delete_refuses_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-update", changes=[_server_change("upcloud", actions=["update"])])

    assert result.returncode != 0
    assert "does not delete expected resource" in result.stderr
    _assert_no_apply(stub.parent)


def test_unexpected_delete_names_address_and_refuses_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)
    unexpected = "upcloud_storage.unreviewed"

    result = _run(root, stub.parent, "ci-123-extra", changes=[_server_change("upcloud"), _change(unexpected)])

    assert result.returncode != 0
    assert unexpected in result.stderr
    _assert_no_apply(stub.parent)


@pytest.mark.parametrize("provider", SERVER_RESOURCES)
def test_provider_allowlist_accepts_all_documented_optional_and_keyed_deletes(tmp_path: Path, provider: str) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)
    changes = [_server_change(provider), *(_change(address) for address in ALLOWED_EXTRAS[provider])]

    result = _run(root, stub.parent, f"ci-123-allow-{provider}", provider=provider, changes=changes)

    assert result.returncode == 0, result.stderr
    assert " apply " in f" {_log(stub.parent)} "


def test_vultr_allowlist_rejects_unapproved_keyed_rule_family(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)
    address = 'vultr_firewall_rule.udp_public["53"]'

    result = _run(root, stub.parent, "ci-123-key", provider="vultr", changes=[_server_change("vultr"), _change(address)])

    assert result.returncode != 0
    assert address in result.stderr
    _assert_no_apply(stub.parent)


def test_interactive_desired_hostname_only_is_not_authorization(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "dev", non_interactive=False, input_text="vpn-ci.test\n")

    assert result.returncode != 0
    assert "planned resource identity mismatch" in result.stderr
    _assert_no_apply(stub.parent)


def test_interactive_mismatch_acknowledgement_and_state_token_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(
        root,
        stub.parent,
        "dev",
        desired_hostname="desired.test",
        non_interactive=False,
        input_text="STATE-MISMATCH\nvpn-ci.test#server-123\nDESTROY\nyes\n",
    )

    assert result.returncode == 0, result.stderr
    assert "desired.test" in result.stderr
    assert "vpn-ci.test" in result.stderr
    assert " apply " in f" {_log(stub.parent)} "


@pytest.mark.parametrize("raw_plan", ["not-json", '{"resource_changes":{}}', '{"resource_changes":[{"address":"upcloud_server.vpn","change":{}}]}'])
def test_malformed_plan_refuses_apply(tmp_path: Path, raw_plan: str) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-malformed", raw_plan=raw_plan)

    assert result.returncode != 0
    assert "malformed" in result.stderr
    _assert_no_apply(stub.parent)


def test_failed_show_refuses_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "ci-123-show", show_exit=1)

    assert result.returncode != 0
    assert "failed to render" in result.stderr
    _assert_no_apply(stub.parent)


def test_ci_workflows_do_not_suppress_destroy_failure_or_cleanup_tfvars_early() -> None:
    for workflow in ("real-vps-deploy.yml", "transport-reachability-matrix.yml"):
        source = (REPO_ROOT / ".github/workflows" / workflow).read_text()
        assert "make destroy DESTROY_ARGS=--non-interactive" in source
        assert "make destroy || true" not in source
        assert 'rm -f "terraform/providers/upcloud/environments/${CI_ENV}.tfvars"' in source
        assert "env.CI_ENV != ''" in source
