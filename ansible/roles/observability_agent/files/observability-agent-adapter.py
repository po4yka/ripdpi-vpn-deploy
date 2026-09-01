#!/usr/bin/env python3
"""Publish a bounded, redacted schema-2 node-manifest adapter metric."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time

MAX_MANIFEST_BYTES = 64 * 1024
NODE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ENVIRONMENT = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AdapterError(RuntimeError):
    """A bounded, non-secret adapter failure."""


def _metric_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise AdapterError("invalid manifest")
        document[key] = value
    return document


def _trusted_directory_fd(
    path: Path, *, allow_shared_final_directory: bool, error: str
) -> int:
    if not path.is_absolute():
        raise AdapterError(error)
    accepted_owners = {0, os.geteuid()}
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open("/", flags)
    try:
        components = path.parts[1:]
        for index, component in enumerate(components):
            metadata = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            shared_final_directory = (
                allow_shared_final_directory
                and index == len(components) - 1
                and bool(metadata.st_mode & stat.S_IWGRP)
                and bool(metadata.st_mode & stat.S_ISGID)
                and bool(metadata.st_mode & stat.S_ISVTX)
                and metadata.st_gid in {os.getegid(), *os.getgroups()}
            )
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid not in accepted_owners
                or metadata.st_mode & stat.S_IWOTH
                or (metadata.st_mode & stat.S_IWGRP and not shared_final_directory)
            ):
                raise AdapterError(error)
            child = os.open(component, flags, dir_fd=descriptor)
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise AdapterError(error)
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _trusted_parent_fd(path: Path) -> int:
    return _trusted_directory_fd(
        path, allow_shared_final_directory=False, error="unsafe manifest"
    )


def _validate_existing_output(parent_fd: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid not in {0, os.geteuid()}
        or metadata.st_nlink != 1
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise AdapterError("unsafe output")


def _require_directory_identity(descriptor: int, path: Path, error: str) -> None:
    try:
        observed = os.lstat(path)
    except OSError as exc:
        raise AdapterError(error) from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino)
    ):
        raise AdapterError(error)


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _temporary_name(name: str) -> str:
    return f".{name}.{secrets.token_hex(16)}.tmp"


def _atomic_write(path: Path, content: str) -> None:
    if path.name in {"", ".", ".."}:
        raise AdapterError("unsafe output")
    parent_fd = _trusted_directory_fd(
        path.parent,
        allow_shared_final_directory=True,
        error="unsafe output directory",
    )
    temporary: str | None = None
    descriptor = -1
    try:
        _validate_existing_output(parent_fd, path.name)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        for _attempt in range(8):
            temporary = _temporary_name(path.name)
            try:
                descriptor = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
                break
            except FileExistsError:
                temporary = None
        else:
            raise AdapterError("unsafe output")
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise AdapterError("unsafe output")
        _write_all(descriptor, content.encode("utf-8"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _require_directory_identity(parent_fd, path.parent, "unsafe output directory")
        os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = None
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _read_manifest(path: Path) -> dict[str, object]:
    parent_fd = _trusted_parent_fd(path.parent)
    descriptor = -1
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_nlink != 1
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or metadata.st_size > MAX_MANIFEST_BYTES
        ):
            raise AdapterError("unsafe manifest")
        content = bytearray()
        while len(content) <= MAX_MANIFEST_BYTES:
            chunk = os.read(
                descriptor, min(8192, MAX_MANIFEST_BYTES + 1 - len(content))
            )
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > MAX_MANIFEST_BYTES:
            raise AdapterError("unsafe manifest")
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError("invalid manifest") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)
    if not isinstance(payload, dict):
        raise AdapterError("invalid manifest")
    return payload


def _render(
    manifest: dict[str, object],
    node_id: str,
    expected_source_revision: str,
    expected_deployable_digest: str,
) -> str:
    if not NODE_ID.fullmatch(node_id):
        raise AdapterError("invalid node ID")
    if manifest.get("schema_version") != 2:
        raise AdapterError("unsupported node manifest schema")
    required = {
        "environment": ENVIRONMENT,
        "provider": PROVIDER,
        "source_revision": SHA1,
        "deployable_digest": SHA256,
    }
    for key, pattern in required.items():
        value = manifest.get(key)
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise AdapterError("invalid manifest identity")
    if not SHA1.fullmatch(expected_source_revision) or not SHA256.fullmatch(
        expected_deployable_digest
    ):
        raise AdapterError("invalid expected identity")
    identity_states = {
        "source-revision": (
            "match"
            if manifest["source_revision"] == expected_source_revision
            else "mismatch"
        ),
        "deployable-digest": (
            "match"
            if manifest["deployable_digest"] == expected_deployable_digest
            else "mismatch"
        ),
    }
    now = int(time.time())
    return "\n".join(
        [
            "# HELP vpn_observability_adapter_collection_success Whether the schema-2 manifest adapter completed.",
            "# TYPE vpn_observability_adapter_collection_success gauge",
            "vpn_observability_adapter_collection_success 1",
            "# HELP vpn_observability_adapter_collected_timestamp_seconds Unix timestamp of the completed adapter collection.",
            "# TYPE vpn_observability_adapter_collected_timestamp_seconds gauge",
            f"vpn_observability_adapter_collected_timestamp_seconds {now}",
            "# HELP vpn_observability_node_manifest_identity Bounded schema-2 source identity comparison.",
            "# TYPE vpn_observability_node_manifest_identity gauge",
            *[
                "vpn_observability_node_manifest_identity"
                f'{{node="{_metric_label(node_id)}",role="{role}",state="{state}"}} 1'
                for role, state in identity_states.items()
            ],
            "",
        ]
    )


def _render_failure(collected_at: int) -> str:
    return "\n".join(
        [
            "# HELP vpn_observability_adapter_collection_success Whether the schema-2 manifest adapter completed.",
            "# TYPE vpn_observability_adapter_collection_success gauge",
            "vpn_observability_adapter_collection_success 0",
            "# HELP vpn_observability_adapter_collected_timestamp_seconds Unix timestamp of the adapter attempt.",
            "# TYPE vpn_observability_adapter_collected_timestamp_seconds gauge",
            f"vpn_observability_adapter_collected_timestamp_seconds {collected_at}",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--expected-source-revision", required=True)
    parser.add_argument("--expected-deployable-digest", required=True)
    args = parser.parse_args(argv)
    try:
        _atomic_write(
            args.output,
            _render(
                _read_manifest(args.manifest),
                args.node_id,
                args.expected_source_revision,
                args.expected_deployable_digest,
            ),
        )
    except (AdapterError, OSError) as exc:
        try:
            _atomic_write(args.output, _render_failure(int(time.time())))
        except (AdapterError, OSError):
            # A hostile or missing output directory can make even the bounded
            # failure marker impossible; preserve the original generic error.
            pass
        print(f"observability-agent-adapter: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
