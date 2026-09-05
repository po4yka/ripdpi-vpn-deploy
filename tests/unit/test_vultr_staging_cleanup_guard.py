"""Contracts for the isolated Vultr staging cleanup adapter."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/vultr-staging-cleanup-guard.py"
SPEC = importlib.util.spec_from_file_location("vultr_cleanup_guard", SCRIPT)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
REAL_TERRAFORM_SHOW = guard._terraform_show_json

SERVER = "00112233-4455-4677-8899-aabbccddeeff"
SSH_RESOURCE = "10112233-4455-4677-8899-aabbccddeeff"
FIREWALL = "20112233-4455-4677-8899-aabbccddeeff"
RULE_ONE = "30112233-4455-4677-8899-aabbccddeeff"
RULE_TWO = "40112233-4455-4677-8899-aabbccddeeff"
RULE_THREE = "50112233-4455-4677-8899-aabbccddeeff"
RULE_FOUR = "60112233-4455-4677-8899-aabbccddeeff"
RULE_FIVE = "70112233-4455-4677-8899-aabbccddeeff"
RULE_SIX = "80112233-4455-4677-8899-aabbccddeeff"
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
CREATED = NOW - timedelta(hours=2)
ENV = "ci-staging-20260905"
HOST = "vpn-ci-staging-20260905"
PLAN_VIEWS: dict[tuple[int, int], bytes] = {}


def _private(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def _request(path: str) -> tuple[int, dict[str, object]]:
    if path == "/v2/account":
        return 200, {"account": {"email": "cleanup@example.test", "balance": "2.83"}}
    if path == f"/v2/instances/{SERVER}":
        return 200, {
            "instance": {
                "id": SERVER,
                "hostname": HOST,
                "date_created": "2026-09-05T10:00:00+00:00",
            }
        }
    if path.startswith("/v2/"):
        return 404, {}
    raise AssertionError(path)


def _absent_request(path: str) -> tuple[int, dict[str, object]]:
    if path == "/v2/account":
        return 200, {"account": {"email": "cleanup@example.test"}}
    if path.startswith("/v2/"):
        return 404, {}
    raise AssertionError(path)


def _state(*, extras: list[dict[str, object]] | None = None) -> dict[str, object]:
    records: list[dict[str, object]] = [
        {
            "mode": "managed",
            "type": "terraform_data",
            "name": "ssh_port",
            "instances": [{"attributes": {"id": "local"}}],
        },
        {
            "mode": "managed",
            "type": "vultr_ssh_key",
            "name": "admin",
            "instances": [{"attributes": {"id": SSH_RESOURCE}}],
        },
        {
            "mode": "managed",
            "type": "vultr_firewall_group",
            "name": "vpn",
            "instances": [{"attributes": {"id": FIREWALL}}],
        },
        {
            "mode": "managed",
            "type": "vultr_instance",
            "name": "vpn",
            "instances": [
                {
                    "attributes": {
                        "id": SERVER,
                        "hostname": HOST,
                        "label": HOST,
                        "backups": "disabled",
                        "firewall_group_id": FIREWALL,
                        "ssh_key_ids": [SSH_RESOURCE],
                    }
                }
            ],
        },
        {
            "mode": "managed",
            "type": "vultr_firewall_rule",
            "name": "icmp",
            "instances": [
                {
                    "index_key": "v4",
                    "attributes": {
                        "id": RULE_ONE,
                        "firewall_group_id": FIREWALL,
                        "protocol": "icmp",
                        "ip_type": "v4",
                        "subnet": "0.0.0.0",
                        "subnet_size": 0,
                    },
                },
                {
                    "index_key": "v6",
                    "attributes": {
                        "id": RULE_FOUR,
                        "firewall_group_id": FIREWALL,
                        "protocol": "icmp",
                        "ip_type": "v6",
                        "subnet": "::",
                        "subnet_size": 0,
                    },
                },
            ],
        },
        {
            "mode": "managed",
            "type": "vultr_firewall_rule",
            "name": "ssh",
            "instances": [
                {
                    "index_key": "203.0.113.1/32",
                    "attributes": {
                        "id": RULE_TWO,
                        "firewall_group_id": FIREWALL,
                        "protocol": "tcp",
                        "ip_type": "v4",
                        "port": "22",
                        "subnet": "203.0.113.1",
                        "subnet_size": 32,
                    },
                },
                {
                    "index_key": "2001:db8::1/128",
                    "attributes": {
                        "id": RULE_FIVE,
                        "firewall_group_id": FIREWALL,
                        "protocol": "tcp",
                        "ip_type": "v6",
                        "port": "22",
                        "subnet": "2001:db8::1",
                        "subnet_size": 128,
                    },
                },
            ],
        },
        {
            "mode": "managed",
            "type": "vultr_firewall_rule",
            "name": "tcp_public",
            "instances": [
                {
                    "index_key": "v4-tcp-443",
                    "attributes": {
                        "id": RULE_THREE,
                        "firewall_group_id": FIREWALL,
                        "protocol": "tcp",
                        "ip_type": "v4",
                        "port": "443",
                        "subnet": "0.0.0.0",
                        "subnet_size": 0,
                    },
                },
                {
                    "index_key": "v6-udp-51820",
                    "attributes": {
                        "id": RULE_SIX,
                        "firewall_group_id": FIREWALL,
                        "protocol": "udp",
                        "ip_type": "v6",
                        "port": "51820",
                        "subnet": "::",
                        "subnet_size": 0,
                    },
                },
            ],
        },
    ]
    return {"version": 4, "resources": records + (extras or [])}


def _manifest(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    private = tmp_path / "private"
    state_path = _private(private / "terraform.tfstate", guard.canonical_json(_state()))
    manifest_path = private / "manifest.json"
    return manifest_path, guard.create_manifest(
        output_path=manifest_path,
        provider="vultr",
        environment=ENV,
        workspace=ENV,
        state_path=state_path,
        hostname=HOST,
        request_json=_request,
        now=NOW,
    )


def _plan() -> dict[str, object]:
    changes = []
    for address, identifier in {
        "terraform_data.ssh_port": "local",
        "vultr_ssh_key.admin": SSH_RESOURCE,
        "vultr_firewall_group.vpn": FIREWALL,
        "vultr_instance.vpn": SERVER,
        'vultr_firewall_rule.icmp["v4"]': RULE_ONE,
        'vultr_firewall_rule.icmp["v6"]': RULE_FOUR,
        'vultr_firewall_rule.ssh["203.0.113.1/32"]': RULE_TWO,
        'vultr_firewall_rule.ssh["2001:db8::1/128"]': RULE_FIVE,
        'vultr_firewall_rule.tcp_public["v4-tcp-443"]': RULE_THREE,
        'vultr_firewall_rule.tcp_public["v6-udp-51820"]': RULE_SIX,
    }.items():
        changes.append(
            {
                "address": address,
                "change": {
                    "actions": ["delete"],
                    "before": {"id": identifier},
                    "after": None,
                },
            }
        )
    return {"format_version": "1.2", "resource_changes": changes}


def _plan_files(parent: Path, view: dict[str, object]) -> tuple[Path, int]:
    binary = _private(parent / "destroy.tfplan", b"TFPLAN\x00private-binary\n")
    fd = os.open(binary, os.O_RDONLY)
    info = os.fstat(fd)
    PLAN_VIEWS[(info.st_dev, info.st_ino)] = guard.canonical_json(view)
    return binary, fd


@pytest.fixture(autouse=True)
def _same_fd_terraform_show(monkeypatch: pytest.MonkeyPatch) -> None:
    PLAN_VIEWS.clear()

    def render(plan_fd: int) -> bytes:
        info = os.fstat(plan_fd)
        try:
            return PLAN_VIEWS[(info.st_dev, info.st_ino)]
        except KeyError as exc:
            raise guard.GuardError("destroy plan JSON view is unavailable") from exc

    monkeypatch.setattr(guard, "_terraform_show_json", render)


def test_manifest_is_private_canonical_and_binds_exact_vultr_resources(
    tmp_path: Path,
) -> None:
    path, manifest = _manifest(tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_bytes() == guard.canonical_json(manifest)
    assert manifest["resources"]["root"] == {
        "kind": "instance-root",
        "server_id": SERVER,
        "separate_storage_id": None,
    }
    assert manifest["created_at"] == "2026-09-05T10:00:00Z"
    assert manifest["target_at"] == "2026-09-06T22:00:00Z"
    assert manifest["escalation_at"] == "2026-09-07T06:00:00Z"
    assert manifest["expiry_at"] == "2026-09-07T09:00:00Z"
    assert (
        manifest["provider_account_binding"]
        == hashlib.sha256(b"vultr-account-v1:cleanup@example.test").hexdigest()
    )
    assert "cleanup@example.test" not in path.read_text()


@pytest.mark.parametrize("kind", ["backup", "ip", "dns", "foreign"])
def test_manifest_refuses_resources_outside_owned_cleanup_set(
    tmp_path: Path, kind: str
) -> None:
    mapping = {
        "backup": {
            "mode": "managed",
            "type": "vultr_instance",
            "name": "backup",
            "instances": [{"attributes": {}}],
        },
        "ip": {
            "mode": "managed",
            "type": "vultr_instance_ipv4",
            "name": "honeypot",
            "instances": [{"attributes": {}}],
        },
        "dns": {
            "mode": "managed",
            "type": "vultr_dns_record",
            "name": "endpoint",
            "instances": [{"attributes": {}}],
        },
        "foreign": {
            "mode": "managed",
            "type": "vultr_reserved_ip",
            "name": "extra",
            "instances": [{"attributes": {}}],
        },
    }
    private = tmp_path / "private"
    state_path = _private(
        private / "state.json", guard.canonical_json(_state(extras=[mapping[kind]]))
    )
    with pytest.raises(guard.GuardError):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="vultr",
            environment=ENV,
            workspace=ENV,
            state_path=state_path,
            hostname=HOST,
            request_json=_request,
            now=NOW,
        )


def test_manifest_refuses_foreign_or_malformed_for_each_firewall_rules(
    tmp_path: Path,
) -> None:
    state = _state()
    rules = next(
        item
        for item in state["resources"]
        if item["type"] == "vultr_firewall_rule" and item["name"] == "icmp"
    )
    rules["name"] = "foreign_listener"
    private = tmp_path / "private"
    state_path = _private(private / "state.json", guard.canonical_json(state))
    with pytest.raises(guard.GuardError, match="firewall rule"):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="vultr",
            environment=ENV,
            workspace=ENV,
            state_path=state_path,
            hostname=HOST,
            request_json=_request,
            now=NOW,
        )


def test_manifest_requires_both_exact_icmp_families(tmp_path: Path) -> None:
    state = _state()
    rules = next(
        item
        for item in state["resources"]
        if item["type"] == "vultr_firewall_rule" and item["name"] == "icmp"
    )
    rules["instances"] = rules["instances"][:1]
    private = tmp_path / "private"
    state_path = _private(private / "state.json", guard.canonical_json(state))
    with pytest.raises(guard.GuardError, match="ICMP v4 and v6"):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="vultr",
            environment=ENV,
            workspace=ENV,
            state_path=state_path,
            hostname=HOST,
            request_json=_request,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("rule_name", "index", "invalid_size"),
    [("ssh", 0, 0), ("tcp_public", 0, 32)],
)
def test_manifest_refuses_malformed_firewall_subnet_sizes(
    tmp_path: Path, rule_name: str, index: int, invalid_size: int
) -> None:
    state = _state()
    rules = next(
        item
        for item in state["resources"]
        if item["type"] == "vultr_firewall_rule" and item["name"] == rule_name
    )
    rules["instances"][index]["attributes"]["subnet_size"] = invalid_size
    private = tmp_path / "private"
    state_path = _private(private / "state.json", guard.canonical_json(state))
    with pytest.raises(guard.GuardError, match="rule is not exact"):
        guard.create_manifest(
            output_path=private / "manifest.json",
            provider="vultr",
            environment=ENV,
            workspace=ENV,
            state_path=state_path,
            hostname=HOST,
            request_json=_request,
            now=NOW,
        )


def test_missing_environment_api_key_refuses_without_disclosure() -> None:
    with pytest.raises(guard.GuardError, match="VULTR_API_KEY"):
        guard._vultr_request_from_environment({})


def test_plan_apply_and_typed_absence_are_bound_to_manifest_and_account(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    reserved = guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    try:
        result = guard.validate_destroy_plan(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
        assert result["server_id"] == SERVER
        started = guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
    finally:
        os.close(fd)
    assert started["status"] == "apply_started"
    verified = guard.verify_vultr_absence(
        manifest_path,
        evidence_path,
        request_json=_absent_request,
        now=NOW + timedelta(minutes=5),
        expected_environment=ENV,
    )
    assert verified["billing_status"] == "no-active-owned-resources"
    assert verified["absent_addresses"] == [
        "vultr_firewall_group.vpn",
        'vultr_firewall_rule.icmp["v4"]',
        'vultr_firewall_rule.icmp["v6"]',
        'vultr_firewall_rule.ssh["2001:db8::1/128"]',
        'vultr_firewall_rule.ssh["203.0.113.1/32"]',
        'vultr_firewall_rule.tcp_public["v4-tcp-443"]',
        'vultr_firewall_rule.tcp_public["v6-udp-51820"]',
        "vultr_instance.vpn",
        "vultr_ssh_key.admin",
    ]
    assert "balance" not in evidence_path.read_text()
    assert manifest["resources"]["server_id"] == SERVER
    assert reserved["status"] == "reserved"


@pytest.mark.parametrize("mutation", ["update", "foreign", "missing-rule"])
def test_destroy_plan_refuses_nonexact_or_nondelete_actions(
    tmp_path: Path, mutation: str
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    plan = _plan()
    if mutation == "update":
        plan["resource_changes"][0]["change"]["actions"] = ["update"]
    elif mutation == "foreign":
        plan["resource_changes"].append(
            {
                "address": 'vultr_firewall_rule.foreign["v4-tcp-443"]',
                "change": {
                    "actions": ["delete"],
                    "before": {"id": SERVER},
                    "after": None,
                },
            }
        )
    else:
        plan["resource_changes"].pop()
    _, fd = _plan_files(manifest_path.parent, plan)
    try:
        with pytest.raises(guard.GuardError):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        os.close(fd)


def test_preapply_reauth_and_evidence_inode_replacement_refuse(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    guard.validate_destroy_plan(
        manifest_path,
        evidence_path,
        request_json=_request,
        plan_fd=fd,
        now=NOW,
        expected_environment=ENV,
    )
    replacement = evidence_path.with_name("replacement.json")
    _private(replacement, evidence_path.read_bytes())
    replacement.replace(evidence_path)
    with pytest.raises(guard.GuardError, match="identity"):
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
    os.close(fd)


def test_evidence_status_uses_atomic_inode_replacement(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    guard.validate_destroy_plan(
        manifest_path,
        evidence_path,
        request_json=_request,
        plan_fd=fd,
        now=NOW,
        expected_environment=ENV,
    )
    reserved_inode = evidence_path.stat().st_ino
    try:
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
    finally:
        os.close(fd)
    assert evidence_path.stat().st_ino != reserved_inode
    assert not list(evidence_path.parent.glob(".evidence.json.previous-*"))


def test_absence_requires_every_id_to_return_404_and_account_to_match(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    try:
        guard.validate_destroy_plan(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
    finally:
        os.close(fd)

    def ambiguous(path: str) -> tuple[int, dict[str, object]]:
        if path == "/v2/account":
            return 200, {"account": {"email": "cleanup@example.test"}}
        return 200, {}

    with pytest.raises(guard.GuardError, match="absence"):
        guard.verify_vultr_absence(
            manifest_path,
            evidence_path,
            request_json=ambiguous,
            now=NOW,
            expected_environment=ENV,
        )


def test_post_apply_empty_terraform_state_does_not_block_typed_provider_absence(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    try:
        guard.validate_destroy_plan(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
    finally:
        os.close(fd)
    _private(
        Path(manifest["state"]["path"]),
        guard.canonical_json({"version": 4, "resources": []}),
    )
    verified = guard.verify_vultr_absence(
        manifest_path,
        evidence_path,
        request_json=_absent_request,
        now=NOW,
        expected_environment=ENV,
    )
    assert verified["billing_status"] == "no-active-owned-resources"


def test_manifest_deadlines_derive_from_delayed_provider_creation(
    tmp_path: Path,
) -> None:
    def delayed(path: str) -> tuple[int, dict[str, object]]:
        if path == "/v2/account":
            return 200, {"account": {"email": "cleanup@example.test"}}
        if path == f"/v2/instances/{SERVER}":
            return 200, {
                "instance": {
                    "id": SERVER,
                    "hostname": HOST,
                    "date_created": "2026-09-05T11:45:00+00:00",
                }
            }
        raise AssertionError(path)

    private = tmp_path / "private"
    state_path = _private(private / "terraform.tfstate", guard.canonical_json(_state()))
    manifest = guard.create_manifest(
        output_path=private / "manifest.json",
        provider="vultr",
        environment=ENV,
        workspace=ENV,
        state_path=state_path,
        hostname=HOST,
        request_json=delayed,
        now=NOW,
    )
    assert manifest["created_at"] == "2026-09-05T11:45:00Z"
    assert manifest["expiry_at"] == "2026-09-07T10:45:00Z"


def test_authenticated_preflight_refuses_account_mismatch_before_plan() -> None:
    def foreign(path: str) -> tuple[int, dict[str, object]]:
        assert path == "/v2/account"
        return 200, {"account": {"email": "other@example.test"}}

    with pytest.raises(guard.GuardError, match="VULTR_API_KEY"):
        guard.authenticated_preflight(foreign, {})
    assert guard.authenticated_preflight(
        _request, {"VULTR_API_KEY": "not-printed"}
    ) != guard.authenticated_preflight(foreign, {"VULTR_API_KEY": "not-printed"})


def test_preapply_account_mismatch_refuses_before_instance_or_plan_use(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    guard.validate_destroy_plan(
        manifest_path,
        evidence_path,
        request_json=_request,
        plan_fd=fd,
        now=NOW,
        expected_environment=ENV,
    )
    calls: list[str] = []

    def foreign(path: str) -> tuple[int, dict[str, object]]:
        calls.append(path)
        return 200, {"account": {"email": "other@example.test"}}

    try:
        with pytest.raises(guard.GuardError, match="account identity changed"):
            guard.mark_apply_started(
                manifest_path,
                evidence_path,
                request_json=foreign,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        os.close(fd)
    assert calls == ["/v2/account"]


def test_same_plan_fd_must_survive_from_validation_to_apply(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    try:
        result = guard.validate_destroy_plan(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
        os.lseek(fd, 0, os.SEEK_SET)
        os.read(fd, 1)
        guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
    finally:
        os.close(fd)


def test_different_plan_bytes_fail_at_apply_boundary(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    first, first_fd = _plan_files(manifest_path.parent, _plan())
    second_plan = _plan()
    second_plan["resource_changes"][0]["change"]["before"]["id"] = "changed"
    second = _private(manifest_path.parent / "second.tfplan", b"TFPLAN\x00other\n")
    second_fd = os.open(second, os.O_RDONLY)
    try:
        result = guard.validate_destroy_plan(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=first_fd,
            now=NOW,
            expected_environment=ENV,
        )
        with pytest.raises(guard.GuardError, match="descriptor changed"):
            guard.mark_apply_started(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=second_fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        os.close(first_fd)
        os.close(second_fd)


def test_controller_owned_plan_view_refuses_mismatched_same_fd_view(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    try:
        info = os.fstat(fd)
        mismatched = _plan()
        mismatched["resource_changes"][0]["change"]["before"]["id"] = "foreign"
        PLAN_VIEWS[(info.st_dev, info.st_ino)] = guard.canonical_json(mismatched)
        with pytest.raises(guard.GuardError, match="binding is foreign"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        os.close(fd)


def test_validation_persists_plan_binding_and_apply_requires_a_descriptor(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    try:
        guard.validate_destroy_plan(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            expected_environment=ENV,
        )
        evidence = guard._json(evidence_path.read_bytes(), "evidence")
        assert evidence["status"] == "plan_validated"
        assert evidence["plan_binding"]["sha256"] == guard.bind_plan_fd(fd).sha256
        with pytest.raises(guard.GuardError, match="descriptor is required"):
            guard.mark_apply_started(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=None,  # type: ignore[arg-type]
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        os.close(fd)


def test_preflight_manifest_account_binds_authentication_before_plan(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    assert (
        guard.preflight_manifest_account(
            manifest_path,
            request_json=_request,
            environment={"VULTR_API_KEY": "not-printed"},
            now=NOW,
            expected_environment=ENV,
        )
        == manifest
    )

    def foreign(path: str) -> tuple[int, dict[str, object]]:
        assert path == "/v2/account"
        return 200, {"account": {"email": "other@example.test"}}

    with pytest.raises(guard.GuardError, match="account identity changed"):
        guard.preflight_manifest_account(
            manifest_path,
            request_json=foreign,
            environment={"VULTR_API_KEY": "not-printed"},
            now=NOW,
            expected_environment=ENV,
        )


def test_release_and_recovery_tombstone_only_the_owned_reservation(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    guard.release_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    assert not evidence_path.exists()
    assert not guard._reservation_path(evidence_path).exists()

    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    guard.recover_reserved_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    assert not evidence_path.exists()
    assert not guard._reservation_path(evidence_path).exists()


def test_reservation_second_write_failure_tombstones_only_new_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    original = guard._private_write_new
    writes = 0

    def fail_reservation(path: Path, data: bytes, label: str) -> tuple[int, int]:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise guard.GuardError("simulated reservation write failure")
        return original(path, data, label)

    monkeypatch.setattr(guard, "_private_write_new", fail_reservation)
    with pytest.raises(guard.GuardError, match="simulated reservation"):
        guard.reserve_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
    assert not evidence_path.exists()
    assert not guard._reservation_path(evidence_path).exists()


def test_transition_recovery_finishes_after_reservation_inode_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._replace_private

    def fail_second(*args: object, **kwargs: object) -> tuple[int, int]:
        if args[0] == guard._reservation_path(evidence_path):
            raise guard.GuardError("simulated reservation replacement failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(guard, "_replace_private", fail_second)
    try:
        with pytest.raises(guard.GuardError, match="simulated reservation"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_replace_private", original)
        os.close(fd)
    value, _ = guard._evidence(manifest, manifest_path, evidence_path, "plan_validated")
    assert value["status"] == "plan_validated"
    assert not guard._transition_path(evidence_path).exists()


def test_transition_recovery_discards_prepublication_journal_only_for_old_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._replace_private

    def fail_evidence_replace(*args: object, **kwargs: object) -> tuple[int, int]:
        if args[0] == evidence_path:
            raise guard.GuardError("simulated evidence replacement failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(guard, "_replace_private", fail_evidence_replace)
    try:
        with pytest.raises(guard.GuardError, match="simulated evidence"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_replace_private", original)
        os.close(fd)
    value, _ = guard._evidence(manifest, manifest_path, evidence_path, "reserved")
    assert value["status"] == "reserved"
    assert not guard._transition_path(evidence_path).exists()


def test_prepublication_recovery_refuses_same_bytes_foreign_evidence_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._replace_private

    def swap_before_evidence_replace(
        *args: object, **kwargs: object
    ) -> tuple[int, int]:
        if args[0] == evidence_path:
            replacement = evidence_path.with_name("old-evidence-copy.json")
            _private(replacement, evidence_path.read_bytes())
            replacement.replace(evidence_path)
            raise guard.GuardError("simulated evidence replacement failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(guard, "_replace_private", swap_before_evidence_replace)
    try:
        with pytest.raises(guard.GuardError, match="simulated evidence"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_replace_private", original)
        os.close(fd)
    with pytest.raises(guard.GuardError, match="manual recovery"):
        guard._evidence(manifest, manifest_path, evidence_path, "reserved")
    assert guard._transition_path(evidence_path).exists()


def test_transition_recovery_refuses_same_bytes_foreign_evidence_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._replace_private

    def replace_then_swap(*args: object, **kwargs: object) -> tuple[int, int]:
        path = args[0]
        if path == guard._reservation_path(evidence_path):
            replacement = evidence_path.with_name("evidence-copy.json")
            _private(replacement, evidence_path.read_bytes())
            replacement.replace(evidence_path)
            raise guard.GuardError("simulated reservation replacement failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(guard, "_replace_private", replace_then_swap)
    try:
        with pytest.raises(guard.GuardError, match="simulated reservation"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_replace_private", original)
        os.close(fd)
    with pytest.raises(guard.GuardError, match="manual recovery"):
        guard._evidence(manifest, manifest_path, evidence_path, "plan_validated")
    assert evidence_path.exists()
    assert guard._transition_path(evidence_path).exists()


def test_terraform_show_uses_same_fd_and_redacts_subprocess_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _private(tmp_path / "private" / "destroy.tfplan", b"TFPLAN\x00")
    fd = os.open(plan, os.O_RDONLY)
    seen: dict[str, object] = {}

    def success(argv: list[str], **kwargs: object) -> SimpleNamespace:
        seen["argv"] = argv
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b"{}")

    monkeypatch.setattr(guard.subprocess, "run", success)
    try:
        assert REAL_TERRAFORM_SHOW(fd) == b"{}"
        assert seen["argv"] == ["terraform", "show", "-json", f"/dev/fd/{fd}"]
        assert seen["pass_fds"] == (fd,)
        assert seen["timeout"] == 30
        monkeypatch.setattr(
            guard.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b"secret"),
        )
        with pytest.raises(guard.GuardError, match="JSON view is unavailable"):
            REAL_TERRAFORM_SHOW(fd)
        monkeypatch.setattr(
            guard.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout=b"x" * (guard.MAX_JSON_BYTES + 1)
            ),
        )
        with pytest.raises(guard.GuardError, match="JSON view is unavailable"):
            REAL_TERRAFORM_SHOW(fd)
        monkeypatch.setattr(
            guard.subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("secret")),
        )
        with pytest.raises(guard.GuardError, match="JSON view is unavailable"):
            REAL_TERRAFORM_SHOW(fd)
    finally:
        os.close(fd)


def test_malformed_controller_generated_plan_view_refuses_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    monkeypatch.setattr(guard, "_terraform_show_json", lambda _fd: b"not-json")
    try:
        with pytest.raises(
            guard.GuardError, match="destroy plan view is not valid JSON"
        ):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        os.close(fd)


def test_cli_create_manifest_uses_env_token_without_printing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private = tmp_path / "private"
    state_path = _private(private / "state.json", guard.canonical_json(_state()))
    output = private / "manifest.json"
    monkeypatch.setenv("VULTR_API_KEY", "secret-token-must-not-print")
    monkeypatch.setattr(guard, "_vultr_https_request", lambda token: _request)
    assert (
        guard.main(
            [
                "create-manifest",
                "--output",
                str(output),
                "--provider",
                "vultr",
                "--environment",
                ENV,
                "--workspace",
                ENV,
                "--state",
                str(state_path),
                "--hostname",
                HOST,
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "manifest created" in captured.out
    assert "secret-token" not in captured.out + captured.err


def test_release_recovery_finishes_after_first_inode_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    original = guard._tombstone_unlink
    unlinks = 0

    def fail_second(*args: object, **kwargs: object) -> None:
        nonlocal unlinks
        unlinks += 1
        if unlinks == 2:
            raise guard.GuardError("simulated reservation release failure")
        original(*args, **kwargs)

    monkeypatch.setattr(guard, "_tombstone_unlink", fail_second)
    with pytest.raises(guard.GuardError, match="simulated reservation release"):
        guard.release_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
    monkeypatch.setattr(guard, "_tombstone_unlink", original)
    guard.recover_reserved_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    assert not evidence_path.exists()
    assert not guard._reservation_path(evidence_path).exists()
    assert not guard._transition_path(evidence_path).exists()


def test_platform_without_nofollow_refuses_private_manifest_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _private(tmp_path / "private" / "manifest.json", b"{}\n")
    monkeypatch.delattr(guard.os, "O_NOFOLLOW", raising=False)
    with pytest.raises(guard.GuardError, match="no-follow"):
        guard._private_read(path, "manifest", max_bytes=1024)
