#!/usr/bin/env python3
"""Guarded destruction for the fixed observability staging topology.

The public operator entry point is ``run``.  It consumes an immutable private
manifest and the completed acceptance journal, prepares all three destroy plans
through ``terraform-env.sh``, proves that each plan deletes exactly its frozen
state set, applies those exact plans, and then queries each provider API for
resource absence.  It intentionally has no production mode or arbitrary
provider/API/command surface.

Manifests, journals and receipts are canonical JSON regular files in
owner-controlled mode-0700 directories.  Inputs are mode 0600 and are read with
no-follow descriptors.  The completion receipt is fresh, redacted, and does not
contain provider identifiers, Terraform addresses, state paths, or endpoints.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import fleet_inspection
import staging_lifecycle as lifecycle

ROOT = Path(__file__).resolve().parents[1]
TF_WRAPPER = ROOT / "scripts/terraform-env.sh"
TASK_ID = "MON-1790650904289505"
CHANGE = "staging-observability-telegram-acceptance"
SCHEMA_VERSION = 1
PROVIDERS = ("upcloud", "hetzner", "scaleway")
MAX_API_BYTES = 64 * 1024
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+~-]{0,255}$")
COMPLETED_CHECKS = (
    "canary-sender-rotation",
    "control-host-loss",
    "control-plane-rollback",
    "control-service-loss",
    "deadman-lifecycle",
    "deadman-service-loss",
    "fresh-metrics",
    "old-material-rejection",
    "primary-authority-loss",
    "primary-bot-rotation",
    "primary-lifecycle",
    "secondary-bot-rotation",
)
HUMAN_OBSERVATIONS = {
    "deadman_loss_primary": True,
    "primary_authority_loss_secondary": True,
    "primary_lifecycle": True,
    "secondary_lifecycle": True,
}

ALLOWED_TERRAFORM_TYPES = {
    "upcloud": {
        "terraform_data",
        "upcloud_server",
        "upcloud_firewall_rules",
    },
    "hetzner": {
        "terraform_data",
        "hcloud_ssh_key",
        "hcloud_server",
        "hcloud_floating_ip",
        "hcloud_firewall",
        "hcloud_firewall_attachment",
    },
    "scaleway": {
        "terraform_data",
        "scaleway_instance_ip",
        "scaleway_instance_server",
        "scaleway_instance_security_group",
    },
}
ALLOWED_RESOURCE_KINDS = {
    "upcloud": {"server", "storage"},
    "hetzner": {"server", "ssh-key", "firewall", "floating-ip"},
    "scaleway": {"server", "ip", "security-group"},
}
EXPECTED_MANIFEST_KEYS = {
    "schema_version",
    "task_id",
    "change",
    "source_revision",
    "deployable_digest",
    "acceptance_journal_sha256",
    "snapshot_sha256",
    "created_at",
    "expires_at",
    "providers",
    "approval",
}
EXPECTED_PROVIDER_KEYS = {
    "provider",
    "account_id",
    "project_id",
    "environment",
    "state_path",
    "state_sha256",
    "destroy_plan_sha256",
    "terraform_addresses",
    "provider_resources",
}
EXPECTED_RESOURCE_KEYS = {
    "terraform_address",
    "kind",
    "provider_id",
    "location",
    "absence_owner",
}
EXPECTED_SNAPSHOT_KEYS = {
    "schema_version",
    "task_id",
    "change",
    "source_revision",
    "deployable_digest",
    "acceptance_journal_sha256",
    "created_at",
    "providers",
    "scope_sha256",
}
EXPECTED_APPROVAL_KEYS = {
    "schema_version",
    "task_id",
    "change",
    "snapshot_sha256",
    "source_revision",
    "deployable_digest",
    "acceptance_journal_sha256",
    "scope_sha256",
    "approval_id",
    "approved_at",
    "expires_at",
    "rollback_retention_closed",
}


class CleanupError(ValueError):
    """Categorical refusal safe to print without private values."""


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CleanupError(f"{label} rejected")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CleanupError(f"{label} rejected") from exc
    if parsed.utcoffset() != timedelta(0) or parsed.microsecond:
        raise CleanupError(f"{label} rejected")
    return parsed


def _format_time(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _absolute(value: Any) -> bool:
    return (
        isinstance(value, str)
        and Path(value).is_absolute()
        and ".." not in Path(value).parts
        and Path(value).name not in {"", ".", ".."}
    )


def _terraform_type(address: str) -> str:
    base = address.split("[", 1)[0]
    if base.startswith("module."):
        raise CleanupError("Terraform address rejected")
    return base.split(".", 1)[0]


def cleanup_scope_sha256(providers: Sequence[Mapping[str, Any]]) -> str:
    """Hash exactly the provider/state/resource set approved for deletion."""

    return hashlib.sha256(canonical_json(list(providers))).hexdigest()


def validate_acceptance_journal(value: Any) -> None:
    expected = {
        "schema_version",
        "task_id",
        "change",
        "status",
        "source_revision",
        "deployable_digest",
        "completed_checks",
        "human_observations",
        "components_removed",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("schema_version") != 1
        or value.get("task_id") != TASK_ID
        or value.get("change") != CHANGE
        or value.get("status") != "ready-for-cleanup"
        or not isinstance(value.get("source_revision"), str)
        or not SHA_RE.fullmatch(value["source_revision"])
        or not isinstance(value.get("deployable_digest"), str)
        or not SHA256_RE.fullmatch(value["deployable_digest"])
        or value.get("completed_checks") != list(COMPLETED_CHECKS)
        or value.get("human_observations") != HUMAN_OBSERVATIONS
        or value.get("components_removed") is not True
    ):
        raise CleanupError("acceptance journal rejected")


def _validate_provider(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != EXPECTED_PROVIDER_KEYS:
        raise CleanupError("provider scope rejected")
    provider = value.get("provider")
    if provider not in PROVIDERS or value.get("environment") != "staging":
        raise CleanupError("provider environment rejected")
    if (
        not isinstance(value.get("account_id"), str)
        or not SAFE_ID_RE.fullmatch(value["account_id"])
        or not _absolute(value.get("state_path"))
        or not isinstance(value.get("state_sha256"), str)
        or not SHA256_RE.fullmatch(value["state_sha256"])
        or not isinstance(value.get("destroy_plan_sha256"), str)
        or not SHA256_RE.fullmatch(value["destroy_plan_sha256"])
    ):
        raise CleanupError("provider identity rejected")
    project = value.get("project_id")
    if provider == "scaleway":
        if not isinstance(project, str) or not UUID_RE.fullmatch(project):
            raise CleanupError("provider project rejected")
    elif project is not None:
        raise CleanupError("provider project rejected")

    addresses = value.get("terraform_addresses")
    if (
        not isinstance(addresses, list)
        or not addresses
        or addresses != sorted(set(addresses))
        or not all(isinstance(item, str) and item for item in addresses)
        or any(
            _terraform_type(item) not in ALLOWED_TERRAFORM_TYPES[provider]
            for item in addresses
        )
    ):
        raise CleanupError("Terraform address set rejected")

    resources = value.get("provider_resources")
    if not isinstance(resources, list) or not resources:
        raise CleanupError("provider resource set rejected")
    seen: set[tuple[str, str]] = set()
    for resource in resources:
        if not isinstance(resource, dict) or set(resource) != EXPECTED_RESOURCE_KEYS:
            raise CleanupError("provider resource rejected")
        address = resource.get("terraform_address")
        kind = resource.get("kind")
        identifier = resource.get("provider_id")
        if (
            address not in addresses
            or kind not in ALLOWED_RESOURCE_KINDS[provider]
            or not isinstance(identifier, str)
            or not SAFE_ID_RE.fullmatch(identifier)
            or (address, kind) in seen
        ):
            raise CleanupError("provider resource rejected")
        seen.add((address, kind))
        location = resource.get("location")
        if provider == "scaleway":
            if not isinstance(location, str) or not re.fullmatch(
                r"[a-z]{2}-[a-z]+-[1-9][0-9]?", location
            ):
                raise CleanupError("provider resource location rejected")
        elif location is not None:
            raise CleanupError("provider resource location rejected")
        owner = resource.get("absence_owner")
        if owner is not None and owner not in addresses:
            raise CleanupError("provider resource owner rejected")

    required_direct = {
        "upcloud": {"server", "storage"},
        "hetzner": {"server", "ssh-key", "firewall"},
        "scaleway": {"server", "ip", "security-group"},
    }[provider]
    if not required_direct.issubset({item[1] for item in seen}):
        raise CleanupError("provider resource set incomplete")


def validate_manifest(
    value: Any, *, now: datetime | None = None, allow_expired: bool = False
) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != EXPECTED_MANIFEST_KEYS
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("task_id") != TASK_ID
        or value.get("change") != CHANGE
        or not isinstance(value.get("source_revision"), str)
        or not SHA_RE.fullmatch(value["source_revision"])
        or not isinstance(value.get("deployable_digest"), str)
        or not SHA256_RE.fullmatch(value["deployable_digest"])
        or not isinstance(value.get("acceptance_journal_sha256"), str)
        or not SHA256_RE.fullmatch(value["acceptance_journal_sha256"])
        or not isinstance(value.get("snapshot_sha256"), str)
        or not SHA256_RE.fullmatch(value["snapshot_sha256"])
    ):
        raise CleanupError("cleanup manifest rejected")
    created = _utc(value.get("created_at"), "manifest time")
    expiry = _utc(value.get("expires_at"), "manifest expiry")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if (
        not created < expiry
        or current < created
        or (not allow_expired and current >= expiry)
    ):
        raise CleanupError("cleanup manifest expired or not active")
    providers = value.get("providers")
    if not isinstance(providers, list) or [
        item.get("provider") if isinstance(item, dict) else None for item in providers
    ] != list(PROVIDERS):
        raise CleanupError("provider topology rejected")
    for provider in providers:
        _validate_provider(provider)

    approval = value.get("approval")
    if (
        not isinstance(approval, dict)
        or set(approval)
        != {
            "approval_id",
            "approved_at",
            "expires_at",
            "rollback_retention_closed",
            "scope_sha256",
        }
        or not isinstance(approval.get("approval_id"), str)
        or not SAFE_ID_RE.fullmatch(approval["approval_id"])
        or approval.get("rollback_retention_closed") is not True
        or approval.get("scope_sha256") != cleanup_scope_sha256(providers)
    ):
        raise CleanupError("destructive approval scope rejected")
    approved = _utc(approval.get("approved_at"), "approval time")
    approval_expiry = _utc(approval.get("expires_at"), "approval expiry")
    if (
        not created <= approved < approval_expiry <= expiry
        or current < approved
        or (not allow_expired and current >= approval_expiry)
    ):
        raise CleanupError("destructive approval expired or not active")


def validate_snapshot(value: Any, *, now: datetime | None = None) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != EXPECTED_SNAPSHOT_KEYS
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("task_id") != TASK_ID
        or value.get("change") != CHANGE
        or not isinstance(value.get("source_revision"), str)
        or not SHA_RE.fullmatch(value["source_revision"])
        or not isinstance(value.get("deployable_digest"), str)
        or not SHA256_RE.fullmatch(value["deployable_digest"])
        or not isinstance(value.get("acceptance_journal_sha256"), str)
        or not SHA256_RE.fullmatch(value["acceptance_journal_sha256"])
    ):
        raise CleanupError("cleanup snapshot rejected")
    created = _utc(value.get("created_at"), "snapshot time")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not created <= current < created + timedelta(hours=4):
        raise CleanupError("cleanup snapshot expired or not active")
    providers = value.get("providers")
    if not isinstance(providers, list) or [
        item.get("provider") if isinstance(item, dict) else None for item in providers
    ] != list(PROVIDERS):
        raise CleanupError("provider topology rejected")
    for provider in providers:
        _validate_provider(provider)
    if value.get("scope_sha256") != cleanup_scope_sha256(providers):
        raise CleanupError("cleanup snapshot scope rejected")


def seal_manifest(
    snapshot: Mapping[str, Any],
    snapshot_raw: bytes,
    approval: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    validate_snapshot(snapshot, now=current)
    snapshot_digest = hashlib.sha256(snapshot_raw).hexdigest()
    if (
        not isinstance(approval, dict)
        or set(approval) != EXPECTED_APPROVAL_KEYS
        or approval.get("schema_version") != SCHEMA_VERSION
        or approval.get("task_id") != TASK_ID
        or approval.get("change") != CHANGE
        or approval.get("snapshot_sha256") != snapshot_digest
        or approval.get("source_revision") != snapshot["source_revision"]
        or approval.get("deployable_digest") != snapshot["deployable_digest"]
        or approval.get("acceptance_journal_sha256")
        != snapshot["acceptance_journal_sha256"]
        or approval.get("scope_sha256") != snapshot["scope_sha256"]
        or not isinstance(approval.get("approval_id"), str)
        or not SAFE_ID_RE.fullmatch(approval["approval_id"])
        or approval.get("rollback_retention_closed") is not True
    ):
        raise CleanupError("destructive approval scope rejected")
    approved = _utc(approval.get("approved_at"), "approval time")
    expiry = _utc(approval.get("expires_at"), "approval expiry")
    if not approved <= current < expiry <= current + timedelta(hours=4):
        raise CleanupError("destructive approval expired or not active")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "change": CHANGE,
        "source_revision": snapshot["source_revision"],
        "deployable_digest": snapshot["deployable_digest"],
        "acceptance_journal_sha256": snapshot["acceptance_journal_sha256"],
        "snapshot_sha256": snapshot_digest,
        "created_at": snapshot["created_at"],
        "expires_at": approval["expires_at"],
        "providers": snapshot["providers"],
        "approval": {
            "approval_id": approval["approval_id"],
            "approved_at": approval["approved_at"],
            "expires_at": approval["expires_at"],
            "rollback_retention_closed": True,
            "scope_sha256": approval["scope_sha256"],
        },
    }
    validate_manifest(manifest, now=current)
    return manifest


def validate_destroy_plan(plan: Any, expected_addresses: Sequence[str]) -> None:
    if not isinstance(plan, dict) or not isinstance(plan.get("resource_changes"), list):
        raise CleanupError("destroy plan rejected")
    changes = plan["resource_changes"]
    observed: list[str] = []
    for change in changes:
        if not isinstance(change, dict) or set(change) < {"address", "change"}:
            raise CleanupError("destroy plan rejected")
        actions = change.get("change", {}).get("actions")
        if actions != ["delete"]:
            raise CleanupError("destroy plan is not delete-only")
        observed.append(change.get("address"))
    if sorted(observed) != list(expected_addresses) or len(observed) != len(
        set(observed)
    ):
        raise CleanupError("destroy plan does not match frozen address set")


def destroy_plan_sha256(plan: Any, expected_addresses: Sequence[str]) -> str:
    """Return a stable digest of only the reviewed address/action contract."""

    validate_destroy_plan(plan, expected_addresses)
    summary = [
        {"address": address, "actions": ["delete"]}
        for address in sorted(expected_addresses)
    ]
    return hashlib.sha256(canonical_json(summary)).hexdigest()


def _state_nonempty(raw: bytes) -> bool:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise CleanupError("Terraform state rejected") from exc
    resources = value.get("resources") if isinstance(value, dict) else None
    if not isinstance(resources, list):
        raise CleanupError("Terraform state rejected")
    return bool(resources)


def validate_state_binding(
    raw: bytes, provider_scope: Mapping[str, Any] | None, state_path: str
) -> None:
    if provider_scope is None:
        if _state_nonempty(raw):
            raise CleanupError("nonempty unbound state rejected")
        return
    if provider_scope.get("state_path") != state_path:
        raise CleanupError("Terraform state path drift")
    if not hmac.compare_digest(
        hashlib.sha256(raw).hexdigest(), str(provider_scope.get("state_sha256", ""))
    ):
        raise CleanupError("Terraform state digest drift")


def verify_provider_absence(
    provider_scope: Mapping[str, Any],
    status_reader: Callable[[Mapping[str, Any], Mapping[str, Any]], int],
) -> None:
    for resource in provider_scope["provider_resources"]:
        if resource.get("absence_owner") is not None:
            continue
        if status_reader(provider_scope, resource) != 404:
            raise CleanupError("provider absence ambiguous")


def provider_presence(
    provider_scope: Mapping[str, Any],
    status_reader: Callable[[Mapping[str, Any], Mapping[str, Any]], int],
) -> str:
    statuses = [
        status_reader(provider_scope, resource)
        for resource in provider_scope["provider_resources"]
        if resource.get("absence_owner") is None
    ]
    if statuses and all(status == 404 for status in statuses):
        return "absent"
    if statuses and all(status == 200 for status in statuses):
        return "present"
    return "ambiguous"


def build_receipt(
    *, manifest: Mapping[str, Any], manifest_bytes: bytes, completed_at: datetime
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "provider-absence-verified",
        "task_id": TASK_ID,
        "change": CHANGE,
        "source_revision": manifest["source_revision"],
        "deployable_digest": manifest["deployable_digest"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "acceptance_journal_sha256": manifest["acceptance_journal_sha256"],
        "completed_at": _format_time(completed_at),
        "providers": [
            {
                "provider": provider,
                "status": "absent",
            }
            for provider in PROVIDERS
        ],
        "local_retirement": "permitted",
    }


def progress_path(receipt_path: Path) -> Path:
    return receipt_path.with_name(receipt_path.name + ".progress")


def build_progress(
    manifest: Mapping[str, Any], manifest_raw: bytes, journal_raw: bytes
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "active",
        "task_id": TASK_ID,
        "change": CHANGE,
        "source_revision": manifest["source_revision"],
        "deployable_digest": manifest["deployable_digest"],
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "acceptance_journal_sha256": hashlib.sha256(journal_raw).hexdigest(),
        "providers": [
            {"provider": provider, "phase": "pending"} for provider in PROVIDERS
        ],
    }


def validate_progress(
    value: Any,
    manifest: Mapping[str, Any],
    manifest_raw: bytes,
    journal_raw: bytes,
) -> None:
    expected = {
        "schema_version",
        "status",
        "task_id",
        "change",
        "source_revision",
        "deployable_digest",
        "manifest_sha256",
        "acceptance_journal_sha256",
        "providers",
    }
    providers = value.get("providers") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("status") != "active"
        or value.get("task_id") != TASK_ID
        or value.get("change") != CHANGE
        or value.get("source_revision") != manifest["source_revision"]
        or value.get("deployable_digest") != manifest["deployable_digest"]
        or value.get("manifest_sha256") != hashlib.sha256(manifest_raw).hexdigest()
        or value.get("acceptance_journal_sha256")
        != hashlib.sha256(journal_raw).hexdigest()
        or not isinstance(providers, list)
        or [
            item.get("provider") if isinstance(item, dict) else None
            for item in providers
        ]
        != list(PROVIDERS)
        or any(
            set(item) != {"provider", "phase"}
            or item.get("phase") not in {"pending", "apply-started", "absent"}
            for item in providers
        )
    ):
        raise CleanupError("cleanup progress rejected")


def advance_progress(
    value: Mapping[str, Any], provider: str, phase: str
) -> dict[str, Any]:
    order = {"pending": 0, "apply-started": 1, "absent": 2}
    if provider not in PROVIDERS or phase not in order:
        raise CleanupError("cleanup progress transition rejected")
    result = json.loads(json.dumps(value))
    entry = next(item for item in result["providers"] if item["provider"] == provider)
    if order[phase] != order[entry["phase"]] + 1:
        raise CleanupError("cleanup progress transition rejected")
    entry["phase"] = phase
    return result


def _read_private(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        with lifecycle._parent(path) as (parent, name):
            raw, identity = lifecycle._read_at(parent, name)
            visible = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if visible.st_nlink != 1 or (visible.st_dev, visible.st_ino) != identity:
                raise lifecycle.GuardError("private artifact identity rejected")
        value = lifecycle._object(raw)
    except (lifecycle.GuardError, OSError) as exc:
        raise CleanupError(f"{label} rejected") from exc
    return value, raw


def _publish_fresh(path: Path, value: Mapping[str, Any]) -> None:
    raw = canonical_json(value)
    try:
        with lifecycle._parent(path) as (parent, name):
            lifecycle._atomic(parent, name, raw, replace=False)
    except (lifecycle.GuardError, OSError) as exc:
        raise CleanupError("cleanup receipt publication failed") from exc


def _replace_private(path: Path, value: Mapping[str, Any]) -> None:
    raw = canonical_json(value)
    try:
        with lifecycle._parent(path) as (parent, name):
            existing, identity = lifecycle._read_at(parent, name)
            visible = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if visible.st_nlink != 1 or (visible.st_dev, visible.st_ino) != identity:
                raise CleanupError("cleanup progress rejected")
            if lifecycle._object(existing).get("status") != "active":
                raise CleanupError("cleanup progress rejected")
            lifecycle._atomic(parent, name, raw, replace=True)
    except (lifecycle.GuardError, OSError) as exc:
        raise CleanupError("cleanup progress update failed") from exc


def _require_fresh_output(path: Path) -> None:
    try:
        with lifecycle._parent(path) as (parent, name):
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return
            if stat.S_ISLNK(info.st_mode):
                raise CleanupError("cleanup receipt output rejected")
            raise CleanupError("cleanup receipt output already exists")
    except lifecycle.GuardError as exc:
        raise CleanupError("cleanup receipt output rejected") from exc


def _private_present(path: Path) -> bool:
    try:
        with lifecycle._parent(path) as (parent, name):
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return False
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise CleanupError("cleanup progress rejected")
            return True
    except lifecycle.GuardError as exc:
        raise CleanupError("cleanup progress rejected") from exc


def _remove_private(path: Path) -> None:
    try:
        with lifecycle._parent(path) as (parent, name):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise CleanupError("cleanup progress rejected")
            os.unlink(name, dir_fd=parent)
            os.fsync(parent)
    except (lifecycle.GuardError, OSError) as exc:
        raise CleanupError("cleanup progress retirement failed") from exc


@contextlib.contextmanager
def _manifest_lock(path: Path):
    try:
        with lifecycle._parent(path) as (parent, name):
            descriptor = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            try:
                info = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                ):
                    raise CleanupError("cleanup manifest rejected")
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise CleanupError("cleanup operation already active") from exc
                yield
            finally:
                os.close(descriptor)
    except lifecycle.GuardError as exc:
        raise CleanupError("cleanup manifest rejected") from exc


def _filtered_environment(provider: str) -> dict[str, str]:
    common = {
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "TF_CLI_CONFIG_FILE",
    }
    credentials = {
        "upcloud": {
            "UPCLOUD_TOKEN",
            "UPCLOUD_USERNAME",
            "UPCLOUD_PASSWORD",
            "UPCLOUD_API_USERNAME",
            "UPCLOUD_API_PASSWORD",
        },
        "hetzner": {"HCLOUD_TOKEN"},
        "scaleway": {
            "SCW_ACCESS_KEY",
            "SCW_SECRET_KEY",
            "SCW_DEFAULT_PROJECT_ID",
            "SCW_DEFAULT_ORGANIZATION_ID",
        },
    }[provider]
    result = {key: os.environ[key] for key in common | credentials if key in os.environ}
    result.update({"PROVIDER": provider, "ENV": "staging"})
    return result


def _debug_disabled() -> None:
    for name in ("TF_LOG", "TF_LOG_PATH"):
        if os.environ.get(name, "").strip():
            raise CleanupError("Terraform debug output forbidden")


def _verify_source(value: Mapping[str, Any]) -> None:
    try:
        completed = subprocess.run(
            [str(ROOT / "scripts/deploy-source-identity.sh"), "--identity"],
            cwd=ROOT,
            env={
                key: os.environ[key]
                for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
                if key in os.environ
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            timeout=15,
        )
        revision, digest = completed.stdout.strip().split()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise CleanupError("source identity unavailable") from exc
    if revision != value["source_revision"] or digest != value["deployable_digest"]:
        raise CleanupError("source identity drift")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
        if key in os.environ
    }
    try:
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                "Makefile",
                "ansible",
                "scripts",
                "terraform",
                "requirements.yml",
            ],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
        protected = subprocess.run(
            ["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CleanupError("source cleanliness unavailable") from exc
    if status.returncode != 0:
        raise CleanupError("source cleanliness unavailable")
    if status.stdout or protected.stdout.strip() != revision:
        raise CleanupError("clean protected-main source required")


def _audit_cleanup() -> None:
    base = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "AGE_KEY")
        if key in os.environ
    }
    for provider in PROVIDERS:
        environment = dict(base)
        environment.update({"ENV": "staging", "PROVIDER": provider})
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [
                    str(ROOT / "scripts/audit-log.sh"),
                    "append-best-effort",
                    "--action",
                    "observability-staging-cleanup",
                    "--env",
                    "staging",
                    "--provider",
                    provider,
                    "--note",
                    "exact-managed-resources-absent",
                ],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )


def _require_credentials(provider: str, environment: Mapping[str, str]) -> None:
    if provider == "upcloud":
        modes = (
            bool(environment.get("UPCLOUD_TOKEN")),
            bool(environment.get("UPCLOUD_USERNAME"))
            and bool(environment.get("UPCLOUD_PASSWORD")),
            bool(environment.get("UPCLOUD_API_USERNAME"))
            and bool(environment.get("UPCLOUD_API_PASSWORD")),
        )
        partial = (
            any(
                environment.get(key) for key in ("UPCLOUD_USERNAME", "UPCLOUD_PASSWORD")
            )
            != modes[1]
        )
        partial |= (
            any(
                environment.get(key)
                for key in ("UPCLOUD_API_USERNAME", "UPCLOUD_API_PASSWORD")
            )
            != modes[2]
        )
        if sum(modes) != 1 or partial:
            raise CleanupError("UpCloud authority rejected")
    elif provider == "hetzner":
        if not environment.get("HCLOUD_TOKEN"):
            raise CleanupError("Hetzner authority rejected")
    elif not all(
        environment.get(key)
        for key in ("SCW_ACCESS_KEY", "SCW_SECRET_KEY", "SCW_DEFAULT_PROJECT_ID")
    ):
        raise CleanupError("Scaleway authority rejected")


def _run_tf(
    provider: str,
    arguments: Sequence[str],
    *,
    pass_fds: Sequence[int] = (),
) -> bytes:
    environment = _filtered_environment(provider)
    _require_credentials(provider, environment)
    try:
        completed = subprocess.run(
            [str(TF_WRAPPER), *arguments],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15 * 60,
            pass_fds=tuple(pass_fds),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CleanupError("Terraform operation failed") from exc
    if completed.returncode != 0:
        raise CleanupError("Terraform operation failed")
    return completed.stdout


def _expected_state_path(provider: str) -> Path:
    return (
        ROOT
        / "terraform/providers"
        / provider
        / "terraform.tfstate.d/staging/terraform.tfstate"
    )


def _state_bytes(provider: str) -> bytes:
    path = _expected_state_path(provider)
    try:
        descriptor = fleet_inspection._open_local_file(path, private=True)
    except fleet_inspection.InspectionError as exc:
        try:
            os.lstat(path)
        except FileNotFoundError:
            return b'{"version":4,"resources":[]}'
        raise CleanupError("Terraform state unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_size > 64 * 1024 * 1024
        ):
            raise CleanupError("Terraform state ownership or mode rejected")
        raw = b""
        while len(raw) <= 64 * 1024 * 1024:
            chunk = os.read(descriptor, min(65536, 64 * 1024 * 1024 + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > 64 * 1024 * 1024:
            raise CleanupError("Terraform state size rejected")
        current = path.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise CleanupError("Terraform state changed during read")
        return raw
    finally:
        os.close(descriptor)


def _state_pull(provider: str) -> bytes:
    # The local-backend bytes, not a reserialized stdout view, are the frozen
    # identity.  Terraform still receives every operation through the routed
    # wrapper; this read only fences the exact state artifact used by it.
    return _state_bytes(provider)


def _instance_address(resource: Mapping[str, Any], instance: Mapping[str, Any]) -> str:
    address = f"{resource['type']}.{resource['name']}"
    if "index_key" not in instance:
        return address
    key = instance["index_key"]
    if type(key) is int:
        return f"{address}[{key}]"
    if isinstance(key, str):
        return f"{address}[{json.dumps(key)}]"
    raise CleanupError("Terraform state instance key rejected")


def extract_provider_scope(
    provider: str,
    raw: bytes,
    *,
    account_id: str,
    project_id: str | None,
) -> dict[str, Any]:
    """Extract the complete managed address and direct provider identity set."""

    try:
        state = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise CleanupError("Terraform state rejected") from exc
    if (
        not isinstance(state, dict)
        or state.get("version") != 4
        or not isinstance(state.get("resources"), list)
    ):
        raise CleanupError("Terraform state rejected")
    addresses: list[str] = []
    direct: list[dict[str, Any]] = []
    for resource in state["resources"]:
        if (
            not isinstance(resource, dict)
            or resource.get("mode") != "managed"
            or "module" in resource
            or resource.get("type") not in ALLOWED_TERRAFORM_TYPES[provider]
            or not isinstance(resource.get("name"), str)
            or not isinstance(resource.get("instances"), list)
        ):
            raise CleanupError("Terraform state resource rejected")
        for instance in resource["instances"]:
            if not isinstance(instance, dict) or not isinstance(
                instance.get("attributes"), dict
            ):
                raise CleanupError("Terraform state instance rejected")
            address = _instance_address(resource, instance)
            attributes = instance["attributes"]
            addresses.append(address)
            resource_type = resource["type"]
            identifier = attributes.get("id")
            location: str | None = None
            kind: str | None = None
            if provider == "upcloud" and resource_type == "upcloud_server":
                kind = "server"
            elif provider == "hetzner":
                kind = {
                    "hcloud_server": "server",
                    "hcloud_ssh_key": "ssh-key",
                    "hcloud_firewall": "firewall",
                    "hcloud_floating_ip": "floating-ip",
                }.get(resource_type)
            elif provider == "scaleway":
                kind = {
                    "scaleway_instance_server": "server",
                    "scaleway_instance_ip": "ip",
                    "scaleway_instance_security_group": "security-group",
                }.get(resource_type)
                location = attributes.get("zone")
            if kind is not None:
                if not isinstance(identifier, (str, int)):
                    raise CleanupError("provider identity missing from state")
                direct.append(
                    {
                        "terraform_address": address,
                        "kind": kind,
                        "provider_id": str(identifier),
                        "location": location,
                        "absence_owner": None,
                    }
                )
            if provider == "upcloud" and resource_type == "upcloud_server":
                template = attributes.get("template")
                if (
                    not isinstance(template, list)
                    or len(template) != 1
                    or not isinstance(template[0], dict)
                    or not isinstance(template[0].get("id"), str)
                ):
                    raise CleanupError("UpCloud root storage identity rejected")
                direct.append(
                    {
                        "terraform_address": address,
                        "kind": "storage",
                        "provider_id": template[0]["id"],
                        "location": None,
                        "absence_owner": None,
                    }
                )
    if not addresses or len(addresses) != len(set(addresses)):
        raise CleanupError("Terraform state address set rejected")
    value = {
        "provider": provider,
        "account_id": account_id,
        "project_id": project_id,
        "environment": "staging",
        "state_path": str(_expected_state_path(provider)),
        "state_sha256": hashlib.sha256(raw).hexdigest(),
        "destroy_plan_sha256": "0" * 64,
        "terraform_addresses": sorted(addresses),
        "provider_resources": sorted(
            direct,
            key=lambda item: (
                item["terraform_address"],
                item["kind"],
                item["provider_id"],
            ),
        ),
    }
    _validate_provider(value)
    return value


def _auth_headers(provider: str) -> dict[str, str]:
    environment = _filtered_environment(provider)
    _require_credentials(provider, environment)
    if provider == "upcloud":
        token = environment.get("UPCLOUD_TOKEN")
        if token:
            authorization = "Bearer " + token
        else:
            username = environment.get("UPCLOUD_USERNAME") or environment.get(
                "UPCLOUD_API_USERNAME", ""
            )
            password = environment.get("UPCLOUD_PASSWORD") or environment.get(
                "UPCLOUD_API_PASSWORD", ""
            )
            authorization = (
                "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
            )
        return {"Authorization": authorization, "Accept": "application/json"}
    if provider == "hetzner":
        return {
            "Authorization": "Bearer " + environment["HCLOUD_TOKEN"],
            "Accept": "application/json",
        }
    return {
        "X-Auth-Token": environment["SCW_SECRET_KEY"],
        "Accept": "application/json",
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _api_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirect(),
    )


def _http_json(provider: str, url: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=_auth_headers(provider), method="GET")
    try:
        response = _api_opener().open(request, timeout=20)
        status = response.status
        raw = response.read(MAX_API_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read(MAX_API_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise CleanupError("provider API unavailable") from exc
    if 300 <= status < 400:
        raise CleanupError("provider API redirect rejected")
    if len(raw) > MAX_API_BYTES:
        raise CleanupError("provider API response rejected")
    try:
        value = json.loads(raw) if raw else {}
    except (ValueError, UnicodeError) as exc:
        raise CleanupError("provider API response rejected") from exc
    if not isinstance(value, dict):
        raise CleanupError("provider API response rejected")
    return status, value


def _account_identity(provider: str, project: str | None) -> str:
    if provider == "upcloud":
        status, value = _http_json(provider, "https://api.upcloud.com/1.3/account")
        account = value.get("account") if status == 200 else None
        observed = account.get("username") if isinstance(account, dict) else None
    elif provider == "hetzner":
        # HCloud exposes no stable account-id endpoint.  Bind the exact ambient
        # account authority by a domain-separated credential fingerprint, then
        # prove authority over every frozen resource before planning.
        token = _filtered_environment(provider).get("HCLOUD_TOKEN", "")
        observed = hashlib.sha256(
            b"hcloud-account-binding\0" + token.encode()
        ).hexdigest()
    else:
        if not isinstance(project, str) or not UUID_RE.fullmatch(project):
            raise CleanupError("provider project rejected")
        quoted = urllib.parse.quote(project, safe="")
        status, value = _http_json(
            provider, f"https://api.scaleway.com/account/v2/projects/{quoted}"
        )
        project_value = value.get("project", value) if status == 200 else None
        if not isinstance(project_value, dict) or project_value.get("id") != project:
            observed = None
        else:
            observed = project_value.get("organization_id")
        if _filtered_environment(provider).get("SCW_DEFAULT_PROJECT_ID") != project:
            observed = None
    if (
        not isinstance(observed, str)
        or not observed
        or not SAFE_ID_RE.fullmatch(observed)
    ):
        raise CleanupError("provider account or project mismatch")
    return observed


def _verify_account(scope: Mapping[str, Any]) -> None:
    observed = _account_identity(scope["provider"], scope.get("project_id"))
    if not hmac.compare_digest(observed, scope["account_id"]):
        raise CleanupError("provider account or project mismatch")


def _resource_url(scope: Mapping[str, Any], resource: Mapping[str, Any]) -> str:
    provider, kind = scope["provider"], resource["kind"]
    identifier = urllib.parse.quote(resource["provider_id"], safe="")
    if provider == "upcloud":
        segment = {"server": "server", "storage": "storage"}[kind]
        return f"https://api.upcloud.com/1.3/{segment}/{identifier}"
    if provider == "hetzner":
        segment = {
            "server": "servers",
            "ssh-key": "ssh_keys",
            "firewall": "firewalls",
            "floating-ip": "floating_ips",
        }[kind]
        return f"https://api.hetzner.cloud/v1/{segment}/{identifier}"
    location = urllib.parse.quote(resource["location"], safe="")
    segment = {
        "server": "servers",
        "ip": "ips",
        "security-group": "security_groups",
    }[kind]
    return (
        f"https://api.scaleway.com/instance/v1/zones/{location}/{segment}/{identifier}"
    )


def _live_absence_status(scope: Mapping[str, Any], resource: Mapping[str, Any]) -> int:
    status, _payload = _http_json(scope["provider"], _resource_url(scope, resource))
    return status


def _verify_resources_exist(scope: Mapping[str, Any]) -> None:
    for resource in scope["provider_resources"]:
        if resource.get("absence_owner") is not None:
            continue
        status, _payload = _http_json(scope["provider"], _resource_url(scope, resource))
        if status != 200:
            raise CleanupError("provider resource binding rejected")


def _write_override(provider: str) -> Path:
    resource = {
        "upcloud": "upcloud_server.vpn",
        "hetzner": "hcloud_server.vpn",
        "scaleway": "scaleway_instance_server.vpn",
    }[provider]
    kind, name = resource.split(".", 1)
    path = (
        ROOT / "terraform/providers" / provider / "_observability_cleanup_override.tf"
    )
    raw = (
        "# Generated by observability-staging-cleanup.py; removed automatically.\n"
        f'resource "{kind}" "{name}" {{\n'
        "  lifecycle {\n    prevent_destroy = false\n  }\n}\n"
    ).encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CleanupError("destroy lifecycle override unavailable") from exc
    return path


def _prepare_plan(
    provider_scope: Mapping[str, Any], directory: Path
) -> tuple[int, str, str]:
    provider = provider_scope["provider"]
    override = _write_override(provider)
    plan = directory / f"{provider}.tfplan"
    try:
        _run_tf(
            provider,
            (
                "plan",
                "-destroy",
                "-input=false",
                "-lock=true",
                "-var-file=environments/staging.tfvars",
                f"-out={plan}",
            ),
        )
        os.chmod(plan, 0o600)
        try:
            descriptor = os.open(plan, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise CleanupError("destroy plan rejected")
            os.unlink(plan)
            view = _run_tf(
                provider,
                ("show", "-json", f"/dev/fd/{descriptor}"),
                pass_fds=(descriptor,),
            )
            try:
                document = json.loads(view)
            except (ValueError, UnicodeError) as exc:
                raise CleanupError("destroy plan rejected") from exc
            summary_digest = destroy_plan_sha256(
                document, provider_scope["terraform_addresses"]
            )
            return descriptor, _descriptor_sha256(descriptor), summary_digest
        except BaseException:
            with contextlib.suppress(UnboundLocalError, OSError):
                os.close(descriptor)
            raise
    finally:
        with contextlib.suppress(FileNotFoundError):
            override.unlink()


def _descriptor_sha256(descriptor: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _apply_plan(provider: str, descriptor: int, expected_digest: str) -> None:
    if not hmac.compare_digest(_descriptor_sha256(descriptor), expected_digest):
        raise CleanupError("destroy plan identity changed")
    _run_tf(
        provider,
        ("apply", "-input=false", "-auto-approve", f"/dev/fd/{descriptor}"),
        pass_fds=(descriptor,),
    )


def execute_snapshot(
    journal_path: Path,
    output_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (
        (now or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .replace(microsecond=0)
    )
    journal, journal_raw = _read_private(journal_path, "acceptance journal")
    validate_acceptance_journal(journal)
    _debug_disabled()
    _verify_source(journal)
    providers: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="observability-cleanup-snapshot-") as tmp:
        directory = Path(tmp).resolve()
        os.chmod(directory, 0o700)
        for provider in PROVIDERS:
            project = (
                _filtered_environment(provider).get("SCW_DEFAULT_PROJECT_ID")
                if provider == "scaleway"
                else None
            )
            account = _account_identity(provider, project)
            raw = _state_pull(provider)
            if not _state_nonempty(raw):
                raise CleanupError("Terraform staging state is empty")
            scope = extract_provider_scope(
                provider,
                raw,
                account_id=account,
                project_id=project,
            )
            _verify_resources_exist(scope)
            descriptor, _plan_digest, summary_digest = _prepare_plan(scope, directory)
            os.close(descriptor)
            scope["destroy_plan_sha256"] = summary_digest
            _validate_provider(scope)
            providers.append(scope)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "change": CHANGE,
        "source_revision": journal["source_revision"],
        "deployable_digest": journal["deployable_digest"],
        "acceptance_journal_sha256": hashlib.sha256(journal_raw).hexdigest(),
        "created_at": _format_time(current),
        "providers": providers,
        "scope_sha256": cleanup_scope_sha256(providers),
    }
    validate_snapshot(snapshot, now=current)
    _publish_fresh(output_path, snapshot)
    return snapshot


def execute_seal(
    snapshot_path: Path,
    approval_path: Path,
    output_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    snapshot, snapshot_raw = _read_private(snapshot_path, "cleanup snapshot")
    approval, _approval_raw = _read_private(approval_path, "cleanup approval")
    manifest = seal_manifest(snapshot, snapshot_raw, approval, now=now)
    _publish_fresh(output_path, manifest)
    return manifest


def execute_run(
    manifest_path: Path,
    journal_path: Path,
    receipt_path: Path,
    *,
    confirmed: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not confirmed:
        raise CleanupError("explicit destructive confirmation required")
    _require_fresh_output(receipt_path)
    current = (
        (now or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .replace(microsecond=0)
    )
    with _manifest_lock(manifest_path):
        manifest, manifest_raw = _read_private(manifest_path, "cleanup manifest")
        journal, journal_raw = _read_private(journal_path, "acceptance journal")
        progress_file = progress_path(receipt_path)
        has_progress = _private_present(progress_file)
        validate_manifest(manifest, now=current, allow_expired=has_progress)
        validate_acceptance_journal(journal)
        _debug_disabled()
        _verify_source(manifest)
        if (
            manifest["acceptance_journal_sha256"]
            != hashlib.sha256(journal_raw).hexdigest()
            or manifest["source_revision"] != journal["source_revision"]
            or manifest["deployable_digest"] != journal["deployable_digest"]
        ):
            raise CleanupError("acceptance journal binding mismatch")

        if has_progress:
            progress, _progress_raw = _read_private(progress_file, "cleanup progress")
            validate_progress(progress, manifest, manifest_raw, journal_raw)
        else:
            progress = build_progress(manifest, manifest_raw, journal_raw)

        plans: list[tuple[Mapping[str, Any], int, str, bool]] = []
        with tempfile.TemporaryDirectory(prefix="observability-cleanup-") as temporary:
            directory = Path(temporary).resolve()
            os.chmod(directory, 0o700)
            try:
                # Recover prior phases, then finish every remaining account,
                # state and plan check before issuing another delete.
                for scope in manifest["providers"]:
                    provider = scope["provider"]
                    phase = next(
                        item["phase"]
                        for item in progress["providers"]
                        if item["provider"] == provider
                    )
                    expected_path = _expected_state_path(scope["provider"])
                    if Path(scope["state_path"]) != expected_path:
                        raise CleanupError("Terraform state path drift")
                    _verify_account(scope)
                    if phase in {"apply-started", "absent"}:
                        observed = provider_presence(scope, _live_absence_status)
                        if observed == "absent":
                            if phase == "apply-started":
                                progress = advance_progress(
                                    progress, provider, "absent"
                                )
                                _replace_private(progress_file, progress)
                            continue
                        if phase == "absent" or observed != "present":
                            raise CleanupError("provider recovery state ambiguous")
                        # The previous apply was interrupted before any provider
                        # resource disappeared. Retry only while the complete
                        # frozen local state is still byte-identical.
                        validate_manifest(manifest, now=current)
                        raw = _state_pull(provider)
                        validate_state_binding(raw, scope, str(expected_path))
                        _verify_resources_exist(scope)
                        already_started = True
                    else:
                        validate_manifest(manifest, now=current)
                        raw = _state_pull(provider)
                        validate_state_binding(raw, scope, str(expected_path))
                        _verify_resources_exist(scope)
                        already_started = False
                    descriptor, digest, summary_digest = _prepare_plan(scope, directory)
                    if not hmac.compare_digest(
                        summary_digest, scope["destroy_plan_sha256"]
                    ):
                        os.close(descriptor)
                        raise CleanupError("reviewed destroy plan drift")
                    plans.append((scope, descriptor, digest, already_started))

                if not _private_present(progress_file):
                    _publish_fresh(progress_file, progress)

                for scope, descriptor, digest, already_started in plans:
                    validate_manifest(manifest)
                    if not already_started:
                        progress = advance_progress(
                            progress, scope["provider"], "apply-started"
                        )
                        _replace_private(progress_file, progress)
                    _apply_plan(scope["provider"], descriptor, digest)
                    _verify_account(scope)
                    verify_provider_absence(scope, _live_absence_status)
                    progress = advance_progress(progress, scope["provider"], "absent")
                    _replace_private(progress_file, progress)

                if any(item["phase"] != "absent" for item in progress["providers"]):
                    raise CleanupError("cleanup progress incomplete")
                for scope in manifest["providers"]:
                    _verify_account(scope)
                    verify_provider_absence(scope, _live_absence_status)

                # Re-read immutable inputs after every external operation.
                manifest_after, manifest_after_raw = _read_private(
                    manifest_path, "cleanup manifest"
                )
                journal_after, journal_after_raw = _read_private(
                    journal_path, "acceptance journal"
                )
                if (
                    manifest_after != manifest
                    or manifest_after_raw != manifest_raw
                    or journal_after != journal
                    or journal_after_raw != journal_raw
                ):
                    raise CleanupError("cleanup authority changed during operation")
                receipt = build_receipt(
                    manifest=manifest,
                    manifest_bytes=manifest_raw,
                    completed_at=datetime.now(timezone.utc).replace(microsecond=0),
                )
                _publish_fresh(receipt_path, receipt)
                _audit_cleanup()
                # The redacted terminal receipt is authoritative. A leftover
                # internal progress file is safe to inspect/remove later and
                # must not downgrade already verified provider absence.
                with contextlib.suppress(CleanupError):
                    _remove_private(progress_file)
                return receipt
            finally:
                for _scope, descriptor, _digest, _already_started in plans:
                    with contextlib.suppress(OSError):
                        os.close(descriptor)


def execute_preflight(manifest_path: Path | None) -> None:
    manifest = None
    if manifest_path is not None:
        manifest, _raw = _read_private(manifest_path, "cleanup manifest")
        validate_manifest(manifest)
    for provider in PROVIDERS:
        raw = _state_pull(provider)
        scope = None
        if manifest is not None:
            scope = next(
                item for item in manifest["providers"] if item["provider"] == provider
            )
        validate_state_binding(raw, scope, str(_expected_state_path(provider)))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--acceptance-journal", type=Path, required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    seal = commands.add_parser("seal")
    seal.add_argument("--snapshot", type=Path, required=True)
    seal.add_argument("--approval", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--acceptance-journal", type=Path, required=True)
    run.add_argument("--receipt", type=Path, required=True)
    run.add_argument("--confirm", action="store_true")
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--manifest", type=Path)
    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--acceptance-journal", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            execute_snapshot(args.acceptance_journal, args.output)
            print("staging cleanup scope snapshot created")
        elif args.command == "seal":
            execute_seal(args.snapshot, args.approval, args.output)
            print("staging cleanup manifest sealed")
        elif args.command == "run":
            execute_run(
                args.manifest,
                args.acceptance_journal,
                args.receipt,
                confirmed=args.confirm,
            )
            print("staging observability provider absence verified")
        elif args.command == "preflight":
            execute_preflight(args.manifest)
            print("staging cleanup state is empty or manifest-bound")
        else:
            manifest, manifest_raw = _read_private(args.manifest, "cleanup manifest")
            journal, journal_raw = _read_private(
                args.acceptance_journal, "acceptance journal"
            )
            validate_manifest(manifest)
            validate_acceptance_journal(journal)
            if (
                manifest["acceptance_journal_sha256"]
                != hashlib.sha256(journal_raw).hexdigest()
                or manifest["source_revision"] != journal["source_revision"]
                or manifest["deployable_digest"] != journal["deployable_digest"]
                or hashlib.sha256(manifest_raw).hexdigest() == ""
            ):
                raise CleanupError("acceptance journal binding mismatch")
            print("staging cleanup authority validated")
        return 0
    except CleanupError as exc:
        print(f"observability staging cleanup refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
