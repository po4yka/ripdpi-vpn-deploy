#!/usr/bin/env python3
"""Inspect and transactionally publish source-build identities and installed bytes.

All authorized writers use the per-project lock. Receipt and output parents are
validated as owner-only and non-writable by group or world. A malicious process
running as the same UID (including root in production) is part of the trusted
computing base: portable POSIX does not provide compare-and-unlink by inode.
Detectable pathname substitutions still fail closed and retain recovery evidence.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

SCHEMA_VERSION = 1
MAX_RECEIPT_BYTES = 64 * 1024
MAX_JOURNAL_BYTES = 256 * 1024
LOCK_TIMEOUT_SECONDS = 300.0
LOCK_POLL_SECONDS = 0.1
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


class UnsafeState(RuntimeError):
    """The receipt namespace or document cannot be trusted."""


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _file_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


def _validate_directory(stat_result: os.stat_result, uid: int, *, leaf: bool) -> None:
    if not stat.S_ISDIR(stat_result.st_mode):
        raise UnsafeState("unsafe-directory")
    if stat_result.st_uid not in ({uid} if leaf else {0, uid}):
        raise UnsafeState("unsafe-directory-owner")
    if stat_result.st_mode & 0o022:
        raise UnsafeState("unsafe-directory-mode")


def _open_directory(path: Path, uid: int) -> int:
    if not path.is_absolute() or path == Path("/"):
        raise UnsafeState("invalid-directory-path")
    parts = path.parts[1:]
    descriptor = os.open("/", _directory_flags())
    try:
        for index, component in enumerate(parts):
            if component in {"", ".", ".."}:
                raise UnsafeState("invalid-directory-component")
            try:
                child = os.open(component, _directory_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                raise
            except OSError as error:
                raise UnsafeState("unsafe-directory-component") from error
            try:
                metadata = os.fstat(child)
                _validate_directory(metadata, uid, leaf=index == len(parts) - 1)
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_output(path: Path, uid: int) -> int:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise UnsafeState("invalid-output-path")
    parent = _open_directory(path.parent, uid)
    try:
        return _open_output_at(parent, path.name, uid)
    finally:
        os.close(parent)


def _open_output_at(
    parent: int,
    name: str,
    uid: int,
    expected: os.stat_result | None = None,
) -> int:
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=parent)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise UnsafeState("unsafe-output") from error
    metadata = os.fstat(descriptor)
    if expected is not None and (metadata.st_dev, metadata.st_ino) != (
        expected.st_dev,
        expected.st_ino,
    ):
        os.close(descriptor)
        raise UnsafeState("output-replaced")
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise UnsafeState("unsafe-output-type")
    if metadata.st_uid != uid or metadata.st_nlink != 1:
        os.close(descriptor)
        raise UnsafeState("unsafe-output-owner")
    if metadata.st_mode & 0o022 or not metadata.st_mode & 0o111:
        os.close(descriptor)
        raise UnsafeState("unsafe-output-mode")
    return descriptor


def _open_relative_output(root: int, relative: Path, uid: int) -> int:
    if relative.is_absolute() or relative.name in {"", ".", ".."}:
        raise UnsafeState("invalid-staged-output-path")
    parts = relative.parts
    directory = os.dup(root)
    try:
        for component in parts[:-1]:
            if component in {"", ".", ".."}:
                raise UnsafeState("invalid-staged-output-path")
            try:
                child = os.open(component, _directory_flags(), dir_fd=directory)
            except OSError as error:
                raise UnsafeState("unsafe-stage-entry") from error
            metadata = os.fstat(child)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != uid
                or metadata.st_mode & 0o022
            ):
                os.close(child)
                raise UnsafeState("unsafe-stage-entry")
            os.close(directory)
            directory = child
        return _open_output_at(directory, parts[-1], uid)
    finally:
        os.close(directory)


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: Path) -> str:
    descriptor = _open_output(Path(path), os.geteuid())
    try:
        return _sha256_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _normalize_source(value: object, *, depth: int = 0) -> object:
    if depth > 8:
        raise UnsafeState("source-identity-too-deep")
    if isinstance(value, dict):
        if not value or len(value) > 32:
            raise UnsafeState("invalid-source-identity")
        normalized: dict[str, object] = {}
        for key in sorted(value):
            if not isinstance(key, str) or SOURCE_KEY_RE.fullmatch(key) is None:
                raise UnsafeState("invalid-source-key")
            normalized[key] = _normalize_source(value[key], depth=depth + 1)
        return normalized
    if isinstance(value, list):
        if not value or len(value) > 32:
            raise UnsafeState("invalid-source-list")
        return [_normalize_source(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        if not value or len(value) > 4096 or "\0" in value:
            raise UnsafeState("invalid-source-value")
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and -(2**63) <= value < 2**63:
        return value
    raise UnsafeState("invalid-source-value")


def _canonical_json(value: object) -> bytes:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise UnsafeState("oversize-descriptor")
    return encoded


def _normalize_steps(value: object) -> list[dict]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise UnsafeState("invalid-build-steps")
    normalized: list[dict] = []
    for step in value:
        if not isinstance(step, dict) or set(step) != {
            "argv",
            "chdir",
            "environment",
            "timeout_seconds",
        }:
            raise UnsafeState("invalid-build-step")
        argv = step["argv"]
        chdir = step["chdir"]
        environment = step["environment"]
        timeout_seconds = step["timeout_seconds"]
        if (
            not isinstance(argv, list)
            or not argv
            or len(argv) > 32
            or any(
                not isinstance(argument, str)
                or not argument
                or len(argument) > 4096
                or "\0" in argument
                for argument in argv
            )
        ):
            raise UnsafeState("invalid-build-argv")
        executable = Path(argv[0])
        if (
            not executable.is_absolute()
            or str(executable) != argv[0]
            or ".." in executable.parts
        ):
            raise UnsafeState("invalid-build-executable")
        if not isinstance(chdir, str) or not Path(chdir).is_absolute():
            raise UnsafeState("invalid-build-directory")
        parsed_chdir = Path(chdir)
        if str(parsed_chdir) != chdir or ".." in parsed_chdir.parts:
            raise UnsafeState("invalid-build-directory")
        if not isinstance(environment, dict) or len(environment) > 32:
            raise UnsafeState("invalid-build-environment")
        normalized_environment: dict[str, str] = {}
        for key in sorted(environment):
            env_value = environment[key]
            if (
                not isinstance(key, str)
                or ENV_KEY_RE.fullmatch(key) is None
                or not isinstance(env_value, str)
                or len(env_value) > 4096
                or "\0" in env_value
            ):
                raise UnsafeState("invalid-build-environment")
            normalized_environment[key] = env_value
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= 1800
        ):
            raise UnsafeState("invalid-build-timeout")
        normalized.append(
            {
                "argv": list(argv),
                "chdir": chdir,
                "environment": normalized_environment,
                "timeout_seconds": timeout_seconds,
            }
        )
    return normalized


def recipe_sha256(steps: object) -> str:
    return hashlib.sha256(_canonical_json(_normalize_steps(steps))).hexdigest()


def _normalize_descriptor(document: object, *, stage_root: Path | None = None) -> dict:
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "name",
        "source",
        "steps",
        "outputs",
    }:
        raise UnsafeState("invalid-descriptor")
    if document["schema_version"] != SCHEMA_VERSION:
        raise UnsafeState("invalid-descriptor-version")
    name = document["name"]
    outputs = document["outputs"]
    if not isinstance(name, str) or NAME_RE.fullmatch(name) is None:
        raise UnsafeState("invalid-descriptor-name")
    source = _normalize_source(document["source"])
    steps = _normalize_steps(document["steps"])
    if not isinstance(outputs, list) or not outputs or len(outputs) > 16:
        raise UnsafeState("invalid-outputs")

    normalized_outputs: list[dict[str, str]] = []
    names: set[str] = set()
    staged_paths: set[str] = set()
    paths: set[str] = set()
    for output in outputs:
        if not isinstance(output, dict) or set(output) not in (
            {"name", "staged_path", "path"},
            {"name", "staged_path", "path", "expected_sha256"},
        ):
            raise UnsafeState("invalid-output")
        output_name = output["name"]
        staged_path = output["staged_path"]
        output_path = output["path"]
        expected_sha256 = output.get("expected_sha256")
        if not isinstance(output_name, str) or NAME_RE.fullmatch(output_name) is None:
            raise UnsafeState("invalid-output-name")
        if (
            not isinstance(staged_path, str)
            or not Path(staged_path).is_absolute()
            or not isinstance(output_path, str)
            or not Path(output_path).is_absolute()
        ):
            raise UnsafeState("invalid-output-path")
        parsed_staged = Path(staged_path)
        parsed_path = Path(output_path)
        canonical_staged = str(parsed_staged)
        canonical = str(parsed_path)
        if (
            canonical_staged != staged_path
            or canonical != output_path
            or ".." in parsed_staged.parts
            or ".." in parsed_path.parts
            or output_name in names
            or canonical_staged in staged_paths
            or canonical in paths
            or canonical_staged == canonical
        ):
            raise UnsafeState("ambiguous-output")
        if stage_root is not None:
            expected_parent = stage_root / name
            try:
                parsed_staged.relative_to(expected_parent)
            except ValueError as error:
                raise UnsafeState("invalid-staged-output-path") from error
            if parsed_staged == expected_parent:
                raise UnsafeState("invalid-staged-output-path")
        if expected_sha256 is not None and (
            not isinstance(expected_sha256, str)
            or SHA256_RE.fullmatch(expected_sha256) is None
        ):
            raise UnsafeState("invalid-expected-output-checksum")
        names.add(output_name)
        staged_paths.add(canonical_staged)
        paths.add(canonical)
        normalized_output = {
            "name": output_name,
            "staged_path": canonical_staged,
            "path": canonical,
        }
        if expected_sha256 is not None:
            normalized_output["expected_sha256"] = expected_sha256
        normalized_outputs.append(normalized_output)

    return {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "source": source,
        "steps": steps,
        "recipe_sha256": recipe_sha256(steps),
        "outputs": normalized_outputs,
    }


def validate(document: object, stage_root: Path | None = None) -> dict:
    """Validate a descriptor without inspecting or mutating host state."""
    _normalize_descriptor(document, stage_root=stage_root)
    return {"schema_version": SCHEMA_VERSION, "valid": True}


def _receipt_path(root: Path, descriptor: dict) -> tuple[int, str]:
    directory = _open_directory(root, os.geteuid())
    return directory, f"{descriptor['name']}.json"


def _read_receipt(directory: int, name: str) -> dict | None:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o644
        or metadata.st_size > MAX_RECEIPT_BYTES
    ):
        raise UnsafeState("unsafe-receipt")
    descriptor = os.open(name, _file_flags(), dir_fd=directory)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise UnsafeState("receipt-replaced")
        raw = bytearray()
        while len(raw) <= MAX_RECEIPT_BYTES:
            chunk = os.read(descriptor, min(8192, MAX_RECEIPT_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > MAX_RECEIPT_BYTES:
            raise UnsafeState("oversize-receipt")
    finally:
        os.close(descriptor)
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnsafeState("invalid-receipt") from error
    if not isinstance(document, dict):
        raise UnsafeState("invalid-receipt")
    return document


def _expected_identity(descriptor: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": descriptor["name"],
        "source": descriptor["source"],
        "recipe_sha256": descriptor["recipe_sha256"],
        "outputs": [
            {key: value for key, value in output.items() if key != "staged_path"}
            for output in descriptor["outputs"]
        ],
    }


def _receipt_matches_descriptor(receipt: dict, descriptor: dict) -> bool:
    return {
        **receipt,
        "outputs": [
            {key: value for key, value in output.items() if key != "sha256"}
            for output in receipt["outputs"]
        ],
    } == _expected_identity(descriptor)


def _output_digests(descriptor: dict) -> tuple[list[dict[str, str]] | None, str | None]:
    outputs: list[dict[str, str]] = []
    for output in descriptor["outputs"]:
        try:
            digest = sha256_path(Path(output["path"]))
        except FileNotFoundError:
            return None, "missing-output"
        expected_sha256 = output.get("expected_sha256")
        if expected_sha256 is not None and digest != expected_sha256:
            raise UnsafeState("output-checksum-mismatch")
        outputs.append(
            {
                **{key: value for key, value in output.items() if key != "staged_path"},
                "sha256": digest,
            }
        )
    return outputs, None


def inspect(receipt_root: Path, document: object) -> dict:
    receipt_root = Path(receipt_root)
    descriptor = _normalize_descriptor(
        document, stage_root=receipt_root.parent / "runtime-build-staging"
    )
    directory, receipt_name = _receipt_path(Path(receipt_root), descriptor)
    try:
        receipt = _read_receipt(directory, receipt_name)
    finally:
        os.close(directory)
    if receipt is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "rebuild_required": True,
            "reason": "missing-receipt",
        }

    if set(receipt) != set(_expected_identity(descriptor)):
        raise UnsafeState("invalid-receipt-shape")
    receipt_outputs = receipt.get("outputs")
    if not isinstance(receipt_outputs, list) or any(
        not isinstance(output, dict)
        or set(output)
        not in (
            {"name", "path", "sha256"},
            {"name", "path", "expected_sha256", "sha256"},
        )
        or not isinstance(output.get("sha256"), str)
        or SHA256_RE.fullmatch(output["sha256"]) is None
        or (
            "expected_sha256" in output
            and (
                not isinstance(output["expected_sha256"], str)
                or SHA256_RE.fullmatch(output["expected_sha256"]) is None
            )
        )
        for output in receipt_outputs
    ):
        raise UnsafeState("invalid-receipt-outputs")
    receipt_identity = {
        **receipt,
        "outputs": [
            {key: value for key, value in output.items() if key != "sha256"}
            for output in receipt_outputs
        ],
    }
    if receipt_identity != _expected_identity(descriptor):
        return {
            "schema_version": SCHEMA_VERSION,
            "rebuild_required": True,
            "reason": "inputs-changed",
        }

    outputs, reason = _output_digests(descriptor)
    if reason is not None:
        return {
            "schema_version": SCHEMA_VERSION,
            "rebuild_required": True,
            "reason": reason,
        }
    if receipt_outputs != outputs:
        return {
            "schema_version": SCHEMA_VERSION,
            "rebuild_required": True,
            "reason": "output-drift",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "rebuild_required": False,
        "reason": "current",
    }


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("receipt-write-incomplete")
        view = view[written:]


def _atomic_write(
    directory: int,
    name: str,
    payload: bytes,
    *,
    mode: int = 0o644,
    publication: dict | None = None,
) -> None:
    temporary = f".{name}.{os.getpid()}.{uuid.uuid4().hex}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=directory,
    )
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass  # A concurrent cleanup may already have removed this private name.
        raise
    published = os.fstat(descriptor)
    os.close(descriptor)
    try:
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        if publication is not None:
            publication["inode"] = (published.st_dev, published.st_ino)
        os.fsync(directory)
    except Exception:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass  # Replacement consumed the private name before the later failure.
        raise


def _receipt_payload(descriptor: dict) -> dict:
    outputs, reason = _output_digests(descriptor)
    if reason is not None or outputs is None:
        raise UnsafeState(reason or "missing-output")
    return {**_expected_identity(descriptor), "outputs": outputs}


def _record_locked(directory: int, receipt_name: str, descriptor: dict) -> dict:
    payload = _receipt_payload(descriptor)
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise UnsafeState("oversize-receipt")
    current = _read_receipt(directory, receipt_name)
    if current == payload:
        return {"schema_version": SCHEMA_VERSION, "changed": False}
    _atomic_write(directory, receipt_name, encoded)
    return {"schema_version": SCHEMA_VERSION, "changed": True}


def _transaction_journal_name(project: str) -> str:
    return f".{project}.transaction.json"


def _file_identity(descriptor: int) -> dict:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise UnsafeState("unsafe-transaction-file")
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = _sha256_descriptor(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "mode": stat.S_IMODE(metadata.st_mode),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "links": metadata.st_nlink,
        "sha256": digest,
    }


def _read_identity_at(directory: int, name: str) -> dict | None:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise UnsafeState("unsafe-transaction-file")
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=directory)
    except OSError as error:
        raise UnsafeState("unsafe-transaction-file") from error
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise UnsafeState("transaction-file-replaced")
        return _file_identity(descriptor)
    finally:
        os.close(descriptor)


def _identity_matches(actual: dict | None, expected: dict, *, inode: bool) -> bool:
    if actual is None:
        return False
    expected_inode = expected.get("inode")
    if inode:
        if isinstance(expected_inode, list):
            if [actual.get("device"), actual.get("inode")] != expected_inode:
                return False
        elif actual.get("device") != expected.get("device") or actual.get(
            "inode"
        ) != expected.get("inode"):
            return False
    return all(
        actual.get(key) == expected.get(key)
        for key in ("mode", "sha256")
        if key in expected
    ) and all(
        actual.get(key) == expected.get(key)
        for key in ("uid", "gid")
        if key in expected
    )


def _validate_journal_file_identity(value: object) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != {"inode", "sha256", "mode"}
        or not isinstance(value["inode"], list)
        or len(value["inode"]) != 2
        or any(not isinstance(item, int) or item < 0 for item in value["inode"])
        or not isinstance(value["sha256"], str)
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or not isinstance(value["mode"], int)
        or isinstance(value["mode"], bool)
        or not 0 <= value["mode"] <= 0o7777
    ):
        raise UnsafeState("invalid-transaction-identity")
    return value


def _validate_journal_receipt(
    value: object, project: str, *, nullable: bool
) -> dict | None:
    if value is None and nullable:
        return None
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "name",
        "source",
        "recipe_sha256",
        "outputs",
    }:
        raise UnsafeState("invalid-transaction-receipt")
    if (
        value["schema_version"] != SCHEMA_VERSION
        or value["name"] != project
        or _normalize_source(value["source"]) != value["source"]
        or not isinstance(value["recipe_sha256"], str)
        or SHA256_RE.fullmatch(value["recipe_sha256"]) is None
        or not isinstance(value["outputs"], list)
        or not 1 <= len(value["outputs"]) <= 16
    ):
        raise UnsafeState("invalid-transaction-receipt")
    names: set[str] = set()
    paths: set[str] = set()
    for output in value["outputs"]:
        if (
            not isinstance(output, dict)
            or set(output)
            not in (
                {"name", "path", "sha256"},
                {"name", "path", "expected_sha256", "sha256"},
            )
            or not isinstance(output.get("name"), str)
            or NAME_RE.fullmatch(output["name"]) is None
            or output["name"] in names
            or not isinstance(output.get("path"), str)
            or not Path(output["path"]).is_absolute()
            or str(Path(output["path"])) != output["path"]
            or output["path"] in paths
            or not isinstance(output.get("sha256"), str)
            or SHA256_RE.fullmatch(output["sha256"]) is None
            or (
                "expected_sha256" in output
                and (
                    not isinstance(output["expected_sha256"], str)
                    or SHA256_RE.fullmatch(output["expected_sha256"]) is None
                )
            )
        ):
            raise UnsafeState("invalid-transaction-receipt")
        names.add(output["name"])
        paths.add(output["path"])
    return value


def _validate_transaction_journal(document: object) -> dict:
    if not isinstance(document, dict) or set(document) != {
        "journal_schema_version",
        "transaction_id",
        "project",
        "previous_receipt",
        "next_receipt",
        "outputs",
    }:
        raise UnsafeState("invalid-transaction-journal")
    project = document["project"]
    transaction_id = document["transaction_id"]
    if (
        document["journal_schema_version"] != 1
        or not isinstance(project, str)
        or NAME_RE.fullmatch(project) is None
        or not isinstance(transaction_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None
    ):
        raise UnsafeState("invalid-transaction-journal")
    _validate_journal_receipt(document["previous_receipt"], project, nullable=True)
    next_receipt = _validate_journal_receipt(
        document["next_receipt"], project, nullable=False
    )
    outputs = document["outputs"]
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= 16:
        raise UnsafeState("invalid-transaction-journal")
    if [
        (item.get("name"), item.get("path"))
        for item in outputs
        if isinstance(item, dict)
    ] != [(item["name"], item["path"]) for item in next_receipt["outputs"]]:
        raise UnsafeState("invalid-transaction-journal")
    for output, receipt_output in zip(outputs, next_receipt["outputs"], strict=True):
        if not isinstance(output, dict) or set(output) != {
            "name",
            "path",
            "before",
            "after",
        }:
            raise UnsafeState("invalid-transaction-journal")
        path = output["path"]
        name = output["name"]
        before = output["before"]
        after = output["after"]
        if (
            not isinstance(name, str)
            or NAME_RE.fullmatch(name) is None
            or not isinstance(path, str)
            or not Path(path).is_absolute()
            or str(Path(path)) != path
            or not isinstance(before, dict)
            or not isinstance(after, dict)
            or set(after) != {"inode", "sha256", "mode", "temporary_name"}
            or after["temporary_name"]
            != f".{Path(path).name}.runtime-build.{transaction_id}"
            or receipt_output["sha256"] != after.get("sha256")
        ):
            raise UnsafeState("invalid-transaction-journal")
        _validate_journal_file_identity(
            {key: after[key] for key in ("inode", "sha256", "mode")}
        )
        if before == {"state": "absent"}:
            continue
        if set(before) != {"state", "inode", "sha256", "mode", "backup"}:
            raise UnsafeState("invalid-transaction-journal")
        if before["state"] != "present" or not isinstance(before["backup"], dict):
            raise UnsafeState("invalid-transaction-journal")
        _validate_journal_file_identity(
            {key: before[key] for key in ("inode", "sha256", "mode")}
        )
        backup = before["backup"]
        if (
            set(backup) != {"name", "inode"}
            or backup["name"] != f".{Path(path).name}.runtime-backup.{transaction_id}"
            or backup["inode"] != before["inode"]
        ):
            raise UnsafeState("invalid-transaction-journal")
    return document


def _read_transaction_journal(
    directory: int, project: str, *, name: str | None = None
) -> tuple[dict, dict] | None:
    name = name or _transaction_journal_name(project)
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink not in {1, 2, 3}
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > MAX_JOURNAL_BYTES
    ):
        raise UnsafeState("unsafe-transaction-journal")
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=directory)
    except OSError as error:
        raise UnsafeState("unsafe-transaction-journal") from error
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise UnsafeState("transaction-journal-replaced")
        raw = bytearray()
        while len(raw) <= MAX_JOURNAL_BYTES:
            chunk = os.read(descriptor, min(8192, MAX_JOURNAL_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > MAX_JOURNAL_BYTES:
            raise UnsafeState("oversize-transaction-journal")
        identity = _file_identity(descriptor)
    finally:
        os.close(descriptor)
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnsafeState("invalid-transaction-journal") from error
    canonical = (
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    if bytes(raw) != canonical:
        raise UnsafeState("noncanonical-transaction-journal")
    journal = _validate_transaction_journal(document)
    if journal["project"] != project:
        raise UnsafeState("invalid-transaction-journal")
    return journal, identity


def _quarantine_remove(
    directory: int, name: str, expected: dict, label: str, *, missing_ok: bool
) -> bool:
    tombstone = f".{name}.quarantine"
    current = _read_identity_at(directory, name)
    quarantined = _read_identity_at(directory, tombstone)
    if current is not None and quarantined is not None:
        if not (
            _identity_matches(current, expected, inode=True)
            and _identity_matches(quarantined, expected, inode=True)
            and current["device"] == quarantined["device"]
            and current["inode"] == quarantined["inode"]
        ):
            raise UnsafeState(f"{label}-manual-recovery")
        if not _identity_matches(
            _read_identity_at(directory, name), expected, inode=True
        ):
            raise UnsafeState(f"{label}-replaced")
        os.unlink(name, dir_fd=directory)
        os.fsync(directory)
        current = None
    if current is None and quarantined is None:
        if missing_ok:
            return False
        raise UnsafeState(f"{label}-missing")
    if quarantined is None:
        if not _identity_matches(current, expected, inode=True):
            raise UnsafeState(f"{label}-replaced")
        try:
            os.link(
                name,
                tombstone,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            raise UnsafeState(f"{label}-manual-recovery") from error
        except OSError as error:
            raise UnsafeState(f"{label}-replaced") from error
        quarantined = _read_identity_at(directory, tombstone)
        if not _identity_matches(quarantined, expected, inode=True):
            raise UnsafeState(f"{label}-manual-recovery")
        if not _identity_matches(
            _read_identity_at(directory, name), expected, inode=True
        ):
            raise UnsafeState(f"{label}-replaced")
        os.unlink(name, dir_fd=directory)
        os.fsync(directory)
    if not _identity_matches(quarantined, expected, inode=True):
        raise UnsafeState(f"{label}-replaced")
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as error:
        raise UnsafeState(f"{label}-manual-recovery") from error
    else:
        raise UnsafeState(f"{label}-manual-recovery")
    try:
        if not _identity_matches(
            _read_identity_at(directory, tombstone), expected, inode=True
        ):
            raise UnsafeState(f"{label}-replaced")
        os.unlink(tombstone, dir_fd=directory)
        os.fsync(directory)
    except OSError:
        try:
            if _read_identity_at(directory, tombstone) is not None:
                os.rename(tombstone, name, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
        except OSError as restore_error:
            raise UnsafeState(f"{label}-manual-recovery") from restore_error
        raise
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError as error:
        raise UnsafeState(f"{label}-manual-recovery") from error
    raise UnsafeState(f"{label}-manual-recovery")


def _write_transaction_journal(directory: int, journal: dict) -> dict:
    encoded = (
        json.dumps(journal, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    if len(encoded) > MAX_JOURNAL_BYTES:
        raise UnsafeState("oversize-transaction-journal")
    name = _transaction_journal_name(journal["project"])
    temporary = f".{journal['project']}.transaction.{journal['transaction_id']}.new"
    descriptor: int | None = None
    identity: dict | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        identity = _file_identity(descriptor)
        os.link(
            temporary,
            name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
            follow_symlinks=False,
        )
        published = _read_identity_at(directory, name)
        if not _identity_matches(published, identity, inode=True):
            raise UnsafeState("transaction-journal-publication-replaced")
        _quarantine_remove(
            directory,
            temporary,
            identity,
            "transaction-journal-temporary",
            missing_ok=False,
        )
        os.fsync(directory)
        return identity
    except FileExistsError as error:
        if identity is not None:
            _quarantine_remove(
                directory,
                temporary,
                identity,
                "transaction-journal-temporary",
                missing_ok=True,
            )
        raise UnsafeState("transaction-journal-exists") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _open_project_lock(directory: int, project: str) -> int:
    name = f".{project}.lock"
    created = False
    try:
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        created = True
    except FileExistsError:
        try:
            descriptor = os.open(
                name,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory,
            )
        except OSError as error:
            raise UnsafeState("unsafe-build-lock") from error
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        os.close(descriptor)
        raise UnsafeState("unsafe-build-lock")
    if created:
        os.fsync(descriptor)
        os.fsync(directory)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError as error:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise UnsafeState("build-lock-timeout") from error
            time.sleep(LOCK_POLL_SECONDS)
    return descriptor


def _ensure_directory(path: Path, uid: int, mode: int) -> int:
    """Create one trusted leaf, then return its validated directory descriptor."""
    parent = _open_directory(path.parent, uid)
    try:
        try:
            os.mkdir(path.name, mode=mode, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass  # The existing leaf is opened and fully validated below.
        try:
            descriptor = os.open(path.name, _directory_flags(), dir_fd=parent)
        except OSError as error:
            raise UnsafeState("unsafe-directory-component") from error
    finally:
        os.close(parent)
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != uid
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        os.close(descriptor)
        raise UnsafeState("unsafe-directory")
    return descriptor


def _remove_directory_contents(directory: int) -> None:
    """Remove a private tree through directory descriptors without following links."""
    for entry in list(os.scandir(directory)):
        metadata = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            try:
                child = os.open(entry.name, _directory_flags(), dir_fd=directory)
            except OSError as error:
                raise UnsafeState("unsafe-stage-entry") from error
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise UnsafeState("stage-entry-replaced")
                _remove_directory_contents(child)
            finally:
                os.close(child)
            os.rmdir(entry.name, dir_fd=directory)
        else:
            os.unlink(entry.name, dir_fd=directory)
    os.fsync(directory)


def _prepare_stage(receipt_root: Path, descriptor: dict) -> tuple[Path, int]:
    stage_root = receipt_root.parent / "runtime-build-staging"
    root_descriptor = _ensure_directory(stage_root, os.geteuid(), 0o700)
    os.close(root_descriptor)
    project_path = stage_root / descriptor["name"]
    project = _ensure_directory(project_path, os.geteuid(), 0o700)
    _remove_directory_contents(project)
    return stage_root, project


def _require_directory_identity(path: Path, expected: int) -> None:
    current = _open_directory(path, os.geteuid())
    try:
        expected_metadata = os.fstat(expected)
        current_metadata = os.fstat(current)
        if (current_metadata.st_dev, current_metadata.st_ino) != (
            expected_metadata.st_dev,
            expected_metadata.st_ino,
        ):
            raise UnsafeState("stage-directory-replaced")
    finally:
        os.close(current)


def _terminate_process_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass  # Escalate the still-live process group from TERM to KILL.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired as error:
        raise UnsafeState("build-process-cleanup-failed") from error


def _retained_cwd_options(directory: int) -> dict:
    linux_path = f"/proc/self/fd/{directory}"
    if os.path.isdir(linux_path):
        return {"cwd": linux_path}
    # macOS cannot chdir to a directory descriptor through /dev/fd. This
    # child-only fallback still changes directory through the retained fd.
    return {"cwd": None, "preexec_fn": lambda: os.fchdir(directory)}


def _run_build_steps(descriptor: dict) -> None:
    for step in descriptor["steps"]:
        directory = _open_directory(Path(step["chdir"]), os.geteuid())
        environment = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            **step["environment"],
        }
        try:
            process = subprocess.Popen(
                step["argv"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                pass_fds=(directory,),
                start_new_session=True,
                **_retained_cwd_options(directory),
            )
        except OSError as error:
            os.close(directory)
            raise UnsafeState("build-step-failed") from error
        try:
            try:
                returncode = process.wait(timeout=step["timeout_seconds"])
            except subprocess.TimeoutExpired as error:
                _terminate_process_group(process)
                raise UnsafeState("build-step-failed") from error
        finally:
            os.close(directory)
        if returncode != 0:
            raise UnsafeState("build-step-failed")


def _copy_descriptor(source: int, destination: int) -> None:
    os.lseek(source, 0, os.SEEK_SET)
    while True:
        chunk = os.read(source, 1024 * 1024)
        if not chunk:
            break
        _write_all(destination, chunk)


def _prepare_publications(
    descriptor: dict,
    stage_root: Path,
    stage_directory: int,
    transaction_id: str,
) -> list[dict]:
    publications: list[dict] = []
    try:
        for output in descriptor["outputs"]:
            parent: int | None = None
            prepared: dict | None = None
            temporary = f".{Path(output['path']).name}.runtime-build.{transaction_id}"
            backup = f".{Path(output['path']).name}.runtime-backup.{transaction_id}"
            staged_relative = Path(output["staged_path"]).relative_to(
                stage_root / descriptor["name"]
            )
            staged = _open_relative_output(
                stage_directory, staged_relative, os.geteuid()
            )
            try:
                staged_identity = _file_identity(staged)
                expected = output.get("expected_sha256")
                if expected is not None and staged_identity["sha256"] != expected:
                    raise UnsafeState("output-checksum-mismatch")
                path = Path(output["path"])
                parent = _open_directory(path.parent, os.geteuid())
                try:
                    current = _read_identity_at(parent, path.name)
                    if current is not None and current["uid"] != os.geteuid():
                        raise UnsafeState("unsafe-output-owner")
                    target = os.open(
                        temporary,
                        os.O_RDWR
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                        dir_fd=parent,
                    )
                    try:
                        _copy_descriptor(staged, target)
                        os.fsync(target)
                        os.fchmod(target, staged_identity["mode"])
                        os.fsync(target)
                        prepared = _file_identity(target)
                    finally:
                        os.close(target)
                    if not _identity_matches(prepared, staged_identity, inode=False):
                        raise UnsafeState("prepared-output-mismatch")
                    os.fsync(parent)
                except Exception:
                    if prepared is not None:
                        _quarantine_remove(
                            parent,
                            temporary,
                            prepared,
                            "transaction-temporary",
                            missing_ok=True,
                        )
                    raise
            except Exception:
                if parent is not None:
                    os.close(parent)
                raise
            finally:
                os.close(staged)
            assert parent is not None
            publications.append(
                {
                    "parent": parent,
                    "output_name": output["name"],
                    "path": str(path),
                    "name": path.name,
                    "temporary": temporary,
                    "backup": backup if current is not None else None,
                    "before": current,
                    "after": prepared,
                }
            )
        return publications
    except Exception:
        _discard_publications(publications)
        raise


def _create_backups(publications: list[dict]) -> None:
    created: list[dict] = []
    try:
        for item in publications:
            before = item["before"]
            if before is None:
                continue
            parent = item["parent"]
            current = _read_identity_at(parent, item["name"])
            if not _identity_matches(current, before, inode=True):
                raise UnsafeState("output-replaced-before-backup")
            os.link(
                item["name"],
                item["backup"],
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
            backup = _read_identity_at(parent, item["backup"])
            if not _identity_matches(backup, before, inode=True):
                raise UnsafeState("output-replaced-before-backup")
            os.fsync(parent)
            created.append(item)
    except Exception:
        for item in reversed(created):
            try:
                _quarantine_remove(
                    item["parent"],
                    item["backup"],
                    item["before"],
                    "transaction-backup",
                    missing_ok=True,
                )
            except Exception:
                pass
        raise


def _planned_receipt(descriptor: dict, publications: list[dict]) -> dict:
    by_path = {item["path"]: item for item in publications}
    return {
        **_expected_identity(descriptor),
        "outputs": [
            {
                **{key: value for key, value in output.items() if key != "staged_path"},
                "sha256": by_path[output["path"]]["after"]["sha256"],
            }
            for output in descriptor["outputs"]
        ],
    }


def _transaction_journal(
    descriptor: dict,
    transaction_id: str,
    previous_receipt: dict | None,
    next_receipt: dict,
    publications: list[dict],
) -> dict:
    outputs = []
    for item in publications:
        before = item["before"]
        outputs.append(
            {
                "name": item["output_name"],
                "path": item["path"],
                "before": (
                    {"state": "absent"}
                    if before is None
                    else {
                        "state": "present",
                        "inode": [before["device"], before["inode"]],
                        "sha256": before["sha256"],
                        "mode": before["mode"],
                        "backup": {
                            "name": item["backup"],
                            "inode": [before["device"], before["inode"]],
                        },
                    }
                ),
                "after": {
                    "inode": [item["after"]["device"], item["after"]["inode"]],
                    "sha256": item["after"]["sha256"],
                    "mode": item["after"]["mode"],
                    "temporary_name": item["temporary"],
                },
            }
        )
    return {
        "journal_schema_version": 1,
        "transaction_id": transaction_id,
        "project": descriptor["name"],
        "previous_receipt": previous_receipt,
        "next_receipt": next_receipt,
        "outputs": outputs,
    }


def _discard_publications(
    publications: list[dict], *, preserve_backups: bool = False
) -> None:
    cleanup_error: Exception | None = None
    for item in publications:
        try:
            try:
                _quarantine_remove(
                    item["parent"],
                    item["temporary"],
                    item["after"],
                    "transaction-temporary",
                    missing_ok=True,
                )
            except Exception as error:
                cleanup_error = cleanup_error or error
            if not preserve_backups and item["backup"] is not None:
                try:
                    _quarantine_remove(
                        item["parent"],
                        item["backup"],
                        item["before"],
                        "transaction-backup",
                        missing_ok=True,
                    )
                except Exception as error:
                    cleanup_error = cleanup_error or error
        finally:
            try:
                os.close(item["parent"])
            except OSError as error:
                cleanup_error = cleanup_error or error
    if cleanup_error is not None:
        raise UnsafeState("publication-cleanup-incomplete") from cleanup_error


def _publish_outputs(publications: list[dict]) -> None:
    for item in publications:
        parent = item["parent"]
        current = _read_identity_at(parent, item["name"])
        before = item["before"]
        if before is None:
            if current is not None:
                raise UnsafeState("output-replaced-before-publication")
        elif not _identity_matches(current, before, inode=True):
            raise UnsafeState("output-replaced-before-publication")
        temporary = _read_identity_at(parent, item["temporary"])
        if not _identity_matches(temporary, item["after"], inode=True):
            raise UnsafeState("prepared-output-replaced")
        if before is not None:
            backup = _read_identity_at(parent, item["backup"])
            if not _identity_matches(backup, before, inode=True):
                raise UnsafeState("backup-replaced-before-publication")
        os.replace(
            item["temporary"],
            item["name"],
            src_dir_fd=parent,
            dst_dir_fd=parent,
        )
        published = _read_identity_at(parent, item["name"])
        if not _identity_matches(published, item["after"], inode=True):
            raise UnsafeState("output-replaced-after-publication")
        os.fsync(parent)


def _journal_before_identity(output: dict) -> dict | None:
    before = output["before"]
    if before["state"] == "absent":
        return None
    return {
        "device": before["inode"][0],
        "inode": before["inode"][1],
        "mode": before["mode"],
        "uid": os.geteuid(),
        "sha256": before["sha256"],
    }


def _journal_after_identity(output: dict) -> dict:
    after = output["after"]
    return {
        "device": after["inode"][0],
        "inode": after["inode"][1],
        "mode": after["mode"],
        "uid": os.geteuid(),
        "sha256": after["sha256"],
    }


def _transaction_entry(directory: int, project: str) -> tuple[dict, dict, str] | None:
    canonical_name = _transaction_journal_name(project)
    tombstone_name = f".{canonical_name}.quarantine"
    canonical = _read_transaction_journal(directory, project, name=canonical_name)
    tombstone = _read_transaction_journal(directory, project, name=tombstone_name)
    if canonical is not None and tombstone is not None:
        if canonical[0] != tombstone[0] or not _identity_matches(
            canonical[1], tombstone[1], inode=True
        ):
            raise UnsafeState("transaction-journal-ambiguous")
        selected = canonical
    elif canonical is not None:
        selected = canonical
    elif tombstone is not None:
        selected = tombstone
    else:
        return None
    journal, identity = selected
    temporary = f".{project}.transaction.{journal['transaction_id']}.new"
    temporary_tombstone = f".{temporary}.quarantine"
    known_links = 0
    for known_name in (
        canonical_name,
        tombstone_name,
        temporary,
        temporary_tombstone,
    ):
        known = _read_identity_at(directory, known_name)
        if known is None:
            continue
        if not _identity_matches(known, identity, inode=True):
            raise UnsafeState("transaction-journal-link-replaced")
        known_links += 1
    if identity["links"] != known_links:
        raise UnsafeState("unsafe-transaction-journal-links")
    if _read_identity_at(directory, temporary) is not None:
        _quarantine_remove(
            directory,
            temporary,
            identity,
            "transaction-journal-temporary",
            missing_ok=False,
        )
    return journal, identity, canonical_name


def _output_parent(output: dict) -> tuple[int, str]:
    path = Path(output["path"])
    return _open_directory(path.parent, os.geteuid()), path.name


def _preflight_precommit_output(output: dict) -> dict:
    parent, name = _output_parent(output)
    try:
        before = _journal_before_identity(output)
        after = _journal_after_identity(output)
        live = _read_identity_at(parent, name)
        temporary = _read_identity_at(parent, output["after"]["temporary_name"])
        if temporary is not None and not _identity_matches(
            temporary, after, inode=True
        ):
            raise UnsafeState("transaction-temporary-replaced")
        backup_name = None if before is None else output["before"]["backup"]["name"]
        backup = None if backup_name is None else _read_identity_at(parent, backup_name)
        if backup is not None and not _identity_matches(backup, before, inode=True):
            raise UnsafeState("transaction-backup-replaced")
        rollback_name = f"{output['after']['temporary_name']}.rollback"
        rollback = _read_identity_at(parent, rollback_name)
        if rollback is not None and not _identity_matches(rollback, after, inode=True):
            raise UnsafeState("transaction-rollback-node-replaced")
        if before is None:
            if live is None:
                state = "previous"
            elif _identity_matches(live, after, inode=True):
                state = "published"
            else:
                raise UnsafeState("transaction-live-ambiguous")
        elif _identity_matches(live, before, inode=True):
            state = "previous"
        elif _identity_matches(live, after, inode=True):
            if backup is None:
                raise UnsafeState("transaction-backup-missing")
            state = "published"
        elif live is None and rollback is not None and backup is not None:
            state = "published-quarantined"
        else:
            raise UnsafeState("transaction-live-ambiguous")
        return {
            "parent": parent,
            "name": name,
            "before": before,
            "after": after,
            "temporary_name": output["after"]["temporary_name"],
            "temporary": temporary,
            "backup": backup,
            "backup_name": backup_name,
            "rollback": rollback,
            "rollback_name": rollback_name,
            "state": state,
        }
    except Exception:
        os.close(parent)
        raise


def _preflight_committed_output(output: dict) -> dict:
    parent, name = _output_parent(output)
    try:
        before = _journal_before_identity(output)
        after = _journal_after_identity(output)
        live = _read_identity_at(parent, name)
        if not _identity_matches(live, after, inode=True):
            raise UnsafeState("committed-output-mismatch")
        temporary = _read_identity_at(parent, output["after"]["temporary_name"])
        if temporary is not None and not _identity_matches(
            temporary, after, inode=True
        ):
            raise UnsafeState("transaction-temporary-replaced")
        backup_name = None if before is None else output["before"]["backup"]["name"]
        backup = None if backup_name is None else _read_identity_at(parent, backup_name)
        if backup is not None and not _identity_matches(backup, before, inode=True):
            raise UnsafeState("transaction-backup-replaced")
        rollback_name = f"{output['after']['temporary_name']}.rollback"
        if _read_identity_at(parent, rollback_name) is not None:
            raise UnsafeState("transaction-rollback-node-ambiguous")
        return {
            "parent": parent,
            "name": name,
            "before": before,
            "after": after,
            "temporary_name": output["after"]["temporary_name"],
            "temporary": temporary,
            "backup": backup,
            "backup_name": backup_name,
        }
    except Exception:
        os.close(parent)
        raise


def _close_recovery_outputs(outputs: list[dict]) -> None:
    for output in outputs:
        try:
            os.close(output["parent"])
        except OSError:
            pass


def _rollback_output(output: dict) -> None:
    parent = output["parent"]
    name = output["name"]
    before = output["before"]
    after = output["after"]
    rollback_name = output["rollback_name"]
    live = _read_identity_at(parent, name)
    rollback = _read_identity_at(parent, rollback_name)
    if _identity_matches(live, after, inode=True):
        if rollback is not None:
            raise UnsafeState("transaction-rollback-node-ambiguous")
        os.rename(name, rollback_name, src_dir_fd=parent, dst_dir_fd=parent)
        rollback = _read_identity_at(parent, rollback_name)
        if not _identity_matches(rollback, after, inode=True):
            raise UnsafeState("transaction-rollback-node-replaced")
        if _read_identity_at(parent, name) is not None:
            raise UnsafeState("transaction-live-ambiguous")
        os.fsync(parent)
        live = None
    elif live is None and rollback is not None:
        if not _identity_matches(rollback, after, inode=True):
            raise UnsafeState("transaction-rollback-node-replaced")
    if before is not None and live is None:
        backup = _read_identity_at(parent, output["backup_name"])
        if not _identity_matches(backup, before, inode=True):
            raise UnsafeState("transaction-backup-missing")
        try:
            os.link(
                output["backup_name"],
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        except OSError as error:
            raise UnsafeState("transaction-live-ambiguous") from error
        restored = _read_identity_at(parent, name)
        if not _identity_matches(restored, before, inode=True):
            raise UnsafeState("transaction-rollback-uncertain")
        os.fsync(parent)
    if output["backup_name"] is not None:
        _quarantine_remove(
            parent,
            output["backup_name"],
            before,
            "transaction-backup",
            missing_ok=True,
        )
    _quarantine_remove(
        parent,
        output["temporary_name"],
        after,
        "transaction-temporary",
        missing_ok=True,
    )
    _quarantine_remove(
        parent,
        rollback_name,
        after,
        "transaction-rollback-node",
        missing_ok=True,
    )
    final = _read_identity_at(parent, name)
    if before is None:
        if final is not None:
            raise UnsafeState("transaction-rollback-uncertain")
    elif not _identity_matches(final, before, inode=True):
        raise UnsafeState("transaction-rollback-uncertain")


def _cleanup_committed_output(output: dict) -> None:
    parent = output["parent"]
    if output["backup_name"] is not None:
        _quarantine_remove(
            parent,
            output["backup_name"],
            output["before"],
            "transaction-backup",
            missing_ok=True,
        )
    _quarantine_remove(
        parent,
        output["temporary_name"],
        output["after"],
        "transaction-temporary",
        missing_ok=True,
    )


def _classify_committed_locked(
    directory: int, receipt_name: str, project: str, journal: dict
) -> tuple[bool, bool]:
    """Classify durable success from receipt and live bytes, never exceptions."""
    if _read_receipt(directory, receipt_name) != journal["next_receipt"]:
        return False, False
    outputs: list[dict] = []
    try:
        for item in journal["outputs"]:
            outputs.append(_preflight_committed_output(item))
    finally:
        _close_recovery_outputs(outputs)
    entry = _transaction_entry(directory, project)
    if entry is None:
        return True, False
    if entry[0] != journal:
        raise UnsafeState("cleanup-journal-receipt-ambiguous")
    return True, True


def _remove_transaction_journal(
    directory: int, project: str, source_name: str, identity: dict
) -> None:
    _quarantine_remove(
        directory,
        source_name,
        identity,
        "transaction-journal",
        missing_ok=False,
    )


def _reconcile_transaction_locked(
    directory: int, receipt_name: str, project: str
) -> tuple[str, bool, dict | None]:
    entry = _transaction_entry(directory, project)
    if entry is None:
        return "none", False, None
    journal, journal_identity, source_name = entry
    receipt = _read_receipt(directory, receipt_name)
    outputs: list[dict] = []
    if receipt == journal["next_receipt"]:
        state = "committed"
        preflight = _preflight_committed_output
    elif receipt == journal["previous_receipt"]:
        state = "precommit"
        preflight = _preflight_precommit_output
    else:
        raise UnsafeState("cleanup-journal-receipt-ambiguous")
    try:
        for item in journal["outputs"]:
            outputs.append(preflight(item))
        if state == "committed":
            for output in outputs:
                _cleanup_committed_output(output)
            if _read_receipt(directory, receipt_name) != journal["next_receipt"]:
                raise UnsafeState("cleanup-journal-receipt-ambiguous")
        else:
            for output in reversed(outputs):
                _rollback_output(output)
            if _read_receipt(directory, receipt_name) != journal["previous_receipt"]:
                raise UnsafeState("cleanup-journal-receipt-ambiguous")
        _remove_transaction_journal(directory, project, source_name, journal_identity)
        return state, False, journal["next_receipt"]
    except OSError:
        if state == "committed":
            observed, pending = _classify_committed_locked(
                directory, receipt_name, project, journal
            )
            if observed:
                return state, pending, journal["next_receipt"]
        raise
    finally:
        _close_recovery_outputs(outputs)


def _close_publication_descriptors(publications: list[dict]) -> None:
    cleanup_error: OSError | None = None
    for item in publications:
        try:
            os.close(item["parent"])
        except OSError as error:
            cleanup_error = cleanup_error or error
            try:
                os.close(item["parent"])
            except OSError:
                pass
    if cleanup_error is not None:
        raise cleanup_error


def _write_receipt_document(directory: int, receipt_name: str, receipt: dict) -> None:
    encoded = (
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise UnsafeState("oversize-receipt")
    _atomic_write(directory, receipt_name, encoded)


def converge(receipt_root: Path, document: object) -> dict:
    receipt_root = Path(receipt_root)
    stage_root = receipt_root.parent / "runtime-build-staging"
    descriptor = _normalize_descriptor(document, stage_root=stage_root)
    directory, receipt_name = _receipt_path(receipt_root, descriptor)
    lock = _open_project_lock(directory, descriptor["name"])
    stage_directory: int | None = None
    publications: list[dict] = []
    journal_active = False
    journal_identity: dict | None = None
    committed_result: dict | None = None
    try:
        recovered, cleanup_pending, recovered_receipt = _reconcile_transaction_locked(
            directory, receipt_name, descriptor["name"]
        )
        if recovered == "committed" and _receipt_matches_descriptor(
            recovered_receipt, descriptor
        ):
            return {
                "schema_version": SCHEMA_VERSION,
                "changed": True,
                **({"cleanup_pending": True} if cleanup_pending else {}),
            }
        if cleanup_pending:
            raise UnsafeState("committed-recovery-cleanup-pending")
        if recovered != "none":
            _stage_path, recovered_stage = _prepare_stage(receipt_root, descriptor)
            os.close(recovered_stage)
        previous_receipt = _read_receipt(directory, receipt_name)
        current = inspect(receipt_root, document)
        if not current["rebuild_required"]:
            return {"schema_version": SCHEMA_VERSION, "changed": False}

        stage_path, stage_directory = _prepare_stage(receipt_root, descriptor)
        _run_build_steps(descriptor)
        _require_directory_identity(stage_path / descriptor["name"], stage_directory)
        transaction_id = uuid.uuid4().hex
        publications = _prepare_publications(
            descriptor, stage_path, stage_directory, transaction_id
        )
        _create_backups(publications)
        next_receipt = _planned_receipt(descriptor, publications)
        journal = _transaction_journal(
            descriptor,
            transaction_id,
            previous_receipt,
            next_receipt,
            publications,
        )
        try:
            journal_identity = _write_transaction_journal(directory, journal)
            journal_active = True
        except BaseException as primary:
            try:
                entry = _read_transaction_journal(directory, descriptor["name"])
                journal_active = entry is not None and entry[0] == journal
            except Exception:
                journal_active = False
            if journal_active:
                _close_publication_descriptors(publications)
                publications = []
                try:
                    outcome, pending, _recovered_receipt = (
                        _reconcile_transaction_locked(
                            directory, receipt_name, descriptor["name"]
                        )
                    )
                except UnsafeState as recovery_error:
                    raise recovery_error from primary
                except Exception as recovery_error:
                    raise UnsafeState(
                        "transaction-recovery-uncertain"
                    ) from recovery_error
                if outcome == "committed":
                    return {
                        "schema_version": SCHEMA_VERSION,
                        "changed": True,
                        **({"cleanup_pending": True} if pending else {}),
                    }
            raise primary

        try:
            entry = _transaction_entry(directory, descriptor["name"])
            if (
                entry is None
                or entry[0] != journal
                or not _identity_matches(entry[1], journal_identity, inode=True)
            ):
                raise UnsafeState("transaction-journal-replaced")
            _publish_outputs(publications)
            _remove_directory_contents(stage_directory)
            _write_receipt_document(directory, receipt_name, next_receipt)
        except BaseException as primary:
            try:
                _close_publication_descriptors(publications)
            except OSError:
                pass
            publications = []
            try:
                outcome, pending, _recovered_receipt = _reconcile_transaction_locked(
                    directory, receipt_name, descriptor["name"]
                )
            except UnsafeState as recovery_error:
                raise recovery_error from primary
            except Exception as recovery_error:
                raise UnsafeState("transaction-recovery-uncertain") from recovery_error
            if outcome == "committed":
                committed_result = {
                    "schema_version": SCHEMA_VERSION,
                    "changed": True,
                    **({"cleanup_pending": True} if pending else {}),
                }
            else:
                raise primary
        else:
            try:
                _close_publication_descriptors(publications)
            except OSError:
                pass  # Receipt/live classification below is authoritative.
            publications = []
            outcome, pending, _recovered_receipt = _reconcile_transaction_locked(
                directory, receipt_name, descriptor["name"]
            )
            if outcome != "committed":
                raise UnsafeState("transaction-commit-not-observed")
            committed_result = {
                "schema_version": SCHEMA_VERSION,
                "changed": True,
                **({"cleanup_pending": True} if pending else {}),
            }
        journal_active = _transaction_entry(directory, descriptor["name"]) is not None
        assert committed_result is not None
        return committed_result
    finally:
        cleanup_error: Exception | None = None
        try:
            if publications:
                _discard_publications(publications, preserve_backups=journal_active)
            if stage_directory is not None:
                try:
                    _remove_directory_contents(stage_directory)
                finally:
                    os.close(stage_directory)
        except Exception as error:
            cleanup_error = error
        finally:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except OSError as error:
                cleanup_error = cleanup_error or error
            try:
                os.close(lock)
            except OSError as error:
                cleanup_error = cleanup_error or error
            try:
                os.close(directory)
            except OSError as error:
                cleanup_error = cleanup_error or error
        if cleanup_error is not None and committed_result is None:
            raise cleanup_error
        # Once receipt and live identities classify as committed, lock/descriptor
        # finalization errors are not durable recovery debt. cleanup_pending is
        # emitted only by the readable-WAL classifier above.


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("validate", "inspect", "converge"))
    parser.add_argument("--receipt-root", type=Path)
    parser.add_argument("--stage-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        encoded = sys.stdin.buffer.read(MAX_RECEIPT_BYTES + 1)
        if len(encoded) > MAX_RECEIPT_BYTES:
            raise UnsafeState("oversize-descriptor")
        document = json.loads(encoded)
        if args.operation == "validate":
            if args.receipt_root is not None:
                raise UnsafeState("unexpected-receipt-root")
            result = validate(document, args.stage_root)
        else:
            if args.receipt_root is None:
                raise UnsafeState("missing-receipt-root")
            expected_stage_root = args.receipt_root.parent / "runtime-build-staging"
            if args.stage_root is not None and args.stage_root != expected_stage_root:
                raise UnsafeState("unexpected-stage-root")
            result = (
                inspect(args.receipt_root, document)
                if args.operation == "inspect"
                else converge(args.receipt_root, document)
            )
    except (
        OSError,
        UnsafeState,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ):
        print("runtime build receipt refused", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
