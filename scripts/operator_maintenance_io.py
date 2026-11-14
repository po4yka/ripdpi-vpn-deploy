"""Private maintenance inputs and bounded encrypted command diagnostics."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import fcntl
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys
import tempfile

from bootstrap_readiness import run_command
from recovery_io import RecoveryError, canonical, module

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 256 * 1024 * 1024
DEPLOY = module('deploy-controller')


class MaintenanceError(RecoveryError):
    """Only categorical diagnostics cross the operator boundary."""


def private_directory(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        info = parent.lstat()
        sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o022 and not sticky):
            raise MaintenanceError('unsafe-directory')
    info = path.lstat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise MaintenanceError('nonprivate-directory')
    return path


def read_bytes(path, *, limit=LIMIT, private=True, allow_empty=False):
    try:
        return DEPLOY.read_input(path, private=private, limit=limit, allow_empty=allow_empty)
    except (OSError, ValueError, DEPLOY.DeployError):
        raise MaintenanceError('unsafe-input') from None


def digest_file(path, *, private=True):
    return hashlib.sha256(read_bytes(path, private=private)).hexdigest()


@contextmanager
def new_file(path):
    path = Path(path).absolute()
    parent = private_directory(path.parent)
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        identity = os.fstat(parent_fd)
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        opened = os.fstat(fd)
    except BaseException:
        os.close(parent_fd)
        raise
    complete = False
    try:
        with os.fdopen(fd, 'wb') as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        current_parent = parent.lstat()
        if ((identity.st_dev, identity.st_ino) != (current_parent.st_dev, current_parent.st_ino)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                or named.st_uid != os.geteuid() or named.st_nlink != 1
                or stat.S_IMODE(named.st_mode) != 0o600):
            raise MaintenanceError('output-changed')
        os.fsync(parent_fd)
        complete = True
    finally:
        if not complete:
            try:
                named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                if (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino):
                    os.unlink(path.name, dir_fd=parent_fd)
            except FileNotFoundError:
                # A failed writer can have removed its own incomplete output.
                pass
        os.close(parent_fd)


def metadata_bytes(value):
    # SOPS authenticates data order; its encrypted output must remain opaque.
    if isinstance(value, dict) and 'sops' in value:
        raise MaintenanceError('encrypted-document-requires-byte-preserving-publication')
    return canonical(value)


def write_document(path, value):
    payload = metadata_bytes(value)
    with new_file(path) as stream:
        stream.write(payload)


def update_document(path, expected_sha256, value):
    """Compare the private authority again before atomic metadata publication."""
    with private_lock(str(path) + '.lock'):
        _update_document(path, expected_sha256, value)


@contextmanager
def private_lock(path):
    """Keep a stable lock inode across atomic document replacements."""
    path = Path(path).absolute()
    private_directory(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise MaintenanceError('unsafe-lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        named = path.lstat()
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
            raise MaintenanceError('lock-changed')
        yield
    finally:
        os.close(fd)


def _update_document(path, expected_sha256, value):
    payload = metadata_bytes(value)
    path = Path(path).absolute()
    private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as locked:
        fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
        opened = os.fstat(locked.fileno())
        if digest_file(path) != expected_sha256:
            raise MaintenanceError('catalog-changed')
        fd, name = tempfile.mkstemp(prefix='.maintenance-ack-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
            named = path.lstat()
            if ((opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                    or digest_file(path) != expected_sha256):
                raise MaintenanceError('catalog-changed')
            os.replace(name, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.lexists(name):
                os.unlink(name)


def command_environment(values=None):
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ')
           if key in os.environ}
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    env.update(values or {})
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    return env


def encrypted_command(command, destination, recipient, *, environment, cwd, timeout=7200,
                      defer_cancellation=False):
    """The child supervisor owns commands; this process owns the age writer."""
    def bounded_writer():
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))

    code, error = None, None
    with new_file(destination) as output:
        age = subprocess.Popen(['age', '--encrypt', '--recipient', recipient],
                               stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
                               env=command_environment(), start_new_session=True,
                               preexec_fn=bounded_writer)
        try:
            try:
                code, _ = run_command(command, timeout=timeout, environment=environment, cwd=cwd,
                                      output_fd=age.stdin.fileno(), defer_cancellation=defer_cancellation)
            except (Exception, KeyboardInterrupt, SystemExit) as caught:
                # Defer cancellation until the authenticated diagnostic is published.
                error = caught
            finally:
                age.stdin.close()
                if age.wait(timeout=30):
                    raise MaintenanceError('diagnostic-encryption-failed')
        finally:
            if age.poll() is None:
                age.kill()
            age.wait(timeout=5)
    if error is not None:
        raise error
    if code is None:
        raise MaintenanceError('command-outcome-missing')
    return code


def require_success(command, *, cwd=ROOT, environment=None, timeout=30):
    code, output = run_command(command, timeout=timeout, environment=environment or command_environment(),
                               cwd=cwd, capture=True, output_limit=1024 * 1024)
    if code:
        raise MaintenanceError('command-failed')
    return output
