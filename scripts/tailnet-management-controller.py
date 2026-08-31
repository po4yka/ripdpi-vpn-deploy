#!/usr/bin/env python3
"""Configure a node for ordinary OpenSSH over Tailscale.

Usage:
  printf '%s' "$TAILSCALE_AUTH_KEY" | sudo -n \
    /usr/local/lib/vpn-tailnet/tailnet-management-controller.py configure
  printf '%s' '["100.64.1.2","fd7a:115c:a1e0::2"]' | \
    ./scripts/tailnet-management-controller.py validate-sources
  sudo -n /usr/local/lib/vpn-tailnet/tailnet-management-controller.py check

`configure` accepts the one-use enrollment credential on stdin only. It never
prints the credential, the generated auth-file path, Tailscale addresses, host
keys, resolver contents, or route details. The command deliberately refuses an
already-running node whose managed preferences differ; source installation may
not silently rewrite an unrelated existing Tailnet configuration.
"""

from __future__ import annotations

import ipaddress
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


class Refusal(RuntimeError):
    """A typed, redacted refusal safe for operator output."""


class CommandPaths(NamedTuple):
    tailscale: str
    sshd: str
    ip: str
    nft: str
    resolv_conf: Path
    auth_directory: Path


Runner = Callable[..., subprocess.CompletedProcess[str]]


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
    if any(preferences.get(key) != expected for key, expected in EXPECTED_PREFS.items()):
        raise Refusal("tailnet-preferences-mismatch")


def _canonical_default_routes(paths: CommandPaths, runner: Runner) -> bytes:
    routes = {}
    for family in ("-4", "-6"):
        output = runner(
            [paths.ip, family, "-json", "route", "show", "default"],
            timeout=COMMAND_TIMEOUT_SECONDS,
        ).stdout
        value = _bounded_json(output, reason="tailnet-routing-invalid")
        if not isinstance(value, list):
            raise Refusal("tailnet-routing-invalid")
        routes[family] = value
    return json.dumps(routes, sort_keys=True, separators=(",", ":")).encode()


def _sshd_policy(paths: CommandPaths, runner: Runner) -> bytes:
    output = runner(
        [paths.sshd, "-T"], timeout=COMMAND_TIMEOUT_SECONDS
    ).stdout.encode()
    if not output or len(output) > 262_144:
        raise Refusal("tailnet-sshd-policy-invalid")
    return output


def _snapshot(paths: CommandPaths, runner: Runner) -> tuple[bytes, bytes, bytes]:
    try:
        resolver = paths.resolv_conf.read_bytes()
    except OSError as error:
        raise Refusal("tailnet-resolver-unreadable") from error
    if not resolver or len(resolver) > 262_144:
        raise Refusal("tailnet-resolver-unreadable")
    return resolver, _canonical_default_routes(paths, runner), _sshd_policy(paths, runner)


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
    *, paths: CommandPaths, runner: Runner, before: tuple[bytes, bytes, bytes]
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
    for current, expected, reason in zip(after, before, reasons, strict=True):
        if current != expected:
            raise Refusal(reason)


def configure(
    *, paths: CommandPaths, runner: Runner = _run, auth_key: str
) -> dict[str, object]:
    before = _snapshot(paths, runner)
    state = _status(paths, runner)
    if state == "Running":
        _require_expected_preferences(_preferences(paths, runner))
        _postconditions(paths=paths, runner=runner, before=before)
        return {"status": "configured", "changed": False}

    auth_path = _write_auth_file(paths.auth_directory, auth_key)
    enrolled = False
    primary_error: BaseException | None = None
    try:
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
        enrolled = True
        _postconditions(paths=paths, runner=runner, before=before)
        return {"status": "configured", "changed": True}
    except (Exception, KeyboardInterrupt, SystemExit) as error:
        primary_error = error
        if enrolled:
            try:
                runner(
                    [paths.tailscale, "logout"], timeout=COMMAND_TIMEOUT_SECONDS
                )
                if _status(paths, runner) == "Running":
                    raise Refusal("tailnet-rollback-uncertain")
                if _snapshot(paths, runner) != before:
                    raise Refusal("tailnet-rollback-uncertain")
                _require_no_tailscale_firewall(paths, runner)
            except (Exception, KeyboardInterrupt, SystemExit) as cleanup_error:
                raise Refusal("tailnet-rollback-uncertain") from cleanup_error
        if isinstance(error, Refusal):
            raise
        raise Refusal("tailnet-enrollment-failed") from error
    finally:
        try:
            _remove_auth_file(auth_path)
        except Refusal:
            if primary_error is not None:
                raise Refusal("tailnet-auth-file-cleanup-failed") from primary_error
            raise


def check(*, paths: CommandPaths, runner: Runner = _run) -> dict[str, object]:
    """Inspect the exact managed state without enrollment or another mutation."""
    before = _snapshot(paths, runner)
    if _status(paths, runner) != "Running":
        return {"status": "pending", "changed": True}
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
    )


def _read_stdin(limit: int) -> str:
    value = sys.stdin.read(limit + 1)
    if len(value.encode()) > limit:
        raise Refusal("tailnet-input-invalid")
    return value


def main(argv: list[str]) -> int:
    try:
        if argv == ["validate-sources"]:
            value = _bounded_json(
                _read_stdin(8192), reason="tailnet-approved-sources-invalid", limit=8192
            )
            sources = validate_sources(value)
            print(json.dumps({"status": "valid", "count": len(sources)}))
            return 0
        if argv == ["configure"]:
            raw_auth_key = _read_stdin(4096)
            auth_key = raw_auth_key[:-1] if raw_auth_key.endswith("\n") else raw_auth_key
            result = configure(paths=_production_paths(), auth_key=auth_key)
            print(json.dumps(result, sort_keys=True))
            return 0
        if argv == ["check"]:
            result = check(paths=_production_paths())
            print(json.dumps(result, sort_keys=True))
            return 0
        raise Refusal("tailnet-command-invalid")
    except Refusal as error:
        print(json.dumps({"status": "error", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
