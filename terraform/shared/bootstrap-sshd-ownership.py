#!/usr/bin/env python3
"""Publish the bounded first-boot SSH 10/20/50 ownership layout."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time


OWNER_UID = 0
OWNER_GID = 0
MAX_FILE = 64 * 1024
MAX_OUTPUT = 64 * 1024
MAX_DIRECTORY_ENTRIES = 256
MAX_RESIDUES = 12
COMMAND_TIMEOUT = 10.0
SSHD = "/usr/sbin/sshd"
BOOT = "10-cloud-init-hardening.conf"
MANAGED = "20-ansible-hardening.conf"
CLOUD = "50-cloud-init.conf"
TARGETS = (BOOT, MANAGED, CLOUD)
MANAGED_CONTENT = b"# first-boot runtime owner\nX11Forwarding no\n"
CANONICAL_INCLUDE = b"Include /etc/ssh/sshd_config.d/*.conf"
RESIDUE = re.compile(
    rb"\.bootstrap-sshd-(10-cloud-init-hardening\.conf|20-ansible-hardening\.conf|"
    rb"50-cloud-init\.conf)\.[0-9a-f]{24}"
)


class BootstrapOwnershipError(ValueError):
    """Categorical first-boot refusal without configuration disclosure."""


def _refuse(code: str) -> None:
    raise BootstrapOwnershipError(code)


def PUBLISH_BOUNDARY_HOOK(phase: str, target: str) -> None:
    """Test seam for process-death boundaries; production is a no-op."""


def _port(value: object) -> str:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        _refuse("invalid-port")
    if len(value) > 5 or value != str(int(value)) or not 1 <= int(value) <= 65535:
        _refuse("invalid-port")
    return value


def _boot_content(port: str) -> bytes:
    return (
        f"Port {port}\n"
        "PasswordAuthentication no\n"
        "KbdInteractiveAuthentication no\n"
        "PermitRootLogin no\n"
        "PubkeyAuthentication yes\n"
    ).encode("ascii")


@contextmanager
def _directory(path: Path):
    if not path.is_absolute() or ".." in path.parts:
        _refuse("unsafe-directory")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError:
                _refuse("unsafe-directory")
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if info.st_uid not in {0, OWNER_UID} or info.st_mode & 0o022:
                _refuse("unsafe-directory")
        yield descriptor
    finally:
        os.close(descriptor)


def _read_optional(directory_fd: int, name: str) -> dict[str, object]:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        return {"exists": False, "data": None, "mode": None, "gid": None}
    except OSError:
        _refuse("unsafe-file")
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != OWNER_UID
            or before.st_mode & 0o022
        ):
            _refuse("unsafe-file")
        if before.st_size > MAX_FILE:
            _refuse("file-too-large")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_FILE + 1)
        after = os.fstat(descriptor)
        if len(data) > MAX_FILE:
            _refuse("file-too-large")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _refuse("read-race")
        return {
            "exists": True,
            "data": data,
            "mode": stat.S_IMODE(before.st_mode),
            "gid": before.st_gid,
        }
    finally:
        os.close(descriptor)


def _read_required(directory_fd: int, name: str) -> dict[str, object]:
    result = _read_optional(directory_fd, name)
    if not result["exists"]:
        _refuse("missing-file")
    return result


def _validate_main_include(snapshot: dict[str, object]) -> None:
    raw = snapshot["data"]
    assert isinstance(raw, bytes)
    if any(byte < 32 and byte not in {9, 10} for byte in raw):
        _refuse("noncanonical-include")
    try:
        raw.decode("ascii")
    except UnicodeDecodeError:
        _refuse("noncanonical-include")
    includes = 0
    for line in raw.splitlines(keepends=True):
        body = line[:-1] if line.endswith(b"\n") else line
        stripped = body.strip(b" \t")
        if not stripped or stripped.startswith(b"#"):
            continue
        directive = re.split(rb"[ \t=]", stripped, maxsplit=1)[0].lower()
        if directive == b"match":
            _refuse("unsupported-match")
        elif directive == b"include":
            if body != CANONICAL_INCLUDE:
                _refuse("noncanonical-include")
            includes += 1
    if includes != 1:
        _refuse("noncanonical-include")


def _cloud_candidate(snapshot: dict[str, object]) -> bytes | None:
    if not snapshot["exists"]:
        return None
    raw = snapshot["data"]
    assert isinstance(raw, bytes)
    if any(byte < 32 and byte not in {9, 10} for byte in raw):
        _refuse("unsupported-cloud-owner")
    try:
        raw.decode("ascii")
    except UnicodeDecodeError:
        _refuse("unsupported-cloud-owner")
    kept: list[bytes] = []
    owned = 0
    for line in raw.splitlines(keepends=True):
        body = line[:-1] if line.endswith(b"\n") else line
        if body == b"PasswordAuthentication no":
            owned += 1
            if owned > 1:
                _refuse("unsupported-cloud-owner")
            continue
        stripped = body.strip(b" \t")
        if stripped and not stripped.startswith(b"#"):
            _refuse("unsupported-cloud-owner")
        kept.append(line)
    return b"".join(kept)


def _validate_existing(snapshot: dict[str, object], expected: bytes) -> None:
    if not snapshot["exists"]:
        return
    if snapshot["data"] != expected:
        _refuse("unsupported-existing-owner")
    if snapshot["mode"] != 0o644 or snapshot["gid"] != OWNER_GID:
        _refuse("unsafe-existing-owner")


def _residues(directory_fd: int) -> list[str]:
    result: list[str] = []
    with os.scandir(directory_fd) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_DIRECTORY_ENTRIES:
                _refuse("unsupported-membership")
            encoded = os.fsencode(entry.name)
            if entry.name.endswith(".conf") and entry.name not in TARGETS:
                _refuse("unsupported-membership")
            if RESIDUE.fullmatch(encoded):
                if len(result) >= MAX_RESIDUES:
                    _refuse("unsupported-residue")
                _read_required(directory_fd, entry.name)
                result.append(entry.name)
    result.sort()
    return result


def _cleanup_residues(directory_fd: int, names: list[str]) -> bool:
    if not names:
        return False
    try:
        for name in names:
            os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except OSError:
        _refuse("residue-cleanup-failed")
    return True


def _terminate_and_wait(
    process: subprocess.Popen[bytes], *, allow_natural_exit_eperm: bool = False
) -> int:
    kill_error: OSError | None = None
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as error:
        kill_error = error
    try:
        returncode = process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        _refuse("effective-validation-uncertain")
    if kill_error is not None and not (
        allow_natural_exit_eperm
        and kill_error.errno == errno.EPERM
        and returncode == 0
    ):
        _refuse("effective-validation-uncertain")
    return returncode


def _capture_effective(main: Path) -> bytes:
    try:
        process = subprocess.Popen(
            [SSHD, "-T", "-f", str(main)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        _refuse("effective-validation-failed")
    assert process.stdout is not None
    output = bytearray()
    deadline = time.monotonic() + COMMAND_TIMEOUT
    selector: selectors.BaseSelector | None = None
    terminated = False

    def terminate_once(*, allow_natural_exit_eperm: bool = False) -> int:
        nonlocal terminated
        if terminated:
            _refuse("effective-validation-uncertain")
        terminated = True
        return _terminate_and_wait(
            process, allow_natural_exit_eperm=allow_natural_exit_eperm
        )

    try:
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_once()
                _refuse("effective-validation-timeout")
            for key, _ in selector.select(min(remaining, 0.1)):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if len(output) > MAX_OUTPUT:
                    terminate_once()
                    _refuse("effective-validation-output")
        returncode = terminate_once(allow_natural_exit_eperm=True)
    except OSError:
        _refuse("effective-validation-failed")
    finally:
        try:
            if not terminated:
                terminate_once()
        finally:
            if selector is not None:
                selector.close()
            process.stdout.close()
    if returncode != 0:
        _refuse("effective-validation-failed")
    return bytes(output)


def _assert_effective(config_dir: Path, port: str) -> None:
    raw = _capture_effective(config_dir / "sshd_config")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        _refuse("effective-policy-mismatch")
    expected = {
        "port": port,
        "passwordauthentication": "no",
        "kbdinteractiveauthentication": "no",
        "permitrootlogin": "no",
        "pubkeyauthentication": "yes",
        "x11forwarding": "no",
    }
    found: dict[str, str] = {}
    for line in text.splitlines():
        fields = line.split(None, 1)
        if not fields:
            continue
        key = fields[0].lower()
        if key not in expected:
            continue
        if len(fields) != 2 or key in found:
            _refuse("effective-policy-mismatch")
        found[key] = fields[1].strip().lower()
    if found != expected:
        _refuse("effective-policy-mismatch")


def _temporary_name(target: str) -> str:
    return f".bootstrap-sshd-{target}.{secrets.token_hex(12)}"


def _write_atomic(
    directory_fd: int,
    target: str,
    data: bytes,
    *,
    mode: int,
    gid: int,
) -> None:
    temporary = _temporary_name(target)
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, OWNER_UID, gid)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(errno.EIO, "short write")
            view = view[written:]
        os.fsync(descriptor)
        PUBLISH_BOUNDARY_HOOK("file-fsync", target)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary,
            target,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        PUBLISH_BOUNDARY_HOOK("replace", target)
        os.fsync(directory_fd)
        PUBLISH_BOUNDARY_HOOK("directory-fsync", target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _restore(directory_fd: int, name: str, snapshot: dict[str, object]) -> None:
    if snapshot["exists"]:
        data = snapshot["data"]
        mode = snapshot["mode"]
        gid = snapshot["gid"]
        assert isinstance(data, bytes) and isinstance(mode, int) and isinstance(gid, int)
        _write_atomic(directory_fd, name, data, mode=mode, gid=gid)
    else:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.fsync(directory_fd)


def normalize(config_dir: Path | str, ssh_port: object) -> bool:
    """Normalize fresh bootstrap ownership, returning whether bytes changed."""
    port = _port(ssh_port)
    root = Path(config_dir)
    with _directory(root) as config_fd, _directory(root / "sshd_config.d") as fragments_fd:
        # The packaged main file remains outside this helper's write set, but
        # it must still be a safe root-owned regular file before publication.
        main = _read_required(config_fd, "sshd_config")
        _validate_main_include(main)
        snapshots = {name: _read_optional(fragments_fd, name) for name in TARGETS}
        boot = _boot_content(port)
        _validate_existing(snapshots[BOOT], boot)
        _validate_existing(snapshots[MANAGED], MANAGED_CONTENT)
        cloud = _cloud_candidate(snapshots[CLOUD])
        residues = _residues(fragments_fd)
        candidates = {BOOT: boot, MANAGED: MANAGED_CONTENT, CLOUD: cloud}
        changed = [
            name
            for name in TARGETS
            if candidates[name] is not None
            and (
                not snapshots[name]["exists"]
                or snapshots[name]["data"] != candidates[name]
            )
        ]
        residue_changed = _cleanup_residues(fragments_fd, residues)
        attempted: list[str] = []
        try:
            for name in changed:
                attempted.append(name)
                snapshot = snapshots[name]
                mode = snapshot["mode"] if snapshot["exists"] else 0o644
                gid = snapshot["gid"] if snapshot["exists"] else OWNER_GID
                assert isinstance(mode, int) and isinstance(gid, int)
                candidate = candidates[name]
                assert isinstance(candidate, bytes)
                _write_atomic(fragments_fd, name, candidate, mode=mode, gid=gid)
            _assert_effective(root, port)
        except (OSError, BootstrapOwnershipError) as error:
            try:
                for name in reversed(attempted):
                    _restore(fragments_fd, name, snapshots[name])
            except (OSError, BootstrapOwnershipError):
                _refuse("rollback-failed")
            if isinstance(error, BootstrapOwnershipError) and str(error).startswith("effective-"):
                raise error
            _refuse("publish-failed")
        return bool(changed or residue_changed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", required=True)
    parser.add_argument("--ssh-port", required=True)
    arguments = parser.parse_args(argv)
    try:
        normalize(arguments.config_dir, arguments.ssh_port)
    except BootstrapOwnershipError as exc:
        print(f"bootstrap SSH ownership refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
