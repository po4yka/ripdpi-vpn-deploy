#!/usr/bin/env python3
"""Fail-closed, exact-resource cleanup contract for a Vultr staging server.

This is deliberately a controller library.  A later operator entrypoint must
call ``reserve_evidence`` -> ``validate_destroy_plan`` ->
``mark_apply_started`` around Terraform, then ``verify_vultr_absence``.
The adapter does not create or delete provider resources itself.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_STATE_BYTES = 64 * 1024 * 1024
TARGET_AFTER = timedelta(hours=36)
ESCALATION_AFTER = timedelta(hours=44)
EXPIRY_AFTER = timedelta(hours=47)
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ENV_RE = re.compile(r"^ci-staging-[A-Za-z0-9][A-Za-z0-9-]{0,47}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,62}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DECIMAL_ID_RE = re.compile(r"^[1-9][0-9]*$")
ALLOWED_BASE_ADDRESSES = {
    "terraform_data.ssh_port",
    "vultr_ssh_key.admin",
    "vultr_firewall_group.vpn",
    "vultr_instance.vpn",
}


class GuardError(ValueError):
    """A categorical failure which is safe to show an operator."""


JsonRequest = Callable[[str], tuple[int, dict[str, Any]]]


class PlanBinding:
    """Identity and digest of the one private plan descriptor to apply."""

    __slots__ = ("identity", "sha256")

    def __init__(self, identity: tuple[int, int], sha256: str) -> None:
        self.identity = identity
        self.sha256 = sha256


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _format_time(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _time(value: datetime | str, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise GuardError(f"{label} is not canonical UTC time") from exc
    else:
        raise GuardError(f"{label} is not canonical UTC time")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise GuardError(f"{label} is not UTC")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _uuid(value: Any, label: str) -> str:
    if not isinstance(value, str) or not UUID_RE.fullmatch(value):
        raise GuardError(f"{label} is not a UUID")
    return value


def _decimal_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not DECIMAL_ID_RE.fullmatch(value):
        raise GuardError(f"{label} is not a positive decimal ID")
    return value


def _json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise GuardError(f"{label} must be a JSON object")
    return value


def _private_parent(path: Path, label: str, *, exact: bool = True) -> tuple[int, str]:
    path = path.absolute()
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise GuardError(f"{label} path is invalid")
    if not hasattr(os, "O_NOFOLLOW"):
        raise GuardError(f"{label} platform lacks no-follow traversal")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    try:
        fd = os.open(path.anchor, flags)
        for part in path.parent.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
    except OSError as exc:
        try:
            os.close(fd)
        except UnboundLocalError:
            # Opening the filesystem anchor itself failed, so no descriptor
            # exists to close on this expected cleanup path.
            pass
        raise GuardError(f"{label} parent is unavailable or unsafe") from exc
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or (mode != 0o700 if exact else bool(mode & 0o022))
    ):
        os.close(fd)
        raise GuardError(f"{label} parent ownership or mode is unsafe")
    return fd, path.name


def _private_read(
    path: Path, label: str, *, max_bytes: int, exact_parent: bool = True
) -> tuple[bytes, tuple[int, int]]:
    parent, name = _private_parent(path, label, exact=exact_parent)
    try:
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            fd = os.open(
                name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent
            )
        except OSError as exc:
            raise GuardError(f"{label} is unavailable") from exc
        try:
            opened = os.fstat(fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise GuardError(f"{label} changed while opening")
            if opened.st_size > max_bytes:
                raise GuardError(f"{label} exceeds size limit")
            data = os.read(fd, max_bytes + 1)
            if len(data) > max_bytes:
                raise GuardError(f"{label} exceeds size limit")
            return data, (opened.st_dev, opened.st_ino)
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _private_write_new(path: Path, data: bytes, label: str) -> tuple[int, int]:
    parent, name = _private_parent(path, label)
    try:
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent,
            )
        except OSError as exc:
            raise GuardError(f"{label} could not be created privately") from exc
        identity = os.fstat(fd)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise GuardError(f"{label} write failed")
                view = view[count:]
            os.fsync(fd)
            info = os.fstat(fd)
        except BaseException:
            os.close(fd)
            fd = -1
            _tombstone_unlink(path, (identity.st_dev, identity.st_ino), label)
            raise
        finally:
            if fd >= 0:
                os.close(fd)
        os.fsync(parent)
        return info.st_dev, info.st_ino
    finally:
        os.close(parent)


def _rewrite_private_inode(
    path: Path, expected_identity: tuple[int, int], data: bytes, label: str
) -> None:
    """Durably rewrite one reserved private inode without changing its identity."""

    parent, name = _private_parent(path, label)
    try:
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            fd = os.open(
                name,
                os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent,
            )
        except OSError as exc:
            raise GuardError(f"{label} is unavailable") from exc
        try:
            opened = os.fstat(fd)
            identity = (opened.st_dev, opened.st_ino)
            if (
                identity != expected_identity
                or identity != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
            ):
                raise GuardError(f"{label} identity changed")
            os.ftruncate(fd, 0)
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise GuardError(f"{label} write failed")
                view = view[count:]
            os.fsync(fd)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != expected_identity:
                raise GuardError(f"{label} identity changed")
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def _transition_evidence(
    evidence_path: Path,
    evidence_identity: tuple[int, int],
    old: dict[str, Any],
    new: dict[str, Any],
) -> tuple[int, int]:
    current_raw, current_identity = _private_read(
        evidence_path, "evidence", max_bytes=MAX_JSON_BYTES
    )
    if current_identity != evidence_identity or current_raw != canonical_json(old):
        raise GuardError("evidence identity or bytes changed")
    reservation_path = _reservation_path(evidence_path)
    raw, reservation_identity = _private_read(
        reservation_path, "evidence reservation", max_bytes=MAX_JSON_BYTES
    )
    reservation = _json(raw, "evidence reservation")
    if reservation != {
        "evidence_identity": [evidence_identity[0], evidence_identity[1]]
    }:
        raise GuardError("evidence reservation changed")
    journal_path = _transition_path(evidence_path)
    journal = {
        "operation": "transition",
        "evidence_identity": [evidence_identity[0], evidence_identity[1]],
        "reservation_identity": [reservation_identity[0], reservation_identity[1]],
        "old_evidence": old,
        "new_evidence": new,
    }
    _private_write_new(journal_path, canonical_json(journal), "evidence transition")
    _rewrite_private_inode(
        evidence_path, evidence_identity, canonical_json(new), "evidence"
    )
    published_raw, published_identity = _private_read(
        evidence_path, "evidence", max_bytes=MAX_JSON_BYTES
    )
    if published_identity != evidence_identity or published_raw != canonical_json(new):
        raise GuardError("evidence publication could not be verified")
    journal_raw, journal_identity = _private_read(
        journal_path, "evidence transition", max_bytes=MAX_JSON_BYTES
    )
    if journal_raw != canonical_json(journal):
        raise GuardError("evidence transition changed")
    _tombstone_unlink(journal_path, journal_identity, "evidence transition")
    return evidence_identity


def _reservation_path(evidence_path: Path) -> Path:
    return evidence_path.with_name(f".{evidence_path.name}.reservation")


def _transition_path(evidence_path: Path) -> Path:
    return evidence_path.with_name(f".{evidence_path.name}.transition")


def _path_present(path: Path, label: str) -> bool:
    parent, name = _private_parent(path, label)
    try:
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True
    finally:
        os.close(parent)


def _valid_identity(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and not isinstance(value[0], bool)
        and isinstance(value[0], int)
        and value[0] >= 0
        and not isinstance(value[1], bool)
        and isinstance(value[1], int)
        and value[1] > 0
    )


def _valid_plan_binding(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"identity", "sha256"}
        and _valid_identity(value.get("identity"))
        and isinstance(value.get("sha256"), str)
        and SHA256_RE.fullmatch(value["sha256"]) is not None
    )


def _receipt_time(value: Any, label: str) -> datetime:
    try:
        parsed = _time(value, label)
    except GuardError as exc:
        raise GuardError("evidence lifecycle receipt is invalid") from exc
    if not isinstance(value, str) or _format_time(parsed) != value:
        raise GuardError("evidence lifecycle receipt is invalid")
    return parsed


def _validate_lifecycle_receipt(
    receipt: dict[str, Any],
    manifest: dict[str, Any],
    manifest_identity: tuple[int, int],
) -> str:
    common = {
        "schema_version": SCHEMA_VERSION,
        "provider": "vultr",
        "environment": manifest["environment"],
        "manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
        "manifest_identity": [manifest_identity[0], manifest_identity[1]],
    }
    if any(receipt.get(key) != value for key, value in common.items()):
        raise GuardError("evidence lifecycle receipt is invalid")
    status = receipt.get("status")
    base_keys = set(common) | {"status"}
    if status == "reserved":
        if set(receipt) != base_keys:
            raise GuardError("evidence lifecycle receipt is invalid")
        return status
    if status == "plan_validated":
        if set(receipt) != base_keys | {"plan_binding"} or not _valid_plan_binding(
            receipt.get("plan_binding")
        ):
            raise GuardError("evidence lifecycle receipt is invalid")
        return status
    expiry = _time(manifest["expiry_at"], "manifest expiry_at")
    if status == "apply_started":
        if set(receipt) != base_keys | {"plan_binding", "apply_started_at"} or not (
            _valid_plan_binding(receipt.get("plan_binding"))
        ):
            raise GuardError("evidence lifecycle receipt is invalid")
        if _receipt_time(receipt.get("apply_started_at"), "apply_started_at") >= expiry:
            raise GuardError("evidence lifecycle receipt is invalid")
        return status
    if status in {"verified", "verified_after_expiry"}:
        verified_keys = base_keys | {
            "deadline_status",
            "apply_started_at",
            "observed_at",
            "server_id",
            "root",
            "absent_addresses",
            "billing_status",
        }
        started = _receipt_time(receipt.get("apply_started_at"), "apply_started_at")
        observed = _receipt_time(receipt.get("observed_at"), "observed_at")
        expected_addresses = sorted(
            {
                "vultr_instance.vpn",
                "vultr_ssh_key.admin",
                "vultr_firewall_group.vpn",
                *manifest["resources"]["firewall_rules"],
            }
        )
        expected_deadline = (
            "within_deadline" if status == "verified" else "expired_after_apply"
        )
        if (
            set(receipt) != verified_keys
            or started >= expiry
            or observed < started
            or (status == "verified" and observed >= expiry)
            or (status == "verified_after_expiry" and observed < expiry)
            or receipt.get("deadline_status") != expected_deadline
            or receipt.get("server_id") != manifest["resources"]["server_id"]
            or receipt.get("root") != manifest["resources"]["root"]
            or receipt.get("absent_addresses") != expected_addresses
            or receipt.get("billing_status") != "no-active-owned-resources"
        ):
            raise GuardError("evidence lifecycle receipt is invalid")
        return status
    raise GuardError("evidence lifecycle receipt is invalid")


def _valid_lifecycle_successor(
    old_status: str,
    new_status: str,
    old_receipt: dict[str, Any],
    new_receipt: dict[str, Any],
) -> bool:
    """Require immutable transaction fields across durable receipt successors."""

    if (old_status, new_status) not in {
        ("reserved", "plan_validated"),
        ("plan_validated", "apply_started"),
        ("apply_started", "verified"),
        ("apply_started", "verified_after_expiry"),
    }:
        return False
    if old_status == "plan_validated":
        return old_receipt["plan_binding"] == new_receipt["plan_binding"]
    if old_status == "apply_started":
        return old_receipt["apply_started_at"] == new_receipt["apply_started_at"]
    return True


def _recover_pair_transition(
    manifest: dict[str, Any],
    manifest_identity: tuple[int, int],
    evidence_path: Path,
) -> None:
    """Finish a journaled evidence/reservation inode transition idempotently."""

    journal_path = _transition_path(evidence_path)
    if not _path_present(journal_path, "evidence transition"):
        return
    raw, journal_identity = _private_read(
        journal_path, "evidence transition", max_bytes=MAX_JSON_BYTES
    )
    journal = _json(raw, "evidence transition")
    if journal.get("operation") == "release":
        _recover_release_transition(
            journal_path,
            journal,
            journal_identity,
            evidence_path,
            manifest,
            manifest_identity,
        )
        return
    if (
        set(journal)
        != {
            "operation",
            "evidence_identity",
            "reservation_identity",
            "old_evidence",
            "new_evidence",
        }
        or journal.get("operation") != "transition"
        or not all(
            isinstance(journal.get(key), list)
            and len(journal[key]) == 2
            and all(isinstance(value, int) for value in journal[key])
            for key in ("evidence_identity", "reservation_identity")
        )
        or not isinstance(journal.get("old_evidence"), dict)
        or not isinstance(journal.get("new_evidence"), dict)
    ):
        raise GuardError("evidence transition is invalid")
    try:
        old_status = _validate_lifecycle_receipt(
            journal["old_evidence"], manifest, manifest_identity
        )
        new_status = _validate_lifecycle_receipt(
            journal["new_evidence"], manifest, manifest_identity
        )
    except GuardError as exc:
        raise GuardError("evidence transition is invalid") from exc
    if not _valid_lifecycle_successor(
        old_status,
        new_status,
        journal["old_evidence"],
        journal["new_evidence"],
    ):
        raise GuardError("evidence transition is invalid")
    evidence_raw, evidence_identity = _private_read(
        evidence_path, "evidence", max_bytes=MAX_JSON_BYTES
    )
    reservation_path = _reservation_path(evidence_path)
    reservation_raw, reservation_identity = _private_read(
        reservation_path, "evidence reservation", max_bytes=MAX_JSON_BYTES
    )
    reservation = _json(reservation_raw, "evidence reservation")
    expected_evidence_identity = tuple(journal["evidence_identity"])
    expected_reservation_identity = tuple(journal["reservation_identity"])
    if (
        tuple(evidence_identity) != expected_evidence_identity
        or reservation_identity != expected_reservation_identity
        or reservation != {"evidence_identity": list(expected_evidence_identity)}
    ):
        raise GuardError("evidence transition requires manual recovery")
    old_raw = canonical_json(journal["old_evidence"])
    new_raw = canonical_json(journal["new_evidence"])
    if (
        evidence_raw != old_raw
        and evidence_raw != new_raw
        and not new_raw.startswith(evidence_raw)
    ):
        raise GuardError("evidence transition requires manual recovery")
    if evidence_raw != new_raw:
        _rewrite_private_inode(
            evidence_path,
            expected_evidence_identity,
            new_raw,
            "evidence",
        )
    recovered_raw, recovered_identity = _private_read(
        evidence_path, "evidence", max_bytes=MAX_JSON_BYTES
    )
    if recovered_identity != expected_evidence_identity or recovered_raw != new_raw:
        raise GuardError("evidence transition requires manual recovery")
    _tombstone_unlink(journal_path, journal_identity, "evidence transition")


def _recover_release_transition(
    journal_path: Path,
    journal: dict[str, Any],
    journal_identity: tuple[int, int],
    evidence_path: Path,
    manifest: dict[str, Any],
    manifest_identity: tuple[int, int],
) -> None:
    if (
        set(journal)
        != {
            "operation",
            "evidence_identity",
            "reservation_identity",
            "evidence",
        }
        or not all(
            isinstance(journal.get(key), list)
            and len(journal[key]) == 2
            and all(isinstance(value, int) for value in journal[key])
            for key in ("evidence_identity", "reservation_identity")
        )
        or not isinstance(journal.get("evidence"), dict)
    ):
        raise GuardError("evidence release transition is invalid")
    try:
        evidence_status = _validate_lifecycle_receipt(
            journal["evidence"], manifest, manifest_identity
        )
    except GuardError as exc:
        raise GuardError("evidence release transition is invalid") from exc
    if evidence_status not in {"reserved", "plan_validated"}:
        raise GuardError("evidence release transition is invalid")
    evidence_identity = tuple(journal["evidence_identity"])
    reservation_identity = tuple(journal["reservation_identity"])
    evidence_present = _path_present(evidence_path, "evidence")
    reservation_path = _reservation_path(evidence_path)
    reservation_present = _path_present(reservation_path, "evidence reservation")
    if evidence_present:
        evidence_raw, actual_evidence_identity = _private_read(
            evidence_path, "evidence", max_bytes=MAX_JSON_BYTES
        )
        if (
            actual_evidence_identity != evidence_identity
            or evidence_raw != canonical_json(journal["evidence"])
        ):
            raise GuardError("evidence release transition requires manual recovery")
    if reservation_present:
        reservation_raw, actual_reservation_identity = _private_read(
            reservation_path, "evidence reservation", max_bytes=MAX_JSON_BYTES
        )
        expected_reservation = canonical_json(
            {"evidence_identity": list(evidence_identity)}
        )
        if (
            actual_reservation_identity != reservation_identity
            or reservation_raw != expected_reservation
        ):
            raise GuardError("evidence release transition requires manual recovery")
    if evidence_present and not reservation_present:
        raise GuardError("evidence release transition requires manual recovery")
    if evidence_present:
        _tombstone_unlink(evidence_path, evidence_identity, "evidence")
    if reservation_present:
        _tombstone_unlink(
            reservation_path, reservation_identity, "evidence reservation"
        )
    _tombstone_unlink(journal_path, journal_identity, "evidence transition")


def _account_binding(request_json: JsonRequest) -> str:
    status, payload = request_json("/v2/account")
    account = payload.get("account")
    email = account.get("email") if isinstance(account, dict) else None
    if status != 200 or not isinstance(email, str) or not email or len(email) > 320:
        raise GuardError("provider account identity could not be verified")
    return hashlib.sha256(("vultr-account-v1:" + email).encode()).hexdigest()


def authenticated_preflight(
    request_json: JsonRequest, environment: Mapping[str, str] = os.environ
) -> str:
    """Require environment-only credentials and return a redacted account binding."""

    _vultr_request_from_environment(environment)
    return _account_binding(request_json)


def preflight_manifest_account(
    manifest_path: Path,
    *,
    request_json: JsonRequest,
    environment: Mapping[str, str],
    now: datetime | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    """Authenticate and bind the manifest account before Terraform is invoked."""

    observed = authenticated_preflight(request_json, environment)
    manifest = load_manifest(
        manifest_path, now=now, expected_environment=expected_environment
    )
    if observed != manifest["provider_account_binding"]:
        raise GuardError("provider account identity changed")
    return manifest


def _provider_created(
    request_json: JsonRequest, *, server_id: str, hostname: str, now: datetime
) -> datetime:
    status, payload = request_json(f"/v2/instances/{server_id}")
    instance = payload.get("instance")
    created = instance.get("date_created") if isinstance(instance, dict) else None
    if (
        status != 200
        or not isinstance(instance, dict)
        or instance.get("id") != server_id
        or instance.get("hostname") != hostname
        or not isinstance(created, str)
    ):
        raise GuardError("provider instance identity or creation time is invalid")
    normalized = created.replace("+00:00", "Z")
    try:
        result = _time(normalized, "provider instance creation time")
    except GuardError as exc:
        raise GuardError(
            "provider instance identity or creation time is invalid"
        ) from exc
    if result > now + timedelta(minutes=5):
        raise GuardError("provider instance identity or creation time is invalid")
    return result


def _state_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if state.get("version") != 4 or not isinstance(state.get("resources"), list):
        raise GuardError("state schema is invalid")
    indexed: dict[str, dict[str, Any]] = {}
    for resource in state["resources"]:
        if (
            not isinstance(resource, dict)
            or resource.get("mode") != "managed"
            or "module" in resource
        ):
            raise GuardError("state resource is invalid")
        kind, name, instances = (
            resource.get("type"),
            resource.get("name"),
            resource.get("instances"),
        )
        if (
            not isinstance(kind, str)
            or not isinstance(name, str)
            or not isinstance(instances, list)
            or not instances
        ):
            raise GuardError("state resource is ambiguous")
        is_firewall_rule = kind == "vultr_firewall_rule"
        if not is_firewall_rule and len(instances) != 1:
            raise GuardError("state resource is ambiguous")
        for instance in instances:
            attributes = (
                instance.get("attributes") if isinstance(instance, dict) else None
            )
            if not isinstance(attributes, dict):
                raise GuardError("state resource is invalid")
            if is_firewall_rule:
                key = instance.get("index_key")
                if not isinstance(key, str) or not key:
                    raise GuardError("firewall rule state lacks an exact for_each key")
                address = f"{kind}.{name}[{json.dumps(key, separators=(',', ':'))}]"
            else:
                if "index_key" in instance:
                    raise GuardError("state resource has an unexpected index")
                address = f"{kind}.{name}"
            if address in indexed:
                raise GuardError("state resource is invalid")
            indexed[address] = attributes
    return indexed


def _extract_identity(state: dict[str, Any], hostname: str) -> dict[str, Any]:
    indexed = _state_index(state)
    forbidden_prefixes = (
        "vultr_instance_ipv4.",
        "vultr_dns_record.",
        "vultr_reserved_ip.",
        "vultr_backup.",
    )
    if any(address.startswith(forbidden_prefixes) for address in indexed):
        raise GuardError("state includes additional IP, DNS, or backup resources")
    firewall_addresses = sorted(
        address for address in indexed if address.startswith("vultr_firewall_rule.")
    )
    allowed = ALLOWED_BASE_ADDRESSES | set(firewall_addresses)
    if not firewall_addresses or set(indexed) != allowed:
        raise GuardError("state contains a foreign or missing cleanup resource")
    instance = indexed["vultr_instance.vpn"]
    server_id = _uuid(instance.get("id"), "server ID")
    if instance.get("hostname") != hostname or instance.get("label") not in (
        None,
        hostname,
    ):
        raise GuardError("state hostname does not match expected hostname")
    if instance.get("backups") not in (None, "disabled", False):
        raise GuardError("state enables backups outside cleanup scope")
    if instance.get("firewall_group_id") != indexed["vultr_firewall_group.vpn"].get(
        "id"
    ):
        raise GuardError("state firewall group does not match instance")
    ssh_id = _uuid(indexed["vultr_ssh_key.admin"].get("id"), "SSH key ID")
    firewall_group_id = _uuid(
        indexed["vultr_firewall_group.vpn"].get("id"), "firewall group ID"
    )
    ssh_ids = instance.get("ssh_key_ids")
    if not isinstance(ssh_ids, list) or ssh_ids != [ssh_id]:
        raise GuardError("state SSH key binding is not exact")
    ssh_port = indexed["terraform_data.ssh_port"].get("input")
    if (
        isinstance(ssh_port, bool)
        or not isinstance(ssh_port, int)
        or not 1 <= ssh_port <= 65535
    ):
        raise GuardError("state SSH port binding is invalid")
    rules: dict[str, str] = {}
    icmp_keys: set[str] = set()
    for address in firewall_addresses:
        rule = indexed[address]
        match = re.fullmatch(
            r'vultr_firewall_rule\.(icmp|ssh|tcp_public)\["([^"\\]+)"\]', address
        )
        if not match:
            raise GuardError("state firewall rule name or key is outside cleanup scope")
        name, key = match.groups()
        if name == "icmp":
            subnet = "0.0.0.0" if key == "v4" else "::"
            if (
                key not in {"v4", "v6"}
                or rule.get("protocol") != "icmp"
                or rule.get("ip_type") != key
                or rule.get("subnet") != subnet
                or rule.get("subnet_size") != 0
            ):
                raise GuardError("state ICMP firewall rule is not exact")
            icmp_keys.add(key)
        elif name == "ssh":
            try:
                source = ipaddress.ip_network(key, strict=True)
            except ValueError as exc:
                raise GuardError("state SSH firewall rule source is invalid") from exc
            ip_type = "v4" if source.version == 4 else "v6"
            if (
                source.prefixlen not in {32, 128}
                or rule.get("protocol") != "tcp"
                or rule.get("ip_type") != ip_type
                or str(rule.get("port")) != str(ssh_port)
                or rule.get("subnet") != str(source.network_address)
                or rule.get("subnet_size") != source.prefixlen
            ):
                raise GuardError("state SSH firewall rule is not exact")
        else:
            listener = re.fullmatch(r"(v[46])-(tcp|udp)-(\d{1,5})(?:-(\d{1,5}))?", key)
            if not listener:
                raise GuardError("state public listener key is not exact")
            ip_type, protocol, first, last = listener.groups()
            start = int(first)
            end = int(last or first)
            subnet = "0.0.0.0" if ip_type == "v4" else "::"
            if (
                not 1 <= start <= end <= 65535
                or rule.get("protocol") != protocol
                or rule.get("ip_type") != ip_type
                or str(rule.get("port"))
                != (first if last is None else f"{first}-{last}")
                or rule.get("subnet") != subnet
                or rule.get("subnet_size") != 0
            ):
                raise GuardError("state public listener rule is not exact")
        rule_id = _decimal_id(rule.get("id"), "firewall rule ID")
        if rule.get("firewall_group_id") != firewall_group_id:
            raise GuardError("state firewall rule belongs to a foreign group")
        rules[address] = rule_id
    if icmp_keys != {"v4", "v6"}:
        raise GuardError("state must bind exact ICMP v4 and v6 rules")
    terraform_data_id = indexed["terraform_data.ssh_port"].get("id")
    if not isinstance(terraform_data_id, str) or not terraform_data_id:
        raise GuardError("state Terraform data binding is invalid")
    return {
        "terraform_data_ssh_port_id": terraform_data_id,
        "ssh_port": ssh_port,
        "server_id": server_id,
        "root": {
            "kind": "instance-root",
            "server_id": server_id,
            "separate_storage_id": None,
        },
        "ssh_key_id": ssh_id,
        "firewall_group_id": firewall_group_id,
        "firewall_rules": rules,
    }


def create_manifest(
    *,
    output_path: Path,
    provider: str,
    environment: str,
    workspace: str,
    state_path: Path,
    hostname: str,
    request_json: JsonRequest,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _time(now or datetime.now(timezone.utc), "current time")
    if (
        provider != "vultr"
        or not ENV_RE.fullmatch(environment)
        or workspace != environment
        or not NAME_RE.fullmatch(hostname)
    ):
        raise GuardError("provider, environment, workspace, or hostname is invalid")
    state_path = state_path.absolute()
    state_bytes, _ = _private_read(
        state_path, "state", max_bytes=MAX_STATE_BYTES, exact_parent=False
    )
    identity = _extract_identity(_json(state_bytes, "state"), hostname)
    binding = _account_binding(request_json)
    created = _provider_created(
        request_json,
        server_id=identity["server_id"],
        hostname=hostname,
        now=current,
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "provider": "vultr",
        "environment": environment,
        "workspace": workspace,
        "hostname": hostname,
        "provider_account_binding": binding,
        "state": {
            "path": str(state_path),
            "sha256": hashlib.sha256(state_bytes).hexdigest(),
        },
        "resources": identity,
        "created_at": _format_time(created),
        "target_at": _format_time(created + TARGET_AFTER),
        "escalation_at": _format_time(created + ESCALATION_AFTER),
        "expiry_at": _format_time(created + EXPIRY_AFTER),
    }
    _private_write_new(output_path.absolute(), canonical_json(manifest), "manifest")
    return manifest


def load_manifest(
    path: Path,
    *,
    now: datetime | None = None,
    expected_provider: str = "vultr",
    expected_environment: str | None = None,
    verify_state: bool = True,
    allow_expired: bool = False,
) -> dict[str, Any]:
    current = _time(now or datetime.now(timezone.utc), "current time")
    raw, _ = _private_read(path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES)
    manifest = _json(raw, "manifest")
    if (
        raw != canonical_json(manifest)
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("provider") != expected_provider
    ):
        raise GuardError("manifest schema or provider is invalid")
    if (
        not isinstance(manifest.get("environment"), str)
        or not ENV_RE.fullmatch(manifest["environment"])
        or manifest.get("workspace") != manifest["environment"]
        or (expected_environment and manifest["environment"] != expected_environment)
    ):
        raise GuardError("manifest environment is invalid")
    if not isinstance(
        manifest.get("provider_account_binding"), str
    ) or not SHA256_RE.fullmatch(manifest["provider_account_binding"]):
        raise GuardError("manifest account binding is invalid")
    created, target, escalation, expiry = (
        _time(manifest.get(key), f"manifest {key}")
        for key in ("created_at", "target_at", "escalation_at", "expiry_at")
    )
    if (
        target != created + TARGET_AFTER
        or escalation != created + ESCALATION_AFTER
        or expiry != created + EXPIRY_AFTER
        or (not allow_expired and current >= expiry)
    ):
        raise GuardError("manifest cleanup schedule is invalid or expired")
    state_info = manifest.get("state")
    if (
        not isinstance(state_info, dict)
        or set(state_info) != {"path", "sha256"}
        or not isinstance(state_info.get("path"), str)
        or not SHA256_RE.fullmatch(state_info.get("sha256", ""))
    ):
        raise GuardError("manifest state binding is invalid")
    resources = manifest.get("resources")
    if not isinstance(resources, dict):
        raise GuardError("manifest resource binding is invalid")
    if verify_state:
        state_bytes, _ = _private_read(
            Path(state_info["path"]),
            "state",
            max_bytes=MAX_STATE_BYTES,
            exact_parent=False,
        )
        if (
            hashlib.sha256(state_bytes).hexdigest() != state_info["sha256"]
            or _extract_identity(_json(state_bytes, "state"), manifest.get("hostname"))
            != resources
        ):
            raise GuardError("state digest does not match manifest")
    else:
        _validate_manifest_resources(resources)
    return manifest


def _validate_manifest_resources(resources: dict[str, Any]) -> None:
    required = {
        "terraform_data_ssh_port_id",
        "ssh_port",
        "server_id",
        "root",
        "ssh_key_id",
        "firewall_group_id",
        "firewall_rules",
    }
    if set(resources) != required:
        raise GuardError("manifest resource binding is invalid")
    server_id = _uuid(resources.get("server_id"), "server ID")
    if resources.get("root") != {
        "kind": "instance-root",
        "server_id": server_id,
        "separate_storage_id": None,
    }:
        raise GuardError("manifest root binding is invalid")
    _uuid(resources.get("ssh_key_id"), "SSH key ID")
    _uuid(resources.get("firewall_group_id"), "firewall group ID")
    if not isinstance(resources.get("terraform_data_ssh_port_id"), str):
        raise GuardError("manifest Terraform data binding is invalid")
    ssh_port = resources.get("ssh_port")
    if (
        isinstance(ssh_port, bool)
        or not isinstance(ssh_port, int)
        or not 1 <= ssh_port <= 65535
    ):
        raise GuardError("manifest SSH port binding is invalid")
    rules = resources.get("firewall_rules")
    if not isinstance(rules, dict) or not rules:
        raise GuardError("manifest firewall rule binding is invalid")
    for address, rule_id in rules.items():
        if not isinstance(address, str) or not address.startswith(
            "vultr_firewall_rule."
        ):
            raise GuardError("manifest firewall rule binding is invalid")
        _decimal_id(rule_id, "firewall rule ID")


def reserve_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    now: datetime | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(
        manifest_path, now=now, expected_environment=expected_environment
    )
    _, identity = _private_read(
        manifest_path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES
    )
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "reserved",
        "provider": "vultr",
        "environment": manifest["environment"],
        "manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
        "manifest_identity": [identity[0], identity[1]],
    }
    evidence_identity = _private_write_new(
        evidence_path.absolute(), canonical_json(evidence), "evidence"
    )
    try:
        _private_write_new(
            _reservation_path(evidence_path).absolute(),
            canonical_json(
                {"evidence_identity": [evidence_identity[0], evidence_identity[1]]}
            ),
            "evidence reservation",
        )
    except BaseException:
        # The reservation file is the durable ownership proof.  If it cannot
        # be published, remove only the inode this call created; do not leave
        # an unrecoverable evidence file that would turn the next reservation
        # into a permanent EEXIST refusal.
        _tombstone_unlink(evidence_path, evidence_identity, "evidence")
        raise
    return evidence


def _tombstone_unlink(path: Path, identity: tuple[int, int], label: str) -> None:
    parent, name = _private_parent(path, label)
    tombstone = f".{name}.release-{secrets.token_hex(16)}"
    try:
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != identity:
            raise GuardError(f"{label} identity changed")
        os.rename(name, tombstone, src_dir_fd=parent, dst_dir_fd=parent)
        moved = os.stat(tombstone, dir_fd=parent, follow_symlinks=False)
        if (moved.st_dev, moved.st_ino) != identity:
            raise GuardError(f"{label} rename race requires manual recovery")
        os.unlink(tombstone, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def release_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    now: datetime | None = None,
    expected_environment: str | None = None,
) -> None:
    """Release an unused reserved evidence pair after a pre-apply failure."""

    manifest = load_manifest(
        manifest_path,
        now=now,
        expected_environment=expected_environment,
        allow_expired=True,
    )
    _, manifest_identity = _private_read(
        manifest_path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES
    )
    reservation_path = _reservation_path(evidence_path)
    reservation_raw, reservation_identity = _private_read(
        reservation_path,
        "evidence reservation",
        max_bytes=MAX_JSON_BYTES,
    )
    evidence, evidence_identity = _evidence(
        manifest,
        manifest_path,
        evidence_path,
        {"reserved", "plan_validated"},
    )
    expected_reservation = canonical_json(
        {"evidence_identity": [evidence_identity[0], evidence_identity[1]]}
    )
    confirmed_reservation_raw, confirmed_reservation_identity = _private_read(
        reservation_path,
        "evidence reservation",
        max_bytes=MAX_JSON_BYTES,
    )
    if (
        reservation_raw != expected_reservation
        or confirmed_reservation_raw != expected_reservation
        or confirmed_reservation_identity != reservation_identity
    ):
        raise GuardError("evidence reservation identity or bytes changed")
    journal_path = _transition_path(evidence_path)
    journal = {
        "operation": "release",
        "evidence_identity": [evidence_identity[0], evidence_identity[1]],
        "reservation_identity": [reservation_identity[0], reservation_identity[1]],
        "evidence": evidence,
    }
    _private_write_new(journal_path, canonical_json(journal), "evidence transition")
    journal_raw, journal_identity = _private_read(
        journal_path, "evidence transition", max_bytes=MAX_JSON_BYTES
    )
    if journal_raw != canonical_json(journal):
        raise GuardError("evidence transition changed")
    _recover_release_transition(
        journal_path,
        journal,
        journal_identity,
        evidence_path,
        manifest,
        manifest_identity,
    )


def recover_reserved_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    now: datetime | None = None,
    expected_environment: str | None = None,
) -> None:
    """Explicit crash recovery for an unused EEXIST reservation."""

    manifest = load_manifest(
        manifest_path,
        now=now,
        expected_environment=expected_environment,
        allow_expired=True,
    )
    _, manifest_identity = _private_read(
        manifest_path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES
    )
    _recover_pair_transition(manifest, manifest_identity, evidence_path)
    if _path_present(evidence_path, "evidence"):
        release_evidence(
            manifest_path,
            evidence_path,
            now=now,
            expected_environment=expected_environment,
        )


def _evidence(
    manifest: dict[str, Any],
    manifest_path: Path,
    evidence_path: Path,
    status: str | set[str],
) -> tuple[dict[str, Any], tuple[int, int]]:
    _, manifest_identity = _private_read(
        manifest_path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES
    )
    _recover_pair_transition(manifest, manifest_identity, evidence_path)
    raw, identity = _private_read(
        evidence_path.absolute(), "evidence", max_bytes=MAX_JSON_BYTES
    )
    value = _json(raw, "evidence")
    expected_statuses = {status} if isinstance(status, str) else status
    try:
        actual_status = _validate_lifecycle_receipt(value, manifest, manifest_identity)
    except GuardError as exc:
        raise GuardError("evidence reservation is invalid") from exc
    if raw != canonical_json(value) or actual_status not in expected_statuses:
        raise GuardError("evidence reservation is invalid")
    reservation_raw, _ = _private_read(
        _reservation_path(evidence_path).absolute(),
        "evidence reservation",
        max_bytes=MAX_JSON_BYTES,
    )
    reservation = _json(reservation_raw, "evidence reservation")
    if reservation != {"evidence_identity": [identity[0], identity[1]]}:
        raise GuardError("evidence identity changed")
    return value, identity


def _delete_bindings(manifest: dict[str, Any]) -> dict[str, str]:
    resources = manifest["resources"]
    bindings = {
        "terraform_data.ssh_port": resources["terraform_data_ssh_port_id"],
        "vultr_instance.vpn": resources["server_id"],
        "vultr_ssh_key.admin": resources["ssh_key_id"],
        "vultr_firewall_group.vpn": resources["firewall_group_id"],
    }
    bindings.update(resources["firewall_rules"])
    return bindings


def bind_plan_fd(fd: int) -> PlanBinding:
    """Hash and rewind one inherited private plan descriptor without reopening it."""

    if not isinstance(fd, int):
        raise GuardError("validated destroy plan descriptor is required")
    try:
        info = os.fstat(fd)
    except OSError as exc:
        raise GuardError("validated destroy plan descriptor is unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size > MAX_JSON_BYTES
    ):
        raise GuardError("destroy plan descriptor is not a private owned regular file")
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = MAX_JSON_BYTES + 1
    while remaining:
        block = os.read(fd, min(1024 * 1024, remaining))
        if not block:
            break
        digest.update(block)
        remaining -= len(block)
    if remaining == 0:
        raise GuardError("destroy plan exceeds size limit")
    os.lseek(fd, 0, os.SEEK_SET)
    return PlanBinding((info.st_dev, info.st_ino), digest.hexdigest())


def _read_bound_plan(fd: int, binding: PlanBinding) -> bytes:
    current = bind_plan_fd(fd)
    if current.identity != binding.identity or current.sha256 != binding.sha256:
        raise GuardError("destroy plan descriptor changed")
    data = os.read(fd, MAX_JSON_BYTES + 1)
    os.lseek(fd, 0, os.SEEK_SET)
    if len(data) > MAX_JSON_BYTES:
        raise GuardError("destroy plan exceeds size limit")
    return data


def _terraform_show_json(plan_fd: int, environment: str) -> bytes:
    """Render the JSON view from the same inherited Terraform binary-plan FD."""

    bind_plan_fd(plan_fd)
    terraform_env = Path(__file__).resolve().with_name("terraform-env.sh")
    child_environment = os.environ.copy()
    child_environment.update({"PROVIDER": "vultr", "ENV": environment})
    try:
        result = subprocess.run(
            [str(terraform_env), "show", "-json", f"/dev/fd/{plan_fd}"],
            check=False,
            env=child_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            pass_fds=(plan_fd,),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GuardError("destroy plan JSON view is unavailable") from exc
    if result.returncode != 0 or len(result.stdout) > MAX_JSON_BYTES:
        raise GuardError("destroy plan JSON view is unavailable")
    return result.stdout


def validate_destroy_plan(
    manifest_path: Path,
    evidence_path: Path,
    *,
    request_json: JsonRequest,
    plan_fd: int,
    now: datetime | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(
        manifest_path, now=now, expected_environment=expected_environment
    )
    evidence, evidence_identity = _evidence(
        manifest, manifest_path, evidence_path, "reserved"
    )
    if _account_binding(request_json) != manifest["provider_account_binding"]:
        raise GuardError("provider account identity changed")
    binding = bind_plan_fd(plan_fd)
    plan = _json(
        _terraform_show_json(plan_fd, manifest["environment"]), "destroy plan view"
    )
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise GuardError("destroy plan lacks resource changes")
    expected = _delete_bindings(manifest)
    found: dict[str, str] = {}
    for item in changes:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("address"), str)
            or not isinstance(item.get("change"), dict)
        ):
            raise GuardError("destroy plan contains an invalid change")
        address, change = item["address"], item["change"]
        if (
            change.get("actions") != ["delete"]
            or change.get("after") is not None
            or address in found
            or address not in expected
        ):
            raise GuardError("destroy plan is not exact delete-only cleanup")
        before = change.get("before")
        if not isinstance(before, dict) or before.get("id") != expected[address]:
            raise GuardError("destroy plan resource binding is foreign")
        found[address] = expected[address]
    if found != expected:
        raise GuardError("destroy plan does not delete every exact owned resource")
    validated = dict(evidence)
    validated.update(
        {
            "status": "plan_validated",
            "plan_binding": {
                "identity": [binding.identity[0], binding.identity[1]],
                "sha256": binding.sha256,
            },
        }
    )
    _transition_evidence(evidence_path, evidence_identity, evidence, validated)
    return {
        "deleted_addresses": sorted(found),
        "server_id": manifest["resources"]["server_id"],
        "root": manifest["resources"]["root"],
        "plan_binding": {
            "identity": [binding.identity[0], binding.identity[1]],
            "sha256": binding.sha256,
        },
    }


def mark_apply_started(
    manifest_path: Path,
    evidence_path: Path,
    *,
    request_json: JsonRequest,
    plan_fd: int,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    read_clock = clock or (lambda: datetime.now(timezone.utc))
    current = _time(now or read_clock(), "current time")
    raw_before, manifest_identity = _private_read(
        manifest_path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES
    )
    manifest = load_manifest(
        manifest_path, now=current, expected_environment=expected_environment
    )
    state_path = Path(manifest["state"]["path"])
    state_before, state_identity = _private_read(
        state_path, "state", max_bytes=MAX_STATE_BYTES, exact_parent=False
    )
    evidence, evidence_identity = _evidence(
        manifest, manifest_path, evidence_path, "plan_validated"
    )
    plan_value = evidence.get("plan_binding")
    if (
        not isinstance(plan_value, dict)
        or set(plan_value) != {"identity", "sha256"}
        or not isinstance(plan_value["identity"], list)
        or len(plan_value["identity"]) != 2
        or not all(isinstance(part, int) for part in plan_value["identity"])
        or not isinstance(plan_value["sha256"], str)
        or not SHA256_RE.fullmatch(plan_value["sha256"])
    ):
        raise GuardError("validated plan binding is invalid")
    _read_bound_plan(
        plan_fd,
        PlanBinding(tuple(plan_value["identity"]), plan_value["sha256"]),
    )
    if _account_binding(request_json) != manifest["provider_account_binding"]:
        raise GuardError("provider account identity changed")
    if _provider_created(
        request_json,
        server_id=manifest["resources"]["server_id"],
        hostname=manifest["hostname"],
        now=current,
    ) != _time(manifest["created_at"], "manifest created_at"):
        raise GuardError("provider instance identity or creation time changed")
    raw_after, identity_after = _private_read(
        manifest_path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES
    )
    state_after, state_identity_after = _private_read(
        state_path, "state", max_bytes=MAX_STATE_BYTES, exact_parent=False
    )
    evidence_after, evidence_identity_after = _evidence(
        manifest, manifest_path, evidence_path, "plan_validated"
    )
    if (
        raw_before != raw_after
        or manifest_identity != identity_after
        or state_before != state_after
        or state_identity != state_identity_after
        or evidence != evidence_after
        or evidence_identity != evidence_identity_after
    ):
        raise GuardError("authorization inputs changed during pre-apply authorization")
    # This is the final binary-plan identity check immediately before the
    # state transition that an operator surrounds with Terraform apply.
    _read_bound_plan(
        plan_fd,
        PlanBinding(tuple(plan_value["identity"]), plan_value["sha256"]),
    )
    final_current = _time(
        read_clock() if clock is not None or now is None else now, "current time"
    )
    if final_current >= _time(manifest["expiry_at"], "manifest expiry_at"):
        raise GuardError("manifest cleanup schedule is invalid or expired")
    started = dict(evidence)
    started.update(
        {"status": "apply_started", "apply_started_at": _format_time(final_current)}
    )
    _transition_evidence(evidence_path, evidence_identity, evidence, started)
    return started


def verify_vultr_absence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    request_json: JsonRequest,
    now: datetime | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    current = _time(now or datetime.now(timezone.utc), "current time")
    manifest = load_manifest(
        manifest_path,
        now=current,
        expected_environment=expected_environment,
        verify_state=False,
        allow_expired=True,
    )
    try:
        started, identity = _evidence(
            manifest, manifest_path, evidence_path, "apply_started"
        )
    except GuardError as exc:
        raise GuardError("apply start receipt is invalid") from exc
    started_at = _receipt_time(started["apply_started_at"], "apply_started_at")
    if started_at > current:
        raise GuardError("apply start receipt is invalid")
    if _account_binding(request_json) != manifest["provider_account_binding"]:
        raise GuardError("provider account identity changed")
    endpoints = {
        "vultr_instance.vpn": f"/v2/instances/{manifest['resources']['server_id']}",
        "vultr_ssh_key.admin": f"/v2/ssh-keys/{manifest['resources']['ssh_key_id']}",
        "vultr_firewall_group.vpn": f"/v2/firewalls/{manifest['resources']['firewall_group_id']}",
    }
    endpoints.update(
        {
            address: f"/v2/firewalls/{manifest['resources']['firewall_group_id']}/rules/{identifier}"
            for address, identifier in manifest["resources"]["firewall_rules"].items()
        }
    )
    for address, endpoint in endpoints.items():
        status, _ = request_json(endpoint)
        if status != 404:
            raise GuardError(f"provider absence for {address} is ambiguous")
    expiry = _time(manifest["expiry_at"], "manifest expiry_at")
    verified = {
        "schema_version": SCHEMA_VERSION,
        "status": "verified_after_expiry" if current >= expiry else "verified",
        "deadline_status": (
            "expired_after_apply" if current >= expiry else "within_deadline"
        ),
        "provider": "vultr",
        "environment": manifest["environment"],
        "manifest_sha256": started["manifest_sha256"],
        "manifest_identity": started["manifest_identity"],
        "apply_started_at": started["apply_started_at"],
        "observed_at": _format_time(current),
        "server_id": manifest["resources"]["server_id"],
        "root": manifest["resources"]["root"],
        "absent_addresses": sorted(endpoints),
        "billing_status": "no-active-owned-resources",
    }
    _transition_evidence(evidence_path, identity, started, verified)
    return verified


def _vultr_request_from_environment(environment: Mapping[str, str] = os.environ) -> str:
    token = environment.get("VULTR_API_KEY", "")
    if not token:
        raise GuardError("VULTR_API_KEY is required in the environment")
    return token


def _vultr_https_request(token: str) -> JsonRequest:
    """Return the bounded, redirect-free Vultr API reader used by the CLI."""

    def request(path: str) -> tuple[int, dict[str, Any]]:
        if not isinstance(path, str) or not path.startswith("/v2/"):
            raise GuardError("provider request path is invalid")
        connection = http.client.HTTPSConnection("api.vultr.com", timeout=10)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            body = response.read(MAX_JSON_BYTES + 1)
            if len(body) > MAX_JSON_BYTES:
                raise GuardError("provider response is unavailable")
            if response.status == 404:
                return 404, {}
            if response.status != 200:
                raise GuardError("provider response is unavailable")
            return 200, _json(body, "provider response")
        except (OSError, http.client.HTTPException, UnicodeDecodeError) as exc:
            raise GuardError("provider response is unavailable") from exc
        finally:
            connection.close()

    return request


def rewind_plan_fd(fd: int) -> None:
    binding = bind_plan_fd(fd)
    _read_bound_plan(fd, binding)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-manifest")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--provider", required=True)
    create.add_argument("--environment", required=True)
    create.add_argument("--workspace", required=True)
    create.add_argument("--state", type=Path, required=True)
    create.add_argument("--hostname", required=True)
    for name in ("authorize-reserve-evidence", "recover-evidence", "release-evidence"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--evidence-output", type=Path, required=True)
        command.add_argument("--expected-provider", required=True)
        command.add_argument("--expected-environment", required=True)
    validate = commands.add_parser("validate-plan")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--evidence-output", type=Path, required=True)
    validate.add_argument("--fd-number", type=int, required=True)
    validate.add_argument("--expected-provider", required=True)
    validate.add_argument("--expected-environment", required=True)
    started = commands.add_parser("mark-apply-started")
    started.add_argument("--manifest", type=Path, required=True)
    started.add_argument("--evidence-output", type=Path, required=True)
    started.add_argument("--fd-number", type=int, required=True)
    started.add_argument("--expected-provider", required=True)
    started.add_argument("--expected-environment", required=True)
    absent = commands.add_parser("verify-vultr-absence")
    absent.add_argument("--manifest", type=Path, required=True)
    absent.add_argument("--evidence-output", type=Path, required=True)
    absent.add_argument("--expected-provider", required=True)
    absent.add_argument("--expected-environment", required=True)
    rewind = commands.add_parser("rewind-plan-fd")
    rewind.add_argument("--fd-number", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.command == "rewind-plan-fd":
        rewind_plan_fd(args.fd_number)
        return 0
    if args.command == "create-manifest":
        token = _vultr_request_from_environment()
        create_manifest(
            output_path=args.output,
            provider=args.provider,
            environment=args.environment,
            workspace=args.workspace,
            state_path=args.state,
            hostname=args.hostname,
            request_json=_vultr_https_request(token),
            now=now,
        )
        print("staging cleanup manifest created")
        return 0
    if args.expected_provider != "vultr":
        raise GuardError("staging cleanup provider is invalid")
    token = _vultr_request_from_environment()
    request_json = _vultr_https_request(token)
    if args.command == "authorize-reserve-evidence":
        preflight_manifest_account(
            args.manifest,
            request_json=request_json,
            environment=os.environ,
            now=now,
            expected_environment=args.expected_environment,
        )
        reserve_evidence(
            args.manifest,
            args.evidence_output,
            now=now,
            expected_environment=args.expected_environment,
        )
        print("staging provider authorization reserved")
        return 0
    if args.command == "recover-evidence":
        recover_reserved_evidence(
            args.manifest,
            args.evidence_output,
            now=now,
            expected_environment=args.expected_environment,
        )
        print("staging provider evidence recovered")
        return 0
    if args.command == "release-evidence":
        release_evidence(
            args.manifest,
            args.evidence_output,
            now=now,
            expected_environment=args.expected_environment,
        )
        print("staging provider evidence released")
        return 0
    if args.command == "validate-plan":
        validate_destroy_plan(
            args.manifest,
            args.evidence_output,
            request_json=request_json,
            plan_fd=args.fd_number,
            now=now,
            expected_environment=args.expected_environment,
        )
        print("staging destroy plan validated")
        return 0
    if args.command == "mark-apply-started":
        mark_apply_started(
            args.manifest,
            args.evidence_output,
            request_json=request_json,
            plan_fd=args.fd_number,
            expected_environment=args.expected_environment,
        )
        print("staging provider apply start recorded")
        return 0
    verify_vultr_absence(
        args.manifest,
        args.evidence_output,
        request_json=request_json,
        now=now,
        expected_environment=args.expected_environment,
    )
    print("staging provider absence verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GuardError as exc:
        print(f"staging cleanup guard: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
