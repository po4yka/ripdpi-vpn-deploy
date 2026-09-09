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
import time
from uuid import UUID
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
RECOVERY_GENERATION = "tailnet-recovery-v2"
LEASE_SECONDS = 300
CONFIRMED_NAME = "confirmed.json"
TRANSACTION_NAME = "transaction.json"
LOCK_NAME = "transaction.lock"
RECOVERY_STATE_MAX_BYTES = 1_048_576
AUTH_FILE_PREFIX = "vpn-tailnet-auth-"


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


def _lease_clock():
    try:
        boot = str(UUID(Path("/proc/sys/kernel/random/boot_id").read_text().strip()))
    except (OSError, ValueError) as error:
        raise Refusal("tailnet-boot-identity-invalid") from error
    return boot, time.monotonic_ns() // 1_000_000


def validate_binding(value):
    if not isinstance(value, dict) or set(value) != {
        "inventory_alias", "public_address", "ssh_port", "public_sources",
        "approved_sources", "host_key_sha256", "source_revision", "deployable_digest",
    }:
        raise Refusal("tailnet-binding-invalid")
    if (not isinstance(value["inventory_alias"], str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value["inventory_alias"]) is None
            or type(value["ssh_port"]) is not int or not 1 <= value["ssh_port"] <= 65535):
        raise Refusal("tailnet-binding-invalid")
    for field, length in (("host_key_sha256", 64), ("source_revision", 40), ("deployable_digest", 64)):
        if not isinstance(value[field], str) or re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value[field]) is None:
            raise Refusal("tailnet-binding-invalid")
    validate_sources(value["approved_sources"])
    sources = value["public_sources"]
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 8
            or any(not isinstance(source, str) for source in sources)
            or len(set(sources)) != len(sources)):
        raise Refusal("tailnet-binding-invalid")
    for raw in [value["public_address"], *sources]:
        try:
            address = ipaddress.ip_address(raw)
        except (ValueError, TypeError) as error:
            raise Refusal("tailnet-binding-invalid") from error
        if (not isinstance(raw, str) or str(address) != raw or address.is_loopback
                or address.is_unspecified or address.is_link_local or address.is_multicast
                or address in (TAILNET_V4 if address.version == 4 else TAILNET_V6)):
            raise Refusal("tailnet-binding-invalid")
    return value


def _publish_record(paths, value, *, name):
    nonce = value["nonce"]
    payload = _canonical_bytes(value)
    recovery_payload = _canonical_bytes({**value, "phase": "firewall_restored"})
    if max(len(payload), len(recovery_payload)) > RECOVERY_STATE_MAX_BYTES:
        raise Refusal("tailnet-recovery-state-write-failed")
    temporary = paths.state_directory / f".{name}.{nonce}"
    canonical = paths.state_directory / name
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
            # Preserve the original write failure; the unpublished random-name
            # file is never considered recovery state or safe to reuse.
            pass
        raise Refusal("tailnet-recovery-state-write-failed") from error



def _write_transaction(
    paths: CommandPaths, *, backend_state: str, snapshot: SystemSnapshot,
    auth_file: str, binding: dict, firewall_snapshot: dict, clock=_lease_clock,
) -> dict:
    validate_binding(binding)
    if (backend_state != "NeedsLogin"
            or re.fullmatch(r"vpn-tailnet-auth-[0-9a-f]{32}", auth_file) is None
            or not isinstance(firewall_snapshot, dict)):
        raise Refusal("tailnet-recovery-state-invalid")
    boot, monotonic = clock()
    if str(UUID(boot)) != boot or type(monotonic) is not int or monotonic < 0:
        raise Refusal("tailnet-boot-identity-invalid")
    value = {
        "schema_version": 2, "generation": RECOVERY_GENERATION,
        "nonce": secrets.token_hex(16), "phase": "armed",
        "original_backend_state": backend_state, "auth_file": auth_file,
        "snapshot": _snapshot_document(snapshot), "binding": binding,
        "firewall": firewall_snapshot,
        "lease": {"boot_id": boot, "started_ms": monotonic,
                  "deadline_ms": monotonic + LEASE_SECONDS * 1000},
    }
    _publish_record(paths, value, name=TRANSACTION_NAME)
    return value


def _read_transaction(paths: CommandPaths, *, name=TRANSACTION_NAME) -> tuple[dict, SystemSnapshot]:
    path = paths.state_directory / name
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
            or metadata.st_nlink not in {1, 2}
            or metadata.st_size > RECOVERY_STATE_MAX_BYTES
        ):
            raise Refusal("tailnet-recovery-state-invalid")
        chunks = []
        remaining = RECOVERY_STATE_MAX_BYTES + 1
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
        payload.decode("utf-8"),
        reason="tailnet-recovery-state-invalid",
        limit=RECOVERY_STATE_MAX_BYTES,
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
            "auth_file",
            "snapshot", "binding", "firewall", "lease",
        }
        or value["schema_version"] != 2
        or value["generation"] != RECOVERY_GENERATION
        or not isinstance(value["nonce"], str)
        or re.fullmatch(r"[0-9a-f]{32}", value["nonce"]) is None
        or value["phase"] not in {"armed", "rolling_back", "firewall_restored", "confirmed"}
        or value["original_backend_state"] != "NeedsLogin"
        or not isinstance(value["auth_file"], str)
        or re.fullmatch(r"vpn-tailnet-auth-[0-9a-f]{32}", value["auth_file"]) is None
        or payload != _canonical_bytes(value)
    ):
        raise Refusal("tailnet-recovery-state-invalid")
    validate_binding(value["binding"])
    lease = value["lease"]
    if (not isinstance(lease, dict) or set(lease) != {"boot_id", "started_ms", "deadline_ms"}
            or not isinstance(lease["boot_id"], str)
            or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", lease["boot_id"]) is None
            or type(lease["started_ms"]) is not int or lease["started_ms"] < 0
            or type(lease["deadline_ms"]) is not int
            or lease["deadline_ms"] - lease["started_ms"] != LEASE_SECONDS * 1000
            or not isinstance(value["firewall"], dict)):
        raise Refusal("tailnet-recovery-state-invalid")
    snapshot = _parse_snapshot(value["snapshot"])
    if metadata.st_nlink == 2:
        interrupted = paths.state_directory / f".{name}.{value['nonce']}"
        try:
            interrupted_metadata = interrupted.stat(follow_symlinks=False)
            if (
                not stat.S_ISREG(interrupted_metadata.st_mode)
                or (interrupted_metadata.st_dev, interrupted_metadata.st_ino)
                != (metadata.st_dev, metadata.st_ino)
                or interrupted_metadata.st_uid != os.geteuid()
                or stat.S_IMODE(interrupted_metadata.st_mode) != 0o600
            ):
                raise Refusal("tailnet-recovery-state-invalid")
            interrupted.unlink()
            _fsync_directory(paths.state_directory)
            canonical_metadata = path.stat(follow_symlinks=False)
            if (canonical_metadata.st_dev, canonical_metadata.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ) or canonical_metadata.st_nlink != 1:
                raise Refusal("tailnet-recovery-state-invalid")
        except OSError as error:
            raise Refusal("tailnet-recovery-state-invalid") from error
    return value, snapshot


def _mark_transaction_confirmed(paths: CommandPaths) -> None:
    _transition(paths, "confirmed", allowed={"armed"})


def _transition(paths, phase, *, allowed):
    """Publish one monotonic state change under the transaction lock."""
    value, _snapshot_value = _read_transaction(paths)
    if value["phase"] == phase:
        # A prior directory fsync may have failed after the rename.
        _fsync_directory(paths.state_directory)
        return
    if value["phase"] not in allowed:
        raise Refusal("tailnet-recovery-transition-invalid")
    value["phase"] = phase
    payload = _canonical_bytes(value)
    if len(payload) > RECOVERY_STATE_MAX_BYTES:
        raise Refusal("tailnet-recovery-confirm-uncertain")
    temporary = (
        paths.state_directory / f".{TRANSACTION_NAME}.{value['nonce']}.{phase}"
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
            # Preserve the confirmation failure. The canonical receipt is
            # re-read below and remains the only authority for commit status.
            pass
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
            if phase != "confirmed" or path.exists():
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


def canonical_sources_fragment(sources: list[str]) -> str:
    """Render validated host addresses in the transaction fragment grammar."""
    canonical = validate_sources(sources)
    by_version = {
        version: sorted(
            (
                f"{source}/{'32' if version == 4 else '128'}"
                for source in canonical
                if ipaddress.ip_address(source).version == version
            ),
            key=lambda token: int(ipaddress.ip_network(token).network_address),
        )
        for version in (4, 6)
    }

    def elements(values: list[str]) -> str:
        return "" if not values else f"  elements = {{ {', '.join(values)} }}\n"

    return (
        "# vpn-tailnet-ssh-sets schema=1\n"
        "set vpn_tailnet_ssh_v4 {\n"
        "  type ipv4_addr\n"
        "  flags interval\n"
        f"{elements(by_version[4])}"
        "}\n\n"
        "set vpn_tailnet_ssh_v6 {\n"
        "  type ipv6_addr\n"
        "  flags interval\n"
        f"{elements(by_version[6])}"
        "}\n"
    )


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
    # getaddrinfo can enumerate the same listening endpoints differently in
    # the recovery unit's address-family sandbox. Canonicalize only those
    # lines, preserving every endpoint, duplicate and other policy byte.
    lines = output.splitlines(keepends=True)
    positions = [index for index, line in enumerate(lines) if line.startswith(b"listenaddress ")]
    listeners = sorted(lines[index] for index in positions)
    for index, listener in zip(positions, listeners):
        lines[index] = listener
    return b"".join(lines)


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
        [paths.nft, "-j", "list", "chains"], timeout=COMMAND_TIMEOUT_SECONDS
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


def _require_tailnet_addresses(paths: CommandPaths, runner: Runner) -> dict:
    reported = set()
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
        reported.add(address)
    document = _bounded_json(
        runner(
            [paths.ip, "-json", "address", "show", "dev", "tailscale0"],
            timeout=COMMAND_TIMEOUT_SECONDS,
        ).stdout,
        reason="tailnet-address-invalid",
    )
    if (
        not isinstance(document, list)
        or len(document) != 1
        or not isinstance(document[0], dict)
        or document[0].get("ifname") != "tailscale0"
        or not isinstance(document[0].get("addr_info"), list)
    ):
        raise Refusal("tailnet-address-invalid")
    assigned = set()
    try:
        for item in document[0]["addr_info"]:
            if not isinstance(item, dict) or not isinstance(item.get("local"), str):
                raise ValueError
            assigned.add(ipaddress.ip_address(item["local"]))
    except ValueError as error:
        raise Refusal("tailnet-address-invalid") from error
    if not reported <= assigned:
        raise Refusal("tailnet-address-invalid")
    return {"ipv" + str(address.version): str(address) for address in reported}


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


def _validate_auth_key(auth_key: str) -> None:
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


def _write_auth_file(directory: Path, auth_key: str, *, name: str) -> Path:
    _validate_auth_key(auth_key)
    if re.fullmatch(r"vpn-tailnet-auth-[0-9a-f]{32}", name) is None:
        raise Refusal("tailnet-auth-file-failed")
    _validate_auth_directory(directory)
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


def _remove_recovery_auth_file(paths: CommandPaths, transaction: dict) -> None:
    _validate_auth_directory(paths.auth_directory)
    path = paths.auth_directory / transaction["auth_file"]
    try:
        path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise Refusal("tailnet-auth-file-cleanup-failed") from error
    _remove_auth_file(path)


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


def _require_recovery_scheduler(paths: CommandPaths, runner: Runner) -> None:
    runner(
        [paths.systemctl, "is-enabled", "vpn-tailnet-recover.timer"],
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    runner(
        [paths.systemctl, "is-active", "vpn-tailnet-recover.timer"],
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def _require_recovery_service_success(paths: CommandPaths, runner: Runner) -> None:
    status = runner(
        [
            paths.systemctl,
            "show",
            "vpn-tailnet-recover.service",
            "--property=Result",
            "--property=ExecMainCode",
            "--property=ExecMainStatus",
            "--no-pager",
        ],
        timeout=COMMAND_TIMEOUT_SECONDS,
    ).stdout
    fields = {}
    for line in status.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key in fields:
            raise Refusal("tailnet-recovery-unavailable")
        fields[key] = value
    if fields != {
        "Result": "success",
        "ExecMainCode": "1",
        "ExecMainStatus": "0",
    }:
        raise Refusal("tailnet-recovery-unavailable")


def _require_recovery_ready(paths: CommandPaths, runner: Runner) -> None:
    _require_recovery_scheduler(paths, runner)
    runner(
        [paths.systemctl, "start", "vpn-tailnet-recover.service"],
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    _require_recovery_service_success(paths, runner)


def _revalidate_recovery_ready(paths: CommandPaths, runner: Runner) -> None:
    _require_recovery_scheduler(paths, runner)
    _require_recovery_service_success(paths, runner)


def _expired(transaction, clock):
    boot, now = clock()
    lease = transaction["lease"]
    return (boot != lease["boot_id"] or type(now) is not int
            or now < lease["started_ms"] or now >= lease["deadline_ms"])


def _owned_identity(paths, runner, transaction):
    document = _bounded_json(runner(
        [paths.tailscale, "status", "--json"], timeout=COMMAND_TIMEOUT_SECONDS,
    ).stdout, reason="tailnet-identity-invalid")
    value = document.get("Self") if isinstance(document, dict) else None
    expected_hostname = "vpn-enroll-" + transaction["nonce"]
    if (not isinstance(value, dict) or document.get("BackendState") != "Running"
            or value.get("HostName") != expected_hostname
            or not isinstance(value.get("ID"), str)
            or re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", value["ID"]) is None):
        raise Refusal("tailnet-identity-mismatch")
    return {"id": value["ID"], "hostname": expected_hostname}


def _node(paths, runner, transaction):
    return {**_owned_identity(paths, runner, transaction),
            **_require_tailnet_addresses(paths, runner)}


def _capability(transaction, node, *, configured=False):
    return {
        "status": "configured" if configured else "pending", "changed": not configured,
        "nonce": transaction["nonce"], "generation": transaction["generation"],
        "binding_sha256": hashlib.sha256(_canonical_bytes(transaction["binding"])).hexdigest(),
        "lease": transaction["lease"], "node": node,
    }


def _match_capability(transaction, capability):
    if (not isinstance(capability, dict)
            or set(capability) != {"status", "changed", "nonce", "generation", "binding_sha256", "lease", "node"}
            or capability["status"] != "pending" or capability["changed"] is not True
            or capability["nonce"] != transaction["nonce"]
            or capability["generation"] != transaction["generation"]
            or capability["lease"] != transaction["lease"]
            or capability["binding_sha256"] != hashlib.sha256(_canonical_bytes(transaction["binding"])).hexdigest()):
        raise Refusal("tailnet-confirmation-invalid")


def _archive_confirmation(paths, transaction):
    try:
        previous, _ = _read_transaction(paths, name=CONFIRMED_NAME)
    except FileNotFoundError:
        _publish_record(paths, transaction, name=CONFIRMED_NAME)
    else:
        if previous != transaction:
            raise Refusal("tailnet-confirmation-conflict")
    _fsync_directory(paths.state_directory)


def _recover_locked(*, paths, runner, firewall, clock, force=False):
    try:
        transaction, before = _read_transaction(paths)
    except FileNotFoundError:
        return {"status": "idle", "changed": False}
    firewall.validate_snapshot(transaction["firewall"])
    if transaction["phase"] == "armed" and not force and not _expired(transaction, clock):
        return {"status": "pending", "changed": False}
    _remove_recovery_auth_file(paths, transaction)
    if transaction["phase"] == "confirmed":
        try:
            _fsync_directory(paths.state_directory)
            _archive_confirmation(paths, transaction)
        except OSError as error:
            raise Refusal("tailnet-recovery-confirm-uncertain") from error
        _remove_transaction(paths, phase="confirmed")
        return {"status": "confirmed", "changed": True}
    if transaction["phase"] == "armed":
        _transition(paths, "rolling_back", allowed={"armed"})
        transaction, before = _read_transaction(paths)
    state = _status(paths, runner)
    changed = False
    if state == "Running":
        # A random transaction hostname survives a crash immediately after login,
        # before the controller can record Self.ID. Never log out a foreign identity.
        _owned_identity(paths, runner, transaction)
        runner([paths.tailscale, "logout"], timeout=COMMAND_TIMEOUT_SECONDS)
        changed = True
    elif state != "NeedsLogin":
        raise Refusal("tailnet-rollback-uncertain")
    if _status(paths, runner) != "NeedsLogin":
        raise Refusal("tailnet-rollback-uncertain")
    _require_no_tailscale_firewall(paths, runner)
    firewall.restore(transaction["firewall"], transaction["binding"])
    if _snapshot(paths, runner) != before:
        raise Refusal("tailnet-rollback-uncertain")
    _remove_transaction(paths, phase=transaction["phase"])
    return {"status": "rolled_back", "changed": changed}


def recover(*, paths: CommandPaths, firewall, runner: Runner = _run, clock=_lease_clock):
    with _transaction_lock(paths, blocking=False):
        return _recover_locked(paths=paths, runner=runner, firewall=firewall, clock=clock)


def recover_firewall(*, paths: CommandPaths, firewall):
    """Early boot phase: no daemon, resolver, route, or service-start dependency.

    Invocation is the boot gate, not the periodic worker. Every unconfirmed
    transaction is rolled back regardless of its lease. The adapter must use
    only files and netlink here; service activation belongs to late recovery.
    """
    with _transaction_lock(paths, blocking=False):
        try:
            transaction, _ = _read_transaction(paths)
        except FileNotFoundError:
            return {"status": "idle", "changed": False}
        if transaction["phase"] == "confirmed":
            _fsync_directory(paths.state_directory)
            return {"status": "confirmed", "changed": False}
        firewall.validate_snapshot(transaction["firewall"])
        if transaction["phase"] == "armed":
            _transition(paths, "rolling_back", allowed={"armed"})
        else:
            _fsync_directory(paths.state_directory)
        # Replay restoration even after firewall_restored: this might be a
        # second reboot, with an empty kernel ruleset and a persisted journal.
        firewall.restore(transaction["firewall"], transaction["binding"], early_boot=True)
        _transition(paths, "firewall_restored", allowed={"rolling_back"})
        return {"status": "firewall_restored", "changed": True}


def enroll(*, paths: CommandPaths, firewall, binding: dict, auth_key: str,
           runner: Runner = _run, clock=_lease_clock):
    """Arm access, enroll, and return an unconfirmed capability for external proof."""
    validate_binding(binding)
    _require_recovery_ready(paths, runner)
    with _transaction_lock(paths, blocking=False):
        recovered = _recover_locked(paths=paths, runner=runner, firewall=firewall, clock=clock)
        if recovered["status"] == "pending":
            raise Refusal("tailnet-recovery-pending")
        before = _snapshot(paths, runner)
        state = _status(paths, runner)
        if state == "Running":
            try:
                previous, _ = _read_transaction(paths, name=CONFIRMED_NAME)
            except FileNotFoundError:
                raise Refusal("tailnet-unowned-existing-identity") from None
            if previous["binding"] != binding:
                raise Refusal("tailnet-binding-mismatch")
            _postconditions(paths=paths, runner=runner, before=before)
            return _capability(previous, _node(paths, runner, previous), configured=True)
        if state != "NeedsLogin":
            raise Refusal("tailnet-existing-state-unsupported")
        if (paths.state_directory / CONFIRMED_NAME).exists():
            raise Refusal("tailnet-confirmed-identity-missing")
        _validate_auth_key(auth_key)
        firewall_snapshot = firewall.snapshot(binding)
        firewall.validate_snapshot(firewall_snapshot)
        auth_name = f"{AUTH_FILE_PREFIX}{secrets.token_hex(16)}"
        try:
            _revalidate_recovery_ready(paths, runner)
            transaction = _write_transaction(paths, backend_state=state, snapshot=before,
                auth_file=auth_name, binding=binding, firewall_snapshot=firewall_snapshot, clock=clock)
            firewall.apply(firewall_snapshot, binding)
            auth_path = _write_auth_file(paths.auth_directory, auth_key, name=auth_name)
            try:
                runner([
                    paths.tailscale, "login", f"--auth-key=file:{auth_path}",
                    "--hostname=vpn-enroll-" + transaction["nonce"],
                    "--accept-dns=false", "--accept-routes=false",
                    "--advertise-exit-node=false", "--advertise-routes=", "--exit-node=",
                    "--netfilter-mode=off", "--shields-up=false", "--ssh=false", "--timeout=30s",
                ], timeout=COMMAND_TIMEOUT_SECONDS)
            finally:
                _remove_auth_file(auth_path)
            _postconditions(paths=paths, runner=runner, before=before)
            firewall.verify(firewall_snapshot, binding)
            if _expired(transaction, clock):
                raise Refusal("tailnet-transaction-expired")
            return _capability(transaction, _node(paths, runner, transaction))
        except (Exception, KeyboardInterrupt, SystemExit) as error:
            try:
                _recover_locked(paths=paths, runner=runner, firewall=firewall, clock=clock, force=True)
            except (Exception, KeyboardInterrupt, SystemExit) as cleanup_error:
                if isinstance(cleanup_error, Refusal) and str(cleanup_error) == "tailnet-auth-file-cleanup-failed":
                    raise
                raise Refusal("tailnet-rollback-uncertain") from cleanup_error
            if isinstance(error, Refusal):
                raise
            raise Refusal("tailnet-enrollment-failed") from error


def _validate_external_contexts(binding, node, contexts):
    from sshd_contexts import ContextError, bind_contexts
    try:
        if not isinstance(contexts, list):
            raise ValueError
        management = {item["laddr"] for item in contexts if item["laddr"] != binding["public_address"]}
        if len(management) != 1 or not management <= {node["ipv4"], node["ipv6"]}:
            raise ValueError
        bind_contexts(contexts, binding["public_address"], next(iter(management)), binding["ssh_port"])
        for item in contexts:
            sources = binding["public_sources"] if item["laddr"] == binding["public_address"] else binding["approved_sources"]
            if item["addr"] not in sources or ipaddress.ip_address(item["addr"]).version != ipaddress.ip_address(item["laddr"]).version:
                raise ValueError
    except (ValueError, KeyError, TypeError, ContextError):
        raise Refusal("tailnet-path-proof-invalid") from None


def confirm(*, paths, firewall, capability, contexts, runner=_run, clock=_lease_clock):
    with _transaction_lock(paths, blocking=False):
        transaction, before = _read_transaction(paths)
        _match_capability(transaction, capability)
        if transaction["phase"] != "armed" or _expired(transaction, clock):
            raise Refusal("tailnet-transaction-expired")
        node = _node(paths, runner, transaction)
        if node != capability["node"]:
            raise Refusal("tailnet-identity-mismatch")
        _validate_external_contexts(transaction["binding"], node, contexts)
        firewall.validate_snapshot(transaction["firewall"])
        firewall.verify(transaction["firewall"], transaction["binding"])
        _postconditions(paths=paths, runner=runner, before=before)
        if _expired(transaction, clock):
            raise Refusal("tailnet-transaction-expired")
        _mark_transaction_confirmed(paths)
        # Confirmed publication is the commit point. A later archive or output
        # failure reports uncertainty but must never authorize an enrollment logout.
        outcome = _recover_locked(paths=paths, runner=runner, firewall=firewall, clock=clock)
        if outcome["status"] != "confirmed":
            raise Refusal("tailnet-recovery-confirm-uncertain")
        return _capability(transaction, node, configured=True)


def rollback(*, paths, firewall, capability, runner=_run, clock=_lease_clock):
    with _transaction_lock(paths, blocking=False):
        transaction, _ = _read_transaction(paths)
        _match_capability(transaction, capability)
        if transaction["phase"] == "confirmed":
            raise Refusal("tailnet-already-confirmed")
        return _recover_locked(paths=paths, runner=runner, firewall=firewall, clock=clock, force=True)


def transaction_status(*, paths, firewall, binding, runner=_run, clock=_lease_clock):
    """Reconcile a lost controller reply without enrolling or logging out."""
    validate_binding(binding)
    with _transaction_lock(paths, blocking=False):
        try:
            transaction, before = _read_transaction(paths)
        except FileNotFoundError:
            try:
                transaction, before = _read_transaction(paths, name=CONFIRMED_NAME)
            except FileNotFoundError:
                return {"status": "idle"}
        if transaction["binding"] != binding:
            raise Refusal("tailnet-binding-mismatch")
        if transaction["phase"] in {"rolling_back", "firewall_restored"}:
            return {"status": transaction["phase"]}
        if transaction["phase"] == "armed" and _expired(transaction, clock):
            return {"status": "expired"}
        _postconditions(paths=paths, runner=runner, before=before)
        firewall.verify(transaction["firewall"], binding)
        node = _node(paths, runner, transaction)
        return _capability(transaction, node, configured=transaction["phase"] == "confirmed")


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
        auth_directory=Path("/run/vpn-tailnet-management"),
        state_directory=Path("/var/lib/vpn-tailnet-management"),
        systemctl=_resolve_command("/usr/bin/systemctl", "/bin/systemctl"),
    )


def _read_stdin(limit: int) -> str:
    value = sys.stdin.read(limit + 1)
    if len(value.encode()) > limit:
        raise Refusal("tailnet-input-invalid")
    return value
