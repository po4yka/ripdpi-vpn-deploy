"""One private, locked, verified SOPS publication for device transactions."""
from __future__ import annotations

import copy
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

MAX_BYTES = 4 * 1024 * 1024


def run_sops(arguments, *, data=None):
    result = subprocess.run(["sops", *arguments], input=data, capture_output=True, timeout=60)
    if result.returncode or len(result.stdout) > MAX_BYTES:
        raise ValueError("encrypted-document-operation-refused")
    return result.stdout


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def private_file(descriptor):
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise ValueError("unsafe-private-document-authority")
    return info


class CommittedPublication(OSError):
    """Authority changed; the caller must retain its completed recipient artifact."""

    def __init__(self, metadata):
        super().__init__("encrypted-document-committed-durability-uncertain")
        self.metadata = metadata


def operate(path, transform, *, runner=run_sops, before_publish=None):
    publication = {}
    try:
        return _operate(path, transform, runner=runner, before_publish=before_publish,
                        publication=publication)
    except Exception as error:
        if "committed" in publication:
            raise CommittedPublication(publication["committed"]) from error
        raise


def _operate(path, transform, *, runner, before_publish, publication):
    path = Path(os.path.abspath(path))
    path = path.parent.resolve(strict=True) / path.name
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    lock = source = candidate = None
    temporary = None
    temporary_identity = None
    try:
        directory = os.fstat(parent)
        if directory.st_uid != os.getuid() or directory.st_mode & 0o022:
            raise ValueError("unsafe-private-document-directory")
        lock = os.open(str(path) + ".new-client.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
        lock_info = private_file(lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        before = private_file(source)
        if before.st_size > MAX_BYTES:
            raise ValueError("private-document-too-large")
        encrypted = os.read(source, before.st_size + 1)
        if len(encrypted) != before.st_size or identity(os.fstat(source)) != identity(before):
            raise ValueError("private-document-changed")
        kind = "json" if path.suffix == ".json" else "yaml"
        original = json.loads(runner(["--decrypt", "--input-type", kind, "--output-type", "json", "/dev/stdin"], data=encrypted))
        if not isinstance(original, dict):
            raise ValueError("invalid-private-document")
        expected, metadata = transform(copy.deepcopy(original))
        if not isinstance(expected, dict) or set(original) - set(expected):
            raise ValueError("invalid-document-transaction")
        if expected != original:
            descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".client.", suffix=path.suffix, dir=path.parent)
            with os.fdopen(descriptor, "wb") as output:
                output.write(encrypted)
                output.flush()
                os.fsync(output.fileno())
            temporary_identity = identity(os.stat(temporary, follow_symlinks=False))
            for name, value in expected.items():
                if name not in original or value != original[name]:
                    runner(["set", "--value-stdin", temporary, "[" + json.dumps(name) + "]"],
                           data=json.dumps(value).encode())
                    temporary_identity = identity(os.stat(temporary, follow_symlinks=False))
            candidate = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            candidate_info = private_file(candidate)
            if identity(candidate_info) != temporary_identity:
                raise ValueError("private-candidate-changed")
            if candidate_info.st_size > MAX_BYTES:
                raise ValueError("private-document-too-large")
            candidate_bytes = os.read(candidate, MAX_BYTES + 1)
            actual = json.loads(runner(["--decrypt", "--input-type", kind, "--output-type", "json", "/dev/stdin"], data=candidate_bytes))
            if actual != expected:
                raise ValueError("encrypted-publication-mismatch")
            os.fsync(candidate)
        named_lock = os.stat(str(path) + ".new-client.lock", follow_symlinks=False)
        if (named_lock.st_dev, named_lock.st_ino) != (lock_info.st_dev, lock_info.st_ino):
            raise ValueError("private-lock-changed")
        if (identity(os.stat(path, follow_symlinks=False)) != identity(before)
                or identity(os.fstat(source)) != identity(before)
                or (os.stat(path.parent).st_dev, os.stat(path.parent).st_ino) != (directory.st_dev, directory.st_ino)):
            raise ValueError("private-document-changed")
        if temporary is not None:
            if (identity(os.stat(temporary, follow_symlinks=False)) != identity(candidate_info)
                    or identity(os.fstat(candidate)) != identity(candidate_info)):
                raise ValueError("private-candidate-changed")
            if before_publish is not None:
                before_publish()
            os.replace(temporary, path)
            publication["committed"] = metadata
            temporary = None
            os.fsync(parent)
        return metadata
    finally:
        try:
            if temporary is not None:
                try:
                    if identity(os.stat(temporary, follow_symlinks=False)) == temporary_identity:
                        Path(temporary).unlink()
                except FileNotFoundError:
                    pass  # An absent owned encrypted stage needs no cleanup.
        finally:
            try:
                if candidate is not None:
                    os.close(candidate)
            finally:
                try:
                    if source is not None:
                        os.close(source)
                finally:
                    try:
                        if lock is not None:
                            os.close(lock)
                    finally:
                        os.close(parent)
