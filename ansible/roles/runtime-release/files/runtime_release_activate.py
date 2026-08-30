#!/usr/bin/env python3
"""Serialize and compensate runtime-release symlink activation."""

from __future__ import annotations

import argparse
from enum import Enum
import fcntl
import grp
import hashlib
import json
import os
import pwd
import re
import stat
import sys
import uuid
from pathlib import Path
from typing import Callable

SAFE_NAME = re.compile(r"^[A-Za-z0-9._+-]+$")
TRANSACTION_RECEIPT = ".runtime-release-transaction.json"


class UnsafeState(RuntimeError):
    """The observed layout is outside the owned runtime-release contract."""


class ActivationFailed(RuntimeError):
    """Activation failed and the exact observed state was restored."""


class CompensationIncomplete(RuntimeError):
    """Activation failed and exact restoration could not be confirmed."""


class _PublicationOutcome(Enum):
    ALREADY_PUBLISHED = "already_published"
    RECEIPT_CREATED = "receipt_created"
    CANDIDATE_AND_RECEIPT_CREATED = "candidate_and_receipt_created"
    NEEDS_STAGED_CANDIDATE = "needs_staged_candidate"


class _DirectoryGuard:
    """A no-follow directory descriptor with its checked identity."""

    def __init__(
        self, path: Path, descriptor: int, identity: tuple[int, int, int, int, int]
    ) -> None:
        self.path = path
        self.descriptor = descriptor
        self.identity = identity

    def close(self) -> None:
        os.close(self.descriptor)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_gid,
        stat.S_IMODE(info.st_mode),
    )


def _open_directory(path: Path) -> _DirectoryGuard:
    """Open every component without following a symlink and retain the leaf fd."""
    _validate_absolute(path)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise UnsafeState("unsafe-directory")
        return _DirectoryGuard(path, descriptor, _identity(info))
    except Exception:
        os.close(descriptor)
        raise


def _validate_storage_ancestors(path: Path, uid: int, *, allow_missing: bool) -> None:
    """Require every existing path component to be owned and non-writable."""
    _validate_absolute(path)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        root_info = os.fstat(descriptor)
        if root_info.st_uid != 0 or stat.S_IMODE(root_info.st_mode) & 0o022:
            raise UnsafeState("unsafe-storage-ancestor")
        for component in path.parts[1:]:
            try:
                next_descriptor = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if allow_missing:
                    return
                raise UnsafeState("missing-storage-ancestor")
            info = os.fstat(next_descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in {0, uid}
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                os.close(next_descriptor)
                raise UnsafeState("unsafe-storage-ancestor")
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        raise UnsafeState("unsafe-storage-ancestor") from error
    finally:
        os.close(descriptor)


def _revalidate_directory(guard: _DirectoryGuard) -> None:
    """Reject a renamed/replaced parent before any namespace mutation."""
    current = os.stat(guard.path, follow_symlinks=False)
    observed = os.fstat(guard.descriptor)
    if (
        not stat.S_ISDIR(current.st_mode)
        or _identity(current) != guard.identity
        or _identity(observed) != guard.identity
    ):
        raise UnsafeState("directory-identity-changed")


def _require_directory_contract(
    guard: _DirectoryGuard, uid: int, gid: int, label: str
) -> None:
    _revalidate_directory(guard)
    info = os.fstat(guard.descriptor)
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o755:
        raise UnsafeState(f"unsafe-{label}-directory")


def _open_child_directory(parent: _DirectoryGuard, name: str) -> _DirectoryGuard:
    _revalidate_directory(parent)
    _validate_name(name)
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent.descriptor,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise UnsafeState("unsafe-directory")
        return _DirectoryGuard(parent.path / name, descriptor, _identity(info))
    except Exception:
        os.close(descriptor)
        raise


def _validate_name(value: str) -> None:
    if not SAFE_NAME.fullmatch(value) or value in {".", ".."}:
        raise UnsafeState("unsafe-name")


def _validate_digest(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise UnsafeState("unsafe-digest")


def _validate_absolute(path: Path) -> None:
    raw = str(path)
    if not path.is_absolute() or os.path.normpath(raw) != raw:
        raise UnsafeState("unsafe-path")


def _release_target(root: Path, target: str) -> str:
    path = Path(target)
    _validate_absolute(path)
    _validate_name(path.name)
    if path.parent != root / "releases":
        raise UnsafeState("unmanaged-release-target")
    return target


def _snapshot_link(
    path: Path,
    *,
    parent: _DirectoryGuard,
    root: Path,
    binary_name: str,
    public: bool = False,
) -> str | None:
    _revalidate_directory(parent)
    try:
        info = os.stat(path.name, dir_fd=parent.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISLNK(info.st_mode):
        raise UnsafeState("unmanaged-link-node")
    target = os.readlink(path.name, dir_fd=parent.descriptor)
    if public:
        expected = str(root / "current" / binary_name)
        if target != expected:
            raise UnsafeState("unmanaged-public-target")
        return target
    return _release_target(root, target)


def _link_node(
    path: Path,
    *,
    parent: _DirectoryGuard,
    root: Path,
    binary_name: str,
    public: bool,
) -> tuple[str | None, tuple[int, int, int, int, int] | None]:
    """Capture a managed link target and the exact node that supplied it."""
    _revalidate_directory(parent)
    try:
        info = os.stat(path.name, dir_fd=parent.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None, None
    if not stat.S_ISLNK(info.st_mode):
        raise UnsafeState("unmanaged-link-node")
    target = os.readlink(path.name, dir_fd=parent.descriptor)
    if public:
        expected = str(root / "current" / binary_name)
        if target != expected:
            raise UnsafeState("unmanaged-public-target")
    else:
        target = _release_target(root, target)
    return target, _identity(info)


def _revalidate_link_node(
    path: Path,
    expected: tuple[str | None, tuple[int, int, int, int, int] | None],
    *,
    parent: _DirectoryGuard,
    root: Path,
    binary_name: str,
    public: bool,
) -> None:
    """Refuse a same-parent name replacement immediately before mutation."""
    try:
        observed = _link_node(
            path,
            parent=parent,
            root=root,
            binary_name=binary_name,
            public=public,
        )
    except UnsafeState as error:
        raise UnsafeState("link-node-changed") from error
    if observed != expected:
        raise UnsafeState("link-node-changed")


def _snapshot(
    root: Path,
    public_link: Path,
    binary_name: str,
    root_directory: _DirectoryGuard,
    public_directory: _DirectoryGuard,
) -> dict[str, str | None]:
    return {
        "current": _snapshot_link(
            root / "current",
            parent=root_directory,
            root=root,
            binary_name=binary_name,
        ),
        "public": _snapshot_link(
            public_link,
            parent=public_directory,
            root=root,
            binary_name=binary_name,
            public=True,
        ),
        "previous": _snapshot_link(
            root / "previous",
            parent=root_directory,
            root=root,
            binary_name=binary_name,
        ),
    }


def _fsync_directory(directory: _DirectoryGuard) -> None:
    _revalidate_directory(directory)
    os.fsync(directory.descriptor)


def _atomic_link(
    directory: _DirectoryGuard,
    name: str,
    target: str,
    *,
    pre_replace: Callable[[], None] | None = None,
) -> None:
    _revalidate_directory(directory)
    _validate_name(name)
    temporary = f".runtime-release-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        os.symlink(target, temporary, dir_fd=directory.descriptor)
        _revalidate_directory(directory)
        if pre_replace is not None:
            pre_replace()
        os.replace(
            temporary,
            name,
            src_dir_fd=directory.descriptor,
            dst_dir_fd=directory.descriptor,
        )
        _fsync_directory(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory.descriptor)
        except FileNotFoundError:
            # A successful replace or external cleanup race consumed the temporary.
            pass


def _atomic_link_checked(
    directory: _DirectoryGuard,
    name: str,
    target: str,
    expected: tuple[str | None, tuple[int, int, int, int, int] | None],
    *,
    root: Path,
    binary_name: str,
    public: bool,
) -> None:
    """Replace a link only while the node observed by this transaction remains."""
    _atomic_link(
        directory,
        name,
        target,
        pre_replace=lambda: _revalidate_link_node(
            directory.path / name,
            expected,
            parent=directory,
            root=root,
            binary_name=binary_name,
            public=public,
        ),
    )


def _set_link_state(
    path: Path,
    target: str | None,
    *,
    parent: _DirectoryGuard,
    root: Path,
    binary_name: str,
    public: bool,
) -> None:
    expected = _link_node(
        path,
        parent=parent,
        root=root,
        binary_name=binary_name,
        public=public,
    )
    observed = expected[0]
    if observed == target:
        return
    if target is None:
        _revalidate_directory(parent)
        _revalidate_link_node(
            path,
            expected,
            parent=parent,
            root=root,
            binary_name=binary_name,
            public=public,
        )
        os.unlink(path.name, dir_fd=parent.descriptor)
        _fsync_directory(parent)
        return
    _atomic_link_checked(
        parent,
        path.name,
        target,
        expected,
        root=root,
        binary_name=binary_name,
        public=public,
    )


def _verify_desired(
    root: Path,
    public_link: Path,
    binary_name: str,
    desired: dict[str, str | None],
    root_directory: _DirectoryGuard,
    public_directory: _DirectoryGuard,
) -> None:
    if (
        _snapshot(root, public_link, binary_name, root_directory, public_directory)
        != desired
    ):
        raise OSError("postcheck-failed")


def _restore_snapshot(
    root: Path,
    public_link: Path,
    binary_name: str,
    before: dict[str, str | None],
    root_directory: _DirectoryGuard,
    public_directory: _DirectoryGuard,
) -> None:
    _set_link_state(
        root / "current",
        before["current"],
        parent=root_directory,
        root=root,
        binary_name=binary_name,
        public=False,
    )
    _set_link_state(
        public_link,
        before["public"],
        parent=public_directory,
        root=root,
        binary_name=binary_name,
        public=True,
    )
    _set_link_state(
        root / "previous",
        before["previous"],
        parent=root_directory,
        root=root,
        binary_name=binary_name,
        public=False,
    )
    if (
        _snapshot(root, public_link, binary_name, root_directory, public_directory)
        != before
    ):
        raise OSError("compensation-postcheck-failed")


def _lock_directory(root: Path, *, check: bool) -> _DirectoryGuard:
    """Lock one no-follow directory inode and retain its descriptor."""
    lock_root = root
    if not lock_root.exists() and check:
        lock_root = root.parent
        while not lock_root.exists() and lock_root != lock_root.parent:
            lock_root = lock_root.parent
    try:
        guard = _open_directory(lock_root)
    except (FileNotFoundError, NotADirectoryError, OSError) as error:
        raise UnsafeState("unsafe-install-root") from error
    try:
        fcntl.flock(guard.descriptor, fcntl.LOCK_EX)
        return guard
    except Exception:
        guard.close()
        raise


def prepare_staging(
    install_root: Path,
    staging_dir: Path,
    artifact_name: str,
    stage_name: str | None,
    candidate_name: str,
    version: str,
    artifact_sha256: str,
    artifact_type: str,
    *,
    owner: str,
    group: str,
) -> dict[str, object]:
    """Create one receipt-owned staging transaction for a single controller."""
    _validate_absolute(install_root)
    _validate_absolute(staging_dir)
    _validate_name(artifact_name)
    _validate_name(candidate_name)
    _validate_name(version)
    _validate_digest(artifact_sha256)
    if artifact_type not in {"binary", "archive"}:
        raise UnsafeState("unsafe-artifact-type")
    if staging_dir.parent != install_root:
        raise UnsafeState("unsafe-staging-directory")
    _validate_name(staging_dir.name)
    if stage_name is not None:
        _validate_name(stage_name)
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    _validate_storage_ancestors(install_root, uid, allow_missing=False)
    root = _open_directory(install_root)
    try:
        _require_directory_contract(root, uid, gid, "install-root")
        try:
            staging = _open_child_directory(root, staging_dir.name)
        except FileNotFoundError:
            created_staging = False
            try:
                os.mkdir(staging_dir.name, 0o700, dir_fd=root.descriptor)
                created_staging = True
            except FileExistsError:
                # A racing controller created the shared staging root; validate it below.
                pass
            try:
                if created_staging:
                    os.chown(
                        staging_dir.name,
                        uid,
                        gid,
                        dir_fd=root.descriptor,
                        follow_symlinks=False,
                    )
                    _fsync_directory(root)
                staging = _open_child_directory(root, staging_dir.name)
            except Exception:
                if created_staging:
                    try:
                        os.rmdir(staging_dir.name, dir_fd=root.descriptor)
                    except OSError:
                        # Retain a raced, replaced, or non-empty node for fail-closed review.
                        pass
                raise
        except OSError as error:
            raise UnsafeState("unsafe-staging-directory") from error
        try:
            _revalidate_directory(staging)
            info = os.fstat(staging.descriptor)
            if (
                info.st_uid != uid
                or info.st_gid != gid
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise UnsafeState("unsafe-staging-directory")
            transaction_name = f"transaction-{uuid.uuid4().hex}"
            os.mkdir(transaction_name, 0o700, dir_fd=staging.descriptor)
            transaction: _DirectoryGuard | None = None
            try:
                os.chown(
                    transaction_name,
                    uid,
                    gid,
                    dir_fd=staging.descriptor,
                    follow_symlinks=False,
                )
                _fsync_directory(staging)
                transaction = _open_child_directory(staging, transaction_name)
                transaction_info = os.fstat(transaction.descriptor)
                if (
                    transaction_info.st_uid != uid
                    or transaction_info.st_gid != gid
                    or stat.S_IMODE(transaction_info.st_mode) != 0o700
                ):
                    raise UnsafeState("unsafe-staging-transaction")
                payload = {
                    "schema_version": 1,
                    "transaction": transaction_name,
                    "artifact_name": artifact_name,
                    "stage_name": stage_name,
                    "candidate_name": candidate_name,
                    "version": version,
                    "artifact_sha256": artifact_sha256,
                    "artifact_type": artifact_type,
                }
                receipt = os.open(
                    TRANSACTION_RECEIPT,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=transaction.descriptor,
                )
                try:
                    os.fchmod(receipt, 0o600)
                    os.fchown(receipt, uid, gid)
                    os.write(
                        receipt,
                        (json.dumps(payload, sort_keys=True) + "\n").encode(),
                    )
                    os.fsync(receipt)
                finally:
                    os.close(receipt)
                if stage_name is not None:
                    os.mkdir(stage_name, 0o700, dir_fd=transaction.descriptor)
                    os.chown(
                        stage_name,
                        uid,
                        gid,
                        dir_fd=transaction.descriptor,
                        follow_symlinks=False,
                    )
                _fsync_directory(transaction)
                transaction_path = staging_dir / transaction_name
                return {
                    "status": "prepared",
                    "changed": False,
                    "transaction_dir": str(transaction_path),
                    "artifact_path": str(transaction_path / artifact_name),
                    "stage_dir": (
                        str(transaction_path / stage_name)
                        if stage_name is not None
                        else None
                    ),
                }
            except Exception:
                if transaction is not None:
                    for child in (stage_name, TRANSACTION_RECEIPT):
                        if child is None:
                            continue
                        try:
                            if child == stage_name:
                                os.rmdir(child, dir_fd=transaction.descriptor)
                            else:
                                os.unlink(child, dir_fd=transaction.descriptor)
                        except OSError:
                            # Preserve the primary setup failure and leave uncertain nodes.
                            pass
                    transaction.close()
                    transaction = None
                try:
                    os.rmdir(transaction_name, dir_fd=staging.descriptor)
                except OSError:
                    # A non-empty or replaced transaction is retained for recovery.
                    pass
                raise
            finally:
                if transaction is not None:
                    transaction.close()
        finally:
            staging.close()
    finally:
        root.close()


def _transaction_payload(
    transaction_name: str,
    artifact_name: str,
    stage_name: str | None,
    candidate_name: str,
    version: str,
    artifact_sha256: str,
    artifact_type: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "transaction": transaction_name,
        "artifact_name": artifact_name,
        "stage_name": stage_name,
        "candidate_name": candidate_name,
        "version": version,
        "artifact_sha256": artifact_sha256,
        "artifact_type": artifact_type,
    }


def _read_transaction_receipt(
    transaction: _DirectoryGuard, uid: int, gid: int
) -> dict[str, object]:
    descriptor = os.open(
        TRANSACTION_RECEIPT,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=transaction.descriptor,
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != uid
            or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise UnsafeState("unsafe-staging-receipt")
        raw = os.read(descriptor, 4096)
        if os.read(descriptor, 1):
            raise UnsafeState("oversize-staging-receipt")
        return json.loads(raw.decode())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnsafeState("invalid-staging-receipt") from error
    finally:
        os.close(descriptor)


def _open_transaction(
    install_root: Path,
    staging_dir: Path,
    transaction_dir: Path,
    uid: int,
    gid: int,
) -> tuple[_DirectoryGuard, _DirectoryGuard, _DirectoryGuard]:
    _validate_absolute(transaction_dir)
    if staging_dir.parent != install_root or transaction_dir.parent != staging_dir:
        raise UnsafeState("unsafe-staging-transaction")
    _validate_name(staging_dir.name)
    _validate_name(transaction_dir.name)
    _validate_storage_ancestors(transaction_dir, uid, allow_missing=False)
    root = _open_directory(install_root)
    try:
        _require_directory_contract(root, uid, gid, "install-root")
        staging = _open_child_directory(root, staging_dir.name)
        try:
            staging_info = os.fstat(staging.descriptor)
            if (
                staging_info.st_uid != uid
                or staging_info.st_gid != gid
                or stat.S_IMODE(staging_info.st_mode) != 0o700
            ):
                raise UnsafeState("unsafe-staging-directory")
            transaction = _open_child_directory(staging, transaction_dir.name)
            transaction_info = os.fstat(transaction.descriptor)
            if (
                transaction_info.st_uid != uid
                or transaction_info.st_gid != gid
                or stat.S_IMODE(transaction_info.st_mode) != 0o700
            ):
                transaction.close()
                raise UnsafeState("unsafe-staging-transaction")
            return root, staging, transaction
        except Exception:
            staging.close()
            raise
    except Exception:
        root.close()
        raise


def validate_staging_root(
    install_root: Path,
    staging_dir: Path,
    *,
    owner: str,
    group: str,
) -> dict[str, object]:
    """Validate the existing staging namespace without creating any node."""
    _validate_absolute(install_root)
    _validate_absolute(staging_dir)
    if staging_dir.parent != install_root:
        raise UnsafeState("unsafe-staging-directory")
    _validate_name(staging_dir.name)
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    _validate_storage_ancestors(install_root, uid, allow_missing=True)
    try:
        root = _open_directory(install_root)
    except FileNotFoundError:
        return {"status": "validated", "changed": False}
    try:
        _require_directory_contract(root, uid, gid, "install-root")
        try:
            staging = _open_child_directory(root, staging_dir.name)
        except FileNotFoundError:
            return {"status": "validated", "changed": False}
        except OSError as error:
            raise UnsafeState("unsafe-staging-directory") from error
        try:
            info = os.fstat(staging.descriptor)
            if (
                info.st_uid != uid
                or info.st_gid != gid
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise UnsafeState("unsafe-staging-directory")
        finally:
            staging.close()
    finally:
        root.close()
    return {"status": "validated", "changed": False}


def validate_staging(
    install_root: Path,
    staging_dir: Path,
    transaction_dir: Path,
    artifact_name: str,
    stage_name: str | None,
    candidate_name: str,
    version: str,
    artifact_sha256: str,
    artifact_type: str,
    phase: str,
    *,
    owner: str,
    group: str,
) -> dict[str, object]:
    """Revalidate a receipt-owned transaction immediately before path writes."""
    for name in (artifact_name, candidate_name, version):
        _validate_name(name)
    _validate_digest(artifact_sha256)
    if artifact_type not in {"binary", "archive"} or phase not in {
        "prepared",
        "downloaded",
    }:
        raise UnsafeState("unsafe-staging-validation")
    if stage_name is not None:
        _validate_name(stage_name)
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    root, staging, transaction = _open_transaction(
        install_root, staging_dir, transaction_dir, uid, gid
    )
    try:
        expected = _transaction_payload(
            transaction_dir.name,
            artifact_name,
            stage_name,
            candidate_name,
            version,
            artifact_sha256,
            artifact_type,
        )
        if _read_transaction_receipt(transaction, uid, gid) != expected:
            raise UnsafeState("staging-receipt-mismatch")
        allowed = {TRANSACTION_RECEIPT}
        if phase == "downloaded":
            allowed.add(artifact_name)
        if stage_name is not None:
            allowed.add(stage_name)
        if set(os.listdir(transaction.descriptor)) != allowed:
            raise UnsafeState("unexpected-staging-node")
        if stage_name is not None:
            stage = _open_child_directory(transaction, stage_name)
            try:
                stage_info = os.fstat(stage.descriptor)
                if (
                    stage_info.st_uid != uid
                    or stage_info.st_gid != gid
                    or stat.S_IMODE(stage_info.st_mode) != 0o700
                    or os.listdir(stage.descriptor)
                ):
                    raise UnsafeState("unsafe-staging-stage")
            finally:
                stage.close()
        if phase == "downloaded":
            descriptor = os.open(
                artifact_name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=transaction.descriptor,
            )
            try:
                info = os.fstat(descriptor)
                expected_mode = 0o700 if artifact_type == "binary" else 0o600
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_uid != uid
                    or info.st_gid != gid
                    or stat.S_IMODE(info.st_mode) != expected_mode
                ):
                    raise UnsafeState("unsafe-staging-artifact")
                digest = hashlib.sha256()
                while True:
                    chunk = os.read(descriptor, 128 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                if digest.hexdigest() != artifact_sha256:
                    raise UnsafeState("staging-artifact-digest-mismatch")
            finally:
                os.close(descriptor)
        return {"status": "validated", "changed": False}
    finally:
        transaction.close()
        staging.close()
        root.close()


def cleanup_staging(
    install_root: Path,
    staging_dir: Path,
    transaction_dir: Path,
    artifact_name: str,
    stage_name: str | None,
    candidate_name: str,
    version: str,
    artifact_sha256: str,
    artifact_type: str,
    *,
    owner: str,
    group: str,
) -> dict[str, object]:
    """Remove only nodes bound by one exact staging transaction receipt."""
    for name in (artifact_name, candidate_name):
        _validate_name(name)
    _validate_name(version)
    _validate_digest(artifact_sha256)
    if artifact_type not in {"binary", "archive"}:
        raise UnsafeState("unsafe-artifact-type")
    if stage_name is not None:
        _validate_name(stage_name)
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    root, staging, transaction = _open_transaction(
        install_root, staging_dir, transaction_dir, uid, gid
    )
    try:
        expected = _transaction_payload(
            transaction_dir.name,
            artifact_name,
            stage_name,
            candidate_name,
            version,
            artifact_sha256,
            artifact_type,
        )
        if _read_transaction_receipt(transaction, uid, gid) != expected:
            raise UnsafeState("staging-receipt-mismatch")
        allowed = {TRANSACTION_RECEIPT, artifact_name}
        if stage_name is not None:
            allowed.add(stage_name)
        if set(os.listdir(transaction.descriptor)) - allowed:
            raise UnsafeState("unexpected-staging-node")
        try:
            artifact_info = os.stat(
                artifact_name,
                dir_fd=transaction.descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            if (
                not stat.S_ISREG(artifact_info.st_mode)
                or artifact_info.st_nlink != 1
                or artifact_info.st_uid != uid
                or artifact_info.st_gid != gid
                or stat.S_IMODE(artifact_info.st_mode) not in {0o600, 0o700}
            ):
                raise UnsafeState("unsafe-staging-artifact")
            os.unlink(artifact_name, dir_fd=transaction.descriptor)
        if stage_name is not None:
            stage = _open_child_directory(transaction, stage_name)
            try:
                stage_info = os.fstat(stage.descriptor)
                if (
                    stage_info.st_uid != uid
                    or stage_info.st_gid != gid
                    or stat.S_IMODE(stage_info.st_mode) != 0o700
                    or set(os.listdir(stage.descriptor)) - {candidate_name}
                ):
                    raise UnsafeState("unsafe-staging-stage")
                try:
                    candidate_info = os.stat(
                        candidate_name,
                        dir_fd=stage.descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    pass
                else:
                    if (
                        not stat.S_ISREG(candidate_info.st_mode)
                        or candidate_info.st_nlink != 1
                        or candidate_info.st_uid != uid
                        or candidate_info.st_gid != gid
                    ):
                        raise UnsafeState("unsafe-staged-candidate")
                    os.unlink(candidate_name, dir_fd=stage.descriptor)
                _fsync_directory(stage)
            finally:
                stage.close()
            os.rmdir(stage_name, dir_fd=transaction.descriptor)
        os.unlink(TRANSACTION_RECEIPT, dir_fd=transaction.descriptor)
        _fsync_directory(transaction)
        transaction.close()
        transaction = None
        os.rmdir(transaction_dir.name, dir_fd=staging.descriptor)
        _fsync_directory(staging)
        return {"status": "cleaned", "changed": False}
    finally:
        if transaction is not None:
            transaction.close()
        staging.close()
        root.close()


def _candidate_digest(
    release: _DirectoryGuard,
    binary_name: str,
    *,
    uid: int | None = None,
    gid: int | None = None,
) -> str:
    _revalidate_directory(release)
    _validate_name(binary_name)
    descriptor = os.open(
        binary_name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=release.descriptor,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise UnsafeState("unsafe-candidate")
        if not info.st_mode & stat.S_IXUSR:
            raise UnsafeState("non-executable-candidate")
        if uid is not None and (
            info.st_uid != uid
            or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != 0o755
        ):
            raise UnsafeState("unsafe-candidate")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 128 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)
    finally:
        os.close(descriptor)


def _receipt_payload(
    version: str,
    binary_name: str,
    artifact_sha256: str,
    candidate_sha256: str,
    arch_key: str,
    arch_slug: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "version": version,
        "arch_key": arch_key,
        "arch_slug": arch_slug,
        "binary_name": binary_name,
        "artifact_sha256": artifact_sha256,
        "binary_sha256": candidate_sha256,
    }


def _atomic_receipt(
    release: _DirectoryGuard, payload: dict[str, object], uid: int, gid: int
) -> None:
    _revalidate_directory(release)
    temporary = f".runtime-release-receipt-{os.getpid()}-{uuid.uuid4().hex}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
        dir_fd=release.descriptor,
    )
    try:
        try:
            encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
            if os.write(descriptor, encoded) != len(encoded):
                raise OSError("receipt-write-incomplete")
            os.fchown(descriptor, uid, gid)
            os.fchmod(descriptor, 0o644)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _revalidate_directory(release)
        os.replace(
            temporary,
            ".runtime-release.json",
            src_dir_fd=release.descriptor,
            dst_dir_fd=release.descriptor,
        )
        _fsync_directory(release)
    finally:
        try:
            os.unlink(temporary, dir_fd=release.descriptor)
        except FileNotFoundError:
            # A successful replace or external cleanup race consumed the temporary.
            pass


def _owned_release_directory(
    root: _DirectoryGuard, version: str, uid: int, gid: int
) -> tuple[_DirectoryGuard, _DirectoryGuard]:
    """Return verified releases/version descriptors, creating only the version leaf."""
    releases = _open_child_directory(root, "releases")
    release: _DirectoryGuard | None = None
    try:
        _require_directory_contract(root, uid, gid, "install-root")
        _require_directory_contract(releases, uid, gid, "releases")
        try:
            release = _open_child_directory(releases, version)
        except FileNotFoundError:
            _revalidate_directory(releases)
            os.mkdir(version, 0o755, dir_fd=releases.descriptor)
            created_release: _DirectoryGuard | None = None
            try:
                created_release = _open_child_directory(releases, version)
                os.fchmod(created_release.descriptor, 0o755)
                os.fchown(created_release.descriptor, uid, gid)
                os.fsync(created_release.descriptor)
                created_release.close()
                created_release = None
                _fsync_directory(releases)
                release = _open_child_directory(releases, version)
            except Exception:
                if created_release is not None:
                    created_release.close()
                try:
                    os.rmdir(version, dir_fd=releases.descriptor)
                except OSError:
                    # Retain a raced, replaced, or non-empty release for validation.
                    pass
                raise
        _require_directory_contract(release, uid, gid, "release")
        return releases, release
    except Exception:
        if release is not None:
            release.close()
        releases.close()
        raise


def _atomic_install_candidate(
    release: _DirectoryGuard,
    binary_name: str,
    source: int,
    expected_digest: str,
    uid: int,
    gid: int,
) -> None:
    try:
        os.stat(binary_name, dir_fd=release.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise UnsafeState("candidate-appeared-during-install")

    temporary = f".runtime-release-candidate-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        source_info = os.fstat(source)
        if (
            not stat.S_ISREG(source_info.st_mode)
            or source_info.st_nlink != 1
            or not source_info.st_mode & stat.S_IXUSR
        ):
            raise UnsafeState("unsafe-staged-candidate")
        os.lseek(source, 0, os.SEEK_SET)
        destination = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o700,
            dir_fd=release.descriptor,
        )
        try:
            digest = hashlib.sha256()
            while True:
                chunk = os.read(source, 128 * 1024)
                if not chunk:
                    break
                if os.write(destination, chunk) != len(chunk):
                    raise UnsafeState("candidate-write-incomplete")
                digest.update(chunk)
            if digest.hexdigest() != expected_digest:
                raise UnsafeState("staged-candidate-digest-mismatch")
            os.fchown(destination, uid, gid)
            os.fchmod(destination, 0o755)
            os.fsync(destination)
        finally:
            os.close(destination)
        _revalidate_directory(release)
        os.replace(
            temporary,
            binary_name,
            src_dir_fd=release.descriptor,
            dst_dir_fd=release.descriptor,
        )
        _fsync_directory(release)
    finally:
        try:
            os.unlink(temporary, dir_fd=release.descriptor)
        except FileNotFoundError:
            # A successful replace or external cleanup race consumed the temporary.
            pass


def _validate_or_publish_receipt(
    root: _DirectoryGuard,
    version: str,
    binary_name: str,
    artifact_sha256: str,
    candidate_sha256: str,
    artifact_type: str,
    arch_key: str,
    arch_slug: str,
    owner: str,
    group: str,
    staged_candidate: int | None,
) -> _PublicationOutcome:
    _validate_digest(artifact_sha256)
    _validate_digest(candidate_sha256)
    _validate_name(arch_key)
    _validate_name(arch_slug)
    if artifact_type not in {"binary", "archive"}:
        raise UnsafeState("unsafe-artifact-type")
    expected = _receipt_payload(
        version, binary_name, artifact_sha256, candidate_sha256, arch_key, arch_slug
    )
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    releases, release = _owned_release_directory(root, version, uid, gid)
    candidate_installed = False
    receipt_created = False
    try:
        try:
            os.stat(binary_name, dir_fd=release.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            if staged_candidate is None:
                try:
                    os.stat(
                        ".runtime-release.json",
                        dir_fd=release.descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    return _PublicationOutcome.NEEDS_STAGED_CANDIDATE
                raise UnsafeState("receipt-without-candidate")
            _atomic_install_candidate(
                release,
                binary_name,
                staged_candidate,
                candidate_sha256,
                uid,
                gid,
            )
            candidate_installed = True
        actual_candidate_digest = _candidate_digest(
            release, binary_name, uid=uid, gid=gid
        )
        if actual_candidate_digest != candidate_sha256:
            raise UnsafeState("candidate-digest-mismatch")
        if artifact_type == "binary" and candidate_sha256 != artifact_sha256:
            raise UnsafeState("binary-pin-mismatch")
        try:
            info = os.stat(
                ".runtime-release.json",
                dir_fd=release.descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            _atomic_receipt(release, expected, uid, gid)
            receipt_created = True
            info = os.stat(
                ".runtime-release.json",
                dir_fd=release.descriptor,
                follow_symlinks=False,
            )
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o644
            or info.st_uid != uid
            or info.st_gid != gid
        ):
            raise UnsafeState("unsafe-receipt")
        descriptor = os.open(
            ".runtime-release.json",
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=release.descriptor,
        )
        try:
            observed = json.loads(os.read(descriptor, 128 * 1024).decode())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UnsafeState("invalid-receipt") from error
        finally:
            os.close(descriptor)
        if observed != expected:
            raise UnsafeState("receipt-mismatch")
        if candidate_installed:
            return _PublicationOutcome.CANDIDATE_AND_RECEIPT_CREATED
        if receipt_created:
            return _PublicationOutcome.RECEIPT_CREATED
        return _PublicationOutcome.ALREADY_PUBLISHED
    finally:
        release.close()
        releases.close()


def _open_staged_candidate(
    install_root: Path,
    staging_dir: Path,
    transaction_dir: Path,
    staged_candidate: Path,
    artifact_name: str,
    stage_name: str | None,
    binary_name: str,
    version: str,
    artifact_sha256: str,
    artifact_type: str,
    candidate_sha256: str,
    uid: int,
    gid: int,
) -> int:
    """Open the receipt-bound candidate without following any path component."""
    root, staging, transaction = _open_transaction(
        install_root, staging_dir, transaction_dir, uid, gid
    )
    candidate_parent: _DirectoryGuard | None = None
    try:
        expected = _transaction_payload(
            transaction_dir.name,
            artifact_name,
            stage_name,
            binary_name,
            version,
            artifact_sha256,
            artifact_type,
        )
        if _read_transaction_receipt(transaction, uid, gid) != expected:
            raise UnsafeState("staging-receipt-mismatch")
        if artifact_type == "binary":
            expected_path = transaction_dir / artifact_name
            candidate_parent = transaction
            candidate_name = artifact_name
        else:
            if stage_name is None:
                raise UnsafeState("missing-staging-stage")
            expected_path = transaction_dir / stage_name / binary_name
            candidate_parent = _open_child_directory(transaction, stage_name)
            stage_info = os.fstat(candidate_parent.descriptor)
            if (
                stage_info.st_uid != uid
                or stage_info.st_gid != gid
                or stat.S_IMODE(stage_info.st_mode) != 0o700
            ):
                raise UnsafeState("unsafe-staging-stage")
            candidate_name = binary_name
        if staged_candidate != expected_path:
            raise UnsafeState("staged-candidate-outside-transaction")
        descriptor = os.open(
            candidate_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=candidate_parent.descriptor,
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != uid
                or info.st_gid != gid
                or not info.st_mode & stat.S_IXUSR
            ):
                raise UnsafeState("unsafe-staged-candidate")
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 128 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            if digest.hexdigest() != candidate_sha256:
                raise UnsafeState("staged-candidate-digest-mismatch")
            os.lseek(descriptor, 0, os.SEEK_SET)
            return descriptor
        except Exception:
            os.close(descriptor)
            raise
    finally:
        if candidate_parent is not None and candidate_parent is not transaction:
            candidate_parent.close()
        transaction.close()
        staging.close()
        root.close()


def activate(
    install_root: Path,
    version: str,
    binary_name: str,
    public_link: Path,
    *,
    check: bool,
    artifact_sha256: str | None = None,
    candidate_sha256: str | None = None,
    artifact_type: str | None = None,
    arch_key: str | None = None,
    arch_slug: str | None = None,
    owner: str | None = None,
    group: str | None = None,
    staged_candidate: Path | None = None,
    staging_dir: Path | None = None,
    transaction_dir: Path | None = None,
    artifact_name: str | None = None,
    stage_name: str | None = None,
    requires_artifact: bool = False,
) -> dict[str, object]:
    _validate_absolute(install_root)
    _validate_absolute(public_link)
    _validate_name(version)
    _validate_name(binary_name)
    if public_link == install_root or install_root in public_link.parents:
        raise UnsafeState("public-link-inside-install-root")
    if (owner is None) != (group is None):
        raise UnsafeState("incomplete-storage-identity")
    if owner is not None:
        _validate_storage_ancestors(
            install_root,
            pwd.getpwnam(owner).pw_uid,
            allow_missing=check,
        )

    public_directory: _DirectoryGuard | None = None
    root_directory: _DirectoryGuard | None = None
    lock_directory = _lock_directory(install_root, check=check)
    try:
        if lock_directory.path == install_root:
            root_directory = lock_directory
        if root_directory is not None:
            storage_uid = (
                pwd.getpwnam(owner).pw_uid
                if owner is not None
                else root_directory.identity[2]
            )
            storage_gid = (
                grp.getgrnam(group).gr_gid
                if group is not None
                else root_directory.identity[3]
            )
            _require_directory_contract(
                root_directory, storage_uid, storage_gid, "install-root"
            )
        try:
            public_directory = _open_directory(public_link.parent)
        except FileNotFoundError:
            public_directory = None
        if public_directory is not None and root_directory is not None:
            _require_directory_contract(
                public_directory, storage_uid, storage_gid, "public-link-parent"
            )

        if root_directory is not None:
            if public_directory is not None:
                before = _snapshot(
                    install_root,
                    public_link,
                    binary_name,
                    root_directory,
                    public_directory,
                )
            else:
                before = {
                    "current": _snapshot_link(
                        install_root / "current",
                        parent=root_directory,
                        root=install_root,
                        binary_name=binary_name,
                    ),
                    "public": None,
                    "previous": _snapshot_link(
                        install_root / "previous",
                        parent=root_directory,
                        root=install_root,
                        binary_name=binary_name,
                    ),
                }
        else:
            before = {
                "current": None,
                "public": (
                    _snapshot_link(
                        public_link,
                        parent=public_directory,
                        root=install_root,
                        binary_name=binary_name,
                        public=True,
                    )
                    if public_directory is not None
                    else None
                ),
                "previous": None,
            }

        release = str(install_root / "releases" / version)
        desired = {
            "current": release,
            "public": str(install_root / "current" / binary_name),
            "previous": (
                before["current"]
                if before["current"] is not None and before["current"] != release
                else before["previous"]
            ),
        }
        changed = desired != before or requires_artifact
        if check:
            return {"status": "predicted", "changed": changed}

        receipt_inputs = (
            artifact_sha256,
            candidate_sha256,
            artifact_type,
            arch_key,
            arch_slug,
            owner,
            group,
        )
        publication_changed = False
        if any(value is not None for value in receipt_inputs):
            if any(value is None for value in receipt_inputs):
                raise UnsafeState("incomplete-receipt-input")
            if root_directory is None:
                raise UnsafeState("missing-install-root")
            outcome = _validate_or_publish_receipt(
                root_directory,
                version,
                binary_name,
                artifact_sha256,
                candidate_sha256,
                artifact_type,
                arch_key,
                arch_slug,
                owner,
                group,
                None,
            )
            if outcome is _PublicationOutcome.NEEDS_STAGED_CANDIDATE:
                if not requires_artifact:
                    raise UnsafeState("missing-staged-candidate")
                transaction_inputs = (
                    staging_dir,
                    transaction_dir,
                    artifact_name,
                    staged_candidate,
                )
                if any(value is None for value in transaction_inputs):
                    raise UnsafeState("incomplete-staging-transaction-input")
                staged_descriptor = _open_staged_candidate(
                    install_root,
                    staging_dir,
                    transaction_dir,
                    staged_candidate,
                    artifact_name,
                    stage_name,
                    binary_name,
                    version,
                    artifact_sha256,
                    artifact_type,
                    candidate_sha256,
                    storage_uid,
                    storage_gid,
                )
                try:
                    outcome = _validate_or_publish_receipt(
                        root_directory,
                        version,
                        binary_name,
                        artifact_sha256,
                        candidate_sha256,
                        artifact_type,
                        arch_key,
                        arch_slug,
                        owner,
                        group,
                        staged_descriptor,
                    )
                finally:
                    os.close(staged_descriptor)
            publication_changed = outcome is not _PublicationOutcome.ALREADY_PUBLISHED
        else:
            if root_directory is None:
                raise UnsafeState("missing-install-root")
            releases = _open_child_directory(root_directory, "releases")
            release_directory = _open_child_directory(releases, version)
            try:
                _candidate_digest(release_directory, binary_name)
            finally:
                release_directory.close()
                releases.close()
        changed = desired != before or publication_changed
        try:
            _set_link_state(
                install_root / "current",
                desired["current"],
                parent=root_directory,
                root=install_root,
                binary_name=binary_name,
                public=False,
            )
            if public_directory is None:
                raise OSError("missing-public-link-parent")
            _set_link_state(
                public_link,
                desired["public"],
                parent=public_directory,
                root=install_root,
                binary_name=binary_name,
                public=True,
            )
            _set_link_state(
                install_root / "previous",
                desired["previous"],
                parent=root_directory,
                root=install_root,
                binary_name=binary_name,
                public=False,
            )
            _verify_desired(
                install_root,
                public_link,
                binary_name,
                desired,
                root_directory,
                public_directory,
            )
        except Exception as activation_error:
            if public_directory is None:
                try:
                    if before["public"] is not None:
                        raise UnsafeState("missing-public-link-parent")
                    _set_link_state(
                        install_root / "current",
                        before["current"],
                        parent=root_directory,
                        root=install_root,
                        binary_name=binary_name,
                        public=False,
                    )
                    _set_link_state(
                        install_root / "previous",
                        before["previous"],
                        parent=root_directory,
                        root=install_root,
                        binary_name=binary_name,
                        public=False,
                    )
                    if (
                        _snapshot_link(
                            install_root / "current",
                            parent=root_directory,
                            root=install_root,
                            binary_name=binary_name,
                        )
                        != before["current"]
                        or _snapshot_link(
                            install_root / "previous",
                            parent=root_directory,
                            root=install_root,
                            binary_name=binary_name,
                        )
                        != before["previous"]
                    ):
                        raise OSError("compensation-postcheck-failed")
                except Exception as compensation_error:
                    raise CompensationIncomplete(
                        "compensation-incomplete"
                    ) from compensation_error
                raise ActivationFailed("activation-failed") from activation_error
            try:
                _restore_snapshot(
                    install_root,
                    public_link,
                    binary_name,
                    before,
                    root_directory,
                    public_directory,
                )
            except Exception as compensation_error:
                raise CompensationIncomplete(
                    "compensation-incomplete"
                ) from compensation_error
            raise ActivationFailed("activation-failed") from activation_error
        return {"status": "committed", "changed": changed}
    finally:
        if root_directory is not None:
            root_directory.close()
        else:
            lock_directory.close()
        if public_directory is not None:
            public_directory.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--version")
    parser.add_argument("--binary-name")
    parser.add_argument("--public-link", type=Path)
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--artifact-type")
    parser.add_argument("--arch-key")
    parser.add_argument("--arch-slug")
    parser.add_argument("--owner")
    parser.add_argument("--group")
    parser.add_argument("--staged-candidate", type=Path)
    parser.add_argument("--staging-dir", type=Path)
    parser.add_argument("--transaction-dir", type=Path)
    parser.add_argument("--artifact-name")
    parser.add_argument("--stage-name")
    parser.add_argument("--phase", choices=("prepared", "downloaded"))
    parser.add_argument(
        "--requires-artifact", choices=("true", "false"), default="false"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--prepare-staging", action="store_true")
    mode.add_argument("--cleanup-staging", action="store_true")
    mode.add_argument("--validate-staging", action="store_true")
    mode.add_argument("--validate-staging-root", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.stage_name == "":
            args.stage_name = None
        if args.transaction_dir is not None and str(args.transaction_dir) == ".":
            args.transaction_dir = None
        if args.prepare_staging:
            if (
                args.staging_dir is None
                or args.artifact_name is None
                or args.binary_name is None
                or args.version is None
                or args.artifact_sha256 is None
                or args.artifact_type is None
                or args.owner is None
                or args.group is None
            ):
                raise UnsafeState("incomplete-staging-input")
            result = prepare_staging(
                args.install_root,
                args.staging_dir,
                args.artifact_name,
                args.stage_name,
                args.binary_name,
                args.version,
                args.artifact_sha256,
                args.artifact_type,
                owner=args.owner,
                group=args.group,
            )
        elif args.validate_staging_root:
            if args.staging_dir is None or args.owner is None or args.group is None:
                raise UnsafeState("incomplete-staging-input")
            result = validate_staging_root(
                args.install_root,
                args.staging_dir,
                owner=args.owner,
                group=args.group,
            )
        elif args.cleanup_staging or args.validate_staging:
            if (
                args.staging_dir is None
                or args.transaction_dir is None
                or args.artifact_name is None
                or args.binary_name is None
                or args.version is None
                or args.artifact_sha256 is None
                or args.artifact_type is None
                or args.owner is None
                or args.group is None
                or (args.validate_staging and args.phase is None)
            ):
                raise UnsafeState("incomplete-staging-input")
            operation = validate_staging if args.validate_staging else cleanup_staging
            operation_args = [
                args.install_root,
                args.staging_dir,
                args.transaction_dir,
                args.artifact_name,
                args.stage_name,
                args.binary_name,
                args.version,
                args.artifact_sha256,
                args.artifact_type,
            ]
            if args.validate_staging:
                operation_args.append(args.phase)
            result = operation(
                *operation_args,
                owner=args.owner,
                group=args.group,
            )
        else:
            if (
                args.version is None
                or args.binary_name is None
                or args.public_link is None
            ):
                raise UnsafeState("incomplete-activation-input")
            result = activate(
                args.install_root,
                args.version,
                args.binary_name,
                args.public_link,
                check=args.check,
                artifact_sha256=args.artifact_sha256,
                candidate_sha256=args.candidate_sha256,
                artifact_type=args.artifact_type,
                arch_key=args.arch_key,
                arch_slug=args.arch_slug,
                owner=args.owner,
                group=args.group,
                staged_candidate=args.staged_candidate,
                staging_dir=args.staging_dir,
                transaction_dir=args.transaction_dir,
                artifact_name=args.artifact_name,
                stage_name=args.stage_name,
                requires_artifact=args.requires_artifact == "true",
            )
    except CompensationIncomplete:
        print(json.dumps({"status": "compensation_incomplete", "changed": False}))
        return 74
    except ActivationFailed:
        print(json.dumps({"status": "activation_failed", "changed": False}))
        return 73
    except UnsafeState:
        print(json.dumps({"status": "unsafe_state", "changed": False}))
        return 65
    except Exception:
        print(json.dumps({"status": "internal_error", "changed": False}))
        return 70
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
