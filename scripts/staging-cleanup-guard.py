#!/usr/bin/env python3
"""Bind temporary staging cleanup to exact Terraform and UpCloud resources.

Operator usage is intentionally limited to the canonical Make targets::

    export UPCLOUD_TOKEN=...
    PROVIDER=upcloud ENV=ci-staging-... make staging-cleanup-manifest \
        STAGING_CLEANUP_STATE=... STAGING_CLEANUP_HOSTNAME=... \
        STAGING_CLEANUP_MANIFEST=...
    PROVIDER=upcloud ENV=ci-staging-... make staging-destroy \
        STAGING_CLEANUP_MANIFEST=... STAGING_POST_DESTROY_EVIDENCE=...

The ``UPCLOUD_USERNAME``/``UPCLOUD_PASSWORD`` and
``UPCLOUD_API_USERNAME``/``UPCLOUD_API_PASSWORD`` pairs remain supported, but
exactly one token or complete pair must come from the inherited environment.
Never pass credentials as Make command-line variables. Direct subcommands below
are internal controller interfaces; their paths must live in owned 0700
directories and their private files must be regular mode-0600 files.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import stat
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 2
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_STATE_BYTES = 64 * 1024 * 1024
MAX_API_BYTES = 64 * 1024
API_ROOT = "https://api.upcloud.com"
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,62}$")
ENV_RE = re.compile(r"^ci-staging-[A-Za-z0-9][A-Za-z0-9-]{0,47}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ACCOUNT_USERNAME_RE = re.compile(r"^[!-~]{4,64}$")
TARGET_AFTER = timedelta(hours=36)
ESCALATION_AFTER = timedelta(hours=44)
EXPIRY_AFTER = timedelta(hours=47)
OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
ALLOWED_DESTROY_ADDRESSES = {
    "terraform_data.ssh_port",
    "upcloud_server.vpn",
    "upcloud_firewall_rules.vpn",
}


class GuardError(ValueError):
    """A categorical cleanup refusal safe to show to an operator."""


JsonRequest = Callable[[str], tuple[int, dict[str, Any]]]


def _provider_authorization(
    environment: Mapping[str, str] = os.environ,
) -> str:
    primary = (
        environment.get("UPCLOUD_USERNAME", ""),
        environment.get("UPCLOUD_PASSWORD", ""),
    )
    alias = (
        environment.get("UPCLOUD_API_USERNAME", ""),
        environment.get("UPCLOUD_API_PASSWORD", ""),
    )
    primary_complete = all(primary)
    alias_complete = all(alias)
    bearer = environment.get("UPCLOUD_TOKEN", "")
    bearer_valid = bool(re.fullmatch(r"[!-~]{16,4096}", bearer))
    if (
        sum((primary_complete, alias_complete, bearer_valid)) != 1
        or any(primary) != primary_complete
        or any(alias) != alias_complete
        or (bool(bearer) != bearer_valid)
    ):
        raise GuardError(
            "provider authentication requires one valid UpCloud credential mode"
        )
    if bearer_valid:
        return f"Bearer {bearer}"
    username, password = primary if primary_complete else alias
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {encoded}"


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _parse_time(value: str | datetime, label: str) -> datetime:
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


def _format_time(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _open_private_parent(
    path: Path, label: str, *, exact_mode: bool = True
) -> tuple[int, str]:
    if not path.is_absolute() or path.name in ("", ".", ".."):
        raise GuardError(f"{label} path is not an absolute file path")
    if not hasattr(os, "O_NOFOLLOW") or not OPEN_SUPPORTS_DIR_FD:
        raise GuardError(f"{label} platform lacks no-follow directory traversal")
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        directory_fd = os.open(path.anchor, flags)
    except OSError as exc:
        raise GuardError(f"{label} ancestor path is unavailable") from exc
    try:
        for component in path.parent.parts[1:]:
            try:
                next_fd = os.open(component, flags, dir_fd=directory_fd)
            except OSError as exc:
                raise GuardError(
                    f"{label} ancestor path is missing, non-directory, or symlink"
                ) from exc
            os.close(directory_fd)
            directory_fd = next_fd
        info = os.fstat(directory_fd)
        if not stat.S_ISDIR(info.st_mode):
            raise GuardError(f"{label} parent is not a directory")
    except BaseException:
        os.close(directory_fd)
        raise
    if info.st_uid != os.getuid():
        os.close(directory_fd)
        raise GuardError(f"{label} parent owner is not current user")
    mode = stat.S_IMODE(info.st_mode)
    if exact_mode and mode != 0o700:
        os.close(directory_fd)
        raise GuardError(f"{label} parent mode must be 0700")
    if not exact_mode and mode & 0o022:
        os.close(directory_fd)
        raise GuardError(f"{label} parent is writable by group or others")
    return directory_fd, path.name


def _private_read(
    path: Path,
    label: str,
    *,
    max_bytes: int,
    exact_parent_mode: bool = True,
) -> bytes:
    parent_fd, name = _open_private_parent(path, label, exact_mode=exact_parent_mode)
    try:
        try:
            info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise GuardError(f"{label} is missing") from exc
        if stat.S_ISLNK(info.st_mode):
            raise GuardError(f"{label} is a symlink")
        if not stat.S_ISREG(info.st_mode):
            raise GuardError(f"{label} is not a regular file")
        if info.st_uid != os.getuid():
            raise GuardError(f"{label} owner is not current user")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise GuardError(f"{label} mode must be 0600")
        if info.st_size > max_bytes:
            raise GuardError(f"{label} exceeds size limit")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(name, flags, dir_fd=parent_fd)
        opened = os.fstat(fd)
        try:
            if opened.st_dev != info.st_dev or opened.st_ino != info.st_ino:
                raise GuardError(f"{label} changed while opening")
            if opened.st_uid != os.getuid() or stat.S_IMODE(opened.st_mode) != 0o600:
                raise GuardError(f"{label} ownership or mode changed while opening")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > max_bytes:
                raise GuardError(f"{label} exceeds size limit")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _private_snapshot(
    path: Path,
    label: str,
    *,
    max_bytes: int,
    exact_parent_mode: bool = True,
) -> tuple[bytes, tuple[int, int]]:
    parent_fd, name = _open_private_parent(
        path.absolute(), label, exact_mode=exact_parent_mode
    )
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW
        try:
            info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise GuardError(f"{label} is unavailable") from exc
        try:
            opened = os.fstat(fd)
            if (
                opened.st_dev != info.st_dev
                or opened.st_ino != info.st_ino
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
            ):
                raise GuardError(f"{label} changed while opening")
            if opened.st_size > max_bytes:
                raise GuardError(f"{label} exceeds size limit")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > max_bytes:
                raise GuardError(f"{label} exceeds size limit")
            return data, (opened.st_dev, opened.st_ino)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _unlink_matching_entry(
    parent_fd: int, name: str, expected: os.stat_result, label: str
) -> None:
    tombstone = f".{name}.release-{secrets.token_hex(16)}"
    try:
        os.rename(
            name,
            tombstone,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
    except OSError as exc:
        raise GuardError(f"{label} changed before release") from exc
    try:
        moved = os.stat(tombstone, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise GuardError(f"{label} release requires manual recovery") from exc
    if moved.st_dev != expected.st_dev or moved.st_ino != expected.st_ino:
        try:
            os.link(
                tombstone,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.unlink(tombstone, dir_fd=parent_fd)
        except OSError as exc:
            raise GuardError(f"{label} changed and requires manual recovery") from exc
        raise GuardError(f"{label} changed before release")
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise GuardError(f"{label} release requires manual recovery") from exc
    else:
        raise GuardError(f"{label} changed and requires manual recovery")
    try:
        os.unlink(tombstone, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError as exc:
        raise GuardError(f"{label} release requires manual recovery") from exc


def _private_write_new(path: Path, data: bytes, label: str) -> tuple[int, int]:
    parent_fd, name = _open_private_parent(path, label)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise GuardError(f"{label} already exists") from exc
        except OSError as exc:
            raise GuardError(f"{label} could not be created privately") from exc
        identity: tuple[int, int]
        try:
            try:
                os.fchmod(fd, 0o600)
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise GuardError(f"{label} write failed")
                    view = view[written:]
                os.fsync(fd)
                opened = os.fstat(fd)
                identity = (opened.st_dev, opened.st_ino)
            except BaseException:
                try:
                    _unlink_matching_entry(parent_fd, name, os.fstat(fd), label)
                except GuardError as exc:
                    raise GuardError(
                        f"{label} write failed and cleanup requires manual recovery"
                    ) from exc
                raise
        finally:
            os.close(fd)
        os.fsync(parent_fd)
        return identity
    finally:
        os.close(parent_fd)


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise GuardError(f"{label} must be a JSON object")
    return value


def _state_resources(state_value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if state_value.get("version") != 4 or not isinstance(
        state_value.get("resources"), list
    ):
        raise GuardError("state schema is invalid")
    indexed: dict[str, dict[str, Any]] = {}
    for resource in state_value["resources"]:
        if not isinstance(resource, dict) or resource.get("mode") != "managed":
            raise GuardError("state contains an invalid managed resource")
        if "module" in resource:
            raise GuardError("state contains a foreign module resource")
        resource_type = resource.get("type")
        resource_name = resource.get("name")
        if not isinstance(resource_type, str) or not isinstance(resource_name, str):
            raise GuardError("state contains an invalid resource address")
        address = f"{resource_type}.{resource_name}"
        instances = resource.get("instances")
        if (
            address in indexed
            or not isinstance(instances, list)
            or len(instances) != 1
            or not isinstance(instances[0], dict)
            or "index_key" in instances[0]
        ):
            raise GuardError("state contains an ambiguous resource instance")
        attributes = instances[0].get("attributes")
        if not isinstance(attributes, dict):
            raise GuardError("state resource attributes are invalid")
        indexed[address] = attributes
    if set(indexed) != ALLOWED_DESTROY_ADDRESSES:
        raise GuardError("state contains a foreign resource")
    return indexed


def _uuid(value: Any, label: str) -> str:
    if not isinstance(value, str) or not UUID_RE.fullmatch(value):
        raise GuardError(f"{label} is not a UUID")
    return value


def _validate_network_interfaces(server: dict[str, Any]) -> None:
    interfaces = server.get("network_interface")
    if not isinstance(interfaces, list) or not all(
        isinstance(interface, dict) for interface in interfaces
    ):
        raise GuardError("state server network interfaces are invalid")
    kinds: list[tuple[Any, Any]] = []
    for interface in interfaces:
        if interface.get("additional_ip_address") not in (None, []):
            raise GuardError(
                "state enables an additional IP outside exact cleanup scope"
            )
        kinds.append((interface.get("type"), interface.get("ip_address_family")))
    public_ipv4 = kinds.count(("public", "IPv4"))
    public_ipv6 = kinds.count(("public", "IPv6"))
    utility = sum(
        interface_type == "utility" and family in (None, "IPv4")
        for interface_type, family in kinds
    )
    if (
        public_ipv4 != 1
        or public_ipv6 > 1
        or utility != 1
        or len(kinds) != public_ipv4 + public_ipv6 + utility
    ):
        raise GuardError("state server network interfaces exceed exact cleanup scope")


def _extract_state_identity(
    state_value: dict[str, Any], hostname: str
) -> tuple[str, str]:
    resources = _state_resources(state_value)
    server = resources["upcloud_server.vpn"]
    server_uuid = _uuid(server.get("id"), "server UUID")
    if server.get("hostname") != hostname:
        raise GuardError("state hostname does not match expected hostname")
    _validate_network_interfaces(server)
    template = server.get("template")
    if (
        not isinstance(template, list)
        or len(template) != 1
        or not isinstance(template[0], dict)
    ):
        raise GuardError("state root storage is ambiguous")
    if template[0].get("backup_rule") not in (None, []) or server.get(
        "simple_backup"
    ) not in (None, []):
        raise GuardError("state enables provider backups outside exact cleanup scope")
    storage_uuid = _uuid(template[0].get("id"), "root storage UUID")
    firewall = resources["upcloud_firewall_rules.vpn"]
    if firewall.get("server_id") != server_uuid:
        raise GuardError("state firewall belongs to a foreign server")
    if firewall.get("id") not in (None, server_uuid):
        raise GuardError("state firewall ID belongs to a foreign server")
    return server_uuid, storage_uuid


def _authenticated_account_username(request_json: JsonRequest) -> str:
    status, payload = request_json("/1.3/account")
    account = payload.get("account")
    username = account.get("username") if isinstance(account, dict) else None
    if (
        status != 200
        or not isinstance(username, str)
        or not ACCOUNT_USERNAME_RE.fullmatch(username)
    ):
        raise GuardError("provider account identity could not be verified")
    return username


def _authenticated_server_created(
    request_json: JsonRequest,
    *,
    server_uuid: str,
    hostname: str,
    now: datetime,
) -> datetime:
    status, payload = request_json(f"/1.3/server/{server_uuid}")
    server = payload.get("server")
    created_value = server.get("created") if isinstance(server, dict) else None
    if (
        status != 200
        or not isinstance(server, dict)
        or server.get("uuid") != server_uuid
        or server.get("hostname") != hostname
        or isinstance(created_value, bool)
        or not isinstance(created_value, int)
        or created_value <= 0
    ):
        raise GuardError("provider server identity or creation time is invalid")
    try:
        created = datetime.fromtimestamp(created_value, timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise GuardError(
            "provider server identity or creation time is invalid"
        ) from exc
    if created > now + timedelta(minutes=5):
        raise GuardError("provider server identity or creation time is invalid")
    return created.replace(microsecond=0)


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
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    if provider != "upcloud":
        raise GuardError("staging cleanup currently supports only upcloud")
    if not ENV_RE.fullmatch(environment) or workspace != environment:
        raise GuardError("environment and workspace must be the same ci-staging name")
    if not NAME_RE.fullmatch(hostname):
        raise GuardError("hostname is invalid")
    state_path = state_path.absolute()
    state_bytes = _private_read(
        state_path,
        "state",
        max_bytes=MAX_STATE_BYTES,
        exact_parent_mode=False,
    )
    state_value = _json_object(state_bytes, "state")
    server_uuid, storage_uuid = _extract_state_identity(state_value, hostname)
    provider_account_username = _authenticated_account_username(request_json)
    created = _authenticated_server_created(
        request_json,
        server_uuid=server_uuid,
        hostname=hostname,
        now=current,
    )
    target = created + TARGET_AFTER
    escalation = created + ESCALATION_AFTER
    expiry = created + EXPIRY_AFTER
    completion = _parse_time(
        (
            clock()
            if clock is not None
            else (current if now is not None else datetime.now(timezone.utc))
        ),
        "current time",
    )
    if completion >= expiry:
        raise GuardError("cleanup manifest is expired")
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "environment": environment,
        "workspace": workspace,
        "state": {
            "path": str(state_path),
            "sha256": hashlib.sha256(state_bytes).hexdigest(),
        },
        "hostname": hostname,
        "provider_account_username": provider_account_username,
        "server_uuid": server_uuid,
        "root_storage_uuid": storage_uuid,
        "created_at": _format_time(created),
        "target_at": _format_time(target),
        "escalation_at": _format_time(escalation),
        "expiry_at": _format_time(expiry),
    }
    _private_write_new(output_path.absolute(), canonical_json(manifest), "manifest")
    return manifest


def _validate_manifest_shape(
    manifest: dict[str, Any], *, now: datetime, allow_expired: bool = False
) -> None:
    expected = {
        "schema_version",
        "provider",
        "environment",
        "workspace",
        "state",
        "hostname",
        "provider_account_username",
        "server_uuid",
        "root_storage_uuid",
        "created_at",
        "target_at",
        "escalation_at",
        "expiry_at",
    }
    if set(manifest) != expected or manifest.get("schema_version") != SCHEMA_VERSION:
        raise GuardError("manifest schema is invalid")
    if manifest.get("provider") != "upcloud":
        raise GuardError("manifest provider is unsupported")
    environment = manifest.get("environment")
    if not isinstance(environment, str) or not ENV_RE.fullmatch(environment):
        raise GuardError("manifest environment is invalid")
    if manifest.get("workspace") != environment:
        raise GuardError("manifest workspace does not match environment")
    hostname = manifest.get("hostname")
    if not isinstance(hostname, str) or not NAME_RE.fullmatch(hostname):
        raise GuardError("manifest hostname is invalid")
    account_username = manifest.get("provider_account_username")
    if not isinstance(account_username, str) or not ACCOUNT_USERNAME_RE.fullmatch(
        account_username
    ):
        raise GuardError("manifest provider account identity is invalid")
    _uuid(manifest.get("server_uuid"), "manifest server UUID")
    _uuid(manifest.get("root_storage_uuid"), "manifest root storage UUID")
    created = _parse_time(manifest.get("created_at"), "manifest created_at")
    target = _parse_time(manifest.get("target_at"), "manifest target_at")
    escalation = _parse_time(manifest.get("escalation_at"), "manifest escalation_at")
    expiry = _parse_time(manifest.get("expiry_at"), "manifest expiry_at")
    if (
        target != created + TARGET_AFTER
        or escalation != created + ESCALATION_AFTER
        or expiry != created + EXPIRY_AFTER
    ):
        raise GuardError("manifest cleanup schedule is not canonical")
    if not allow_expired and now >= expiry:
        raise GuardError("cleanup manifest is expired")
    state_info = manifest.get("state")
    if not isinstance(state_info, dict) or set(state_info) != {"path", "sha256"}:
        raise GuardError("manifest state binding is invalid")
    state_path = state_info.get("path")
    state_digest = state_info.get("sha256")
    if not isinstance(state_path, str) or not Path(state_path).is_absolute():
        raise GuardError("manifest state path is not absolute")
    if not isinstance(state_digest, str) or not SHA256_RE.fullmatch(state_digest):
        raise GuardError("manifest state digest is invalid")


def load_manifest(
    path: Path,
    *,
    now: datetime | None = None,
    verify_state: bool = True,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
    allow_expired: bool = False,
) -> dict[str, Any]:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    raw = _private_read(path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES)
    manifest = _json_object(raw, "manifest")
    if raw != canonical_json(manifest):
        raise GuardError("manifest is not canonical JSON")
    _validate_manifest_shape(manifest, now=current, allow_expired=allow_expired)
    if expected_provider is not None and manifest["provider"] != expected_provider:
        raise GuardError("manifest provider does not match destroy target")
    if (
        expected_environment is not None
        and manifest["environment"] != expected_environment
    ):
        raise GuardError("manifest environment does not match destroy target")
    if verify_state:
        state_info = manifest["state"]
        state_bytes = _private_read(
            Path(state_info["path"]),
            "state",
            max_bytes=MAX_STATE_BYTES,
            exact_parent_mode=False,
        )
        if hashlib.sha256(state_bytes).hexdigest() != state_info["sha256"]:
            raise GuardError("state digest does not match manifest")
    return manifest


def validate_destroy_plan(
    manifest_path: Path,
    plan_path: Path,
    evidence_path: Path,
    *,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    manifest = load_manifest(
        manifest_path,
        now=current,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    _require_evidence_status(
        manifest, manifest_path, evidence_path, "reserved", now=current
    )
    plan = _json_object(
        _private_read(plan_path.absolute(), "destroy plan", max_bytes=MAX_JSON_BYTES),
        "destroy plan",
    )
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise GuardError("destroy plan lacks resource changes")
    indexed: dict[str, dict[str, Any]] = {}
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get("address"), str):
            raise GuardError("destroy plan contains an invalid change")
        address = item["address"]
        if address in indexed:
            raise GuardError("destroy plan repeats a resource")
        change = item.get("change")
        if (
            not isinstance(change, dict)
            or change.get("actions") != ["delete"]
            or change.get("after") is not None
        ):
            raise GuardError("destroy plan is not delete-only")
        indexed[address] = change
    if set(indexed) != ALLOWED_DESTROY_ADDRESSES:
        raise GuardError("destroy plan contains a foreign resource")
    server = indexed["upcloud_server.vpn"].get("before")
    if not isinstance(server, dict) or server.get("id") != manifest["server_uuid"]:
        raise GuardError("destroy plan server UUID does not match manifest")
    if server.get("hostname") != manifest["hostname"]:
        raise GuardError("destroy plan hostname does not match manifest")
    _validate_network_interfaces(server)
    template = server.get("template")
    if (
        not isinstance(template, list)
        or len(template) != 1
        or not isinstance(template[0], dict)
    ):
        raise GuardError("destroy plan root storage is ambiguous")
    if template[0].get("id") != manifest["root_storage_uuid"]:
        raise GuardError("destroy plan storage UUID does not match manifest")
    if template[0].get("backup_rule") not in (None, []) or server.get(
        "simple_backup"
    ) not in (None, []):
        raise GuardError(
            "destroy plan includes provider backups outside exact cleanup scope"
        )
    firewall = indexed["upcloud_firewall_rules.vpn"].get("before")
    if (
        not isinstance(firewall, dict)
        or firewall.get("server_id") != manifest["server_uuid"]
    ):
        raise GuardError("destroy plan firewall belongs to a foreign server")
    if firewall.get("id") not in (None, manifest["server_uuid"]):
        raise GuardError("destroy plan firewall ID belongs to a foreign server")
    return {
        "deleted_addresses": sorted(indexed),
        "root_storage_uuid": manifest["root_storage_uuid"],
        "server_uuid": manifest["server_uuid"],
    }


def _error_code(body: dict[str, Any]) -> str | None:
    error = body.get("error")
    return error.get("error_code") if isinstance(error, dict) else None


def _reserved_evidence(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "reserved",
        "provider": manifest["provider"],
        "environment": manifest["environment"],
        "provider_account_username": manifest["provider_account_username"],
        "manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
        "server_uuid": manifest["server_uuid"],
        "root_storage_uuid": manifest["root_storage_uuid"],
    }


def _reservation_with_identity(
    reserved: dict[str, Any], identity: tuple[int, int]
) -> dict[str, Any]:
    bound = dict(reserved)
    bound["reservation_device"] = identity[0]
    bound["reservation_inode"] = identity[1]
    return bound


def _reservation_identity(reserved: dict[str, Any]) -> tuple[int, int]:
    device = reserved.get("reservation_device")
    inode = reserved.get("reservation_inode")
    if (
        isinstance(device, bool)
        or not isinstance(device, int)
        or device < 0
        or isinstance(inode, bool)
        or not isinstance(inode, int)
        or inode <= 0
    ):
        raise GuardError("provider evidence reservation identity is invalid")
    return device, inode


def _write_reservation(evidence_path: Path, reserved: dict[str, Any]) -> dict[str, Any]:
    identity = _private_write_new(
        evidence_path.absolute(), canonical_json(reserved), "provider evidence"
    )
    bound = _reservation_with_identity(reserved, identity)
    _rewrite_reserved_evidence(
        evidence_path, reserved, bound, expected_identity=identity
    )
    return bound


def _require_evidence_status(
    manifest: dict[str, Any],
    manifest_path: Path,
    evidence_path: Path,
    status: str,
    *,
    now: datetime,
) -> dict[str, Any]:
    raw, identity = _private_snapshot(
        evidence_path.absolute(),
        "provider evidence reservation",
        max_bytes=MAX_JSON_BYTES,
    )
    evidence = _json_object(raw, "provider evidence reservation")
    expected = _reservation_with_identity(_reserved_evidence(manifest), identity)
    if status == "reserved":
        if evidence != expected:
            raise GuardError("provider evidence reservation does not match manifest")
        return evidence
    if status == "apply_started":
        common = dict(evidence)
        started_at = common.pop("apply_started_at", None)
        if common.get("status") != "apply_started":
            raise GuardError("provider evidence does not prove apply start")
        common["status"] = "reserved"
        if common != expected:
            raise GuardError("provider evidence does not match manifest")
        started = _parse_time(started_at, "apply_started_at")
        expiry = _parse_time(manifest["expiry_at"], "manifest expiry_at")
        if started >= expiry:
            raise GuardError("provider evidence apply start missed cleanup deadline")
        if started > now:
            raise GuardError("provider evidence apply start is in the future")
        return evidence
    raise GuardError("provider evidence status is unsupported")


def reserve_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(
        manifest_path,
        now=now,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    return _write_reservation(evidence_path, _reserved_evidence(manifest))


def authorize_reserve_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    request_json: JsonRequest,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    manifest_path = manifest_path.absolute()
    before, before_identity = _private_snapshot(
        manifest_path, "manifest", max_bytes=MAX_JSON_BYTES
    )
    manifest = load_manifest(
        manifest_path,
        now=current,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    state_path = Path(manifest["state"]["path"])
    state_bytes, state_identity = _private_snapshot(
        state_path,
        "state",
        max_bytes=MAX_STATE_BYTES,
        exact_parent_mode=False,
    )
    _require_account_matches(manifest, request_json)
    after, after_identity = _private_snapshot(
        manifest_path, "manifest", max_bytes=MAX_JSON_BYTES
    )
    confirmed_state, confirmed_state_identity = _private_snapshot(
        state_path,
        "state",
        max_bytes=MAX_STATE_BYTES,
        exact_parent_mode=False,
    )
    if (
        after != before
        or after_identity != before_identity
        or confirmed_state != state_bytes
        or confirmed_state_identity != state_identity
    ):
        raise GuardError("manifest changed during provider authorization")
    confirmed = load_manifest(
        manifest_path,
        now=current,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    if confirmed != manifest:
        raise GuardError("manifest changed during provider authorization")
    completion = _parse_time(
        (
            clock()
            if clock is not None
            else (current if now is not None else datetime.now(timezone.utc))
        ),
        "current time",
    )
    if completion >= _parse_time(manifest["expiry_at"], "manifest expiry_at"):
        raise GuardError("cleanup manifest is expired")
    return _write_reservation(evidence_path, _reserved_evidence(manifest))


def release_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
) -> None:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    manifest = load_manifest(
        manifest_path,
        now=current,
        allow_expired=True,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    reserved = _require_evidence_status(
        manifest, manifest_path, evidence_path, "reserved", now=current
    )
    expected = canonical_json(reserved)
    expected_identity = _reservation_identity(reserved)
    path = evidence_path.absolute()
    parent_fd, name = _open_private_parent(path, "provider evidence reservation")
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise GuardError("provider evidence reservation is unavailable") from exc
        try:
            opened = os.fstat(fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
            ):
                raise GuardError(
                    "provider evidence reservation ownership or mode changed"
                )
            if (opened.st_dev, opened.st_ino) != expected_identity:
                raise GuardError("provider evidence reservation identity changed")
            actual = os.read(fd, len(expected) + 1)
            if actual != expected:
                raise GuardError(
                    "provider evidence reservation does not match manifest"
                )
            _unlink_matching_entry(
                parent_fd, name, opened, "provider evidence reservation"
            )
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def rewind_plan_fd(fd: int) -> None:
    if fd < 3:
        raise GuardError("plan descriptor is invalid")
    try:
        opened = os.fstat(fd)
    except OSError as exc:
        raise GuardError("plan descriptor is unavailable") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o600
    ):
        raise GuardError("plan descriptor is not a private owned regular file")
    try:
        os.lseek(fd, 0, os.SEEK_SET)
    except OSError as exc:
        raise GuardError("plan descriptor is not seekable") from exc


def _rewrite_reserved_evidence(
    path: Path,
    reserved: dict[str, Any],
    evidence: dict[str, Any],
    *,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    path = path.absolute()
    parent_fd, name = _open_private_parent(path, "provider evidence")
    flags = os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise GuardError("provider evidence reservation is unavailable") from exc
        try:
            opened = os.fstat(fd)
            bound_identity = expected_identity or _reservation_identity(reserved)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
            ):
                raise GuardError(
                    "provider evidence reservation ownership or mode changed while opening"
                )
            if (opened.st_dev, opened.st_ino) != bound_identity:
                raise GuardError("provider evidence reservation identity changed")
            expected = canonical_json(reserved)
            actual = os.read(fd, len(expected) + 1)
            if actual != expected:
                raise GuardError("provider evidence reservation content changed")
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if current.st_dev != opened.st_dev or current.st_ino != opened.st_ino:
                raise GuardError("provider evidence reservation changed while opening")
            final = canonical_json(evidence)
            os.lseek(fd, 0, os.SEEK_SET)
            view = memoryview(final)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise GuardError("provider evidence write failed")
                view = view[written:]
            os.ftruncate(fd, len(final))
            os.fsync(fd)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if current.st_dev != opened.st_dev or current.st_ino != opened.st_ino:
                raise GuardError("provider evidence path changed during verified write")
            os.fsync(parent_fd)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _require_account_matches(
    manifest: dict[str, Any], request_json: JsonRequest
) -> None:
    authenticated_username = _authenticated_account_username(request_json)
    if not hmac.compare_digest(
        authenticated_username.encode("ascii"),
        manifest["provider_account_username"].encode("ascii"),
    ):
        raise GuardError("provider account identity does not match manifest")


def verify_upcloud_account(
    manifest_path: Path,
    *,
    request_json: JsonRequest,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
) -> None:
    manifest = load_manifest(
        manifest_path,
        now=now,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    _require_account_matches(manifest, request_json)


def mark_apply_started(
    manifest_path: Path,
    evidence_path: Path,
    *,
    request_json: JsonRequest,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    manifest_path = manifest_path.absolute()
    before, before_identity = _private_snapshot(
        manifest_path, "manifest", max_bytes=MAX_JSON_BYTES
    )
    manifest = load_manifest(
        manifest_path,
        now=current,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    state_path = Path(manifest["state"]["path"])
    state_bytes, state_identity = _private_snapshot(
        state_path,
        "state",
        max_bytes=MAX_STATE_BYTES,
        exact_parent_mode=False,
    )
    reserved = _require_evidence_status(
        manifest, manifest_path, evidence_path, "reserved", now=current
    )
    _require_account_matches(manifest, request_json)
    after, after_identity = _private_snapshot(
        manifest_path, "manifest", max_bytes=MAX_JSON_BYTES
    )
    confirmed_state, confirmed_state_identity = _private_snapshot(
        state_path,
        "state",
        max_bytes=MAX_STATE_BYTES,
        exact_parent_mode=False,
    )
    if (
        after != before
        or after_identity != before_identity
        or confirmed_state != state_bytes
        or confirmed_state_identity != state_identity
    ):
        raise GuardError("manifest changed during pre-apply authorization")
    confirmed = load_manifest(
        manifest_path,
        now=current,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    if confirmed != manifest:
        raise GuardError("manifest changed during pre-apply authorization")
    confirmed_reservation = _require_evidence_status(
        manifest, manifest_path, evidence_path, "reserved", now=current
    )
    if confirmed_reservation != reserved:
        raise GuardError("provider evidence reservation changed during authorization")
    after_authorization = _parse_time(
        (
            clock()
            if clock is not None
            else (current if now is not None else datetime.now(timezone.utc))
        ),
        "current time",
    )
    if after_authorization >= _parse_time(manifest["expiry_at"], "manifest expiry_at"):
        raise GuardError("cleanup manifest is expired")
    started = dict(reserved)
    started["status"] = "apply_started"
    started["apply_started_at"] = _format_time(after_authorization)
    _rewrite_reserved_evidence(evidence_path, reserved, started)
    return started


def verify_upcloud_absence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    request_json: JsonRequest,
    observed_at: str | datetime | None = None,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    initial = _parse_time(now or datetime.now(timezone.utc), "current time")
    manifest = load_manifest(
        manifest_path,
        now=initial,
        verify_state=False,
        allow_expired=True,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    started = _require_evidence_status(
        manifest, manifest_path, evidence_path, "apply_started", now=initial
    )
    _require_account_matches(manifest, request_json)
    server_status, server = request_json(f"/1.3/server/{manifest['server_uuid']}")
    if server_status == 200:
        raise GuardError("server still exists")
    if server_status != 404 or _error_code(server) != "SERVER_NOT_FOUND":
        raise GuardError("server absence is ambiguous")
    storage_status, storage = request_json(
        f"/1.3/storage/{manifest['root_storage_uuid']}"
    )
    if storage_status == 200:
        raise GuardError("storage still exists")
    if storage_status != 404 or _error_code(storage) != "STORAGE_NOT_FOUND":
        raise GuardError("storage absence is ambiguous")
    observed = _parse_time(
        (
            clock()
            if clock is not None
            else (
                observed_at if observed_at is not None else datetime.now(timezone.utc)
            )
        ),
        "observed_at",
    )
    expiry = _parse_time(manifest["expiry_at"], "manifest expiry_at")
    expired = observed >= expiry
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "verified_after_expiry" if expired else "verified",
        "deadline_status": "expired_after_apply" if expired else "within_deadline",
        "provider": "upcloud",
        "environment": manifest["environment"],
        "provider_account_username": manifest["provider_account_username"],
        "manifest_sha256": started["manifest_sha256"],
        "apply_started_at": started["apply_started_at"],
        "expiry_at": manifest["expiry_at"],
        "observed_at": _format_time(observed),
        "server_uuid": manifest["server_uuid"],
        "root_storage_uuid": manifest["root_storage_uuid"],
        "server_status": "absent",
        "root_storage_status": "absent",
        "billing_status": "no-active-owned-resources",
    }
    _rewrite_reserved_evidence(evidence_path, started, evidence)
    return evidence


def _upcloud_request(authorization: str, *, timeout: float = 15.0) -> JsonRequest:
    context = ssl.create_default_context()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
        ) -> None:
            return None

    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        NoRedirect(),
    )

    def request(path: str) -> tuple[int, dict[str, Any]]:
        if not path.startswith("/1.3/") or "?" in path or "#" in path:
            raise GuardError("provider request path is invalid")
        req = urllib.request.Request(
            API_ROOT + path,
            headers={"Authorization": authorization, "Accept": "application/json"},
            method="GET",
        )
        try:
            response = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError) as exc:
            raise GuardError("provider request failed") from exc
        try:
            status = int(response.status)
            body = response.read(MAX_API_BYTES + 1)
        finally:
            response.close()
        if len(body) > MAX_API_BYTES:
            raise GuardError("provider response exceeds size limit")
        return status, _json_object(body, "provider response")

    return request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-manifest")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--provider", required=True)
    create.add_argument("--environment", required=True)
    create.add_argument("--workspace", required=True)
    create.add_argument("--state", type=Path, required=True)
    create.add_argument("--hostname", required=True)
    check = sub.add_parser("validate-manifest")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--expected-provider", required=True)
    check.add_argument("--expected-environment", required=True)
    authorize = sub.add_parser("authorize-reserve-evidence")
    authorize.add_argument("--manifest", type=Path, required=True)
    authorize.add_argument("--evidence-output", type=Path, required=True)
    authorize.add_argument("--expected-provider", required=True)
    authorize.add_argument("--expected-environment", required=True)
    release = sub.add_parser("release-evidence")
    release.add_argument("--manifest", type=Path, required=True)
    release.add_argument("--evidence-output", type=Path, required=True)
    release.add_argument("--expected-provider", required=True)
    release.add_argument("--expected-environment", required=True)
    account = sub.add_parser("verify-upcloud-account")
    account.add_argument("--manifest", type=Path, required=True)
    account.add_argument("--expected-provider", required=True)
    account.add_argument("--expected-environment", required=True)
    rewind = sub.add_parser("rewind-plan-fd")
    rewind.add_argument("--fd-number", type=int, required=True)
    plan = sub.add_parser("validate-plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--plan-view", type=Path, required=True)
    plan.add_argument("--evidence-output", type=Path, required=True)
    plan.add_argument("--expected-provider", required=True)
    plan.add_argument("--expected-environment", required=True)
    verify = sub.add_parser("verify-upcloud-absence")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--evidence-output", type=Path, required=True)
    verify.add_argument("--expected-provider", required=True)
    verify.add_argument("--expected-environment", required=True)
    started = sub.add_parser("mark-apply-started")
    started.add_argument("--manifest", type=Path, required=True)
    started.add_argument("--evidence-output", type=Path, required=True)
    started.add_argument("--expected-provider", required=True)
    started.add_argument("--expected-environment", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.command == "create-manifest":
        authorization = _provider_authorization()
        create_manifest(
            output_path=args.output,
            provider=args.provider,
            environment=args.environment,
            workspace=args.workspace,
            state_path=args.state,
            hostname=args.hostname,
            request_json=_upcloud_request(authorization),
        )
        print("staging cleanup manifest created")
        return 0
    if args.command == "validate-plan":
        validate_destroy_plan(
            args.manifest,
            args.plan_view,
            args.evidence_output,
            now=now,
            expected_provider=args.expected_provider,
            expected_environment=args.expected_environment,
        )
        print("staging destroy plan validated")
        return 0
    if args.command == "validate-manifest":
        load_manifest(
            args.manifest,
            now=now,
            expected_provider=args.expected_provider,
            expected_environment=args.expected_environment,
        )
        print("staging cleanup manifest validated")
        return 0
    if args.command == "release-evidence":
        release_evidence(
            args.manifest,
            args.evidence_output,
            now=now,
            expected_provider=args.expected_provider,
            expected_environment=args.expected_environment,
        )
        print("staging provider evidence reservation released")
        return 0
    if args.command == "rewind-plan-fd":
        rewind_plan_fd(args.fd_number)
        return 0
    authorization = _provider_authorization()
    if args.command == "authorize-reserve-evidence":
        authorize_reserve_evidence(
            args.manifest,
            args.evidence_output,
            request_json=_upcloud_request(authorization),
            expected_provider=args.expected_provider,
            expected_environment=args.expected_environment,
        )
        print("staging provider authorization reserved")
        return 0
    if args.command == "mark-apply-started":
        mark_apply_started(
            args.manifest,
            args.evidence_output,
            request_json=_upcloud_request(authorization),
            expected_provider=args.expected_provider,
            expected_environment=args.expected_environment,
        )
        print("staging provider apply start recorded")
        return 0
    if args.command == "verify-upcloud-account":
        verify_upcloud_account(
            args.manifest,
            request_json=_upcloud_request(authorization),
            now=now,
            expected_provider=args.expected_provider,
            expected_environment=args.expected_environment,
        )
        print("staging provider account verified")
        return 0
    verify_upcloud_absence(
        args.manifest,
        args.evidence_output,
        request_json=_upcloud_request(authorization),
        expected_provider=args.expected_provider,
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
