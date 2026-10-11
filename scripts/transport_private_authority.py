"""Bounded private files and the observed systemd per-unit credential ACL contract."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import stat
import struct


class PrivateAuthorityError(ValueError):
    """Categorical refusal; never includes a pathname or private payload."""


def _refuse():
    raise PrivateAuthorityError("unsafe-private-authority") from None


def _acl(path):
    reader = getattr(os, "getxattr", None)
    if reader is None:
        _refuse()
    try:
        value = reader(path, "system.posix_acl_access", follow_symlinks=False)
    except OSError as error:
        if error.errno in (errno.ENODATA, errno.ENOTSUP):
            return None
        _refuse()
    if len(value) < 4 or len(value) > 44 or (len(value) - 4) % 8 or struct.unpack_from("<I", value)[0] != 2:
        _refuse()
    return [struct.unpack_from("<HHI", value, offset) for offset in range(4, len(value), 8)]


def _private_acl(info, entries, actor, *, directory=False):
    """Only root and the exact service actor may read the private credential."""
    wanted = 5 if directory else 4
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid not in (0, actor) or mode & 0o7000:
        _refuse()
    if entries is None:
        if mode != wanted << 6 or info.st_uid != actor and actor != 0:
            _refuse()
        return
    by_tag = {}
    for tag, permission, identity in entries:
        if tag in by_tag or tag not in {1, 2, 4, 16, 32}:
            _refuse()
        if tag == 2:
            if identity != actor or permission != wanted:
                _refuse()
        elif identity != 0xFFFFFFFF:
            _refuse()
        by_tag[tag] = permission
    if not {1, 4, 32} <= set(by_tag) or by_tag[1] != wanted or by_tag[4] or by_tag[32]:
        _refuse()
    if 2 in by_tag and by_tag.get(16) != wanted:
        _refuse()
    if 16 in by_tag and by_tag[16] != wanted:
        _refuse()
    if info.st_uid != actor and actor != 0 and 2 not in by_tag:
        _refuse()
    effective_group = by_tag.get(16, by_tag[4])
    if mode != (by_tag[1] << 6 | effective_group << 3 | by_tag[32]):
        _refuse()


def _credential_directory(path, actor):
    authority = os.environ.get("CREDENTIALS_DIRECTORY")
    if not authority or path.parent != Path(authority):
        return False
    directory = Path(authority)
    if (not directory.is_absolute() or directory != Path(os.path.normpath(authority))
            or directory.parent != Path("/run/credentials") or not directory.name.endswith(".service")
            or directory.resolve(strict=True) != directory or path.resolve(strict=True) != path):
        _refuse()
    for parent in (Path("/"), Path("/run"), directory.parent):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            _refuse()
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or not os.statvfs(directory).f_flag & os.ST_RDONLY:
        _refuse()
    _private_acl(info, _acl(directory), actor, directory=True)
    return True


def _read_private_file(path, *, max_bytes, expected_uid=None):
    """Read owner-only ordinary files, or exact privately ACL-scoped systemd credentials."""
    actor = os.geteuid() if expected_uid is None else expected_uid
    if type(actor) is not int or actor < 0 or type(max_bytes) is not int or not 1 <= max_bytes <= 4194304:
        _refuse()
    path = Path(os.path.abspath(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > max_bytes
                or before.st_uid not in (0, actor)):
            _refuse()
        if _credential_directory(path, actor):
            if not os.fstatvfs(descriptor).f_flag & os.ST_RDONLY:
                _refuse()
            _private_acl(before, _acl(path), actor)
        elif before.st_mode & 0o077:
            _refuse()
        content = bytearray()
        while len(content) <= max_bytes:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
        attributes = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(content) > max_bytes or any(getattr(before, key) != getattr(after, key) for key in attributes):
            _refuse()
        return bytes(content)
    finally:
        os.close(descriptor)


def read_private_file(path, *, max_bytes, expected_uid=None):
    try:
        return _read_private_file(path, max_bytes=max_bytes, expected_uid=expected_uid)
    except (OSError, TypeError, ValueError):
        _refuse()
