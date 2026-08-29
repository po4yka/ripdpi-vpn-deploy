#!/usr/bin/env python3
"""Bind temporary staging cleanup to exact Terraform and UpCloud resources."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import ssl
import stat
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
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
ALLOWED_DESTROY_ADDRESSES = {
    "terraform_data.ssh_port",
    "upcloud_server.vpn",
    "upcloud_firewall_rules.vpn",
}


class GuardError(ValueError):
    """A categorical cleanup refusal safe to show to an operator."""


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


def _private_directory(path: Path, label: str, *, exact_mode: bool = True) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise GuardError(f"{label} directory is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise GuardError(f"{label} directory is not a real directory")
    if info.st_uid != os.getuid():
        raise GuardError(f"{label} directory owner is not current user")
    mode = stat.S_IMODE(info.st_mode)
    if exact_mode and mode != 0o700:
        raise GuardError(f"{label} directory mode must be 0700")
    if not exact_mode and mode & 0o022:
        raise GuardError(f"{label} directory is writable by group or others")


def _private_read(
    path: Path,
    label: str,
    *,
    max_bytes: int,
    exact_parent_mode: bool = True,
) -> bytes:
    _private_directory(path.parent, f"{label} parent", exact_mode=exact_parent_mode)
    try:
        info = path.lstat()
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
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
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


def _private_write_new(path: Path, data: bytes, label: str) -> None:
    _private_directory(path.parent, label)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise GuardError(f"{label} already exists") from exc
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise GuardError(f"{label} write failed")
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(fd)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


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


def create_manifest(
    *,
    output_path: Path,
    provider: str,
    environment: str,
    workspace: str,
    state_path: Path,
    hostname: str,
    created_at: str | datetime,
    expiry_at: str | datetime,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    created = _parse_time(created_at, "created_at")
    expiry = _parse_time(expiry_at, "expiry_at")
    if provider != "upcloud":
        raise GuardError("staging cleanup currently supports only upcloud")
    if not ENV_RE.fullmatch(environment) or workspace != environment:
        raise GuardError("environment and workspace must be the same ci-staging name")
    if not NAME_RE.fullmatch(hostname):
        raise GuardError("hostname is invalid")
    if created > current + timedelta(minutes=5):
        raise GuardError("created_at is in the future")
    if expiry <= created or expiry - created > timedelta(hours=48):
        raise GuardError("cleanup expiry must be within 48 hours of creation")
    if current > expiry:
        raise GuardError("cleanup manifest is expired")
    state_path = state_path.absolute()
    state_bytes = _private_read(
        state_path,
        "state",
        max_bytes=MAX_STATE_BYTES,
        exact_parent_mode=False,
    )
    state_value = _json_object(state_bytes, "state")
    server_uuid, storage_uuid = _extract_state_identity(state_value, hostname)
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
        "server_uuid": server_uuid,
        "root_storage_uuid": storage_uuid,
        "created_at": _format_time(created),
        "expiry_at": _format_time(expiry),
    }
    _private_write_new(output_path.absolute(), canonical_json(manifest), "manifest")
    return manifest


def _validate_manifest_shape(manifest: dict[str, Any], *, now: datetime) -> None:
    expected = {
        "schema_version",
        "provider",
        "environment",
        "workspace",
        "state",
        "hostname",
        "server_uuid",
        "root_storage_uuid",
        "created_at",
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
    _uuid(manifest.get("server_uuid"), "manifest server UUID")
    _uuid(manifest.get("root_storage_uuid"), "manifest root storage UUID")
    created = _parse_time(manifest.get("created_at"), "manifest created_at")
    expiry = _parse_time(manifest.get("expiry_at"), "manifest expiry_at")
    if expiry <= created or expiry - created > timedelta(hours=48):
        raise GuardError("manifest expiry exceeds 48 hours")
    if now > expiry:
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
) -> dict[str, Any]:
    current = _parse_time(now or datetime.now(timezone.utc), "current time")
    raw = _private_read(path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES)
    manifest = _json_object(raw, "manifest")
    if raw != canonical_json(manifest):
        raise GuardError("manifest is not canonical JSON")
    _validate_manifest_shape(manifest, now=current)
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


JsonRequest = Callable[[str], tuple[int, dict[str, Any]]]


def _error_code(body: dict[str, Any]) -> str | None:
    error = body.get("error")
    return error.get("error_code") if isinstance(error, dict) else None


def _manifest_digest(manifest_path: Path) -> str:
    return hashlib.sha256(
        _private_read(manifest_path.absolute(), "manifest", max_bytes=MAX_JSON_BYTES)
    ).hexdigest()


def _reserved_evidence(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "reserved",
        "provider": manifest["provider"],
        "environment": manifest["environment"],
        "manifest_sha256": _manifest_digest(manifest_path),
        "server_uuid": manifest["server_uuid"],
        "root_storage_uuid": manifest["root_storage_uuid"],
    }


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
    reserved = _reserved_evidence(manifest, manifest_path)
    _private_write_new(
        evidence_path.absolute(), canonical_json(reserved), "provider evidence"
    )
    return reserved


def release_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
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
    expected = canonical_json(_reserved_evidence(manifest, manifest_path))
    actual = _private_read(
        evidence_path.absolute(),
        "provider evidence reservation",
        max_bytes=MAX_JSON_BYTES,
    )
    if actual != expected:
        raise GuardError("provider evidence reservation does not match manifest")
    path = evidence_path.absolute()
    before = path.lstat()
    parent_fd = os.open(path.parent, os.O_RDONLY)
    try:
        current = path.lstat()
        if current.st_dev != before.st_dev or current.st_ino != before.st_ino:
            raise GuardError("provider evidence reservation changed before release")
        path.unlink()
        os.fsync(parent_fd)
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
    path: Path, reserved: dict[str, Any], evidence: dict[str, Any]
) -> None:
    path = path.absolute()
    _private_directory(path.parent, "provider evidence")
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise GuardError("provider evidence reservation is missing") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise GuardError("provider evidence reservation is not a regular file")
    if before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600:
        raise GuardError("provider evidence reservation ownership or mode changed")
    flags = os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if opened.st_dev != before.st_dev or opened.st_ino != before.st_ino:
            raise GuardError("provider evidence reservation changed while opening")
        if opened.st_uid != os.getuid() or stat.S_IMODE(opened.st_mode) != 0o600:
            raise GuardError(
                "provider evidence reservation ownership or mode changed while opening"
            )
        expected = canonical_json(reserved)
        actual = os.read(fd, len(expected) + 1)
        if actual != expected:
            raise GuardError("provider evidence reservation content changed")
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
    finally:
        os.close(fd)


def verify_upcloud_absence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    request_json: JsonRequest,
    observed_at: str | datetime,
    now: datetime | None = None,
    expected_provider: str | None = None,
    expected_environment: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(
        manifest_path,
        now=now,
        verify_state=False,
        expected_provider=expected_provider,
        expected_environment=expected_environment,
    )
    reserved = _reserved_evidence(manifest, manifest_path)
    reserved_bytes = _private_read(
        evidence_path.absolute(),
        "provider evidence reservation",
        max_bytes=MAX_JSON_BYTES,
    )
    if reserved_bytes != canonical_json(reserved):
        raise GuardError("provider evidence reservation does not match manifest")
    account_status, account = request_json("/1.3/account")
    if account_status != 200 or not isinstance(account.get("account"), dict):
        raise GuardError("provider authentication could not be verified")
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
    observed = _parse_time(observed_at, "observed_at")
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "verified",
        "provider": "upcloud",
        "environment": manifest["environment"],
        "manifest_sha256": reserved["manifest_sha256"],
        "observed_at": _format_time(observed),
        "server_uuid": manifest["server_uuid"],
        "root_storage_uuid": manifest["root_storage_uuid"],
        "server_status": "absent",
        "root_storage_status": "absent",
        "billing_status": "no-active-owned-resources",
    }
    _rewrite_reserved_evidence(evidence_path, reserved, evidence)
    return evidence


def _upcloud_request(
    username: str, password: str, *, timeout: float = 15.0
) -> JsonRequest:
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
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
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
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
    create.add_argument("--created-at", required=True)
    create.add_argument("--expiry-at", required=True)
    check = sub.add_parser("validate-manifest")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--expected-provider", required=True)
    check.add_argument("--expected-environment", required=True)
    reserve = sub.add_parser("reserve-evidence")
    reserve.add_argument("--manifest", type=Path, required=True)
    reserve.add_argument("--evidence-output", type=Path, required=True)
    reserve.add_argument("--expected-provider", required=True)
    reserve.add_argument("--expected-environment", required=True)
    release = sub.add_parser("release-evidence")
    release.add_argument("--manifest", type=Path, required=True)
    release.add_argument("--evidence-output", type=Path, required=True)
    release.add_argument("--expected-provider", required=True)
    release.add_argument("--expected-environment", required=True)
    rewind = sub.add_parser("rewind-plan-fd")
    rewind.add_argument("--fd-number", type=int, required=True)
    plan = sub.add_parser("validate-plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--plan-view", type=Path, required=True)
    plan.add_argument("--expected-provider", required=True)
    plan.add_argument("--expected-environment", required=True)
    verify = sub.add_parser("verify-upcloud-absence")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--evidence-output", type=Path, required=True)
    verify.add_argument("--expected-provider", required=True)
    verify.add_argument("--expected-environment", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.command == "create-manifest":
        create_manifest(
            output_path=args.output,
            provider=args.provider,
            environment=args.environment,
            workspace=args.workspace,
            state_path=args.state,
            hostname=args.hostname,
            created_at=args.created_at,
            expiry_at=args.expiry_at,
            now=now,
        )
        print("staging cleanup manifest created")
        return 0
    if args.command == "validate-plan":
        validate_destroy_plan(
            args.manifest,
            args.plan_view,
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
    if args.command == "reserve-evidence":
        reserve_evidence(
            args.manifest,
            args.evidence_output,
            now=now,
            expected_provider=args.expected_provider,
            expected_environment=args.expected_environment,
        )
        print("staging provider evidence reserved")
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
    username = os.environ.get("UPCLOUD_USERNAME", "")
    password = os.environ.get("UPCLOUD_PASSWORD", "")
    if not username or not password:
        raise GuardError("provider authentication is unavailable")
    verify_upcloud_absence(
        args.manifest,
        args.evidence_output,
        request_json=_upcloud_request(username, password),
        observed_at=now,
        now=now,
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
