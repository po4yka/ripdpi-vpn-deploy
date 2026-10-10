"""Descriptor-bound ownership, type and privacy gates."""

import os
from pathlib import Path
import stat
import tempfile


def require_owner(metadata, uid):
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != uid:
        raise ValueError("protected file must be a regular file owned by the current user")


def open_owned(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as error:
        raise ValueError("open protected regular file without following symlinks") from error
    try:
        metadata = os.fstat(fd)
        require_owner(metadata, os.getuid())
        return os.fdopen(fd, "rb"), metadata
    except BaseException:
        os.close(fd)
        raise


def open_private(path):
    handle, metadata = open_owned(path)
    if metadata.st_mode & 0o077:
        handle.close()
        raise ValueError("protected file has unsafe owner, type, or permissions; use 0600")
    return handle


def harden(path):
    handle, _ = open_owned(path)
    with handle:
        try:
            os.fchmod(handle.fileno(), 0o600)
        except OSError as error:
            raise ValueError("set 0600 on protected file descriptor") from error


def write_private(path, payload):
    path = Path(path)
    if not path.name:
        raise ValueError("protected output must name a file")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            # Successful replacement already consumed the temporary name.
            pass
