"""Regression coverage for fail-closed CI destruction."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_UUID = "00112233-4455-4677-8899-aabbccddeeff"
STORAGE_UUID = "ffeeddcc-bbaa-4988-8766-554433221100"


def _test_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in (
        "check-vultr-control-plane.py",
        "destroy.sh",
        "staging-cleanup-guard.py",
        "terraform-env.sh",
    ):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts / name)
    for provider in ("upcloud", "hetzner", "vultr", "scaleway"):
        (root / f"terraform/providers/{provider}/environments").mkdir(parents=True)
    return root


def _terraform_stub(tmp_path: Path, *, fail_apply: bool = False) -> Path:
    stub = tmp_path / "terraform"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\n\' "$*" >> "$STUB_LOG"\n'
        'TF_CHDIR=""\n'
        'while [[ "${1:-}" == -chdir=* ]]; do TF_CHDIR="${1#-chdir=}"; shift; done\n'
        'if [[ "${1:-}" == plan ]]; then for arg in "$@"; do if [[ "$arg" == -out=* ]]; then PLAN_PATH="${arg#-out=}"; [[ "$PLAN_PATH" == /* ]] || PLAN_PATH="${TF_CHDIR}/${PLAN_PATH}"; printf \'%s\\n\' guarded-plan > "$PLAN_PATH"; PLAN_MODE="$(/usr/bin/python3 -c \'import os,stat,sys; print(format(stat.S_IMODE(os.stat(sys.argv[1]).st_mode), "o"))\' "$PLAN_PATH")"; printf \'plan-mode=%s\\n\' "$PLAN_MODE" >> "$STUB_LOG"; if [[ -n "${RACE_PLAN_LOG:-}" ]]; then printf \'%s\\n\' "$PLAN_PATH" > "$RACE_PLAN_LOG"; fi; fi; done; fi\n'
        'if [[ "${1:-}" == plan && -n "${OVERRIDE_PATH:-}" ]]; then cat "$OVERRIDE_PATH" >> "$STUB_LOG"; fi\n'
        'if [[ "${1:-}" == show ]]; then if [[ -n "${RACE_PLAN_LOG:-}" ]]; then printf \'%s\\n\' substituted-plan > "$(cat "$RACE_PLAN_LOG")"; fi; printf \'show-plan-content=%s\\n\' "$(cat "$3")" >> "$STUB_LOG"; printf \'{"resource_changes":[{"address":"%s","change":{"actions":["delete"]}}]}\\n\' "$PLAN_RESOURCE"; exit 0; fi\n'
        'if [[ "${1:-}" == apply ]]; then printf \'apply-plan-content=%s\\n\' "$(cat "$2")" >> "$STUB_LOG"; fi\n'
        'if [[ "${1:-}" == apply && "${FAIL_APPLY:-false}" == true ]]; then exit 1; fi\n'
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    python = tmp_path / "python3"
    python.write_text("#!/usr/bin/env bash\nexit 0\n")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
    return stub


def _guard_stub(root: Path, *, fail_command: str = "") -> Path:
    guard = root / "scripts/staging-cleanup-guard.py"
    guard.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\n\' "$*" >> "$GUARD_LOG"\n'
        'if [[ "$1" == "${GUARD_FAIL_COMMAND:-}" ]]; then exit 9; fi\n'
        'if [[ "$1" == reserve-evidence || "$1" == authorize-reserve-evidence ]]; then\n'
        "  while [[ $# -gt 0 ]]; do\n"
        '    if [[ "$1" == --evidence-output ]]; then shift; printf \'%s\\n\' reserved > "$1"; chmod 600 "$1"; break; fi\n'
        "    shift\n"
        "  done\n"
        "fi\n"
        'if [[ "$1" == mark-apply-started ]]; then\n'
        "  while [[ $# -gt 0 ]]; do\n"
        '    if [[ "$1" == --evidence-output ]]; then shift; printf \'%s\\n\' apply_started > "$1"; chmod 600 "$1"; break; fi\n'
        "    shift\n"
        "  done\n"
        "fi\n"
        'if [[ "$1" == rewind-plan-fd ]]; then\n'
        "  shift\n"
        '  [[ "$1" == --fd-number ]]\n'
        "  shift\n"
        "  /usr/bin/python3 -c 'import os,sys; os.lseek(int(sys.argv[1]),0,os.SEEK_SET)' \"$1\"\n"
        "fi\n"
        'if [[ "$1" == release-evidence ]]; then\n'
        "  while [[ $# -gt 0 ]]; do\n"
        '    if [[ "$1" == --evidence-output ]]; then shift; rm -f "$1"; break; fi\n'
        "    shift\n"
        "  done\n"
        "fi\n"
    )
    guard.chmod(0o755)
    return guard


def _audit_stub(root: Path) -> Path:
    audit = root / "scripts/audit-log.sh"
    audit.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$AUDIT_LOG_STUB\"\n"
    )
    audit.chmod(0o755)
    return audit


def _make_staging_repo(tmp_path: Path) -> Path:
    root = tmp_path / "make-repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "Makefile", root / "Makefile")
    logger = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['MAKE_STAGING_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps({'program': os.path.basename(sys.argv[0]), "
        "'argv': sys.argv[1:], 'env': {key: os.environ.get(key) for key in "
        "['ENV', 'PROVIDER', 'STAGING_CLEANUP_MANIFEST', 'STAGING_CLEANUP_STATE', "
        "'STAGING_CLEANUP_HOSTNAME', "
        "'STAGING_POST_DESTROY_EVIDENCE', 'DEPLOY_SOURCE_REVISION', "
        "'DEPLOYABLE_SOURCE_DIGEST', 'UPCLOUD_USERNAME', 'UPCLOUD_PASSWORD', "
        "'UPCLOUD_API_USERNAME', 'UPCLOUD_API_PASSWORD']}}) + '\\n')\n"
    )
    for name in ("staging-cleanup-guard.py", "destroy.sh"):
        path = scripts / name
        path.write_text(logger)
        path.chmod(0o755)
    identity = scripts / "deploy-source-identity.sh"
    identity.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' called >> \"$MAKE_GIT_SPY\"\n"
    )
    identity.chmod(0o755)
    return root


def _run_staging_make(
    root: Path,
    tmp_path: Path,
    goal: str,
    *assignments: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for field in (
        "UPCLOUD_USERNAME",
        "UPCLOUD_PASSWORD",
        "UPCLOUD_API_USERNAME",
        "UPCLOUD_API_PASSWORD",
    ):
        env.pop(field, None)
    supplied_env = extra_env or {}
    if extra_env is None:
        env.update(
            {
                "UPCLOUD_USERNAME": "staging-test-user",
                "UPCLOUD_PASSWORD": "staging-test-password",
            }
        )
    env.update(supplied_env)
    env.update(
        {
            "MAKE_STAGING_LOG": str(tmp_path / "make-staging.jsonl"),
            "MAKE_GIT_SPY": str(tmp_path / "make-git-spy.log"),
        }
    )
    return subprocess.run(
        ["make", goal, *assignments],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize("goal", ["staging-cleanup-manifest", "staging-destroy"])
@pytest.mark.parametrize(
    "credential",
    [
        "UPCLOUD_USERNAME",
        "UPCLOUD_PASSWORD",
        "UPCLOUD_API_USERNAME",
        "UPCLOUD_API_PASSWORD",
    ],
)
def test_staging_make_refuses_command_line_credentials_before_expansion(
    tmp_path: Path, goal: str, credential: str
) -> None:
    root = _make_staging_repo(tmp_path)
    marker = tmp_path / f"{goal}-{credential}.marker"

    result = _run_staging_make(
        root,
        tmp_path,
        goal,
        f"{credential}=$(shell touch {marker})",
    )

    assert result.returncode != 0
    assert "credentials must come from the environment" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / "make-staging.jsonl").exists()
    assert not (tmp_path / "make-git-spy.log").exists()


@pytest.mark.parametrize("goal", ["staging-cleanup-manifest", "staging-destroy"])
@pytest.mark.parametrize("pair", ["primary", "alias"])
def test_staging_make_canonicalizes_one_literal_ambient_credential_pair(
    tmp_path: Path, goal: str, pair: str
) -> None:
    root = _make_staging_repo(tmp_path)
    marker = tmp_path / f"{goal}-{pair}.marker"
    literal_password = f"$(shell touch {marker}) ' spaced\nsecond-line"
    credential_env = (
        {
            "UPCLOUD_USERNAME": "staging-test-user",
            "UPCLOUD_PASSWORD": literal_password,
        }
        if pair == "primary"
        else {
            "UPCLOUD_API_USERNAME": "staging-test-user",
            "UPCLOUD_API_PASSWORD": literal_password,
        }
    )

    result = _run_staging_make(
        root,
        tmp_path,
        goal,
        "ENV=ci-staging-make",
        "PROVIDER=upcloud",
        "STAGING_CLEANUP_MANIFEST=/private/manifest.json",
        "STAGING_CLEANUP_STATE=/private/state.json",
        "STAGING_CLEANUP_HOSTNAME=vpn-ci-staging.test",
        "STAGING_POST_DESTROY_EVIDENCE=/private/evidence.json",
        extra_env=credential_env,
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    record = json.loads((tmp_path / "make-staging.jsonl").read_text())
    assert record["env"]["UPCLOUD_USERNAME"] == "staging-test-user"
    assert record["env"]["UPCLOUD_PASSWORD"] == literal_password
    assert record["env"]["UPCLOUD_API_USERNAME"] is None
    assert record["env"]["UPCLOUD_API_PASSWORD"] is None


@pytest.mark.parametrize("goal", ["staging-cleanup-manifest", "staging-destroy"])
@pytest.mark.parametrize(
    "credential_env",
    [
        {},
        {"UPCLOUD_USERNAME": "user-only"},
        {"UPCLOUD_PASSWORD": "password-only"},
        {"UPCLOUD_API_USERNAME": "alias-user-only"},
        {"UPCLOUD_API_PASSWORD": "alias-password-only"},
        {"UPCLOUD_USERNAME": "primary", "UPCLOUD_API_PASSWORD": "cross"},
        {
            "UPCLOUD_USERNAME": "primary",
            "UPCLOUD_PASSWORD": "primary-password",
            "UPCLOUD_API_USERNAME": "alias",
            "UPCLOUD_API_PASSWORD": "alias-password",
        },
    ],
)
def test_staging_make_refuses_missing_partial_cross_or_ambiguous_credentials(
    tmp_path: Path, goal: str, credential_env: dict[str, str]
) -> None:
    root = _make_staging_repo(tmp_path)

    result = _run_staging_make(
        root,
        tmp_path,
        goal,
        extra_env=credential_env,
    )

    assert result.returncode != 0
    assert "requires exactly one complete UpCloud credential pair" in result.stderr
    assert not (tmp_path / "make-staging.jsonl").exists()
    assert not (tmp_path / "make-git-spy.log").exists()


def _run(
    root: Path,
    stub_dir: Path,
    env_name: str,
    *,
    provider: str = "upcloud",
    fail_apply: bool = False,
    plan_resource: str | None = None,
    destroy_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    non_interactive: bool = True,
    input_text: str | None = None,
    ambient_umask: str | None = None,
) -> subprocess.CompletedProcess[str]:
    resource = {
        "upcloud": "upcloud_server.vpn",
        "hetzner": "hcloud_server.vpn",
        "vultr": "vultr_instance.vpn",
        "scaleway": "scaleway_instance_server.vpn",
    }[provider]
    env = os.environ | {
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "PROVIDER": provider,
        "ENV": env_name,
        "STUB_LOG": str(stub_dir / "terraform.log"),
        "OVERRIDE_PATH": str(
            root / f"terraform/providers/{provider}/_destroy_override.tf"
        ),
        "EXPECTED_RESOURCE": resource,
        "PLAN_RESOURCE": plan_resource or resource,
        "FAIL_APPLY": str(fail_apply).lower(),
        "UPCLOUD_USERNAME": "staging-test-user",
        "UPCLOUD_PASSWORD": "staging-test-password",
    }
    env.update(extra_env or {})
    command = ["bash", str(root / "scripts/destroy.sh")]
    if non_interactive:
        command.append("--non-interactive")
    command.extend(destroy_args or [])
    if ambient_umask is not None:
        command = ["bash", "-c", f'umask {ambient_umask}; exec "$@"', "bash", *command]
    return subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        input=input_text,
    )


@pytest.mark.parametrize("goal", ["staging-cleanup-manifest", "staging-destroy"])
@pytest.mark.parametrize("field", ["ENV", "PROVIDER"])
def test_staging_make_captures_labels_before_eager_path_expansion(
    tmp_path: Path, goal: str, field: str
) -> None:
    root = _make_staging_repo(tmp_path)
    marker = tmp_path / f"{goal}-{field}.marker"
    result = subprocess.run(
        ["make", "-n", goal, f"{field}=$(shell touch {marker})"],
        cwd=root,
        env=os.environ
        | {
            "UPCLOUD_USERNAME": "staging-test-user",
            "UPCLOUD_PASSWORD": "staging-test-password",
        },
        text=True,
        capture_output=True,
    )

    assert not marker.exists(), result.stderr
    assert str(marker) not in result.stdout


@pytest.mark.parametrize(
    ("goal", "field"),
    [
        ("staging-cleanup-manifest", "STAGING_CLEANUP_MANIFEST"),
        ("staging-cleanup-manifest", "STAGING_CLEANUP_STATE"),
        ("staging-cleanup-manifest", "STAGING_CLEANUP_HOSTNAME"),
        ("staging-destroy", "STAGING_CLEANUP_MANIFEST"),
        ("staging-destroy", "STAGING_POST_DESTROY_EVIDENCE"),
    ],
)
def test_staging_make_never_executes_operator_field_as_make_or_shell_syntax(
    tmp_path: Path, goal: str, field: str
) -> None:
    root = _make_staging_repo(tmp_path)
    marker = tmp_path / f"{field}.marker"
    malicious = f"$(shell touch {marker}) ' quoted $() value\nsecond-line"
    assignments = {
        "ENV": "ci-staging-make",
        "PROVIDER": "upcloud",
        "STAGING_CLEANUP_MANIFEST": "/private/manifest.json",
        "STAGING_CLEANUP_STATE": "/private/state.json",
        "STAGING_CLEANUP_HOSTNAME": "vpn-ci-staging.test",
        "STAGING_POST_DESTROY_EVIDENCE": "/private/evidence.json",
    }
    assignments[field] = malicious

    result = _run_staging_make(
        root,
        tmp_path,
        goal,
        *(f"{name}={value}" for name, value in assignments.items()),
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    record = json.loads((tmp_path / "make-staging.jsonl").read_text())
    assert record["env"][field] == malicious


def test_staging_manifest_make_passes_only_literal_operator_fields(tmp_path: Path) -> None:
    root = _make_staging_repo(tmp_path)
    marker = tmp_path / "manifest-field.marker"
    literal = f"$(shell touch {marker}) ' spaced value"
    assignments = [
        "ENV=ci-staging-make",
        "PROVIDER=upcloud",
        f"STAGING_CLEANUP_MANIFEST={literal}",
        "STAGING_CLEANUP_STATE=/private/state path",
        "STAGING_CLEANUP_HOSTNAME=vpn-ci-staging.test",
    ]

    result = _run_staging_make(
        root, tmp_path, "staging-cleanup-manifest", *assignments
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    record = json.loads((tmp_path / "make-staging.jsonl").read_text())
    assert record["program"] == "staging-cleanup-guard.py"
    assert record["argv"] == [
        "create-manifest",
        "--output",
        literal,
        "--provider",
        "upcloud",
        "--environment",
        "ci-staging-make",
        "--workspace",
        "ci-staging-make",
        "--state",
        "/private/state path",
        "--hostname",
        "vpn-ci-staging.test",
    ]
    assert record["env"]["STAGING_CLEANUP_MANIFEST"] == literal
    assert record["env"]["DEPLOY_SOURCE_REVISION"] == ""
    assert record["env"]["DEPLOYABLE_SOURCE_DIGEST"] == ""
    assert not (tmp_path / "make-git-spy.log").exists()


def test_staging_destroy_make_ignores_free_form_destroy_args(tmp_path: Path) -> None:
    root = _make_staging_repo(tmp_path)
    marker = tmp_path / "destroy-field.marker"
    manifest = f"$(shell touch {marker}) manifest path"
    result = _run_staging_make(
        root,
        tmp_path,
        "staging-destroy",
        "ENV=ci-staging-make",
        "PROVIDER=upcloud",
        f"STAGING_CLEANUP_MANIFEST={manifest}",
        "STAGING_POST_DESTROY_EVIDENCE=/private/evidence path",
        "DESTROY_ARGS=$(shell touch should-not-run) --foreign",
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    record = json.loads((tmp_path / "make-staging.jsonl").read_text())
    assert record["argv"] == [
        "--non-interactive",
        "--staging-manifest",
        manifest,
        "--post-destroy-evidence",
        "/private/evidence path",
    ]
    assert "--foreign" not in record["argv"]
    assert not (tmp_path / "make-git-spy.log").exists()


@pytest.mark.parametrize(
    "goals",
    [
        ["staging-destroy", "help"],
        ["staging-cleanup-manifest", "staging-destroy"],
        ["staging-destroy", "staging-destroy"],
    ],
)
def test_staging_make_refuses_mixed_or_repeated_goals_before_any_child(
    tmp_path: Path, goals: list[str]
) -> None:
    root = _make_staging_repo(tmp_path)
    result = subprocess.run(
        ["make", *goals],
        cwd=root,
        env=os.environ
        | {
            "MAKE_STAGING_LOG": str(tmp_path / "make-staging.jsonl"),
            "MAKE_GIT_SPY": str(tmp_path / "make-git-spy.log"),
            "UPCLOUD_USERNAME": "staging-test-user",
            "UPCLOUD_PASSWORD": "staging-test-password",
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "requires exactly one Make goal" in result.stderr
    assert not (tmp_path / "make-staging.jsonl").exists()
    assert not (tmp_path / "make-git-spy.log").exists()


def _real_staging_manifest(root: Path, private: Path, environment: str) -> Path:
    private.mkdir(parents=True, mode=0o700)
    private.chmod(0o700)
    state = {
        "version": 4,
        "terraform_version": "1.14.5",
        "serial": 1,
        "lineage": "12345678-1234-4234-8234-123456789abc",
        "resources": [
            {
                "mode": "managed",
                "type": "terraform_data",
                "name": "ssh_port",
                "instances": [{"attributes": {"id": "local-only"}}],
            },
            {
                "mode": "managed",
                "type": "upcloud_server",
                "name": "vpn",
                "instances": [
                    {
                        "attributes": {
                            "id": SERVER_UUID,
                            "hostname": "vpn-ci-staging.test",
                            "template": [{"id": STORAGE_UUID}],
                            "network_interface": [
                                {"type": "public", "ip_address_family": "IPv4"},
                                {"type": "public", "ip_address_family": "IPv6"},
                                {"type": "utility", "ip_address_family": "IPv4"},
                            ],
                        }
                    }
                ],
            },
            {
                "mode": "managed",
                "type": "upcloud_firewall_rules",
                "name": "vpn",
                "instances": [
                    {"attributes": {"id": SERVER_UUID, "server_id": SERVER_UUID}}
                ],
            },
        ],
    }
    state_path = private / "terraform.tfstate"
    state_path.write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
    )
    state_path.chmod(0o600)
    created = datetime.now(timezone.utc).replace(microsecond=0)
    manifest = private / "manifest.json"
    state_bytes = state_path.read_bytes()
    payload = {
        "schema_version": 2,
        "provider": "upcloud",
        "environment": environment,
        "workspace": environment,
        "state": {
            "path": str(state_path.absolute()),
            "sha256": hashlib.sha256(state_bytes).hexdigest(),
        },
        "hostname": "vpn-ci-staging.test",
        "provider_account_username": "staging-owner",
        "server_uuid": SERVER_UUID,
        "root_storage_uuid": STORAGE_UUID,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "target_at": (created + timedelta(hours=36)).isoformat().replace("+00:00", "Z"),
        "escalation_at": (created + timedelta(hours=44)).isoformat().replace("+00:00", "Z"),
        "expiry_at": (created + timedelta(hours=47)).isoformat().replace("+00:00", "Z"),
    }
    manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    manifest.chmod(0o600)
    return manifest


def test_ci_destroy_skips_prompts_and_cleans_inventory_after_apply(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-123-cleanup"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci.test"\n'
    )
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\n")
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name)

    assert result.returncode == 0, result.stderr
    assert "CI destroy authorization accepted" in result.stdout
    assert not inventory.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert "plan -destroy" in (stub.parent / "terraform.log").read_text()
    assert "apply" in (stub.parent / "terraform.log").read_text()


def test_noninteractive_destroy_rejects_non_ci_environment(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    (root / "terraform/providers/upcloud/environments/prod.tfvars").write_text(
        'server_name = "vpn-prod.test"\n'
    )
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, "prod")

    assert result.returncode == 2
    assert "restricted to validated ci-* environments" in result.stderr
    assert not (stub.parent / "terraform.log").exists()


def test_destroy_refuses_to_run_over_a_stale_override(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-123-stale"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci.test"\n'
    )
    stale = root / "terraform/providers/upcloud/_destroy_override.tf"
    stale.write_text("# leftover from a crashed destroy\n")
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name)

    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert "prevent_destroy" in result.stderr
    assert stale.exists()
    assert not (stub.parent / "terraform.log").exists()


def test_failed_ci_destroy_keeps_inventory_for_diagnosis(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-123-failure"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci.test"\n'
    )
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\n")
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name, fail_apply=True)

    assert result.returncode != 0
    assert inventory.exists()


def test_destroy_uses_the_provider_specific_server_resource(tmp_path: Path) -> None:
    for provider, resource in {
        "upcloud": "upcloud_server.vpn",
        "hetzner": "hcloud_server.vpn",
        "vultr": "vultr_instance.vpn",
        "scaleway": "scaleway_instance_server.vpn",
    }.items():
        root = _test_repo(tmp_path / provider)
        env_name = f"ci-123-{provider}"
        (
            root / f"terraform/providers/{provider}/environments/{env_name}.tfvars"
        ).write_text('server_name = "vpn-ci.test"\n')
        stub = _terraform_stub(tmp_path / provider)

        result = _run(root, stub.parent, env_name, provider=provider)

        assert result.returncode == 0, result.stderr
        assert (
            f'resource "{resource.split(".")[0]}" "vpn"'
            in (stub.parent / "terraform.log").read_text()
        )


def test_destroy_rejects_unknown_provider_before_writing_override(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    stub = _terraform_stub(tmp_path)
    env = os.environ | {
        "PATH": f"{stub.parent}:{os.environ['PATH']}",
        "PROVIDER": "unknown",
        "ENV": "ci-123-unknown",
    }

    result = subprocess.run(
        ["bash", str(root / "scripts/destroy.sh"), "--non-interactive"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "unsupported PROVIDER for destroy" in result.stderr


def test_destroy_refuses_apply_when_plan_lacks_expected_server_address(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-123-plan-mismatch"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci.test"\n'
    )
    stub = _terraform_stub(tmp_path)

    result = _run(
        root, stub.parent, env_name, plan_resource="upcloud_firewall_rules.vpn"
    )

    assert result.returncode != 0
    assert "does not delete expected resource upcloud_server.vpn" in result.stderr
    assert not any(
        line.split()[-2:] == ["apply", f"{env_name}.destroy.tfplan"]
        for line in (stub.parent / "terraform.log").read_text().splitlines()
        if line.startswith("-chdir=")
    )


def test_staging_destroy_requires_uuid_guard_before_override_or_terraform(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-missing-guard"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    stub = _terraform_stub(tmp_path)

    result = _run(root, stub.parent, env_name)

    assert result.returncode == 2
    assert "requires --staging-manifest and --post-destroy-evidence" in result.stderr
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert not (stub.parent / "terraform.log").exists()


def test_staging_destroy_refuses_foreign_account_before_override_or_terraform(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-foreign-account"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = private / "manifest.json"
    manifest.write_bytes(b"{}\n")
    manifest.chmod(0o600)
    evidence = private / "evidence.json"
    guard_log = private / "guard.log"
    _guard_stub(root)
    stub = _terraform_stub(tmp_path)

    result = _run(
        root,
        stub.parent,
        env_name,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
        extra_env={
            "GUARD_LOG": str(guard_log),
            "GUARD_FAIL_COMMAND": "authorize-reserve-evidence",
        },
    )

    assert result.returncode == 9
    assert guard_log.read_text().splitlines() == [
        f"authorize-reserve-evidence --manifest {manifest} "
        f"--evidence-output {evidence} --expected-provider upcloud "
        f"--expected-environment {env_name}",
    ]
    assert not evidence.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert not (stub.parent / "terraform.log").exists()


def test_interactive_staging_abort_before_authorization_creates_nothing(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-interactive-abort"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = private / "manifest.json"
    manifest.write_text("{}\n")
    manifest.chmod(0o600)
    evidence = private / "post-destroy.json"
    _guard_stub(root)
    stub = _terraform_stub(tmp_path)

    result = _run(
        root,
        stub.parent,
        env_name,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
        extra_env={"GUARD_LOG": str(private / "guard.log")},
        non_interactive=False,
        input_text="wrong-hostname\n",
    )

    assert result.returncode == 1
    assert not evidence.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert not (stub.parent / "terraform.log").exists()


def test_interactive_staging_abort_after_plan_releases_reservation(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-final-abort"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = private / "manifest.json"
    manifest.write_text("{}\n")
    manifest.chmod(0o600)
    evidence = private / "post-destroy.json"
    _guard_stub(root)
    _audit_stub(root)
    stub = _terraform_stub(tmp_path)
    audit_log = private / "audit.log"

    result = _run(
        root,
        stub.parent,
        env_name,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
        extra_env={
            "GUARD_LOG": str(private / "guard.log"),
            "AUDIT_LOG_STUB": str(audit_log),
        },
        non_interactive=False,
        input_text="vpn-ci-staging.test\nDESTROY\nno\n",
    )

    assert result.returncode == 1
    assert not evidence.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    calls = (stub.parent / "terraform.log").read_text().splitlines()
    assert any(" plan " in f" {line} " for line in calls)
    assert not any(" apply " in f" {line} " for line in calls)
    assert not audit_log.exists()


def test_staging_destroy_refuses_cross_environment_manifest_before_override_or_terraform(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    manifest_env = "ci-staging-one"
    destroy_env = "ci-staging-two"
    (
        root / f"terraform/providers/upcloud/environments/{destroy_env}.tfvars"
    ).write_text('server_name = "vpn-ci-staging.test"\n')
    private = tmp_path / "private-real"
    manifest = _real_staging_manifest(root, private, manifest_env)
    evidence = private / "post-destroy.json"
    stub = _terraform_stub(tmp_path)
    (tmp_path / "python3").unlink()

    result = _run(
        root,
        stub.parent,
        destroy_env,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
    )

    assert result.returncode == 1
    assert "environment does not match destroy target" in result.stderr
    assert not evidence.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert not (stub.parent / "terraform.log").exists()


def test_staging_destroy_refuses_unsafe_evidence_before_override_or_terraform(
    tmp_path: Path,
) -> None:
    for kind in ("existing", "symlink", "unsafe-parent"):
        case = tmp_path / kind
        root = _test_repo(case)
        env_name = f"ci-staging-{kind}"
        (
            root / f"terraform/providers/upcloud/environments/{env_name}.tfvars"
        ).write_text('server_name = "vpn-ci-staging.test"\n')
        private = case / "private-real"
        manifest = _real_staging_manifest(root, private, env_name)
        if kind == "unsafe-parent":
            evidence_parent = case / "unsafe-evidence"
            evidence_parent.mkdir(mode=0o755)
            evidence_parent.chmod(0o755)
            evidence = evidence_parent / "post-destroy.json"
        else:
            evidence = private / "post-destroy.json"
            if kind == "existing":
                evidence.write_text("existing\n")
                evidence.chmod(0o600)
            else:
                target = private / "target.json"
                target.write_text("target\n")
                target.chmod(0o600)
                evidence.symlink_to(target.name)
        stub = _terraform_stub(case)
        (case / "python3").unlink()

        result = _run(
            root,
            stub.parent,
            env_name,
            destroy_args=[
                "--staging-manifest",
                str(manifest),
                "--post-destroy-evidence",
                str(evidence),
            ],
        )

        assert result.returncode == 1, (kind, result.stderr)
        assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
        assert not (stub.parent / "terraform.log").exists()


def test_staging_destroy_validates_manifest_and_plan_before_apply_then_verifies_absence(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-guarded"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = private / "manifest.json"
    manifest.write_text("{}\n")
    manifest.chmod(0o600)
    evidence = private / "post-destroy.json"
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\nvpn-p0 ansible_host=192.0.2.10\n")
    inventory_before = inventory.read_bytes()
    guard_log = private / "guard.log"
    audit_log = private / "audit.log"
    race_plan_log = private / "race-plan.log"
    _guard_stub(root)
    _audit_stub(root)
    stub = _terraform_stub(tmp_path)

    result = _run(
        root,
        stub.parent,
        env_name,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
        extra_env={
            "GUARD_LOG": str(guard_log),
            "AUDIT_LOG_STUB": str(audit_log),
            "RACE_PLAN_LOG": str(race_plan_log),
        },
        ambient_umask="022",
    )

    assert result.returncode == 0, result.stderr
    guard_calls = guard_log.read_text().splitlines()
    target = f"--expected-provider upcloud --expected-environment {env_name}"
    assert guard_calls[0] == (
        f"authorize-reserve-evidence --manifest {manifest} "
        f"--evidence-output {evidence} {target}"
    )
    assert guard_calls[1].startswith(
        f"validate-plan --manifest {manifest} --plan-view "
    )
    assert f"--evidence-output {evidence}" in guard_calls[1]
    assert guard_calls[1].endswith(target)
    assert guard_calls[2].startswith("rewind-plan-fd --fd-number ")
    assert guard_calls[3] == (
        f"mark-apply-started --manifest {manifest} "
        f"--evidence-output {evidence} {target}"
    )
    assert guard_calls[4] == (
        f"verify-upcloud-absence --manifest {manifest} --evidence-output {evidence} {target}"
    )
    terraform_calls = (stub.parent / "terraform.log").read_text().splitlines()
    apply_index = next(
        i for i, line in enumerate(terraform_calls) if " apply " in f" {line} "
    )
    show_call = next(line for line in terraform_calls if " show " in f" {line} ")
    apply_call = next(line for line in terraform_calls if " apply " in f" {line} ")
    show_input = show_call.split()[-1]
    apply_input = apply_call.split()[-1]
    assert show_input == apply_input
    assert show_input.startswith("/dev/fd/")
    assert "plan-mode=600" in terraform_calls
    assert "show-plan-content=guarded-plan" in terraform_calls
    assert "apply-plan-content=guarded-plan" in terraform_calls
    assert not Path(race_plan_log.read_text().strip()).exists()
    assert evidence.exists()
    assert inventory.read_bytes() == inventory_before
    audit_call = audit_log.read_text().strip()
    assert audit_call == (
        f"append-best-effort --action staging-destroy --env {env_name} "
        "--provider upcloud --note exact-owned-resources-absent"
    )
    assert SERVER_UUID not in audit_call
    assert STORAGE_UUID not in audit_call
    assert apply_index > 0


def test_staging_destroy_refuses_apply_when_exact_plan_guard_fails(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-plan-refusal"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = private / "manifest.json"
    manifest.write_text("{}\n")
    manifest.chmod(0o600)
    evidence = private / "post-destroy.json"
    _guard_stub(root)
    _audit_stub(root)
    stub = _terraform_stub(tmp_path)
    audit_log = private / "audit.log"

    result = _run(
        root,
        stub.parent,
        env_name,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
        extra_env={
            "GUARD_LOG": str(private / "guard.log"),
            "GUARD_FAIL_COMMAND": "validate-plan",
            "AUDIT_LOG_STUB": str(audit_log),
        },
    )

    assert result.returncode == 9
    assert not evidence.exists()
    assert not (root / "terraform/providers/upcloud/_destroy_override.tf").exists()
    assert not any(
        " apply " in f" {line} "
        for line in (stub.parent / "terraform.log").read_text().splitlines()
    )
    assert not audit_log.exists()


def test_staging_destroy_does_not_audit_failed_apply(tmp_path: Path) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-apply-failure"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = private / "manifest.json"
    manifest.write_text("{}\n")
    manifest.chmod(0o600)
    evidence = private / "post-destroy.json"
    audit_log = private / "audit.log"
    _guard_stub(root)
    _audit_stub(root)
    stub = _terraform_stub(tmp_path, fail_apply=True)

    result = _run(
        root,
        stub.parent,
        env_name,
        fail_apply=True,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
        extra_env={
            "GUARD_LOG": str(private / "guard.log"),
            "AUDIT_LOG_STUB": str(audit_log),
        },
    )

    assert result.returncode != 0
    assert not audit_log.exists()


def test_staging_destroy_keeps_inventory_and_plan_when_provider_absence_is_unverified(
    tmp_path: Path,
) -> None:
    root = _test_repo(tmp_path)
    env_name = "ci-staging-absence-refusal"
    (root / f"terraform/providers/upcloud/environments/{env_name}.tfvars").write_text(
        'server_name = "vpn-ci-staging.test"\n'
    )
    inventory = root / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text("[vpn]\n")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = private / "manifest.json"
    manifest.write_text("{}\n")
    manifest.chmod(0o600)
    evidence = private / "post-destroy.json"
    _guard_stub(root)
    _audit_stub(root)
    stub = _terraform_stub(tmp_path)
    audit_log = private / "audit.log"

    result = _run(
        root,
        stub.parent,
        env_name,
        destroy_args=[
            "--staging-manifest",
            str(manifest),
            "--post-destroy-evidence",
            str(evidence),
        ],
        extra_env={
            "GUARD_LOG": str(private / "guard.log"),
            "GUARD_FAIL_COMMAND": "verify-upcloud-absence",
            "AUDIT_LOG_STUB": str(audit_log),
        },
    )

    assert result.returncode == 9
    assert inventory.exists()
    assert not (
        root / f"terraform/providers/upcloud/{env_name}.destroy.tfplan"
    ).exists()
    assert evidence.read_text() == "apply_started\n"
    assert not audit_log.exists()


def test_ci_workflows_do_not_suppress_destroy_failure_or_cleanup_tfvars_early() -> None:
    for workflow in ("real-vps-deploy.yml", "transport-reachability-matrix.yml"):
        source = (REPO_ROOT / ".github/workflows" / workflow).read_text()
        assert "make destroy DESTROY_ARGS=--non-interactive" in source
        assert "make destroy || true" not in source
        assert (
            'rm -f "terraform/providers/upcloud/environments/${CI_ENV}.tfvars"'
            in source
        )
        assert "env.CI_ENV != ''" in source
