#!/usr/bin/env python3
"""Serialize and compensate runtime-release symlink activation."""

from __future__ import annotations

import argparse
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


class UnsafeState(RuntimeError):
    """The observed layout is outside the owned runtime-release contract."""


class ActivationFailed(RuntimeError):
    """Activation failed and the exact observed state was restored."""


class CompensationIncomplete(RuntimeError):
    """Activation failed and exact restoration could not be confirmed."""


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
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))


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
    *,
    owner: str,
    group: str,
) -> None:
    """Create an immutable staging namespace before root writes artifacts into it."""
    _validate_absolute(install_root)
    _validate_absolute(staging_dir)
    _validate_name(artifact_name)
    if staging_dir.parent != install_root:
        raise UnsafeState("unsafe-staging-directory")
    _validate_name(staging_dir.name)
    if stage_name is not None:
        _validate_name(stage_name)
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    root = _open_directory(install_root)
    try:
        _require_directory_contract(root, uid, gid, "install-root")
        try:
            staging = _open_child_directory(root, staging_dir.name)
        except FileNotFoundError:
            os.mkdir(staging_dir.name, 0o700, dir_fd=root.descriptor)
            try:
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
                try:
                    os.rmdir(staging_dir.name, dir_fd=root.descriptor)
                except OSError:
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
            for name in (artifact_name, stage_name):
                if name is None:
                    continue
                try:
                    os.stat(name, dir_fd=staging.descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise UnsafeState("staging-node-exists")
            if stage_name is not None:
                os.mkdir(stage_name, 0o700, dir_fd=staging.descriptor)
                try:
                    os.chown(
                        stage_name,
                        uid,
                        gid,
                        dir_fd=staging.descriptor,
                        follow_symlinks=False,
                    )
                    _fsync_directory(staging)
                except Exception:
                    try:
                        os.rmdir(stage_name, dir_fd=staging.descriptor)
                    except OSError:
                        pass
                    raise
        finally:
            staging.close()
    finally:
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
        0o644,
        dir_fd=release.descriptor,
    )
    try:
        os.fchmod(descriptor, 0o644)
        os.fchown(descriptor, uid, gid)
        os.write(descriptor, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
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
            pass


def _owned_release_directory(
    root: _DirectoryGuard, version: str, uid: int, gid: int
) -> tuple[_DirectoryGuard, _DirectoryGuard]:
    """Return verified releases/version descriptors, creating only the version leaf."""
    releases = _open_child_directory(root, "releases")
    try:
        _require_directory_contract(root, uid, gid, "install-root")
        _require_directory_contract(releases, uid, gid, "releases")
        try:
            release = _open_child_directory(releases, version)
        except FileNotFoundError:
            _revalidate_directory(releases)
            os.mkdir(version, 0o755, dir_fd=releases.descriptor)
            try:
                os.chown(version, uid, gid, dir_fd=releases.descriptor, follow_symlinks=False)
                _fsync_directory(releases)
                release = _open_child_directory(releases, version)
            except Exception:
                try:
                    os.rmdir(version, dir_fd=releases.descriptor)
                except OSError:
                    pass
                raise
        _require_directory_contract(release, uid, gid, "release")
        return releases, release
    except Exception:
        releases.close()
        raise


def _atomic_install_candidate(
    release: _DirectoryGuard,
    binary_name: str,
    staged_candidate: Path,
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

    source = os.open(staged_candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    temporary = f".runtime-release-candidate-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        source_info = os.fstat(source)
        if (
            not stat.S_ISREG(source_info.st_mode)
            or source_info.st_nlink != 1
            or not source_info.st_mode & stat.S_IXUSR
        ):
            raise UnsafeState("unsafe-staged-candidate")
        destination = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o755,
            dir_fd=release.descriptor,
        )
        try:
            digest = hashlib.sha256()
            while True:
                chunk = os.read(source, 128 * 1024)
                if not chunk:
                    break
                os.write(destination, chunk)
                digest.update(chunk)
            if digest.hexdigest() != expected_digest:
                raise UnsafeState("staged-candidate-digest-mismatch")
            os.fchmod(destination, 0o755)
            os.fchown(destination, uid, gid)
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
        os.close(source)
        try:
            os.unlink(temporary, dir_fd=release.descriptor)
        except FileNotFoundError:
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
    staged_candidate: Path | None,
) -> None:
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
    try:
        try:
            os.stat(binary_name, dir_fd=release.descriptor, follow_symlinks=False)
        except FileNotFoundError:
            if staged_candidate is None:
                raise UnsafeState("missing-staged-candidate")
            _atomic_install_candidate(
                release,
                binary_name,
                staged_candidate,
                candidate_sha256,
                uid,
                gid,
            )
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
    finally:
        release.close()
        releases.close()


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
) -> dict[str, object]:
    _validate_absolute(install_root)
    _validate_absolute(public_link)
    _validate_name(version)
    _validate_name(binary_name)
    if public_link == install_root or install_root in public_link.parents:
        raise UnsafeState("public-link-inside-install-root")

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
        changed = desired != before
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
        if any(value is not None for value in receipt_inputs):
            if any(value is None for value in receipt_inputs):
                raise UnsafeState("incomplete-receipt-input")
            if root_directory is None:
                raise UnsafeState("missing-install-root")
            _validate_or_publish_receipt(
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
                staged_candidate,
            )
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
        try:
            if root_directory is None:
                raise UnsafeState("missing-install-root")
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
                    if root_directory is None or before["public"] is not None:
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
                    if _snapshot_link(
                        install_root / "current",
                        parent=root_directory,
                        root=install_root,
                        binary_name=binary_name,
                    ) != before["current"] or _snapshot_link(
                        install_root / "previous",
                        parent=root_directory,
                        root=install_root,
                        binary_name=binary_name,
                    ) != before["previous"]:
                        raise OSError("compensation-postcheck-failed")
                except Exception as compensation_error:
                    raise CompensationIncomplete("compensation-incomplete") from compensation_error
                raise ActivationFailed("activation-failed") from activation_error
            try:
                if root_directory is None:
                    raise UnsafeState("missing-install-root")
                _restore_snapshot(
                    install_root,
                    public_link,
                    binary_name,
                    before,
                    root_directory,
                    public_directory,
                )
            except Exception as compensation_error:
                raise CompensationIncomplete("compensation-incomplete") from compensation_error
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
    parser.add_argument("--stage-name")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--prepare-staging", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.prepare_staging:
            if (
                args.staging_dir is None
                or args.binary_name is None
                or args.owner is None
                or args.group is None
            ):
                raise UnsafeState("incomplete-staging-input")
            prepare_staging(
                args.install_root,
                args.staging_dir,
                args.binary_name,
                args.stage_name,
                owner=args.owner,
                group=args.group,
            )
            result = {"status": "prepared", "changed": False}
        else:
            if args.version is None or args.binary_name is None or args.public_link is None:
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
