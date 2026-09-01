"""Restricted Tailnet management domain logic shared by single-job CLIs."""

from __future__ import annotations

import ipaddress
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
from typing import Callable, NamedTuple

COMMAND_TIMEOUT_SECONDS = 30
TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")
TAILNET_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
EXPECTED_PREFS = {
    "accept-dns": False,
    "accept-routes": False,
    "advertise-exit-node": False,
    "advertise-routes": "",
    "exit-node": "",
    "netfilter-mode": "off",
    "shields-up": False,
    "ssh": False,
}
RECOVERY_GENERATION = "tailnet-recovery-v1"
TRANSACTION_NAME = "transaction.json"
LOCK_NAME = "transaction.lock"


class Refusal(RuntimeError):
    """A typed, redacted refusal safe for operator output."""


class Busy(Refusal):
    """The periodic worker must retry after the active controller releases."""


class CommandPaths(NamedTuple):
    tailscale: str
    sshd: str
    ip: str
    nft: str
    resolv_conf: Path
    auth_directory: Path
    state_directory: Path
    systemctl: str


class SystemSnapshot(NamedTuple):
    resolver: bytes
    routes: bytes
    sshd: bytes
    resolver_mode: int
    resolver_uid: int
    resolver_gid: int


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_private_directory(path: Path) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Refusal("tailnet-recovery-state-unsafe") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise Refusal("tailnet-recovery-state-unsafe")


@contextmanager
def _transaction_lock(paths: CommandPaths, *, blocking: bool):
    _validate_private_directory(paths.state_directory)
    lock_path = paths.state_directory / LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise Refusal("tailnet-recovery-lock-unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as error:
            raise Busy("tailnet-recovery-busy") from error
        yield
    except OSError as error:
        raise Refusal("tailnet-recovery-lock-unsafe") from error
    finally:
        if "fd" in locals():
            os.close(fd)


def _snapshot_document(snapshot: SystemSnapshot) -> dict[str, object]:
    names = ("resolver", "routes", "sshd")
    document = {
        name: {
            "base64": base64.b64encode(payload).decode("ascii"),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for name, payload in zip(
            names, (snapshot.resolver, snapshot.routes, snapshot.sshd), strict=True
        )
    }
    document["resolver_metadata"] = {
        "mode": snapshot.resolver_mode,
        "uid": snapshot.resolver_uid,
        "gid": snapshot.resolver_gid,
    }
    return document


def _parse_snapshot(value: object) -> SystemSnapshot:
    if not isinstance(value, dict) or set(value) != {
        "resolver",
        "routes",
        "sshd",
        "resolver_metadata",
    }:
        raise Refusal("tailnet-recovery-state-invalid")
    result = []
    for name in ("resolver", "routes", "sshd"):
        item = value[name]
        if not isinstance(item, dict) or set(item) != {"base64", "sha256"}:
            raise Refusal("tailnet-recovery-state-invalid")
        encoded, digest = item["base64"], item["sha256"]
        if not isinstance(encoded, str) or not isinstance(digest, str):
            raise Refusal("tailnet-recovery-state-invalid")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise Refusal("tailnet-recovery-state-invalid") from error
        if (
            not payload
            or len(payload) > 262_144
            or hashlib.sha256(payload).hexdigest() != digest
        ):
            raise Refusal("tailnet-recovery-state-invalid")
        result.append(payload)
    metadata = value["resolver_metadata"]
    if (
        not isinstance(metadata, dict)
        or set(metadata) != {"mode", "uid", "gid"}
        or not all(isinstance(metadata[key], int) for key in ("mode", "uid", "gid"))
        or metadata["mode"] < 0
        or metadata["mode"] > 0o7777
        or metadata["uid"] < 0
        or metadata["gid"] < 0
    ):
        raise Refusal("tailnet-recovery-state-invalid")
    return SystemSnapshot(
        resolver=result[0],
        routes=result[1],
        sshd=result[2],
        resolver_mode=metadata["mode"],
        resolver_uid=metadata["uid"],
        resolver_gid=metadata["gid"],
    )


def _transaction_path(paths: CommandPaths) -> Path:
    return paths.state_directory / TRANSACTION_NAME


def _write_transaction(
    paths: CommandPaths, *, backend_state: str, snapshot: SystemSnapshot
) -> None:
    if backend_state != "NeedsLogin":
        raise Refusal("tailnet-recovery-state-invalid")
    nonce = secrets.token_hex(16)
    value = {
        "schema_version": 1,
        "generation": RECOVERY_GENERATION,
        "nonce": nonce,
        "phase": "armed",
        "original_backend_state": backend_state,
        "snapshot": _snapshot_document(snapshot),
    }
    payload = _canonical_bytes(value)
    temporary = paths.state_directory / f".{TRANSACTION_NAME}.{nonce}"
    canonical = _transaction_path(paths)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(temporary, flags, 0o600)
        os.fchmod(fd, 0o600)
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.link(temporary, canonical, follow_symlinks=False)
        temporary.unlink()
        _fsync_directory(paths.state_directory)
    except (FileExistsError, OSError) as error:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise Refusal("tailnet-recovery-state-write-failed") from error


def _read_transaction(paths: CommandPaths) -> tuple[dict, SystemSnapshot]:
    path = _transaction_path(paths)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_size > 1_048_576
        ):
            raise Refusal("tailnet-recovery-state-invalid")
        chunks = []
        remaining = 1_048_577
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise Refusal("tailnet-recovery-state-invalid") from error
    finally:
        if "fd" in locals():
            os.close(fd)
    value = _bounded_json(
        payload.decode("utf-8"), reason="tailnet-recovery-state-invalid"
    )
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "generation",
            "nonce",
            "phase",
            "original_backend_state",
            "snapshot",
        }
        or value["schema_version"] != 1
        or value["generation"] != RECOVERY_GENERATION
        or not isinstance(value["nonce"], str)
        or re.fullmatch(r"[0-9a-f]{32}", value["nonce"]) is None
        or value["phase"] not in {"armed", "confirmed"}
        or value["original_backend_state"] != "NeedsLogin"
        or payload != _canonical_bytes(value)
    ):
        raise Refusal("tailnet-recovery-state-invalid")
    return value, _parse_snapshot(value["snapshot"])


def _mark_transaction_confirmed(paths: CommandPaths) -> None:
    value, _snapshot_value = _read_transaction(paths)
    if value["phase"] == "confirmed":
        return
    value["phase"] = "confirmed"
    payload = _canonical_bytes(value)
    temporary = (
        paths.state_directory / f".{TRANSACTION_NAME}.{value['nonce']}.confirmed"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(temporary, flags, 0o600)
        os.fchmod(fd, 0o600)
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(temporary, _transaction_path(paths))
        _fsync_directory(paths.state_directory)
    except OSError as error:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            current, _ = _read_transaction(paths)
        except (FileNotFoundError, Refusal):
            raise Refusal("tailnet-recovery-confirm-uncertain") from error
        if current != value:
            raise Refusal("tailnet-recovery-confirm-uncertain") from error


def _remove_transaction(paths: CommandPaths, *, phase: str) -> None:
    path = _transaction_path(paths)
    try:
        metadata = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise Refusal("tailnet-recovery-state-invalid")
        value, _ = _read_transaction(paths)
        if value["phase"] != phase:
            raise Refusal("tailnet-recovery-state-invalid")
        path.unlink()
        try:
            _fsync_directory(paths.state_directory)
        except OSError:
            # Confirmation was committed before cleanup. A possible reappearing
            # confirmed receipt is cleanup debt and never authorizes rollback.
            if path.exists():
                raise
    except OSError as error:
        raise Refusal("tailnet-recovery-state-cleanup-failed") from error


def _run(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Refusal("tailnet-command-failed") from error
    if result.returncode != 0:
        raise Refusal("tailnet-command-failed")
    return result


def _bounded_json(text: str, *, reason: str, limit: int = 262_144):
    if len(text.encode()) > limit:
        raise Refusal(reason)
    try:
        return json.loads(text)
    except (TypeError, ValueError) as error:
        raise Refusal(reason) from error


def validate_sources(sources) -> list[str]:
    if not isinstance(sources, list) or not sources:
        raise Refusal("tailnet-approved-sources-invalid")
    result: list[str] = []
    for raw in sources:
        if not isinstance(raw, str) or not raw or "/" in raw:
            raise Refusal("tailnet-approved-sources-invalid")
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise Refusal("tailnet-approved-sources-invalid") from error
        if address not in (TAILNET_V4 if address.version == 4 else TAILNET_V6):
            raise Refusal("tailnet-approved-sources-invalid")
        canonical = str(address)
        if canonical != raw or canonical in result:
            raise Refusal("tailnet-approved-sources-invalid")
        result.append(canonical)
    return result


def _status(paths: CommandPaths, runner: Runner) -> str:
    output = runner(
        [paths.tailscale, "status", "--json"], timeout=COMMAND_TIMEOUT_SECONDS
    ).stdout
    value = _bounded_json(output, reason="tailnet-status-invalid")
    state = value.get("BackendState") if isinstance(value, dict) else None
    if state not in {"Running", "NeedsLogin", "Stopped"}:
        raise Refusal("tailnet-status-invalid")
    return state


def _preferences(paths: CommandPaths, runner: Runner) -> dict:
    output = runner(
        [paths.tailscale, "get", "--json", "all"],
        timeout=COMMAND_TIMEOUT_SECONDS,
    ).stdout
    value = _bounded_json(output, reason="tailnet-preferences-invalid")
    if not isinstance(value, dict):
        raise Refusal("tailnet-preferences-invalid")
    return value


def _require_expected_preferences(preferences: dict) -> None:
    if any(
        preferences.get(key) != expected for key, expected in EXPECTED_PREFS.items()
    ):
        raise Refusal("tailnet-preferences-mismatch")


def _canonical_default_routes(paths: CommandPaths, runner: Runner) -> bytes:
    volatile_keys = frozenset(
        {
            "age",
            "cache",
            "expires",
            "lastuse",
            "statistics",
            "used",
        }
    )

    def stable(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: stable(item)
                for key, item in value.items()
                if key not in volatile_keys
            }
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value

    routes = {}
    for family in ("-4", "-6"):
        output = runner(
            [paths.ip, family, "-json", "route", "show", "default"],
            timeout=COMMAND_TIMEOUT_SECONDS,
        ).stdout
        value = _bounded_json(output, reason="tailnet-routing-invalid")
        if not isinstance(value, list):
            raise Refusal("tailnet-routing-invalid")
        routes[family] = stable(value)
    return json.dumps(routes, sort_keys=True, separators=(",", ":")).encode()


def _sshd_policy(paths: CommandPaths, runner: Runner) -> bytes:
    output = runner([paths.sshd, "-T"], timeout=COMMAND_TIMEOUT_SECONDS).stdout.encode()
    if not output or len(output) > 262_144:
        raise Refusal("tailnet-sshd-policy-invalid")
    return output


def _snapshot(paths: CommandPaths, runner: Runner) -> SystemSnapshot:
    try:
        resolver = paths.resolv_conf.read_bytes()
        resolver_metadata = paths.resolv_conf.stat()
    except OSError as error:
        raise Refusal("tailnet-resolver-unreadable") from error
    if not resolver or len(resolver) > 262_144:
        raise Refusal("tailnet-resolver-unreadable")
    return SystemSnapshot(
        resolver=resolver,
        routes=_canonical_default_routes(paths, runner),
        sshd=_sshd_policy(paths, runner),
        resolver_mode=stat.S_IMODE(resolver_metadata.st_mode),
        resolver_uid=resolver_metadata.st_uid,
        resolver_gid=resolver_metadata.st_gid,
    )


def _require_no_tailscale_firewall(paths: CommandPaths, runner: Runner) -> None:
    output = runner(
        [paths.nft, "-j", "list", "ruleset"], timeout=COMMAND_TIMEOUT_SECONDS
    ).stdout
    ruleset = _bounded_json(output, reason="tailnet-firewall-state-invalid")

    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    for item in walk(ruleset):
        names = [item.get("name"), item.get("jump"), item.get("goto")]
        if any(isinstance(name, str) and name.startswith("ts-") for name in names):
            raise Refusal("tailnet-netfilter-not-off")


def _require_tailnet_addresses(paths: CommandPaths, runner: Runner) -> None:
    for flag, network in (("-4", TAILNET_V4), ("-6", TAILNET_V6)):
        raw = runner(
            [paths.tailscale, "ip", flag], timeout=COMMAND_TIMEOUT_SECONDS
        ).stdout.strip()
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise Refusal("tailnet-address-invalid") from error
        if address not in network:
            raise Refusal("tailnet-address-invalid")


def _validate_auth_directory(path: Path) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Refusal("tailnet-auth-directory-unsafe") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise Refusal("tailnet-auth-directory-unsafe")


def _write_auth_file(directory: Path, auth_key: str) -> Path:
    if (
        not isinstance(auth_key, str)
        or not auth_key
        or re.fullmatch(r"tskey-auth-[A-Za-z0-9_-]{8,480}", auth_key) is None
        or "\x00" in auth_key
        or "\n" in auth_key
        or "\r" in auth_key
        or not auth_key.isascii()
        or auth_key.strip() != auth_key
    ):
        raise Refusal("tailnet-auth-required")
    _validate_auth_directory(directory)
    name = f"vpn-tailnet-auth-{secrets.token_hex(16)}"
    path = directory / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            payload = (auth_key + "\n").encode()
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError("short write")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as error:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass  # The typed refusal remains authoritative; the role runs in /run.
        raise Refusal("tailnet-auth-file-failed") from error
    return path


def _remove_auth_file(path: Path) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise Refusal("tailnet-auth-file-cleanup-failed")
        path.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as error:
        raise Refusal("tailnet-auth-file-cleanup-failed") from error


def _postconditions(
    *, paths: CommandPaths, runner: Runner, before: SystemSnapshot
) -> None:
    if _status(paths, runner) != "Running":
        raise Refusal("tailnet-enrollment-incomplete")
    _require_expected_preferences(_preferences(paths, runner))
    _require_tailnet_addresses(paths, runner)
    _require_no_tailscale_firewall(paths, runner)
    after = _snapshot(paths, runner)
    reasons = (
        "tailnet-resolver-drift",
        "tailnet-routing-drift",
        "tailnet-sshd-policy-drift",
    )
    for current, expected, reason in zip(
        (after.resolver, after.routes, after.sshd),
        (before.resolver, before.routes, before.sshd),
        reasons,
        strict=True,
    ):
        if current != expected:
            raise Refusal(reason)
    if (
        after.resolver_mode,
        after.resolver_uid,
        after.resolver_gid,
    ) != (
        before.resolver_mode,
        before.resolver_uid,
        before.resolver_gid,
    ):
        raise Refusal("tailnet-resolver-drift")


def _require_recovery_ready(paths: CommandPaths, runner: Runner) -> None:
    runner(
        [paths.systemctl, "is-enabled", "vpn-tailnet-recover.timer"],
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    runner(
        [paths.systemctl, "is-active", "vpn-tailnet-recover.timer"],
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def _recover_locked(*, paths: CommandPaths, runner: Runner) -> dict[str, object]:
    try:
        transaction, before = _read_transaction(paths)
    except FileNotFoundError:
        return {"status": "idle", "changed": False}
    if transaction["phase"] == "confirmed":
        _remove_transaction(paths, phase="confirmed")
        return {"status": "confirmed", "changed": True}
    state = _status(paths, runner)
    changed = False
    if state == "Running":
        runner([paths.tailscale, "logout"], timeout=COMMAND_TIMEOUT_SECONDS)
        changed = True
    elif state != "NeedsLogin":
        raise Refusal("tailnet-rollback-uncertain")
    if _status(paths, runner) != "NeedsLogin":
        raise Refusal("tailnet-rollback-uncertain")
    _require_no_tailscale_firewall(paths, runner)
    if _snapshot(paths, runner) != before:
        raise Refusal("tailnet-rollback-uncertain")
    _remove_transaction(paths, phase="armed")
    return {"status": "rolled_back", "changed": changed}


def recover(*, paths: CommandPaths, runner: Runner = _run) -> dict[str, object]:
    with _transaction_lock(paths, blocking=False):
        return _recover_locked(paths=paths, runner=runner)


def configure(
    *, paths: CommandPaths, runner: Runner = _run, auth_key: str
) -> dict[str, object]:
    with _transaction_lock(paths, blocking=True):
        try:
            recovered = _recover_locked(paths=paths, runner=runner)
        except Refusal:
            raise
        before = _snapshot(paths, runner)
        state = _status(paths, runner)
        if state == "Running":
            _require_expected_preferences(_preferences(paths, runner))
            _postconditions(paths=paths, runner=runner, before=before)
            return {"status": "configured", "changed": recovered["changed"]}
        if state != "NeedsLogin":
            raise Refusal("tailnet-existing-state-unsupported")

        auth_path = _write_auth_file(paths.auth_directory, auth_key)
        primary_error: BaseException | None = None
        try:
            _require_recovery_ready(paths, runner)
            _write_transaction(paths, backend_state=state, snapshot=before)
            runner(
                [
                    paths.tailscale,
                    "login",
                    f"--auth-key=file:{auth_path}",
                    "--accept-dns=false",
                    "--accept-routes=false",
                    "--advertise-exit-node=false",
                    "--advertise-routes=",
                    "--exit-node=",
                    "--netfilter-mode=off",
                    "--shields-up=false",
                    "--ssh=false",
                    "--timeout=30s",
                ],
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
            _remove_auth_file(auth_path)
            auth_path = None
            _postconditions(paths=paths, runner=runner, before=before)
            _mark_transaction_confirmed(paths)
            _remove_transaction(paths, phase="confirmed")
            return {"status": "configured", "changed": True}
        except (Exception, KeyboardInterrupt, SystemExit) as error:
            primary_error = error
            try:
                outcome = _recover_locked(paths=paths, runner=runner)
            except (Exception, KeyboardInterrupt, SystemExit) as cleanup_error:
                raise Refusal("tailnet-rollback-uncertain") from cleanup_error
            if outcome["status"] == "confirmed":
                return {"status": "configured", "changed": True}
            if isinstance(error, Refusal):
                raise
            raise Refusal("tailnet-enrollment-failed") from error
        finally:
            if auth_path is not None:
                try:
                    _remove_auth_file(auth_path)
                except Refusal:
                    if primary_error is not None:
                        raise Refusal(
                            "tailnet-auth-file-cleanup-failed"
                        ) from primary_error
                    raise


def check(*, paths: CommandPaths, runner: Runner = _run) -> dict[str, object]:
    """Inspect the exact managed state without enrollment or another mutation."""
    with _transaction_lock(paths, blocking=False):
        if _transaction_path(paths).exists():
            raise Refusal("tailnet-recovery-pending")
        before = _snapshot(paths, runner)
        state = _status(paths, runner)
        if state == "NeedsLogin":
            return {"status": "pending", "changed": True}
        if state != "Running":
            raise Refusal("tailnet-existing-state-unsupported")
        _require_expected_preferences(_preferences(paths, runner))
        _postconditions(paths=paths, runner=runner, before=before)
        return {"status": "configured", "changed": False}


def _resolve_command(*candidates: str) -> str:
    for candidate in candidates:
        path = Path(candidate)
        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError:
            continue
        if (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == 0
            and not metadata.st_mode & 0o022
            and os.access(path, os.X_OK)
        ):
            return str(path)
    raise Refusal("tailnet-command-unavailable")


def _production_paths() -> CommandPaths:
    return CommandPaths(
        tailscale=_resolve_command("/usr/bin/tailscale", "/usr/local/bin/tailscale"),
        sshd=_resolve_command("/usr/sbin/sshd", "/usr/bin/sshd"),
        ip=_resolve_command("/usr/sbin/ip", "/usr/bin/ip"),
        nft=_resolve_command("/usr/sbin/nft", "/usr/bin/nft"),
        resolv_conf=Path("/etc/resolv.conf"),
        auth_directory=Path("/run"),
        state_directory=Path("/var/lib/vpn-tailnet-management"),
        systemctl=_resolve_command("/usr/bin/systemctl", "/bin/systemctl"),
    )


def _read_stdin(limit: int) -> str:
    value = sys.stdin.read(limit + 1)
    if len(value.encode()) > limit:
        raise Refusal("tailnet-input-invalid")
    return value
