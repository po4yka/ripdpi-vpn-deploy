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
RULE_ONE = "30112233"
RULE_TWO = "40112233"
RULE_THREE = "50112233"
RULE_FOUR = "60112233"
RULE_FIVE = "70112233"
RULE_SIX = "80112233"
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


def _state(
    *, ssh_port: int = 22, extras: list[dict[str, object]] | None = None
) -> dict[str, object]:
    records: list[dict[str, object]] = [
        {
            "mode": "managed",
            "type": "terraform_data",
            "name": "ssh_port",
            "instances": [{"attributes": {"id": "local", "input": ssh_port}}],
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
                        "port": str(ssh_port),
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
                        "port": str(ssh_port),
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

    def render(plan_fd: int, environment: str) -> bytes:
        assert environment == ENV
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
    assert manifest["resources"]["ssh_port"] == 22
    assert manifest["created_at"] == "2026-09-05T10:00:00Z"
    assert manifest["target_at"] == "2026-09-06T22:00:00Z"
    assert manifest["escalation_at"] == "2026-09-07T06:00:00Z"
    assert manifest["expiry_at"] == "2026-09-07T09:00:00Z"
    assert (
        manifest["provider_account_binding"]
        == hashlib.sha256(b"vultr-account-v1:cleanup@example.test").hexdigest()
    )
    assert "cleanup@example.test" not in path.read_text()


def test_manifest_binds_configured_ssh_port_and_decimal_firewall_rule_ids(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    state_path = _private(
        private / "terraform.tfstate", guard.canonical_json(_state(ssh_port=2222))
    )
    manifest = guard.create_manifest(
        output_path=private / "manifest.json",
        provider="vultr",
        environment=ENV,
        workspace=ENV,
        state_path=state_path,
        hostname=HOST,
        request_json=_request,
        now=NOW,
    )

    assert manifest["resources"]["ssh_port"] == 2222
    assert set(manifest["resources"]["firewall_rules"].values()) == {
        RULE_ONE,
        RULE_TWO,
        RULE_THREE,
        RULE_FOUR,
        RULE_FIVE,
        RULE_SIX,
    }


@pytest.mark.parametrize("rule_id", ["0", "-1", "1.5", "rule-123", 123])
def test_manifest_refuses_non_decimal_firewall_rule_ids(
    tmp_path: Path, rule_id: object
) -> None:
    state = _state()
    rule = next(
        item for item in state["resources"] if item["type"] == "vultr_firewall_rule"
    )["instances"][0]["attributes"]
    rule["id"] = rule_id
    private = tmp_path / "private"
    state_path = _private(private / "state.json", guard.canonical_json(state))

    with pytest.raises(guard.GuardError, match="positive decimal ID"):
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


@pytest.mark.parametrize("missing", ["ssh", "tcp_public"])
def test_manifest_requires_every_firewall_rule_class(
    tmp_path: Path, missing: str
) -> None:
    state = _state()
    state["resources"] = [
        item
        for item in state["resources"]
        if not (
            item.get("type") == "vultr_firewall_rule" and item.get("name") == missing
        )
    ]
    private = tmp_path / "private"
    state_path = _private(private / "state.json", guard.canonical_json(state))

    with pytest.raises(guard.GuardError, match="firewall rule class"):
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
    reserved_inode = evidence_path.stat().st_ino
    evidence_fd = os.open(evidence_path, os.O_RDONLY)
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
    assert evidence_path.stat().st_ino == reserved_inode
    os.lseek(evidence_fd, 0, os.SEEK_SET)
    try:
        assert os.read(evidence_fd, guard.MAX_JSON_BYTES) == guard.canonical_json(
            verified
        )
    finally:
        os.close(evidence_fd)
    assert manifest["resources"]["server_id"] == SERVER
    assert reserved["status"] == "reserved"


def test_plan_refuses_byte_identical_state_inode_replacement_after_reservation(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    state_path = Path(manifest["state"]["path"])
    replacement = _private(
        state_path.with_name("replacement.tfstate"), state_path.read_bytes()
    )
    replacement.replace(state_path)
    _, fd = _plan_files(manifest_path.parent, _plan())
    try:
        with pytest.raises(guard.GuardError, match="state identity changed"):
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


def test_apply_started_recovery_verifies_absence_without_a_second_plan_or_apply(
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

    assert (
        guard.recover_reserved_evidence(
            manifest_path,
            evidence_path,
            request_json=_absent_request,
            now=NOW + timedelta(minutes=1),
            expected_environment=ENV,
        )
        == "verified"
    )
    assert guard._json(evidence_path.read_bytes(), "evidence")["status"] == "verified"


def test_apply_started_recovery_accepts_destroyed_state_before_absence_verification(
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

    state_path = Path(manifest["state"]["path"])
    state_path.write_bytes(b'{"version":4,"resources":[]}\n')
    state_path.chmod(0o600)

    assert (
        guard.recover_reserved_evidence(
            manifest_path,
            evidence_path,
            request_json=_absent_request,
            now=NOW + timedelta(minutes=1),
            expected_environment=ENV,
        )
        == "verified"
    )
    assert guard._json(evidence_path.read_bytes(), "evidence")["status"] == "verified"


def test_terminal_absence_receipt_recovery_is_idempotent_without_provider_calls(
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
    guard.verify_vultr_absence(
        manifest_path,
        evidence_path,
        request_json=_absent_request,
        now=NOW,
        clock=lambda: NOW + timedelta(minutes=1),
        expected_environment=ENV,
    )
    before = evidence_path.read_bytes()
    before_inode = evidence_path.stat().st_ino

    def unexpected_request(path: str) -> tuple[int, dict[str, object]]:
        raise AssertionError(f"terminal recovery must not request {path}")

    assert (
        guard.recover_reserved_evidence(
            manifest_path,
            evidence_path,
            request_json=unexpected_request,
            now=NOW + timedelta(minutes=2),
            expected_environment=ENV,
        )
        == "verified"
    )
    assert evidence_path.read_bytes() == before
    assert evidence_path.stat().st_ino == before_inode


def test_absence_samples_observation_clock_after_all_provider_absence_reads(
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
    observed = NOW + timedelta(minutes=2)
    receipt = guard.verify_vultr_absence(
        manifest_path,
        evidence_path,
        request_json=_absent_request,
        now=NOW,
        clock=lambda: observed,
        expected_environment=ENV,
    )
    assert receipt["observed_at"] == guard._format_time(observed)


def test_absence_default_clock_is_sampled_after_provider_reads(tmp_path: Path) -> None:
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
    provider_reads: list[datetime] = []

    def absent(path: str) -> tuple[int, dict[str, object]]:
        provider_reads.append(datetime.now(timezone.utc))
        return _absent_request(path)

    receipt = guard.verify_vultr_absence(
        manifest_path,
        evidence_path,
        request_json=absent,
        now=NOW,
        expected_environment=ENV,
    )
    observed = guard._receipt_time(receipt["observed_at"], "observed_at")
    assert provider_reads
    assert observed >= provider_reads[-1].replace(microsecond=0)


def test_absence_refuses_manifest_replacement_during_provider_reads(
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
    replaced = False

    def replace_manifest(path: str) -> tuple[int, dict[str, object]]:
        nonlocal replaced
        if path != "/v2/account" and not replaced:
            replacement = _private(
                manifest_path.with_name("replacement-manifest.json"),
                manifest_path.read_bytes(),
            )
            replacement.replace(manifest_path)
            replaced = True
        return _absent_request(path)

    with pytest.raises(guard.GuardError, match="manifest identity changed"):
        guard.verify_vultr_absence(
            manifest_path,
            evidence_path,
            request_json=replace_manifest,
            now=NOW,
            clock=lambda: NOW + timedelta(minutes=1),
            expected_environment=ENV,
        )
    assert (
        guard._json(evidence_path.read_bytes(), "evidence")["status"] == "apply_started"
    )


@pytest.mark.parametrize(
    ("instance_index", "key", "subnet", "prefix"),
    [
        (0, "203.0.113.42/24", "203.0.113.0", 24),
        (1, "2001:db8::42/64", "2001:db8::", 64),
    ],
)
def test_manifest_accepts_a_terraform_valid_ssh_cidr_with_host_bits(
    tmp_path: Path,
    instance_index: int,
    key: str,
    subnet: str,
    prefix: int,
) -> None:
    state = _state()
    ssh = next(
        item
        for item in state["resources"]
        if item["type"] == "vultr_firewall_rule" and item["name"] == "ssh"
    )
    ssh["instances"][instance_index]["index_key"] = key
    ssh["instances"][instance_index]["attributes"]["subnet"] = subnet
    ssh["instances"][instance_index]["attributes"]["subnet_size"] = prefix
    private = tmp_path / "private"
    state_path = _private(private / "state.json", guard.canonical_json(state))
    manifest = guard.create_manifest(
        output_path=private / "manifest.json",
        provider="vultr",
        environment=ENV,
        workspace=ENV,
        state_path=state_path,
        hostname=HOST,
        request_json=_request,
        now=NOW,
    )
    assert (
        f'vultr_firewall_rule.ssh["{key}"]' in manifest["resources"]["firewall_rules"]
    )


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


def test_preapply_same_inode_evidence_byte_change_refuses(tmp_path: Path) -> None:
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
    original_inode = evidence_path.stat().st_ino
    with evidence_path.open("r+b") as stream:
        stream.seek(0)
        stream.write(b"{}\n")
        stream.truncate()
        os.fsync(stream.fileno())
    assert evidence_path.stat().st_ino == original_inode
    try:
        with pytest.raises(guard.GuardError, match="evidence"):
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


def test_evidence_status_preserves_the_reserved_inode(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    reserved_inode = evidence_path.stat().st_ino
    _, fd = _plan_files(manifest_path.parent, _plan())
    guard.validate_destroy_plan(
        manifest_path,
        evidence_path,
        request_json=_request,
        plan_fd=fd,
        now=NOW,
        expected_environment=ENV,
    )
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
    assert evidence_path.stat().st_ino == reserved_inode
    assert not list(evidence_path.parent.glob(".evidence.json.previous-*"))


def test_apply_start_rereads_clock_and_refuses_at_expiry(tmp_path: Path) -> None:
    manifest_path, manifest = _manifest(tmp_path)
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
    expiry = datetime.fromisoformat(manifest["expiry_at"].replace("Z", "+00:00"))
    try:
        with pytest.raises(guard.GuardError, match="expired"):
            guard.mark_apply_started(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=expiry - timedelta(seconds=1),
                clock=lambda: expiry,
                expected_environment=ENV,
            )
    finally:
        os.close(fd)
    assert (
        guard._json(evidence_path.read_bytes(), "evidence")["status"]
        == "plan_validated"
    )


def test_apply_start_persists_the_final_clock_read(tmp_path: Path) -> None:
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
    final = NOW + timedelta(minutes=3)
    try:
        started = guard.mark_apply_started(
            manifest_path,
            evidence_path,
            request_json=_request,
            plan_fd=fd,
            now=NOW,
            clock=lambda: final,
            expected_environment=ENV,
        )
    finally:
        os.close(fd)
    assert started["apply_started_at"] == "2026-09-05T12:03:00Z"


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


@pytest.mark.parametrize(
    "receipt_mutation",
    [
        "missing-started-at",
        "malformed-started-at",
        "expiry-started-at",
        "after-expiry-started-at",
        "missing-plan-binding",
    ],
)
def test_absence_refuses_untyped_or_late_apply_receipt_before_provider_lookup(
    tmp_path: Path, receipt_mutation: str
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
    raw, identity = guard._private_read(
        evidence_path, "evidence", max_bytes=guard.MAX_JSON_BYTES
    )
    started = guard._json(raw, "evidence")
    expiry = datetime.fromisoformat(manifest["expiry_at"].replace("Z", "+00:00"))
    if receipt_mutation == "missing-started-at":
        started.pop("apply_started_at")
    elif receipt_mutation == "malformed-started-at":
        started["apply_started_at"] = "not-a-time"
    elif receipt_mutation == "expiry-started-at":
        started["apply_started_at"] = guard._format_time(expiry)
    elif receipt_mutation == "after-expiry-started-at":
        started["apply_started_at"] = guard._format_time(expiry + timedelta(seconds=1))
    else:
        started.pop("plan_binding")
    guard._rewrite_private_inode(
        evidence_path, identity, guard.canonical_json(started), "evidence"
    )
    calls: list[str] = []

    def unexpected_provider_lookup(path: str) -> tuple[int, dict[str, object]]:
        calls.append(path)
        return 404, {}

    with pytest.raises(guard.GuardError, match="apply start"):
        guard.verify_vultr_absence(
            manifest_path,
            evidence_path,
            request_json=unexpected_provider_lookup,
            now=expiry + timedelta(minutes=1),
            expected_environment=ENV,
        )
    assert calls == []


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
        guard.validate_destroy_plan(
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
        guard.validate_destroy_plan(
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


def test_recovery_discards_unpublished_transition_temp_before_releasing_pair(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    pending = guard._transition_pending_path(guard._transition_path(evidence_path))
    guard._private_write_new(pending, b"partial", "evidence transition")

    assert (
        guard.recover_reserved_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
        == "released"
    )
    assert not pending.exists()
    assert not evidence_path.exists()
    assert not guard._reservation_path(evidence_path).exists()


def test_recovery_releases_orphan_reserved_evidence_before_reservation_publish(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    reservation_path = guard._reservation_path(evidence_path)
    _, reservation_identity = guard._private_read(
        reservation_path, "evidence reservation", max_bytes=guard.MAX_JSON_BYTES
    )
    guard._tombstone_unlink(
        reservation_path, reservation_identity, "evidence reservation"
    )

    assert (
        guard.recover_reserved_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
        == "released"
    )
    assert not evidence_path.exists()


@pytest.mark.parametrize("partial", ["evidence", "reservation"])
def test_recovery_discards_partial_initial_evidence_publication(
    tmp_path: Path, partial: str
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    reservation_path = guard._reservation_path(evidence_path)
    if partial == "evidence":
        reservation_path.unlink()
        evidence_path.write_bytes(evidence_path.read_bytes()[:17])
        evidence_path.chmod(0o600)
    else:
        reservation_path.write_bytes(reservation_path.read_bytes()[:17])
        reservation_path.chmod(0o600)

    assert (
        guard.recover_reserved_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
        == "released"
    )
    assert not evidence_path.exists()
    assert not reservation_path.exists()


def test_release_accepts_plan_validated_evidence_before_apply(tmp_path: Path) -> None:
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
    finally:
        os.close(fd)
    expiry = datetime.fromisoformat(manifest["expiry_at"].replace("Z", "+00:00"))
    guard.release_evidence(
        manifest_path,
        evidence_path,
        now=expiry + timedelta(minutes=1),
        expected_environment=ENV,
    )
    assert not evidence_path.exists()
    assert not guard._reservation_path(evidence_path).exists()
    assert not guard._transition_path(evidence_path).exists()


def test_release_refuses_replaced_reservation_before_journal_without_unlinking_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    reservation_path = guard._reservation_path(evidence_path)
    original_evidence_inode = evidence_path.stat().st_ino
    original_reservation = reservation_path.read_bytes()
    original_write = guard._private_write_new

    def replace_reservation_before_journal(
        path: Path, data: bytes, label: str
    ) -> tuple[int, int]:
        if path == guard._transition_pending_path(
            guard._transition_path(evidence_path)
        ):
            replacement = reservation_path.with_name("foreign-reservation.json")
            _private(replacement, original_reservation)
            replacement.replace(reservation_path)
        return original_write(path, data, label)

    monkeypatch.setattr(guard, "_private_write_new", replace_reservation_before_journal)
    with pytest.raises(guard.GuardError, match="identity changed|manual recovery"):
        guard.release_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
    assert evidence_path.stat().st_ino == original_evidence_inode
    assert reservation_path.read_bytes() == original_reservation
    assert guard._transition_path(evidence_path).exists()


def test_release_refuses_changed_reservation_bytes_before_unlinking_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    reservation_path = guard._reservation_path(evidence_path)
    evidence_inode = evidence_path.stat().st_ino
    _, reservation_identity = guard._private_read(
        reservation_path,
        "evidence reservation",
        max_bytes=guard.MAX_JSON_BYTES,
    )
    original_write = guard._private_write_new

    def change_reservation_before_journal(
        path: Path, data: bytes, label: str
    ) -> tuple[int, int]:
        if path == guard._transition_pending_path(
            guard._transition_path(evidence_path)
        ):
            guard._rewrite_private_inode(
                reservation_path,
                reservation_identity,
                b"{}\n",
                "evidence reservation",
            )
        return original_write(path, data, label)

    monkeypatch.setattr(guard, "_private_write_new", change_reservation_before_journal)
    with pytest.raises(guard.GuardError, match="manual recovery"):
        guard.release_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
    assert evidence_path.stat().st_ino == evidence_inode
    assert reservation_path.stat().st_ino == reservation_identity[1]
    assert reservation_path.read_bytes() == b"{}\n"
    assert guard._transition_path(evidence_path).exists()


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


def test_transition_recovery_finishes_after_evidence_publish_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._rewrite_private_inode
    crashed = False

    def crash_after_publish(*args: object, **kwargs: object) -> None:
        nonlocal crashed
        original(*args, **kwargs)
        if args[0] == evidence_path and not crashed:
            crashed = True
            raise guard.GuardError("simulated post-publish crash")

    reserved_inode = evidence_path.stat().st_ino
    monkeypatch.setattr(guard, "_rewrite_private_inode", crash_after_publish)
    try:
        with pytest.raises(guard.GuardError, match="post-publish"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_rewrite_private_inode", original)
        os.close(fd)
    value, _ = guard._evidence(manifest, manifest_path, evidence_path, "plan_validated")
    assert value["status"] == "plan_validated"
    assert evidence_path.stat().st_ino == reserved_inode
    assert not guard._transition_path(evidence_path).exists()


def test_transition_recovery_completes_prepublication_journal_on_reserved_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._rewrite_private_inode

    def fail_evidence_rewrite(*args: object, **kwargs: object) -> None:
        if args[0] == evidence_path:
            raise guard.GuardError("simulated evidence rewrite failure")
        return original(*args, **kwargs)

    reserved_inode = evidence_path.stat().st_ino
    monkeypatch.setattr(guard, "_rewrite_private_inode", fail_evidence_rewrite)
    try:
        with pytest.raises(guard.GuardError, match="simulated evidence rewrite"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_rewrite_private_inode", original)
        os.close(fd)
    value, _ = guard._evidence(manifest, manifest_path, evidence_path, "plan_validated")
    assert value["status"] == "plan_validated"
    assert evidence_path.stat().st_ino == reserved_inode
    assert not guard._transition_path(evidence_path).exists()


def test_prepublication_recovery_refuses_foreign_evidence_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._rewrite_private_inode

    def swap_before_evidence_rewrite(*args: object, **kwargs: object) -> None:
        if args[0] == evidence_path:
            replacement = evidence_path.with_name("old-evidence-copy.json")
            _private(replacement, evidence_path.read_bytes())
            replacement.replace(evidence_path)
            raise guard.GuardError("simulated evidence rewrite failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(guard, "_rewrite_private_inode", swap_before_evidence_rewrite)
    try:
        with pytest.raises(guard.GuardError, match="simulated evidence rewrite"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_rewrite_private_inode", original)
        os.close(fd)
    with pytest.raises(guard.GuardError, match="manual recovery"):
        guard._evidence(manifest, manifest_path, evidence_path, "reserved")
    assert guard._transition_path(evidence_path).exists()


def test_transition_recovery_repairs_partial_new_evidence_on_reserved_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    _, fd = _plan_files(manifest_path.parent, _plan())
    original = guard._rewrite_private_inode
    reserved_inode = evidence_path.stat().st_ino

    def partial_then_fail(*args: object, **kwargs: object) -> None:
        if args[0] == evidence_path:
            partial = args[2][: len(args[2]) // 2]
            original(args[0], args[1], partial, args[3])
            raise guard.GuardError("simulated partial evidence write")
        return original(*args, **kwargs)

    monkeypatch.setattr(guard, "_rewrite_private_inode", partial_then_fail)
    try:
        with pytest.raises(guard.GuardError, match="simulated partial"):
            guard.validate_destroy_plan(
                manifest_path,
                evidence_path,
                request_json=_request,
                plan_fd=fd,
                now=NOW,
                expected_environment=ENV,
            )
    finally:
        monkeypatch.setattr(guard, "_rewrite_private_inode", original)
        os.close(fd)
    value, identity = guard._evidence(
        manifest, manifest_path, evidence_path, "plan_validated"
    )
    assert value["status"] == "plan_validated"
    assert identity[1] == reserved_inode
    assert not guard._transition_path(evidence_path).exists()


@pytest.mark.parametrize("mutation", ["malformed", "cross-status", "foreign-manifest"])
def test_transition_recovery_refuses_invalid_lifecycle_journal_without_mutation(
    tmp_path: Path, mutation: str
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    evidence_raw, evidence_identity = guard._private_read(
        evidence_path, "evidence", max_bytes=guard.MAX_JSON_BYTES
    )
    reservation_path = guard._reservation_path(evidence_path)
    _, reservation_identity = guard._private_read(
        reservation_path,
        "evidence reservation",
        max_bytes=guard.MAX_JSON_BYTES,
    )
    old = guard._json(evidence_raw, "evidence")
    if mutation == "cross-status":
        new = {
            **old,
            "status": "verified",
            "deadline_status": "within_deadline",
            "apply_started_at": guard._format_time(NOW),
            "observed_at": guard._format_time(NOW + timedelta(minutes=1)),
            "server_id": manifest["resources"]["server_id"],
            "root": manifest["resources"]["root"],
            "absent_addresses": [
                "vultr_firewall_group.vpn",
                'vultr_firewall_rule.icmp["v4"]',
                'vultr_firewall_rule.icmp["v6"]',
                'vultr_firewall_rule.ssh["2001:db8::1/128"]',
                'vultr_firewall_rule.ssh["203.0.113.1/32"]',
                'vultr_firewall_rule.tcp_public["v4-tcp-443"]',
                'vultr_firewall_rule.tcp_public["v6-udp-51820"]',
                "vultr_instance.vpn",
                "vultr_ssh_key.admin",
            ],
            "billing_status": "no-active-owned-resources",
        }
    else:
        new = {
            **old,
            "status": "plan_validated",
            "plan_binding": {
                "identity": [evidence_identity[0], evidence_identity[1]],
                "sha256": "a" * 64,
            },
        }
        if mutation == "malformed":
            new.pop("plan_binding")
        else:
            new["manifest_sha256"] = "f" * 64
    journal_path = guard._transition_path(evidence_path)
    journal = {
        "operation": "transition",
        "evidence_identity": [evidence_identity[0], evidence_identity[1]],
        "reservation_identity": [
            reservation_identity[0],
            reservation_identity[1],
        ],
        "old_evidence": old,
        "new_evidence": new,
    }
    guard._private_write_new(
        journal_path, guard.canonical_json(journal), "evidence transition"
    )
    journal_bytes = journal_path.read_bytes()

    with pytest.raises(guard.GuardError, match="invalid"):
        guard._evidence(manifest, manifest_path, evidence_path, "reserved")
    assert evidence_path.read_bytes() == evidence_raw
    assert evidence_path.stat().st_ino == evidence_identity[1]
    assert journal_path.read_bytes() == journal_bytes


@pytest.mark.parametrize(
    "transition",
    ["plan-binding", "apply-started-at"],
)
def test_transition_recovery_refuses_mismatched_successor_fields_without_mutation(
    tmp_path: Path, transition: str
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
        if transition == "apply-started-at":
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
    evidence_raw, evidence_identity = guard._private_read(
        evidence_path, "evidence", max_bytes=guard.MAX_JSON_BYTES
    )
    old = guard._json(evidence_raw, "evidence")
    if transition == "plan-binding":
        new = {
            **old,
            "status": "apply_started",
            "plan_binding": {
                "identity": [evidence_identity[0], evidence_identity[1] + 1],
                "sha256": old["plan_binding"]["sha256"],
            },
            "apply_started_at": guard._format_time(NOW),
        }
    else:
        new = {
            "schema_version": guard.SCHEMA_VERSION,
            "status": "verified",
            "deadline_status": "within_deadline",
            "provider": "vultr",
            "environment": manifest["environment"],
            "manifest_sha256": old["manifest_sha256"],
            "manifest_identity": old["manifest_identity"],
            "apply_started_at": guard._format_time(NOW + timedelta(minutes=1)),
            "observed_at": guard._format_time(NOW + timedelta(minutes=2)),
            "server_id": manifest["resources"]["server_id"],
            "root": manifest["resources"]["root"],
            "absent_addresses": sorted(
                {
                    "vultr_instance.vpn",
                    "vultr_ssh_key.admin",
                    "vultr_firewall_group.vpn",
                    *manifest["resources"]["firewall_rules"],
                }
            ),
            "billing_status": "no-active-owned-resources",
        }
    reservation_path = guard._reservation_path(evidence_path)
    _, reservation_identity = guard._private_read(
        reservation_path,
        "evidence reservation",
        max_bytes=guard.MAX_JSON_BYTES,
    )
    journal_path = guard._transition_path(evidence_path)
    journal = {
        "operation": "transition",
        "evidence_identity": [evidence_identity[0], evidence_identity[1]],
        "reservation_identity": [
            reservation_identity[0],
            reservation_identity[1],
        ],
        "old_evidence": old,
        "new_evidence": new,
    }
    guard._private_write_new(
        journal_path, guard.canonical_json(journal), "evidence transition"
    )
    journal_bytes = journal_path.read_bytes()

    with pytest.raises(guard.GuardError, match="invalid"):
        guard._evidence(manifest, manifest_path, evidence_path, old["status"])
    assert evidence_path.read_bytes() == evidence_raw
    assert evidence_path.stat().st_ino == evidence_identity[1]
    assert journal_path.read_bytes() == journal_bytes


@pytest.mark.parametrize("status", ["reserved", "plan_validated"])
def test_evidence_refuses_nonexact_preapply_status_schema(
    tmp_path: Path, status: str
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    raw, identity = guard._private_read(
        evidence_path, "evidence", max_bytes=guard.MAX_JSON_BYTES
    )
    value = guard._json(raw, "evidence")
    if status == "reserved":
        value["unexpected"] = True
    else:
        value["status"] = "plan_validated"
    guard._rewrite_private_inode(
        evidence_path, identity, guard.canonical_json(value), "evidence"
    )

    with pytest.raises(guard.GuardError, match="evidence reservation is invalid"):
        guard._evidence(manifest, manifest_path, evidence_path, status)


def test_terraform_show_uses_routed_provider_workspace_same_fd_and_redacts_failures(
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
        assert REAL_TERRAFORM_SHOW(fd, ENV) == b"{}"
        assert seen["argv"] == [
            str(ROOT / "scripts/terraform-env.sh"),
            "show",
            "-json",
            f"/dev/fd/{fd}",
        ]
        assert seen["env"]["PROVIDER"] == "vultr"
        assert seen["env"]["ENV"] == ENV
        assert seen["pass_fds"] == (fd,)
        assert seen["timeout"] == 30
        monkeypatch.setattr(
            guard.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b"secret"),
        )
        with pytest.raises(guard.GuardError, match="JSON view is unavailable"):
            REAL_TERRAFORM_SHOW(fd, ENV)
        monkeypatch.setattr(
            guard.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout=b"x" * (guard.MAX_JSON_BYTES + 1)
            ),
        )
        with pytest.raises(guard.GuardError, match="JSON view is unavailable"):
            REAL_TERRAFORM_SHOW(fd, ENV)
        monkeypatch.setattr(
            guard.subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("secret")),
        )
        with pytest.raises(guard.GuardError, match="JSON view is unavailable"):
            REAL_TERRAFORM_SHOW(fd, ENV)
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
    monkeypatch.setattr(
        guard, "_terraform_show_json", lambda _fd, _environment: b"not-json"
    )
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


def test_direct_release_refuses_byte_identical_state_inode_replacement(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    reservation_path = guard._reservation_path(evidence_path)
    evidence_before = evidence_path.read_bytes()
    reservation_before = reservation_path.read_bytes()
    state_path = Path(manifest["state"]["path"])
    replacement = _private(
        state_path.with_name("replacement-before-release.tfstate"),
        state_path.read_bytes(),
    )
    replacement.replace(state_path)

    with pytest.raises(guard.GuardError, match="state identity changed"):
        guard.release_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )

    assert evidence_path.read_bytes() == evidence_before
    assert reservation_path.read_bytes() == reservation_before
    assert not guard._transition_path(evidence_path).exists()


def test_release_journal_recovery_refuses_replaced_state_without_unlinking_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, manifest = _manifest(tmp_path)
    evidence_path = manifest_path.with_name("evidence.json")
    guard.reserve_evidence(
        manifest_path, evidence_path, now=NOW, expected_environment=ENV
    )
    reservation_path = guard._reservation_path(evidence_path)
    original = guard._tombstone_unlink

    def interrupt_before_unlink(*args: object, **kwargs: object) -> None:
        raise guard.GuardError("simulated release interruption")

    monkeypatch.setattr(guard, "_tombstone_unlink", interrupt_before_unlink)
    with pytest.raises(guard.GuardError, match="simulated release interruption"):
        guard.release_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )
    monkeypatch.setattr(guard, "_tombstone_unlink", original)

    journal_path = guard._transition_path(evidence_path)
    evidence_before = evidence_path.read_bytes()
    reservation_before = reservation_path.read_bytes()
    journal_before = journal_path.read_bytes()
    state_path = Path(manifest["state"]["path"])
    replacement = _private(
        state_path.with_name("replacement-before-recovery.tfstate"),
        state_path.read_bytes(),
    )
    replacement.replace(state_path)

    with pytest.raises(guard.GuardError, match="state identity changed"):
        guard.recover_reserved_evidence(
            manifest_path, evidence_path, now=NOW, expected_environment=ENV
        )

    assert evidence_path.read_bytes() == evidence_before
    assert reservation_path.read_bytes() == reservation_before
    assert journal_path.read_bytes() == journal_before


def test_platform_without_nofollow_refuses_private_manifest_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _private(tmp_path / "private" / "manifest.json", b"{}\n")
    monkeypatch.delattr(guard.os, "O_NOFOLLOW", raising=False)
    with pytest.raises(guard.GuardError, match="no-follow"):
        guard._private_read(path, "manifest", max_bytes=1024)
