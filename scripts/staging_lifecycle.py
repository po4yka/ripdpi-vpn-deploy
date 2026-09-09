"""Single-controller resource coordination for private staging cleanup artifacts.

The registry is fixed beneath the trusted controller user's home, never selected
by a manifest/evidence/state argument. Provider guards own provider semantics and
receipt recovery. This module owns serialization, publication, and the durable
exclusive claim on one node. A copied checkout shares the same registry; a second
controller with another home does not, and must not operate on the same node.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import functools
import hashlib
import inspect
import json
import os
import secrets
import stat
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Iterator

MAX_BYTES = 4 * 1024 * 1024
_LOCAL = threading.local()


class GuardError(ValueError):
    """Categorical refusal; never include private artifact contents."""


def _json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _path(path: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts or path.name in {"", ".", ".."}:
        raise GuardError("lifecycle artifact path is invalid")
    return path


@contextlib.contextmanager
def _parent(path: Path, *, private: bool = True) -> Iterator[tuple[int, str]]:
    path = _path(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != os.getuid() or (mode != 0o700 if private else mode & 0o022):
            raise GuardError("lifecycle artifact parent ownership or mode is unsafe")
        yield fd, path.name
    except OSError as exc:
        raise GuardError("lifecycle artifact parent is unavailable or unsafe") from exc
    finally:
        os.close(fd)


def _read_at(parent: int, name: str) -> tuple[bytes, tuple[int, int]]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_size > MAX_BYTES
        ):
            raise GuardError("lifecycle artifact ownership, mode, or size is unsafe")
        data = b""
        while len(data) <= MAX_BYTES:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        identity = opened.st_dev, opened.st_ino
        if len(data) > MAX_BYTES or (current.st_dev, current.st_ino) != identity:
            raise GuardError("lifecycle artifact changed during read")
        return data, identity
    finally:
        os.close(fd)


def read(path: Path) -> tuple[bytes, tuple[int, int]]:
    with _parent(path) as (parent, name):
        return _read_at(parent, name)


def _object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise GuardError("lifecycle artifact is invalid JSON") from exc
    if not isinstance(value, dict) or _json(value) != raw:
        raise GuardError("lifecycle artifact is not canonical JSON")
    return value


def _present(path: Path) -> bool:
    with _parent(path) as (parent, name):
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True


def _atomic(parent: int, name: str, raw: bytes, *, replace: bool) -> tuple[int, int]:
    if len(raw) > MAX_BYTES:
        raise GuardError("lifecycle journal exceeds size limit")
    temporary = ".staging-" + secrets.token_hex(16)
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=parent,
    )
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise GuardError("lifecycle artifact write failed")
            view = view[written:]
        os.fsync(fd)
        info = os.fstat(fd)
        if replace:
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        else:
            os.link(
                temporary,
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        os.fsync(parent)
        return info.st_dev, info.st_ino
    finally:
        os.close(fd)
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.fsync(parent)


def _registry() -> Path:
    # HOME is trusted controller configuration, not an operator command field.
    home = Path.home()
    if not home.is_absolute():
        raise GuardError("controller home must be an absolute path")
    home = _path(home)
    with _parent(home / ".local", private=False) as (home_fd, _):
        fd = os.dup(home_fd)
        try:
            for part in (".local", "state", "vpn-deploy", "staging-cleanup"):
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                info = os.fstat(child)
                if (
                    info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o022
                    or (
                        part == "staging-cleanup"
                        and stat.S_IMODE(info.st_mode) != 0o700
                    )
                ):
                    os.close(child)
                    raise GuardError("lifecycle registry ownership or mode is unsafe")
                os.close(fd)
                fd = child
        finally:
            os.close(fd)
    return home / ".local/state/vpn-deploy/staging-cleanup"


def key(manifest: dict[str, Any]) -> str:
    provider = manifest.get("provider")
    if provider == "upcloud":
        account = manifest.get("provider_account_username")
        server = manifest.get("server_uuid")
    elif provider == "vultr":
        account = manifest.get("provider_account_binding")
        resources = manifest.get("resources")
        server = resources.get("server_id") if isinstance(resources, dict) else None
    else:
        raise GuardError("lifecycle provider is invalid")
    if not all(isinstance(value, str) and value for value in (account, server)):
        raise GuardError("lifecycle resource identity is invalid")
    return hashlib.sha256(_json([provider, account, server])).hexdigest()


def _identity(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(type(part) is int for part in value)
        and value[0] >= 0
        and value[1] > 0
    )


def _absolute(value: Any) -> bool:
    return (
        isinstance(value, str)
        and Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _entry(value: Any, node: str) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "manifest", "identity"}
        or not _absolute(value["path"])
        or not isinstance(value["manifest"], dict)
        or not _identity(value["identity"])
    ):
        return False
    return key(value["manifest"]) == node


def _released(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"path", "receipt", "identity"}
        and _absolute(value["path"])
        and _identity(value["identity"])
        and isinstance(value["receipt"], dict)
        and value["receipt"].get("status") in {"reserved", "plan_validated"}
    )


def _validate_record(record: dict[str, Any], node: str) -> None:
    current, pending, claim = record["current"], record["publish"], record["claim"]
    if current is not None and not _entry(current, node):
        raise GuardError("lifecycle current generation is invalid")
    if current is None and pending is None:
        raise GuardError("lifecycle journal lost its current generation")
    if pending is not None:
        if (
            not isinstance(pending, dict)
            or set(pending) != {"path", "manifest", "previous"}
            or not _absolute(pending["path"])
            or not isinstance(pending["manifest"], dict)
            or key(pending["manifest"]) != node
            or (pending["previous"] is not None and not _absolute(pending["previous"]))
            or claim is not None
        ):
            raise GuardError("lifecycle publication intent is invalid")
    if claim is not None:
        if (
            not isinstance(claim, dict)
            or current is None
            or not _absolute(claim.get("path"))
            or claim.get("phase") not in {"reserving", "reserved", "releasing"}
            or set(claim)
            != (
                {"path", "phase", "receipt"}
                if claim.get("phase") == "releasing"
                else {"path", "phase"}
            )
            or (claim.get("phase") == "releasing" and not _released(claim["receipt"]))
        ):
            raise GuardError("lifecycle reservation intent is invalid")
    if not all(_entry(entry, node) for entry in record["history"]) or not all(
        _released(entry) for entry in record["released"]
    ):
        raise GuardError("lifecycle retained history is invalid")


class Journal:
    def __init__(self, directory: int, node: str, lock_fd: int):
        self.lock_fd = lock_fd
        self.directory = directory
        self.node = node
        self.name = node + ".json"
        try:
            raw, identity = _read_at(directory, self.name)
        except FileNotFoundError:
            self.record = {
                "version": 1,
                "key": node,
                "current": None,
                "publish": None,
                "claim": None,
                "history": [],
                "released": [],
            }
            self.exists = False
        else:
            self.snapshot = raw
            self.identity = identity
            self.record = _object(raw)
            expected = {
                "version",
                "key",
                "current",
                "publish",
                "claim",
                "history",
                "released",
            }
            if (
                set(self.record) != expected
                or self.record["version"] != 1
                or self.record["key"] != node
                or not isinstance(self.record["history"], list)
                or not isinstance(self.record["released"], list)
            ):
                raise GuardError("lifecycle journal schema is invalid")
            _validate_record(self.record, node)
            self.exists = True

    def save(self) -> None:
        _validate_record(self.record, self.node)
        if self.exists:
            raw, identity = _read_at(self.directory, self.name)
            if raw != self.snapshot or identity != self.identity:
                raise GuardError("lifecycle journal changed during operation")
        raw = _json(self.record)
        self.identity = _atomic(self.directory, self.name, raw, replace=self.exists)
        self.snapshot = raw
        self.exists = True

    def current(self, path: Path, manifest: dict[str, Any]) -> None:
        current = self.record["current"]
        if self.record["publish"] is not None:
            raise GuardError("manifest publication requires recovery")
        if (
            not isinstance(current, dict)
            or current.get("path") != str(_path(path))
            or current.get("manifest") != manifest
        ):
            raise GuardError("manifest is not the registered current generation")
        raw, identity = read(path)
        if raw != _json(manifest) or list(identity) != current.get("identity"):
            raise GuardError("registered manifest identity changed")


@contextlib.contextmanager
def locked(manifest: dict[str, Any]) -> Iterator[Journal]:
    node = key(manifest)
    scope = os.getpid(), str(Path.home()), node
    held = getattr(_LOCAL, "held", {})
    if scope in held:
        yield held[scope]
        return
    directory = _registry()
    with _parent(directory / (node + ".lock")) as (parent, name):
        inherited = os.environ.get("VPN_STAGING_LOCK_FD")
        if inherited is not None:
            if (
                not inherited.isascii()
                or not inherited.isdecimal()
                or len(inherited) > 10
                or not 3 <= int(inherited) <= 2147483647
            ):
                raise GuardError("inherited lifecycle lock descriptor is invalid")
            try:
                fd = os.dup(int(inherited))
            except OSError as exc:
                raise GuardError(
                    "inherited lifecycle lock descriptor is unavailable"
                ) from exc
        else:
            fd = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=parent,
            )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise GuardError("lifecycle lock ownership or mode is unsafe")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise GuardError("another node lifecycle operation is active") from exc
            visible = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (visible.st_dev, visible.st_ino) != (info.st_dev, info.st_ino):
                raise GuardError("lifecycle lock identity changed")
            journal = Journal(parent, node, fd)
            _LOCAL.held = held
            held[scope] = journal
            try:
                yield journal
            finally:
                held.pop(scope)
        finally:
            os.close(fd)


def check_manifest(path: Path, manifest: dict[str, Any]) -> None:
    with locked(manifest) as journal:
        journal.current(path, manifest)


def publish(
    manifest: dict[str, Any], output: Path, previous: Path | None = None
) -> None:
    output = _path(output)
    with locked(manifest) as journal:
        record = journal.record
        proposed = {
            "path": str(output),
            "manifest": manifest,
            "previous": str(_path(previous)) if previous is not None else None,
        }
        pending = record["publish"]
        if pending is not None:
            if pending != proposed:
                raise GuardError("another manifest publication requires recovery")
        else:
            if record["claim"] is not None:
                raise GuardError("node has an outstanding destruction reservation")
            current = record["current"]
            if previous is None:
                if current is not None:
                    raise GuardError(
                        "node already registered; use explicit manifest reissue"
                    )
            else:
                if current is None:
                    raise GuardError("previous manifest is not registered")
                journal.current(previous, current["manifest"])
                old = current["manifest"]
                stable = {k: v for k, v in manifest.items() if k != "state"}
                before = {k: v for k, v in old.items() if k != "state"}
                if (
                    stable != before
                    or manifest["state"]["path"] != old["state"]["path"]
                    or manifest["state"]["sha256"] == old["state"]["sha256"]
                ):
                    raise GuardError(
                        "manifest reissue must preserve identity and deadlines for changed state"
                    )
            if _present(output):
                raise GuardError("manifest output already exists")
            record["publish"] = proposed
            journal.save()
        raw = _json(manifest)
        if _present(output):
            actual, identity = read(output)
            if actual != raw:
                raise GuardError("pending manifest output does not match publication")
        else:
            with _parent(output) as (parent, name):
                identity = _atomic(parent, name, raw, replace=False)
        if record["current"] is not None:
            record["history"].append(record["current"])
        record["current"] = {
            "path": str(output),
            "manifest": manifest,
            "identity": list(identity),
        }
        record["publish"] = None
        journal.save()


def evidence_paths(manifest: dict[str, Any], evidence: Path) -> list[Path]:
    paths = [_path(evidence)]
    if manifest["provider"] == "vultr":
        reservation = evidence.with_name("." + evidence.name + ".reservation")
        transition = evidence.with_name("." + evidence.name + ".transition")
        paths += [
            reservation,
            transition,
            transition.with_name("." + transition.name + ".pending"),
        ]
    return paths


def begin_reservation(manifest: dict[str, Any], evidence_path: Path) -> None:
    """Called after the provider guard validates all reservation inputs."""
    with locked(manifest) as journal:
        if journal.record["claim"] is not None:
            raise GuardError("node has an outstanding destruction reservation")
        if any(_present(path) for path in evidence_paths(manifest, evidence_path)):
            raise GuardError("evidence output already exists")
        journal.record["claim"] = {
            "path": str(_path(evidence_path)),
            "phase": "reserving",
        }
        journal.save()


def reservation_phase(manifest: dict[str, Any]) -> str:
    with locked(manifest) as journal:
        claim = journal.record["claim"]
        if not isinstance(claim, dict):
            raise GuardError("node has no destruction reservation")
        return claim["phase"]


def begin_release(
    manifest: dict[str, Any], evidence_path: Path, receipt: dict[str, Any]
) -> None:
    """Called only after a provider guard proves a releasable receipt."""
    with locked(manifest) as journal:
        claim = journal.record["claim"]
        if not isinstance(claim, dict) or claim.get("path") != str(
            _path(evidence_path)
        ):
            raise GuardError("evidence does not own the node reservation")
        raw, identity = read(evidence_path)
        if raw != _json(receipt):
            raise GuardError("release receipt changed")
        claim["phase"] = "releasing"
        claim["receipt"] = {
            "path": str(_path(evidence_path)),
            "receipt": receipt,
            "identity": list(identity),
        }
        journal.save()


def _finish_release(journal: Journal, paths: list[Path]) -> None:
    if any(_present(path) for path in paths):
        raise GuardError("evidence release is incomplete")
    claim = journal.record["claim"]
    if claim is not None and claim.get("receipt") is not None:
        journal.record["released"].append(claim["receipt"])
    journal.record["claim"] = None
    journal.save()


def operation(kind: str) -> Callable:
    """Serialize provider guard entrypoints, retaining uncertain write intent."""

    def decorate(function: Callable) -> Callable:
        @functools.wraps(function)
        def run(*args: Any, **kwargs: Any) -> Any:
            arguments = inspect.signature(function).bind(*args, **kwargs).arguments
            manifest_path = arguments["manifest_path"]
            evidence_path = arguments["evidence_path"]
            manifest = _object(read(manifest_path)[0])
            with locked(manifest) as journal:
                journal.current(manifest_path, manifest)
                paths = evidence_paths(manifest, evidence_path)
                claim = journal.record["claim"]
                if kind == "reserve":
                    if claim is not None:
                        raise GuardError(
                            "node has an outstanding destruction reservation"
                        )
                    if any(_present(path) for path in paths):
                        raise GuardError("evidence output already exists")
                    try:
                        result = function(*args, **kwargs)
                    except BaseException:
                        if journal.record["claim"] is not None and not any(
                            _present(path) for path in paths
                        ):
                            _finish_release(journal, paths)
                        raise
                    journal.record["claim"]["phase"] = "reserved"
                    journal.save()
                    return result
                if claim is None:
                    if kind == "recover" and not any(_present(path) for path in paths):
                        return "none"
                    raise GuardError("evidence does not own the node reservation")
                if claim.get("path") != str(_path(evidence_path)):
                    raise GuardError("evidence path does not own the node reservation")
                if kind == "recover" and not any(_present(path) for path in paths):
                    if claim.get("phase") not in {"reserving", "releasing"}:
                        raise GuardError("registered evidence is missing")
                    _finish_release(journal, paths)
                    return "released"
                if (
                    kind not in {"recover", "release"}
                    and claim.get("phase") != "reserved"
                ):
                    raise GuardError("node reservation requires recovery")
                result = function(*args, **kwargs)
                if kind == "release" or (
                    kind == "recover" and result in {"none", "released"}
                ):
                    _finish_release(journal, paths)
                return result

        return run

    return decorate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run-destroy")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    manifest = _object(read(args.manifest)[0])
    forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    with locked(manifest) as journal:
        journal.current(args.manifest, manifest)
        environment = dict(os.environ, VPN_STAGING_LOCK_FD=str(journal.lock_fd))
        return subprocess.run(
            ["bash", str(Path(__file__).with_name("destroy.sh")), *forwarded],
            env=environment,
            pass_fds=(journal.lock_fd,),
            check=False,
        ).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GuardError, OSError) as error:
        print(
            str(error)
            if isinstance(error, GuardError)
            else "lifecycle I/O operation failed",
            file=sys.stderr,
        )
        raise SystemExit(2)
