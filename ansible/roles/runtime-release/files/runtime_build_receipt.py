#!/usr/bin/env python3
"""Inspect and atomically record source-build identities and installed bytes."""

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


def _atomic_write(directory: int, name: str, payload: bytes) -> None:
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
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass  # A concurrent cleanup may already have removed this private name.
        raise
    os.close(descriptor)
    try:
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except Exception:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass  # Replacement consumed the private name before the later failure.
        raise


def _record_locked(directory: int, receipt_name: str, descriptor: dict) -> dict:
    outputs, reason = _output_digests(descriptor)
    if reason is not None or outputs is None:
        raise UnsafeState(reason or "missing-output")
    payload = {**_expected_identity(descriptor), "outputs": outputs}
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
    descriptor: dict, stage_root: Path, stage_directory: int
) -> list[dict]:
    publications: list[dict] = []
    try:
        for output in descriptor["outputs"]:
            parent: int | None = None
            existing: dict | None = None
            temporary: str | None = None
            staged_relative = Path(output["staged_path"]).relative_to(
                stage_root / descriptor["name"]
            )
            staged = _open_relative_output(
                stage_directory, staged_relative, os.geteuid()
            )
            try:
                digest = _sha256_descriptor(staged)
                expected = output.get("expected_sha256")
                if expected is not None and digest != expected:
                    raise UnsafeState("output-checksum-mismatch")

                path = Path(output["path"])
                parent = _open_directory(path.parent, os.geteuid())
                try:
                    metadata = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    metadata = None
                if metadata is not None:
                    current = _open_output_at(parent, path.name, os.geteuid(), metadata)
                    existing = {
                        "inode": (metadata.st_dev, metadata.st_ino),
                        "mode": stat.S_IMODE(metadata.st_mode),
                        "descriptor": current,
                    }

                temporary = (
                    f".{path.name}.runtime-build.{os.getpid()}.{uuid.uuid4().hex}"
                )
                target = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent,
                )
                try:
                    _copy_descriptor(staged, target)
                    os.fsync(target)
                    os.fchmod(target, stat.S_IMODE(os.fstat(staged).st_mode))
                    os.fsync(target)
                except Exception:
                    os.close(target)
                    os.unlink(temporary, dir_fd=parent)
                    raise
                os.close(target)
            except Exception:
                if temporary is not None and parent is not None:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass  # Earlier cleanup may already have consumed the temp file.
                if existing is not None and existing.get("descriptor") is not None:
                    os.close(existing["descriptor"])
                    existing["descriptor"] = None
                if parent is not None:
                    os.close(parent)
                raise
            finally:
                os.close(staged)
            assert parent is not None and temporary is not None
            publications.append(
                {
                    "parent": parent,
                    "name": path.name,
                    "temporary": temporary,
                    "existing": existing,
                    "published_inode": None,
                    "backup": None,
                }
            )
        return publications
    except Exception:
        _discard_publications(publications)
        raise


def _discard_publications(
    publications: list[dict], *, preserve_backups: bool = False
) -> None:
    for item in publications:
        existing = item.get("existing")
        if existing is not None and existing.get("descriptor") is not None:
            os.close(existing["descriptor"])
            existing["descriptor"] = None
        keys = ("temporary",) if preserve_backups else ("temporary", "backup")
        removed = False
        for key in keys:
            name = item.get(key)
            if name:
                try:
                    os.unlink(name, dir_fd=item["parent"])
                    removed = True
                except FileNotFoundError:
                    pass  # The publication or rollback may already have consumed it.
        if removed:
            os.fsync(item["parent"])
        try:
            os.close(item["parent"])
        except OSError:
            pass  # Cleanup is idempotent when a prior failure closed the descriptor.


def _publish_outputs(publications: list[dict]) -> None:
    for item in publications:
        parent = item["parent"]
        name = item["name"]
        existing = item["existing"]
        try:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if existing is None:
            if current is not None:
                raise UnsafeState("output-replaced-before-publication")
        elif current is None or (current.st_dev, current.st_ino) != existing["inode"]:
            raise UnsafeState("output-replaced-before-publication")

        if existing is not None:
            backup = f".{name}.runtime-backup.{os.getpid()}.{uuid.uuid4().hex}"
            try:
                os.link(
                    name,
                    backup,
                    src_dir_fd=parent,
                    dst_dir_fd=parent,
                    follow_symlinks=False,
                )
                linked = os.stat(backup, dir_fd=parent, follow_symlinks=False)
                if (linked.st_dev, linked.st_ino) != existing["inode"]:
                    raise UnsafeState("output-replaced-before-backup")
                os.fsync(parent)
            except Exception:
                try:
                    os.unlink(backup, dir_fd=parent)
                except FileNotFoundError:
                    pass  # The failed link operation may not have created a backup.
                raise
            os.close(existing["descriptor"])
            existing["descriptor"] = None
            item["backup"] = backup

        prepared = os.stat(item["temporary"], dir_fd=parent, follow_symlinks=False)
        prepared_inode = (prepared.st_dev, prepared.st_ino)
        os.replace(item["temporary"], name, src_dir_fd=parent, dst_dir_fd=parent)
        item["temporary"] = None
        item["published_inode"] = prepared_inode
        published = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (published.st_dev, published.st_ino) != prepared_inode:
            raise UnsafeState("output-replaced-after-publication")
        os.fsync(parent)


def _rollback_publications(publications: list[dict]) -> None:
    uncertain = False
    for item in reversed(publications):
        published_inode = item.get("published_inode")
        if published_inode is None:
            continue
        parent = item["parent"]
        name = item["name"]
        try:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is None or (current.st_dev, current.st_ino) != published_inode:
            uncertain = True
            continue
        if item["backup"] is None:
            os.unlink(name, dir_fd=parent)
        else:
            os.replace(item["backup"], name, src_dir_fd=parent, dst_dir_fd=parent)
            item["backup"] = None
        os.fsync(parent)
    if uncertain:
        raise UnsafeState("publication-rollback-uncertain")


def converge(receipt_root: Path, document: object) -> dict:
    receipt_root = Path(receipt_root)
    stage_root = receipt_root.parent / "runtime-build-staging"
    descriptor = _normalize_descriptor(document, stage_root=stage_root)
    directory, receipt_name = _receipt_path(Path(receipt_root), descriptor)
    lock = _open_project_lock(directory, descriptor["name"])
    stage_directory: int | None = None
    publications: list[dict] = []
    preserve_backups = False
    previous_receipt: dict | None = None
    try:
        previous_receipt = _read_receipt(directory, receipt_name)
        current = inspect(receipt_root, document)
        if not current["rebuild_required"]:
            return {"schema_version": SCHEMA_VERSION, "changed": False}
        _stage_root, stage_directory = _prepare_stage(receipt_root, descriptor)
        _run_build_steps(descriptor)
        _require_directory_identity(_stage_root / descriptor["name"], stage_directory)
        publications = _prepare_publications(descriptor, _stage_root, stage_directory)
        try:
            _publish_outputs(publications)
            result = _record_locked(directory, receipt_name, descriptor)
        except Exception:
            try:
                _rollback_publications(publications)
            except Exception:
                preserve_backups = True
                raise
            try:
                if previous_receipt is None:
                    try:
                        os.unlink(receipt_name, dir_fd=directory)
                        os.fsync(directory)
                    except FileNotFoundError:
                        pass  # Absence is the required pre-transaction receipt state.
                else:
                    encoded = (
                        json.dumps(
                            previous_receipt, sort_keys=True, separators=(",", ":")
                        )
                        + "\n"
                    ).encode()
                    _atomic_write(directory, receipt_name, encoded)
            except Exception as error:
                raise UnsafeState("receipt-rollback-uncertain") from error
            raise
        completed_publications = publications
        publications = []
        _discard_publications(completed_publications)
        return result
    finally:
        cleanup_error: Exception | None = None
        try:
            if publications:
                _discard_publications(publications, preserve_backups=preserve_backups)
            if stage_directory is not None:
                try:
                    _remove_directory_contents(stage_directory)
                finally:
                    os.close(stage_directory)
        except Exception as error:
            cleanup_error = error
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
            os.close(directory)
        if cleanup_error is not None:
            raise cleanup_error


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
