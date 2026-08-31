"""Fail-closed contracts for exact-resource staging cleanup."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/staging-cleanup-guard.py"
SPEC = importlib.util.spec_from_file_location("staging_cleanup_guard", SCRIPT)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

SERVER_UUID = "00112233-4455-4677-8899-aabbccddeeff"
STORAGE_UUID = "ffeeddcc-bbaa-4988-8766-554433221100"
ACCOUNT_USERNAME = "staging-owner"
HOSTNAME = "vpn-ci-staging-20260829-fi-hel1"
CREATED = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
EXPIRY = CREATED + timedelta(hours=47)


def _creation_get(path: str) -> tuple[int, dict[str, object]]:
    if path == "/1.3/account":
        return 200, {"account": {"username": ACCOUNT_USERNAME, "credits": 12.34}}
    if path == f"/1.3/server/{SERVER_UUID}":
        return 200, {
            "server": {
                "uuid": SERVER_UUID,
                "hostname": HOSTNAME,
                "created": int(CREATED.timestamp()),
            }
        }
    raise AssertionError(path)


def _fresh_creation_get(path: str) -> tuple[int, dict[str, object]]:
    if path == "/1.3/account":
        return 200, {"account": {"username": ACCOUNT_USERNAME}}
    if path == f"/1.3/server/{SERVER_UUID}":
        return 200, {
            "server": {
                "uuid": SERVER_UUID,
                "hostname": HOSTNAME,
                "created": int(datetime.now(timezone.utc).timestamp()),
            }
        }
    raise AssertionError(path)


def _private_file(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def _state_view() -> dict[str, object]:
    return {
        "version": 4,
        "terraform_version": "1.14.5",
        "serial": 3,
        "lineage": "12345678-1234-4234-8234-123456789abc",
        "resources": [
            {
                "mode": "managed",
                "type": "terraform_data",
                "name": "ssh_port",
                "instances": [
                    {"schema_version": 0, "attributes": {"id": "local-only"}}
                ],
            },
            {
                "mode": "managed",
                "type": "upcloud_server",
                "name": "vpn",
                "instances": [
                    {
                        "schema_version": 0,
                        "attributes": {
                            "id": SERVER_UUID,
                            "hostname": HOSTNAME,
                            "template": [{"id": STORAGE_UUID}],
                            "network_interface": [
                                {"type": "public", "ip_address_family": "IPv4"},
                                {"type": "public", "ip_address_family": "IPv6"},
                                {"type": "utility", "ip_address_family": "IPv4"},
                            ],
                        },
                    }
                ],
            },
            {
                "mode": "managed",
                "type": "upcloud_firewall_rules",
                "name": "vpn",
                "instances": [
                    {
                        "schema_version": 0,
                        "attributes": {"id": SERVER_UUID, "server_id": SERVER_UUID},
                    }
                ],
            },
        ],
    }


def _destroy_plan(
    *, server_uuid: str = SERVER_UUID, storage_uuid: str = STORAGE_UUID
) -> dict[str, object]:
    return {
        "format_version": "1.2",
        "resource_changes": [
            {
                "address": "terraform_data.ssh_port",
                "mode": "managed",
                "type": "terraform_data",
                "name": "ssh_port",
                "change": {
                    "actions": ["delete"],
                    "before": {"id": "local-only"},
                    "after": None,
                },
            },
            {
                "address": "upcloud_server.vpn",
                "mode": "managed",
                "type": "upcloud_server",
                "name": "vpn",
                "change": {
                    "actions": ["delete"],
                    "before": {
                        "id": server_uuid,
                        "hostname": HOSTNAME,
                        "template": [{"id": storage_uuid}],
                        "network_interface": [
                            {"type": "public", "ip_address_family": "IPv4"},
                            {"type": "public", "ip_address_family": "IPv6"},
                            {"type": "utility", "ip_address_family": "IPv4"},
                        ],
                    },
                    "after": None,
                },
            },
            {
                "address": "upcloud_firewall_rules.vpn",
                "mode": "managed",
                "type": "upcloud_firewall_rules",
                "name": "vpn",
                "change": {
                    "actions": ["delete"],
                    "before": {"id": server_uuid, "server_id": server_uuid},
                    "after": None,
                },
            },
        ],
    }


def _manifest(
    tmp_path: Path, *, now: datetime = CREATED
) -> tuple[Path, dict[str, object]]:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state_bytes = guard.canonical_json(_state_view())
    state_path = _private_file(private / "terraform.tfstate", state_bytes)
    manifest_path = private / "cleanup-manifest.json"
    manifest = guard.create_manifest(
        output_path=manifest_path,
        provider="upcloud",
        environment="ci-staging-20260829",
        workspace="ci-staging-20260829",
        state_path=state_path,
        hostname=HOSTNAME,
        request_json=_creation_get,
        now=now,
    )
    return manifest_path, manifest


def _reserved_evidence_path(manifest_path: Path) -> Path:
    evidence_path = manifest_path.with_name("reserved-evidence.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )
    return evidence_path


def _mark_started(manifest_path: Path, evidence_path: Path) -> dict[str, object]:
    return guard.mark_apply_started(
        manifest_path,
        evidence_path,
        request_json=lambda path: (
            (200, {"account": {"username": ACCOUNT_USERNAME}})
            if path == "/1.3/account"
            else (_ for _ in ()).throw(AssertionError(path))
        ),
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )


def test_manifest_is_canonical_private_and_bound_to_exact_state_ids(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)

    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert manifest_path.read_bytes() == guard.canonical_json(manifest)
    assert manifest["server_uuid"] == SERVER_UUID
    assert manifest["root_storage_uuid"] == STORAGE_UUID
    assert manifest["provider_account_username"] == ACCOUNT_USERNAME
    assert manifest["hostname"] == HOSTNAME
    assert manifest["workspace"] == "ci-staging-20260829"
    assert manifest["target_at"] == "2026-08-31T00:00:00Z"
    assert manifest["escalation_at"] == "2026-08-31T08:00:00Z"
    assert manifest["expiry_at"] == "2026-08-31T11:00:00Z"
    state = manifest["state"]
    assert (
        state["sha256"]
        == hashlib.sha256(guard.canonical_json(_state_view())).hexdigest()
    )


def test_manifest_schedule_is_derived_from_provider_creation_not_invocation_time(
    tmp_path: Path,
) -> None:
    _, manifest = _manifest(tmp_path, now=CREATED + timedelta(hours=12))

    assert manifest["created_at"] == "2026-08-29T12:00:00Z"
    assert manifest["target_at"] == "2026-08-31T00:00:00Z"
    assert manifest["escalation_at"] == "2026-08-31T08:00:00Z"
    assert manifest["expiry_at"] == "2026-08-31T11:00:00Z"


@pytest.mark.parametrize(
    "server",
    [
        {"uuid": SERVER_UUID, "hostname": HOSTNAME, "created": "1788004800"},
        {"uuid": SERVER_UUID, "hostname": HOSTNAME, "created": True},
        {"uuid": SERVER_UUID, "hostname": HOSTNAME, "created": 0},
        {
            "uuid": STORAGE_UUID,
            "hostname": HOSTNAME,
            "created": int(CREATED.timestamp()),
        },
        {
            "uuid": SERVER_UUID,
            "hostname": "foreign.test",
            "created": int(CREATED.timestamp()),
        },
        {
            "uuid": SERVER_UUID,
            "hostname": HOSTNAME,
            "created": int((CREATED + timedelta(minutes=6)).timestamp()),
        },
    ],
)
def test_manifest_refuses_ambiguous_authenticated_server_creation(
    tmp_path: Path, server: dict[str, object]
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(_state_view())
    )

    def request(path: str) -> tuple[int, dict[str, object]]:
        if path == "/1.3/account":
            return 200, {"account": {"username": ACCOUNT_USERNAME}}
        assert path == f"/1.3/server/{SERVER_UUID}"
        return 200, {"server": server}

    with pytest.raises(guard.GuardError, match="server identity or creation time"):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="upcloud",
            environment="ci-staging-created",
            workspace="ci-staging-created",
            state_path=state_path,
            hostname=HOSTNAME,
            request_json=request,
            now=CREATED,
        )


def test_create_manifest_cli_authenticates_without_printing_account_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(_state_view())
    )
    output = private / "manifest.json"
    monkeypatch.setenv("UPCLOUD_USERNAME", "secret-api-user")
    monkeypatch.setenv("UPCLOUD_PASSWORD", "secret-api-password")
    monkeypatch.setattr(
        guard, "_upcloud_request", lambda *_args, **_kwargs: _fresh_creation_get
    )

    result = guard.main(
        [
            "create-manifest",
            "--output",
            str(output),
            "--provider",
            "upcloud",
            "--environment",
            "ci-staging-cli",
            "--workspace",
            "ci-staging-cli",
            "--state",
            str(state_path),
            "--hostname",
            HOSTNAME,
        ]
    )

    assert result == 0
    output_text = capsys.readouterr().out
    assert output_text == "staging cleanup manifest created\n"
    assert ACCOUNT_USERNAME not in output_text


def test_create_manifest_cli_accepts_only_one_complete_api_alias_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(_state_view())
    )
    monkeypatch.delenv("UPCLOUD_USERNAME", raising=False)
    monkeypatch.delenv("UPCLOUD_PASSWORD", raising=False)
    monkeypatch.setenv("UPCLOUD_API_USERNAME", "secret-api-user")
    monkeypatch.setenv("UPCLOUD_API_PASSWORD", "secret-api-password")
    observed: list[str] = []

    def request_factory(authorization: str) -> guard.JsonRequest:
        observed.append(authorization)
        return _fresh_creation_get

    monkeypatch.setattr(guard, "_upcloud_request", request_factory)

    result = guard.main(
        [
            "create-manifest",
            "--output",
            str(private / "manifest.json"),
            "--provider",
            "upcloud",
            "--environment",
            "ci-staging-alias",
            "--workspace",
            "ci-staging-alias",
            "--state",
            str(state_path),
            "--hostname",
            HOSTNAME,
        ]
    )

    assert result == 0
    expected = base64.b64encode(b"secret-api-user:secret-api-password").decode("ascii")
    assert observed == [f"Basic {expected}"]


def test_create_manifest_cli_accepts_one_literal_bearer_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(_state_view())
    )
    for name in (
        "UPCLOUD_USERNAME",
        "UPCLOUD_PASSWORD",
        "UPCLOUD_API_USERNAME",
        "UPCLOUD_API_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("UPCLOUD_TOKEN", "uct_test_bearer_token_123456")
    observed: list[str] = []

    def request_factory(authorization: str) -> guard.JsonRequest:
        observed.append(authorization)
        return _fresh_creation_get

    monkeypatch.setattr(guard, "_upcloud_request", request_factory)

    result = guard.main(
        [
            "create-manifest",
            "--output",
            str(private / "manifest.json"),
            "--provider",
            "upcloud",
            "--environment",
            "ci-staging-token",
            "--workspace",
            "ci-staging-token",
            "--state",
            str(state_path),
            "--hostname",
            HOSTNAME,
        ]
    )

    assert result == 0
    assert observed == ["Bearer uct_test_bearer_token_123456"]


@pytest.mark.parametrize(
    "credentials",
    [
        {"UPCLOUD_USERNAME": "only-user"},
        {"UPCLOUD_API_PASSWORD": "only-alias-password"},
        {
            "UPCLOUD_USERNAME": "primary",
            "UPCLOUD_PASSWORD": "primary-password",
            "UPCLOUD_API_USERNAME": "alias",
            "UPCLOUD_API_PASSWORD": "alias-password",
        },
        {
            "UPCLOUD_USERNAME": "primary",
            "UPCLOUD_PASSWORD": "primary-password",
            "UPCLOUD_TOKEN": "uct_ambiguous_token_123456",
        },
        {"UPCLOUD_TOKEN": "short"},
        {"UPCLOUD_TOKEN": "uct_invalid\nheader_value_123456"},
    ],
)
def test_create_manifest_cli_refuses_partial_or_ambiguous_credential_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    credentials: dict[str, str],
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(_state_view())
    )
    for name in (
        "UPCLOUD_USERNAME",
        "UPCLOUD_PASSWORD",
        "UPCLOUD_API_USERNAME",
        "UPCLOUD_API_PASSWORD",
        "UPCLOUD_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in credentials.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(guard.GuardError, match="one valid UpCloud credential mode"):
        guard.main(
            [
                "create-manifest",
                "--output",
                str(private / "manifest.json"),
                "--provider",
                "upcloud",
                "--environment",
                "ci-staging-ambiguous",
                "--workspace",
                "ci-staging-ambiguous",
                "--state",
                str(state_path),
                "--hostname",
                HOSTNAME,
            ]
        )


def test_manifest_accepts_owned_state_under_non_writable_repository_directory(
    tmp_path: Path,
) -> None:
    repo_state = tmp_path / "terraform.tfstate.d" / "ci-staging-20260829"
    repo_state.mkdir(parents=True, mode=0o755)
    repo_state.chmod(0o755)
    state_path = _private_file(
        repo_state / "terraform.tfstate", guard.canonical_json(_state_view())
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)

    manifest = guard.create_manifest(
        output_path=private / "manifest.json",
        provider="upcloud",
        environment="ci-staging-20260829",
        workspace="ci-staging-20260829",
        state_path=state_path,
        hostname=HOSTNAME,
        request_json=_creation_get,
        now=CREATED,
    )

    assert manifest["state"]["path"] == str(state_path.absolute())


@pytest.mark.parametrize("bad_mode", [0o400, 0o640, 0o644])
def test_manifest_refuses_non_private_exact_mode(tmp_path: Path, bad_mode: int) -> None:
    manifest_path, _ = _manifest(tmp_path)
    manifest_path.chmod(bad_mode)

    with pytest.raises(guard.GuardError, match="manifest mode"):
        guard.load_manifest(manifest_path, now=CREATED)


def test_manifest_refuses_symlink(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    target = manifest_path.with_name("real.json")
    manifest_path.rename(target)
    manifest_path.symlink_to(target.name)

    with pytest.raises(guard.GuardError, match="manifest.*symlink"):
        guard.load_manifest(manifest_path, now=CREATED)


def test_manifest_refuses_foreign_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    actual_uid = os.getuid()
    monkeypatch.setattr(guard.os, "getuid", lambda: actual_uid + 1)

    with pytest.raises(guard.GuardError, match="manifest.*owner"):
        guard.load_manifest(manifest_path, now=CREATED)


def test_private_read_rechecks_mode_on_opened_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    original_open = guard.os.open

    def open_then_widen(
        path: object, flags: int, *args: object, **kwargs: object
    ) -> int:
        fd = original_open(path, flags, *args, **kwargs)
        if path == manifest_path.name:
            os.fchmod(fd, 0o644)
        return fd

    monkeypatch.setattr(guard.os, "open", open_then_widen)

    with pytest.raises(guard.GuardError, match="mode changed while opening"):
        guard.load_manifest(manifest_path, now=CREATED)


def test_manifest_refuses_expired_deadline(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)

    with pytest.raises(guard.GuardError, match="expired"):
        guard.load_manifest(manifest_path, now=EXPIRY)


@pytest.mark.parametrize("replaced", ["manifest", "state"])
def test_authorize_reservation_refuses_same_bytes_replacement_during_account_check(
    tmp_path: Path, replaced: str
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    target = (
        manifest_path if replaced == "manifest" else Path(manifest["state"]["path"])
    )

    def replace_during_account(path: str) -> tuple[int, dict[str, object]]:
        assert path == "/1.3/account"
        replacement = target.with_name(f".{target.name}.replacement")
        _private_file(replacement, target.read_bytes())
        os.replace(replacement, target)
        return 200, {"account": {"username": ACCOUNT_USERNAME}}

    with pytest.raises(guard.GuardError, match="changed during provider authorization"):
        guard.authorize_reserve_evidence(
            manifest_path,
            evidence_path,
            request_json=replace_during_account,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert not evidence_path.exists()


def test_authorize_reservation_binds_account_and_manifest_before_plan(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")

    reserved = guard.authorize_reserve_evidence(
        manifest_path,
        evidence_path,
        request_json=lambda path: (
            200,
            {"account": {"username": ACCOUNT_USERNAME}},
        ),
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    assert (
        reserved["manifest_sha256"]
        == hashlib.sha256(guard.canonical_json(manifest)).hexdigest()
    )
    assert evidence_path.read_bytes() == guard.canonical_json(reserved)


def test_authorize_reservation_refuses_foreign_account_before_evidence(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    requested: list[str] = []

    def foreign(path: str) -> tuple[int, dict[str, object]]:
        requested.append(path)
        return 200, {"account": {"username": "different-valid-account"}}

    with pytest.raises(guard.GuardError, match="account identity"):
        guard.authorize_reserve_evidence(
            manifest_path,
            evidence_path,
            request_json=foreign,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert requested == ["/1.3/account"]
    assert not evidence_path.exists()


def test_authorize_crossing_expiry_creates_no_reservation(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")

    with pytest.raises(guard.GuardError, match="expired"):
        guard.authorize_reserve_evidence(
            manifest_path,
            evidence_path,
            request_json=lambda path: (
                200,
                {"account": {"username": ACCOUNT_USERNAME}},
            ),
            now=EXPIRY - timedelta(seconds=1),
            clock=lambda: EXPIRY,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert not evidence_path.exists()


def test_manifest_refuses_noncanonical_cleanup_schedule(tmp_path: Path) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    manifest["target_at"] = "2026-08-31T00:00:01Z"
    manifest["escalation_at"] = "2026-08-31T08:00:00Z"
    manifest_path.write_bytes(guard.canonical_json(manifest))

    with pytest.raises(guard.GuardError, match="cleanup schedule"):
        guard.load_manifest(manifest_path, now=CREATED)


@pytest.mark.parametrize("kind", ["manifest", "state", "evidence"])
def test_private_paths_refuse_symlinked_higher_ancestor(
    tmp_path: Path, kind: str
) -> None:
    real_root = tmp_path / "real-root"
    private = real_root / "private"
    private.mkdir(parents=True, mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real_root, target_is_directory=True)
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(_state_view())
    )
    manifest_path = private / "manifest.json"

    if kind == "state":
        with pytest.raises(guard.GuardError, match="ancestor.*symlink"):
            guard.create_manifest(
                output_path=manifest_path,
                provider="upcloud",
                environment="ci-staging-ancestor",
                workspace="ci-staging-ancestor",
                state_path=alias / "private/terraform.tfstate",
                hostname=HOSTNAME,
                request_json=_creation_get,
                now=CREATED,
            )
        return

    guard.create_manifest(
        output_path=manifest_path,
        provider="upcloud",
        environment="ci-staging-ancestor",
        workspace="ci-staging-ancestor",
        state_path=state_path,
        hostname=HOSTNAME,
        request_json=_creation_get,
        now=CREATED,
    )
    if kind == "manifest":
        with pytest.raises(guard.GuardError, match="ancestor.*symlink"):
            guard.load_manifest(alias / "private/manifest.json", now=CREATED)
    else:
        with pytest.raises(guard.GuardError, match="ancestor.*symlink"):
            guard.reserve_evidence(
                manifest_path,
                alias / "private/post-destroy.json",
                now=CREATED,
                expected_provider="upcloud",
                expected_environment="ci-staging-ancestor",
            )


def test_manifest_refuses_different_destroy_environment(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)

    with pytest.raises(guard.GuardError, match="environment does not match"):
        guard.load_manifest(
            manifest_path,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-foreign",
        )


def test_manifest_refuses_state_drift(tmp_path: Path) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    Path(manifest["state"]["path"]).write_bytes(b"foreign state\n")

    with pytest.raises(guard.GuardError, match="state digest"):
        guard.load_manifest(manifest_path, now=CREATED)


@pytest.mark.parametrize(
    "username",
    ["abc", "x" * 65, "owner\nname", " owner", "ownér"],
)
def test_manifest_refuses_malformed_authenticated_account_identity(
    tmp_path: Path, username: str
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(_state_view())
    )

    def malformed_account(path: str) -> tuple[int, dict[str, object]]:
        assert path == "/1.3/account"
        return 200, {"account": {"username": username}}

    with pytest.raises(guard.GuardError, match="account identity"):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="upcloud",
            environment="ci-staging-account",
            workspace="ci-staging-account",
            state_path=state_path,
            hostname=HOSTNAME,
            request_json=malformed_account,
            now=CREATED,
        )


@pytest.mark.parametrize("backup_kind", ["storage", "simple"])
def test_manifest_refuses_provider_backups_outside_exact_cleanup_scope(
    tmp_path: Path, backup_kind: str
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state = _state_view()
    server = next(
        resource
        for resource in state["resources"]
        if resource["type"] == "upcloud_server"
    )["instances"][0]["attributes"]
    if backup_kind == "storage":
        server["template"][0]["backup_rule"] = [{"interval": "daily"}]
    else:
        server["simple_backup"] = [{"plan": "daily", "time": "2200"}]
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(state)
    )

    with pytest.raises(guard.GuardError, match="provider backups"):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="upcloud",
            environment="ci-staging-with-backup",
            workspace="ci-staging-with-backup",
            state_path=state_path,
            hostname=HOSTNAME,
            request_json=_creation_get,
            now=CREATED,
        )


def test_manifest_refuses_secondary_public_ipv4_outside_exact_cleanup_scope(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    state = _state_view()
    server = next(
        resource
        for resource in state["resources"]
        if resource["type"] == "upcloud_server"
    )["instances"][0]["attributes"]
    server["network_interface"].insert(
        1, {"type": "public", "ip_address_family": "IPv4"}
    )
    state_path = _private_file(
        private / "terraform.tfstate", guard.canonical_json(state)
    )

    with pytest.raises(guard.GuardError, match="network interfaces exceed"):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="upcloud",
            environment="ci-staging-secondary-ip",
            workspace="ci-staging-secondary-ip",
            state_path=state_path,
            hostname=HOSTNAME,
            request_json=_creation_get,
            now=CREATED,
        )


def test_destroy_plan_accepts_only_exact_owned_delete_set(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    plan_path = _private_file(
        manifest_path.with_name("destroy-plan.json"),
        guard.canonical_json(_destroy_plan()),
    )

    summary = guard.validate_destroy_plan(
        manifest_path, plan_path, evidence_path, now=CREATED
    )

    assert summary == {
        "deleted_addresses": [
            "terraform_data.ssh_port",
            "upcloud_firewall_rules.vpn",
            "upcloud_server.vpn",
        ],
        "root_storage_uuid": STORAGE_UUID,
        "server_uuid": SERVER_UUID,
    }


@pytest.mark.parametrize("actions", [["create"], ["update"], ["delete", "create"]])
def test_destroy_plan_refuses_create_update_or_replace(
    tmp_path: Path, actions: list[str]
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    plan = _destroy_plan()
    plan["resource_changes"][0]["change"]["actions"] = actions
    plan_path = _private_file(
        manifest_path.with_name("plan.json"), guard.canonical_json(plan)
    )

    with pytest.raises(guard.GuardError, match="delete-only"):
        guard.validate_destroy_plan(
            manifest_path, plan_path, evidence_path, now=CREATED
        )


@pytest.mark.parametrize(
    ("server_uuid", "storage_uuid", "message"),
    [
        ("11111111-2222-4333-8444-555555555555", STORAGE_UUID, "server UUID"),
        (SERVER_UUID, "11111111-2222-4333-8444-555555555555", "storage UUID"),
    ],
)
def test_destroy_plan_refuses_foreign_ids(
    tmp_path: Path, server_uuid: str, storage_uuid: str, message: str
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    plan_path = _private_file(
        manifest_path.with_name("plan.json"),
        guard.canonical_json(
            _destroy_plan(server_uuid=server_uuid, storage_uuid=storage_uuid)
        ),
    )

    with pytest.raises(guard.GuardError, match=message):
        guard.validate_destroy_plan(
            manifest_path, plan_path, evidence_path, now=CREATED
        )


def test_destroy_plan_refuses_foreign_delete_address(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    plan = _destroy_plan()
    plan["resource_changes"].append(
        {
            "address": "upcloud_storage.foreign",
            "change": {
                "actions": ["delete"],
                "before": {"id": STORAGE_UUID},
                "after": None,
            },
        }
    )
    plan_path = _private_file(
        manifest_path.with_name("plan.json"), guard.canonical_json(plan)
    )

    with pytest.raises(guard.GuardError, match="foreign resource"):
        guard.validate_destroy_plan(
            manifest_path, plan_path, evidence_path, now=CREATED
        )


def test_destroy_plan_refuses_refreshed_secondary_public_ipv4(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    plan = _destroy_plan()
    server = next(
        item
        for item in plan["resource_changes"]
        if item["address"] == "upcloud_server.vpn"
    )["change"]["before"]
    server["network_interface"].append({"type": "public", "ip_address_family": "IPv4"})
    plan_path = _private_file(
        manifest_path.with_name("plan.json"), guard.canonical_json(plan)
    )

    with pytest.raises(guard.GuardError, match="network interfaces exceed"):
        guard.validate_destroy_plan(
            manifest_path, plan_path, evidence_path, now=CREATED
        )


def test_destroy_plan_refuses_manifest_replacement_after_reservation(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    plan_path = _private_file(
        manifest_path.with_name("plan.json"), guard.canonical_json(_destroy_plan())
    )
    shifted = CREATED + timedelta(seconds=1)
    manifest["created_at"] = guard._format_time(shifted)
    manifest["target_at"] = guard._format_time(shifted + timedelta(hours=36))
    manifest["escalation_at"] = guard._format_time(shifted + timedelta(hours=44))
    manifest["expiry_at"] = guard._format_time(shifted + timedelta(hours=47))
    _private_file(manifest_path, guard.canonical_json(manifest))

    with pytest.raises(guard.GuardError, match="reservation"):
        guard.validate_destroy_plan(
            manifest_path, plan_path, evidence_path, now=CREATED
        )


def test_destroy_plan_refuses_same_bytes_reservation_inode_replacement(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    plan_path = _private_file(
        manifest_path.with_name("plan.json"), guard.canonical_json(_destroy_plan())
    )
    replacement = evidence_path.with_name("replacement.json")
    _private_file(replacement, evidence_path.read_bytes())
    os.replace(replacement, evidence_path)

    with pytest.raises(guard.GuardError, match="reservation"):
        guard.validate_destroy_plan(
            manifest_path, plan_path, evidence_path, now=CREATED
        )


def test_mark_apply_refuses_same_bytes_reservation_replacement_before_account(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    replacement = evidence_path.with_name("replacement.json")
    _private_file(replacement, evidence_path.read_bytes())
    os.replace(replacement, evidence_path)
    requested: list[str] = []

    with pytest.raises(guard.GuardError, match="reservation"):
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=lambda path: (
                requested.append(path),
                (200, {}),
            )[1],
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert requested == []


@pytest.mark.parametrize("replaced", ["manifest", "state"])
def test_mark_apply_refuses_replacement_during_account_without_rewrite(
    tmp_path: Path, replaced: str
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    reserved = evidence_path.read_bytes()
    target = (
        manifest_path if replaced == "manifest" else Path(manifest["state"]["path"])
    )

    def replace_during_account(path: str) -> tuple[int, dict[str, object]]:
        replacement = target.with_name(f".{target.name}.replacement")
        _private_file(replacement, target.read_bytes())
        os.replace(replacement, target)
        return 200, {"account": {"username": ACCOUNT_USERNAME}}

    with pytest.raises(guard.GuardError, match="pre-apply authorization"):
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=replace_during_account,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert evidence_path.read_bytes() == reserved


def test_mark_apply_refuses_same_bytes_replacement_after_final_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    reserved = evidence_path.read_bytes()
    original_rewrite = guard._rewrite_reserved_evidence

    def replace_before_rewrite(
        path: Path,
        expected: dict[str, object],
        final: dict[str, object],
        **kwargs: object,
    ) -> None:
        replacement = evidence_path.with_name("replacement.json")
        _private_file(replacement, evidence_path.read_bytes())
        os.replace(replacement, evidence_path)
        original_rewrite(path, expected, final, **kwargs)

    monkeypatch.setattr(guard, "_rewrite_reserved_evidence", replace_before_rewrite)

    with pytest.raises(guard.GuardError, match="identity changed"):
        _mark_started(manifest_path, evidence_path)

    assert evidence_path.read_bytes() == reserved


def test_mark_apply_started_refuses_exclusive_expiry_boundary(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)

    with pytest.raises(guard.GuardError, match="expired"):
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=lambda path: (
                200,
                {"account": {"username": ACCOUNT_USERNAME}},
            ),
            now=EXPIRY,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert guard._json_object(evidence_path.read_bytes(), "evidence")["status"] == (
        "reserved"
    )


def test_expired_reserved_evidence_refuses_absence_requests(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    requested: list[str] = []

    with pytest.raises(guard.GuardError, match="does not prove apply start"):
        guard.verify_upcloud_absence(
            manifest_path,
            evidence_path,
            request_json=lambda path: (
                requested.append(path),
                (200, {}),
            )[1],
            observed_at=EXPIRY,
            now=EXPIRY,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert requested == []


def test_future_apply_started_evidence_refuses_absence_requests(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    reserved = guard._json_object(evidence_path.read_bytes(), "evidence")
    started = dict(reserved)
    started["status"] = "apply_started"
    started["apply_started_at"] = guard._format_time(CREATED + timedelta(seconds=1))
    guard._rewrite_reserved_evidence(evidence_path, reserved, started)
    requested: list[str] = []

    with pytest.raises(guard.GuardError, match="future"):
        guard.verify_upcloud_absence(
            manifest_path,
            evidence_path,
            request_json=lambda path: (
                requested.append(path),
                (200, {}),
            )[1],
            observed_at=CREATED,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert requested == []


def test_apply_started_before_deadline_can_finalize_absence_after_expiry(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    guard.mark_apply_started(
        manifest_path,
        evidence_path,
        request_json=lambda path: (
            200,
            {"account": {"username": ACCOUNT_USERNAME}},
        ),
        now=EXPIRY - timedelta(seconds=1),
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    evidence = guard.verify_upcloud_absence(
        manifest_path,
        evidence_path,
        request_json=_absent_get,
        observed_at=EXPIRY + timedelta(minutes=1),
        now=EXPIRY + timedelta(minutes=1),
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    assert evidence["status"] == "verified_after_expiry"
    assert evidence["deadline_status"] == "expired_after_apply"
    assert evidence["apply_started_at"] == guard._format_time(
        EXPIRY - timedelta(seconds=1)
    )
    assert "within_deadline" not in evidence_path.read_text()


def test_absence_check_crossing_expiry_records_late_completion(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    guard.mark_apply_started(
        manifest_path,
        evidence_path,
        request_json=lambda path: (
            200,
            {"account": {"username": ACCOUNT_USERNAME}},
        ),
        now=EXPIRY - timedelta(seconds=2),
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    evidence = guard.verify_upcloud_absence(
        manifest_path,
        evidence_path,
        request_json=_absent_get,
        now=EXPIRY - timedelta(seconds=1),
        clock=lambda: EXPIRY,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    assert evidence["status"] == "verified_after_expiry"
    assert evidence["deadline_status"] == "expired_after_apply"
    assert evidence["observed_at"] == guard._format_time(EXPIRY)


def test_absence_finalization_refuses_same_bytes_replacement_during_provider_get(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    _mark_started(manifest_path, evidence_path)
    started = evidence_path.read_bytes()

    def replace_during_storage(path: str) -> tuple[int, dict[str, object]]:
        if path == f"/1.3/storage/{STORAGE_UUID}":
            replacement = evidence_path.with_name("replacement.json")
            _private_file(replacement, evidence_path.read_bytes())
            os.replace(replacement, evidence_path)
        return _absent_get(path)

    with pytest.raises(guard.GuardError, match="identity changed"):
        guard.verify_upcloud_absence(
            manifest_path,
            evidence_path,
            request_json=replace_during_storage,
            observed_at=CREATED + timedelta(minutes=1),
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert evidence_path.read_bytes() == started


def _absent_get(path: str) -> tuple[int, dict[str, object]]:
    if path == "/1.3/account":
        return 200, {"account": {"credits": 12.34, "username": ACCOUNT_USERNAME}}
    if path == f"/1.3/server/{SERVER_UUID}":
        return 404, {"error": {"error_code": "SERVER_NOT_FOUND"}}
    if path == f"/1.3/storage/{STORAGE_UUID}":
        return 404, {"error": {"error_code": "STORAGE_NOT_FOUND"}}
    raise AssertionError(path)


def test_post_destroy_requires_authenticated_exact_provider_absence(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("post-destroy.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )
    _mark_started(manifest_path, evidence_path)
    reserved_inode = evidence_path.stat().st_ino

    evidence = guard.verify_upcloud_absence(
        manifest_path,
        evidence_path,
        request_json=_absent_get,
        observed_at=CREATED + timedelta(minutes=30),
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    assert stat.S_IMODE(evidence_path.stat().st_mode) == 0o600
    assert evidence_path.stat().st_ino == reserved_inode
    assert evidence_path.read_bytes() == guard.canonical_json(evidence)
    assert evidence["server_status"] == "absent"
    assert evidence["root_storage_status"] == "absent"
    assert evidence["billing_status"] == "no-active-owned-resources"
    assert evidence["provider_account_username"] == ACCOUNT_USERNAME
    assert "credits" not in evidence_path.read_text()


def test_post_destroy_refuses_authenticated_foreign_account(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("post-destroy.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )
    reserved = _mark_started(manifest_path, evidence_path)

    requested: list[str] = []

    def foreign_account(path: str) -> tuple[int, dict[str, object]]:
        requested.append(path)
        if path == "/1.3/account":
            return 200, {"account": {"username": "different-valid-account"}}
        return _absent_get(path)

    with pytest.raises(guard.GuardError, match="account identity"):
        guard.verify_upcloud_absence(
            manifest_path,
            evidence_path,
            request_json=foreign_account,
            observed_at=CREATED + timedelta(minutes=30),
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert evidence_path.read_bytes() == guard.canonical_json(reserved)
    assert requested == ["/1.3/account"]


@pytest.mark.parametrize("kind", ["existing", "symlink", "unsafe-parent"])
def test_evidence_reservation_refuses_unsafe_output_before_cleanup(
    tmp_path: Path, kind: str
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_parent = manifest_path.parent
    evidence_path = evidence_parent / "post-destroy.json"
    if kind == "existing":
        _private_file(evidence_path, b"existing\n")
    elif kind == "symlink":
        target = _private_file(evidence_parent / "target.json", b"target\n")
        evidence_path.symlink_to(target.name)
    else:
        evidence_parent = tmp_path / "unsafe-evidence"
        evidence_parent.mkdir(mode=0o755)
        evidence_parent.chmod(0o755)
        evidence_path = evidence_parent / "post-destroy.json"

    with pytest.raises(guard.GuardError, match="already exists|mode must be 0700"):
        guard.reserve_evidence(
            manifest_path,
            evidence_path,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )


def test_evidence_rewrite_rechecks_mode_on_opened_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("post-destroy.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )
    reserved = _mark_started(manifest_path, evidence_path)
    original_open = guard.os.open

    def open_then_widen(
        path: object, flags: int, *args: object, **kwargs: object
    ) -> int:
        fd = original_open(path, flags, *args, **kwargs)
        if path == evidence_path.name and flags & os.O_RDWR:
            os.fchmod(fd, 0o644)
        return fd

    monkeypatch.setattr(guard.os, "open", open_then_widen)

    with pytest.raises(guard.GuardError, match="mode changed while opening"):
        guard._rewrite_reserved_evidence(
            evidence_path,
            reserved,
            {"schema_version": guard.SCHEMA_VERSION, "status": "verified"},
        )


def test_pre_apply_evidence_reservation_can_be_released_exactly(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("post-destroy.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    guard.release_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )

    assert not evidence_path.exists()


def test_evidence_release_refuses_replaced_path_after_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("post-destroy.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )
    original_rename = guard.os.rename
    replacement = guard.canonical_json(
        {"schema_version": guard.SCHEMA_VERSION, "status": "foreign"}
    )
    replaced = False

    def replace_then_rename(
        source: object, target: object, *args: object, **kwargs: object
    ) -> None:
        nonlocal replaced
        if source == evidence_path.name and not replaced:
            replaced = True
            held = evidence_path.with_name("held-reservation.json")
            evidence_path.rename(held)
            _private_file(evidence_path, replacement)
        original_rename(source, target, *args, **kwargs)

    monkeypatch.setattr(guard.os, "rename", replace_then_rename)

    with pytest.raises(guard.GuardError, match="changed before release"):
        guard.release_evidence(
            manifest_path,
            evidence_path,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert evidence_path.read_bytes() == replacement


def test_evidence_release_retains_expected_inode_when_replacement_appears_after_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("post-destroy.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )
    replacement = guard.canonical_json(
        {"schema_version": guard.SCHEMA_VERSION, "status": "foreign"}
    )
    original_stat = guard.os.stat
    inserted = False

    def stat_after_rename(
        path: object, *args: object, **kwargs: object
    ) -> os.stat_result:
        nonlocal inserted
        if (
            path == evidence_path.name
            and kwargs.get("dir_fd") is not None
            and not inserted
        ):
            try:
                return original_stat(path, *args, **kwargs)
            except FileNotFoundError:
                inserted = True
                _private_file(evidence_path, replacement)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(guard.os, "stat", stat_after_rename)

    with pytest.raises(guard.GuardError, match="requires manual recovery"):
        guard.release_evidence(
            manifest_path,
            evidence_path,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert evidence_path.read_bytes() == replacement
    recovery = list(evidence_path.parent.glob(".post-destroy.json.release-*"))
    assert len(recovery) == 1
    assert stat.S_IMODE(recovery[0].stat().st_mode) == 0o600


def test_evidence_release_refuses_replacement_between_validation_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = _reserved_evidence_path(manifest_path)
    reserved = evidence_path.read_bytes()
    retained = evidence_path.with_name("retained-original.json")
    original_open_parent = guard._open_private_parent
    evidence_opens = 0

    def replace_before_second_open(
        path: Path, label: str, *, exact_mode: bool = True
    ) -> tuple[int, str]:
        nonlocal evidence_opens
        result = original_open_parent(path, label, exact_mode=exact_mode)
        if label == "provider evidence reservation":
            evidence_opens += 1
            if evidence_opens == 2:
                evidence_path.rename(retained)
                _private_file(evidence_path, reserved)
        return result

    monkeypatch.setattr(guard, "_open_private_parent", replace_before_second_open)

    with pytest.raises(guard.GuardError, match="identity changed"):
        guard.release_evidence(
            manifest_path,
            evidence_path,
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert retained.read_bytes() == reserved
    assert evidence_path.read_bytes() == reserved


def test_private_plan_descriptor_rewinds_same_inode(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    plan_path = _private_file(private / "destroy.tfplan", b"binary-plan")
    fd = os.open(plan_path, os.O_RDONLY)
    try:
        assert os.read(fd, 64) == b"binary-plan"

        guard.rewind_plan_fd(fd)

        assert os.read(fd, 64) == b"binary-plan"
    finally:
        os.close(fd)


def test_plan_descriptor_refuses_non_private_inode(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    plan_path = _private_file(private / "destroy.tfplan", b"binary-plan")
    plan_path.chmod(0o644)
    fd = os.open(plan_path, os.O_RDONLY)
    try:
        with pytest.raises(guard.GuardError, match="not a private owned regular file"):
            guard.rewind_plan_fd(fd)
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    ("failed_path", "status", "body", "message"),
    [
        (
            "account",
            401,
            {"error": {"error_code": "AUTHENTICATION_FAILED"}},
            "account identity",
        ),
        ("server", 200, {"server": {"uuid": SERVER_UUID}}, "server still exists"),
        (
            "server",
            403,
            {"error": {"error_code": "SERVER_FORBIDDEN"}},
            "server absence",
        ),
        ("storage", 200, {"storage": {"uuid": STORAGE_UUID}}, "storage still exists"),
        (
            "storage",
            403,
            {"error": {"error_code": "STORAGE_FORBIDDEN"}},
            "storage absence",
        ),
    ],
)
def test_post_destroy_refuses_auth_existing_or_ambiguous_resources(
    tmp_path: Path,
    failed_path: str,
    status: int,
    body: dict[str, object],
    message: str,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("post.json")
    guard.reserve_evidence(
        manifest_path,
        evidence_path,
        now=CREATED,
        expected_provider="upcloud",
        expected_environment="ci-staging-20260829",
    )
    reserved = _mark_started(manifest_path, evidence_path)

    def request(path: str) -> tuple[int, dict[str, object]]:
        if failed_path == "account" and path == "/1.3/account":
            return status, body
        if path == "/1.3/account":
            return 200, {"account": {"username": ACCOUNT_USERNAME}}
        if failed_path == "server" and path.endswith(SERVER_UUID):
            return status, body
        if path.endswith(SERVER_UUID):
            return 404, {"error": {"error_code": "SERVER_NOT_FOUND"}}
        if failed_path == "storage" and path.endswith(STORAGE_UUID):
            return status, body
        return 404, {"error": {"error_code": "STORAGE_NOT_FOUND"}}

    with pytest.raises(guard.GuardError, match=message):
        guard.verify_upcloud_absence(
            manifest_path,
            evidence_path,
            request_json=request,
            observed_at=CREATED + timedelta(minutes=30),
            now=CREATED,
            expected_provider="upcloud",
            expected_environment="ci-staging-20260829",
        )

    assert evidence_path.read_bytes() == guard.canonical_json(reserved)
