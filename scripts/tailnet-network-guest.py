#!/usr/bin/env python3
"""Durable guest transaction for firewall-owned Tailnet SSH source sets."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from uuid import UUID, uuid4

SCHEMA = 1
MAX_FILE = 256 * 1024
MAX_STATE = 1024 * 1024
# This standalone helper cannot import the controller deployment tree.  The
# contract test keeps this ceiling equal to promotion.TRANSACTION_LEASE_SECONDS,
# whose expression covers the complete bounded forward and recovery path.
MAX_TIMEOUT = 2955
MAX_CANDIDATE = 49125
TERMINAL = {"committed", "rolled_back"}
STATES = TERMINAL | {
    "prepared",
    "applying",
    "applied",
    "rolling_back",
    "recovery_failed",
}
HEX = re.compile(r"[0-9a-f]{64}\Z")


class Refusal(RuntimeError):
    """Categorical only; never include file contents or subprocess output."""


class Busy(Refusal):
    pass


class Paths:
    def __init__(
        self, fragment: Path, main: Path, state: Path, resolver: Path, boot_id: Path
    ):
        self.fragment, self.main, self.state = fragment, main, state
        self.resolver, self.boot_id = resolver, boot_id

    @classmethod
    def for_root(cls, root: Path):
        return cls(
            root / "etc/nftables.d/vpn-tailnet-ssh-sets.nft",
            root / "etc/nftables.conf",
            root / "var/lib/vpn-tailnet-network",
            root / "etc/resolv.conf",
            root / "proc/sys/kernel/random/boot_id",
        )


def _json(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _directory(path: Path, *, private=False):
    for current in (path, *path.parents):
        info = current.lstat()
        sticky = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in {0, os.geteuid()}
            or (info.st_mode & 0o022 and not sticky)
        ):
            raise Refusal("directory-unsafe")
    if private:
        info = path.lstat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Refusal("state-directory-unsafe")


def _integrity(info):
    return tuple(
        getattr(info, key)
        for key in (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
    )


def _read(path: Path, *, private=False, limit=MAX_FILE):
    _directory(path.parent)
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise Refusal("file-unavailable") from None
    try:
        before = os.fstat(fd)
        denied = 0o077 if private else 0o022
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_mode & denied
            or before.st_size > limit
        ):
            raise Refusal("file-unsafe")
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(fd)
        if (
            len(content) > limit
            or _integrity(before) != _integrity(after)
            or _integrity(path.lstat()) != _integrity(after)
        ):
            raise Refusal("file-changed")
        return content, after
    finally:
        os.close(fd)


def _write_all(fd: int, content: bytes):
    view = memoryview(content)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short-write")
        view = view[written:]


def _sync(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path: Path, content: bytes, mode=0o600, uid=None, gid=None):
    _directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".tailnet-network-", dir=path.parent)
    try:
        if uid is not None and gid is not None:
            os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
        _write_all(fd, content)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            # The temporary name was already atomically published or removed.
            pass


def canonical_fragment(raw: bytes) -> bytes:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise Refusal("fragment-invalid") from None
    pattern = (
        r"# vpn-tailnet-ssh-sets schema=1\nset vpn_tailnet_ssh_v4 \{\n"
        r"  type ipv4_addr\n  flags interval\n"
        r"(?:  elements = \{ (?P<v4>[^\s,]+/32(?:, [^\s,]+/32)*) \}\n)?\}\n\n"
        r"set vpn_tailnet_ssh_v6 \{\n  type ipv6_addr\n  flags interval\n"
        r"(?:  elements = \{ (?P<v6>[^\s,]+/128(?:, [^\s,]+/128)*) \}\n)?\}\n\Z"
    )
    match = re.fullmatch(pattern, text)
    if match is None:
        raise Refusal("fragment-invalid")

    def items(value, version, prefix):
        tokens = [] if value is None else value.split(", ")
        try:
            networks = [ipaddress.ip_network(token, strict=True) for token in tokens]
        except ValueError:
            raise Refusal("fragment-invalid") from None
        canonical = sorted(
            {str(network) for network in networks},
            key=lambda item: int(ipaddress.ip_network(item).network_address),
        )
        if tokens != canonical or any(
            n.version != version or n.prefixlen != prefix for n in networks
        ):
            raise Refusal("fragment-invalid")
        return canonical

    v4, v6 = items(match["v4"], 4, 32), items(match["v6"], 6, 128)
    form = lambda values: (
        "" if not values else "  elements = { " + ", ".join(values) + " }\n"
    )
    result = (
        "# vpn-tailnet-ssh-sets schema=1\nset vpn_tailnet_ssh_v4 {\n"
        "  type ipv4_addr\n  flags interval\n" + form(v4) + "}\n\n"
        "set vpn_tailnet_ssh_v6 {\n  type ipv6_addr\n  flags interval\n"
        + form(v6)
        + "}\n"
    ).encode()
    if result != raw:
        raise Refusal("fragment-invalid")
    return result


def _record(path: Path):
    content, info = _read(path)
    return {
        "data_b64": base64.b64encode(content).decode(),
        "sha256": _hash(content),
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
    }


def _resolver_read(path: Path):
    """Read a managed resolver file through a bounded, no-follow link chain."""
    root = path.parents[1]
    allowed_roots = tuple(
        root / relative
        for relative in (
            "run/systemd/resolve",
            "run/NetworkManager",
            "run/resolvconf",
        )
    )
    current = path
    for _ in range(4):
        info = current.lstat()
        if not stat.S_ISLNK(info.st_mode):
            return _read(current, limit=64 * 1024)[0]
        if info.st_uid != os.geteuid():
            raise Refusal("file-unsafe")
        target = Path(os.readlink(current))
        current = target if target.is_absolute() else current.parent / target
        current = Path(os.path.normpath(str(current)))
        try:
            current.relative_to(root)
        except ValueError:
            raise Refusal("file-unsafe") from None
        if not any(
            current == allowed or allowed in current.parents
            for allowed in allowed_roots
        ):
            raise Refusal("file-unsafe")
    raise Refusal("file-unsafe")


def _record_bytes(value):
    try:
        content = base64.b64decode(value["data_b64"], validate=True)
        if (
            set(value) != {"data_b64", "sha256", "mode", "uid", "gid"}
            or _hash(content) != value["sha256"]
            or len(content) > MAX_FILE
            or type(value["mode"]) is not int
            or value["mode"] & 0o022
            or type(value["uid"]) is not int
            or value["uid"] != os.geteuid()
            or type(value["gid"]) is not int
        ):
            raise ValueError
        return content
    except (KeyError, TypeError, ValueError):
        raise Refusal("state-invalid") from None


def _fragment_sources(fragment: bytes):
    canonical_fragment(fragment)
    result = {4: [], 6: []}
    for token in re.findall(r"(?:[0-9.]+/32|[0-9a-f:]+/128)", fragment.decode("ascii")):
        network = ipaddress.ip_network(token)
        result[network.version].append(str(network))
    return result


class Runtime:
    def __init__(
        self, paths: Paths, command=None, clock=time.time, monotonic=time.monotonic
    ):
        self.paths, self.command = paths, command or self._command
        self.clock, self.monotonic = clock, monotonic

    @staticmethod
    def _command(argv, timeout=15):
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env={
                    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "TZ": "UTC",
                },
            )
            try:
                output = process.communicate(timeout=timeout)[0]
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, 9)
                except ProcessLookupError:
                    # The bounded child exited between timeout and cleanup.
                    pass
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    # SIGKILLed descendants could not be reaped in the cleanup bound.
                    pass
                raise Refusal("runtime-command-failed") from None
        except OSError:
            raise Refusal("runtime-command-failed") from None
        if process.returncode != 0 or len(output) > 64 * 1024:
            raise Refusal("runtime-command-failed")
        return output

    def boot_id(self):
        try:
            return str(UUID(_read(self.paths.boot_id, limit=128)[0].decode().strip()))
        except (UnicodeError, ValueError):
            raise Refusal("boot-id-invalid") from None

    def fences(self):
        volatile = {"age", "cache", "expires", "lastuse", "statistics", "used"}

        def stable(value):
            if isinstance(value, dict):
                return {
                    key: stable(item)
                    for key, item in value.items()
                    if key not in volatile
                }
            if isinstance(value, list):
                return [stable(item) for item in value]
            return value

        routes = {}
        for family in ("-4", "-6"):
            try:
                value = json.loads(
                    self.command(["ip", family, "-json", "route", "show", "default"])
                )
                if not isinstance(value, list):
                    raise ValueError
            except (TypeError, ValueError, json.JSONDecodeError):
                raise Refusal("routing-invalid") from None
            routes[family] = sorted(
                (stable(item) for item in value),
                key=lambda item: json.dumps(
                    item, sort_keys=True, separators=(",", ":")
                ),
            )
        return {
            "resolver_sha256": _hash(_resolver_read(self.paths.resolver)),
            "routes_sha256": _hash(
                json.dumps(routes, sort_keys=True, separators=(",", ":")).encode()
            ),
            "sshd_sha256": _hash(self.command(["sshd", "-T"])),
        }

    def validate(self):
        self.command(["nft", "-c", "-f", str(self.paths.main)])

    def reload(self):
        self.command(["systemctl", "reload", "nftables"])

    def readback(self, fragment: bytes):
        expected, actual = _fragment_sources(fragment), {}
        for family, name in ((4, "vpn_tailnet_ssh_v4"), (6, "vpn_tailnet_ssh_v6")):
            try:
                doc = json.loads(
                    self.command(["nft", "-j", "list", "set", "inet", "filter", name])
                )
                sets = [item["set"] for item in doc["nftables"] if "set" in item]
                elements = sets[0].get("elem", [])
                if (
                    len(sets) != 1
                    or sets[0].get("family") != "inet"
                    or sets[0].get("table") != "filter"
                    or sets[0].get("name") != name
                    or not isinstance(elements, list)
                    or len(elements)
                    != len({json.dumps(item, sort_keys=True) for item in elements})
                ):
                    raise ValueError
                canonical = []
                for item in elements:
                    if isinstance(item, dict):
                        if (
                            set(item) != {"elem"}
                            or not isinstance(item["elem"], dict)
                            or set(item["elem"]) != {"val"}
                        ):
                            raise ValueError
                        item = item["elem"]["val"]
                    if not isinstance(item, str):
                        raise ValueError
                    suffix = "/32" if family == 4 else "/128"
                    network = ipaddress.ip_network(
                        item if "/" in item else item + suffix, strict=True
                    )
                    if network.version != family or network.prefixlen != int(
                        suffix[1:]
                    ):
                        raise ValueError
                    canonical.append(str(network))
                actual[family] = sorted(
                    canonical,
                    key=lambda item: int(ipaddress.ip_network(item).network_address),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                raise Refusal("runtime-readback-invalid") from None
        if actual != expected:
            raise Refusal("runtime-readback-invalid")


class Transaction:
    def __init__(self, runtime: Runtime):
        self.runtime, self.paths = runtime, runtime.paths

    @contextmanager
    def _locked(self, *, create=False, create_lock=True):
        if create and not self.paths.state.exists():
            _directory(self.paths.state.parent)
            created = False
            try:
                self.paths.state.mkdir(mode=0o700)
                created = True
            except FileExistsError:
                # A concurrent creator won; the no-follow metadata check below
                # decides whether that directory is safe to share.
                pass
            if created:
                directory_fd = os.open(
                    self.paths.state,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    os.fchmod(directory_fd, 0o700)
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                _sync(self.paths.state.parent)
        _directory(self.paths.state, private=True)
        flags = (
            os.O_RDWR
            | (os.O_CREAT if create_lock else 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(self.paths.state / "transaction.lock", flags, 0o600)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise Refusal("lock-unsafe")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Busy("busy") from None
            yield
        finally:
            os.close(fd)

    def _path(self):
        return self.paths.state / "transaction.json"

    def _load(self):
        path = self._path()
        if not os.path.lexists(path):
            if self.paths.state.exists() and (
                os.path.lexists(self.paths.state / "initialized")
                or any(i.name != "transaction.lock" for i in self.paths.state.iterdir())
            ):
                raise Refusal("state-orphaned")
            return None
        raw = _read(path, private=True, limit=MAX_STATE)[0]
        try:
            value = json.loads(raw, object_pairs_hook=_unique_object)
            fields = {
                "schema_version",
                "generation",
                "nonce",
                "created",
                "deadline",
                "monotonic_created",
                "monotonic_deadline",
                "boot_id",
                "status",
                "plan",
                "checksum",
            }
            if (
                set(value) != fields
                or type(value["schema_version"]) is not int
                or value["schema_version"] != SCHEMA
                or value["status"] not in STATES
                or str(UUID(value["generation"])) != value["generation"]
                or str(UUID(value["boot_id"])) != value["boot_id"]
                or HEX.fullmatch(value["nonce"]) is None
                or any(
                    type(value[k]) is not int
                    for k in (
                        "created",
                        "deadline",
                        "monotonic_created",
                        "monotonic_deadline",
                    )
                )
                or not 60 <= value["deadline"] - value["created"] <= MAX_TIMEOUT
                or value["monotonic_deadline"] - value["monotonic_created"]
                != value["deadline"] - value["created"]
                or _hash(_json({k: v for k, v in value.items() if k != "checksum"}))
                != value["checksum"]
                or raw != _json(value)
            ):
                raise ValueError
            self._validate_plan(value["plan"])
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise Refusal("state-invalid") from None

    @staticmethod
    def _validate_plan(plan):
        try:
            if (
                set(plan)
                != {
                    "schema_version",
                    "before",
                    "after",
                    "main",
                    "fences",
                    "snapshot_digest",
                }
                or type(plan["schema_version"]) is not int
                or plan["schema_version"] != 1
                or HEX.fullmatch(plan["snapshot_digest"]) is None
            ):
                raise ValueError
            before, after, main = (
                _record_bytes(plan[k]) for k in ("before", "after", "main")
            )
            canonical_fragment(before)
            canonical_fragment(after)
            if b'include "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"' not in main:
                raise ValueError
            if (
                set(plan["fences"])
                != {"resolver_sha256", "routes_sha256", "sshd_sha256"}
                or any(HEX.fullmatch(v) is None for v in plan["fences"].values())
                or _hash(
                    _json({k: v for k, v in plan.items() if k != "snapshot_digest"})
                )
                != plan["snapshot_digest"]
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise Refusal("state-invalid") from None

    def _save(self, state):
        state["checksum"] = _hash(
            _json({k: v for k, v in state.items() if k != "checksum"})
        )
        content = _json(state)
        if len(content) > MAX_STATE:
            raise Refusal("state-too-large")
        _atomic(self._path(), content)

    @staticmethod
    def _receipt(state):
        if state is None:
            return {"status": "idle"}
        return {k: state[k] for k in ("generation", "nonce", "status", "deadline")} | {
            "snapshot_digest": state["plan"]["snapshot_digest"]
        }

    @staticmethod
    def _identity(state, generation, nonce, snapshot_digest, deadline):
        if (
            state is None
            or state["generation"] != generation
            or not isinstance(nonce, str)
            or not hmac.compare_digest(state["nonce"], nonce)
            or snapshot_digest != state["plan"]["snapshot_digest"]
            or deadline != state["deadline"]
        ):
            raise Refusal("identity-mismatch")

    def _expired(self, state):
        return (
            state["boot_id"] != self.runtime.boot_id()
            or self.runtime.clock() < state["created"]
            or self.runtime.clock() >= state["deadline"]
            or self.runtime.monotonic() < state["monotonic_created"]
            or self.runtime.monotonic() >= state["monotonic_deadline"]
        )

    def _live(self, state):
        if self._expired(state):
            raise Refusal("transaction-expired")

    def _graph(self, plan, phase):
        if phase not in {"before", "after", "mixed"}:
            raise Refusal("phase-invalid")
        if _record(self.paths.main) != plan["main"]:
            raise Refusal("configuration-drift")
        current = _record(self.paths.fragment)
        allowed = [plan["before"], plan["after"]] if phase == "mixed" else [plan[phase]]
        if current not in allowed:
            raise Refusal("configuration-drift")

    def _publish(self, record):
        _atomic(
            self.paths.fragment,
            _record_bytes(record),
            record["mode"],
            record["uid"],
            record["gid"],
        )

    def _new_plan(self, candidate):
        before, main = _record(self.paths.fragment), _record(self.paths.main)
        after = {
            **before,
            "data_b64": base64.b64encode(candidate).decode(),
            "sha256": _hash(candidate),
        }
        plan = {
            "schema_version": 1,
            "before": before,
            "after": after,
            "main": main,
            "fences": self.runtime.fences(),
        }
        plan["snapshot_digest"] = _hash(_json(plan))
        self._validate_plan(plan)
        self._graph(plan, "before")
        return plan

    def prepare(self, candidate: bytes, timeout=300):
        candidate = canonical_fragment(candidate)
        if type(timeout) is not int or not 60 <= timeout <= MAX_TIMEOUT:
            raise Refusal("timeout-invalid")
        with self._locked(create=True):
            previous = self._load()
            if previous is not None and previous["status"] not in TERMINAL:
                raise Refusal("transaction-pending")
            plan = self._new_plan(candidate)
            if plan["before"] == plan["after"]:
                return {
                    "status": "unchanged",
                    "snapshot_digest": plan["snapshot_digest"],
                }
            if previous is not None:
                archive = self.paths.state / (previous["generation"] + ".json")
                encoded = _json(previous)
                if os.path.lexists(archive):
                    if _read(archive, private=True, limit=MAX_STATE)[0] != encoded:
                        raise Refusal("state-invalid")
                else:
                    _atomic(archive, encoded)
            now, mono = int(self.runtime.clock()), int(self.runtime.monotonic())
            state = {
                "schema_version": SCHEMA,
                "generation": str(uuid4()),
                "nonce": secrets.token_hex(32),
                "created": now,
                "deadline": now + timeout,
                "monotonic_created": mono,
                "monotonic_deadline": mono + timeout,
                "boot_id": self.runtime.boot_id(),
                "status": "prepared",
                "plan": plan,
            }
            self._save(state)
            # The durable receipt is the recovery authority.  Publishing the
            # initialization marker first can strand a marker-only state if
            # the process exits before transaction.json is committed.
            _atomic(self.paths.state / "initialized", b"1\n")
            return self._receipt(state)

    def preview(self, candidate: bytes):
        candidate = canonical_fragment(candidate)
        with self._locked(create=False, create_lock=False):
            previous = self._load()
            if previous is not None and previous["status"] not in TERMINAL:
                raise Refusal("transaction-pending")
            plan = self._new_plan(candidate)
            return {
                "status": (
                    "would-change" if plan["before"] != plan["after"] else "unchanged"
                ),
                "snapshot_digest": plan["snapshot_digest"],
            }

    def apply(self, generation, nonce, snapshot_digest, deadline):
        with self._locked():
            state = self._load()
            self._identity(state, generation, nonce, snapshot_digest, deadline)
            self._live(state)
            if state["status"] == "applied":
                self._graph(state["plan"], "after")
                return self._receipt(state)
            if state["status"] != "prepared":
                raise Refusal("state-not-prepared")
            self._graph(state["plan"], "before")
            state["status"] = "applying"
            self._save(state)
            try:
                self._publish(state["plan"]["after"])
                self.runtime.validate()
                self._live(state)
                self.runtime.reload()
                self.runtime.readback(_record_bytes(state["plan"]["after"]))
                if self.runtime.fences() != state["plan"]["fences"]:
                    raise Refusal("fence-drift")
                state["status"] = "applied"
                self._save(state)
                return self._receipt(state)
            except Exception:
                self._rollback(state, boot=False)
                raise Refusal("activation-failed-rolled-back") from None

    def _rollback(self, state, *, boot):
        try:
            self._graph(state["plan"], "mixed")
            state["status"] = "rolling_back"
            self._save(state)
            self._publish(state["plan"]["before"])
            self.runtime.validate()
            if not boot:
                self.runtime.reload()
                self.runtime.readback(_record_bytes(state["plan"]["before"]))
            # At boot the pre-transaction resolver/routes/sshd fence may not
            # exist yet. Exact file restoration is the authoritative boundary;
            # nftables.service loads the already validated config afterwards.
            if not boot and self.runtime.fences() != state["plan"]["fences"]:
                raise Refusal("fence-drift")
            state["status"] = "rolled_back"
            self._save(state)
            return self._receipt(state)
        except Exception:
            state["status"] = "recovery_failed"
            self._save(state)
            raise Refusal("recovery-failed") from None

    def confirm(self, generation, nonce, snapshot_digest, deadline):
        with self._locked():
            state = self._load()
            self._identity(state, generation, nonce, snapshot_digest, deadline)
            if state["status"] == "committed":
                self._graph(state["plan"], "after")
                return self._receipt(state)
            self._live(state)
            if state["status"] != "applied":
                raise Refusal("state-not-applied")
            self._graph(state["plan"], "after")
            self.runtime.readback(_record_bytes(state["plan"]["after"]))
            if self.runtime.fences() != state["plan"]["fences"]:
                raise Refusal("fence-drift")
            state["status"] = "committed"
            self._save(state)
            return self._receipt(state)

    def rollback(self, generation, nonce, snapshot_digest, deadline):
        with self._locked():
            state = self._load()
            self._identity(state, generation, nonce, snapshot_digest, deadline)
            if state["status"] == "rolled_back":
                return self._receipt(state)
            if state["status"] == "committed":
                raise Refusal("already-committed")
            return self._rollback(state, boot=False)

    def recover(self, *, boot=False):
        with self._locked():
            state = self._load()
            if state is None or state["status"] in TERMINAL:
                return self._receipt(state)
            if (
                boot
                or state["status"] in {"applying", "rolling_back", "recovery_failed"}
                or self._expired(state)
            ):
                return self._rollback(state, boot=boot)
            return self._receipt(state)

    def status(self):
        with self._locked():
            return self._receipt(self._load())


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _request():
    raw = sys.stdin.buffer.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise Refusal("request-too-large")
    try:
        value = json.loads(raw or b"{}", object_pairs_hook=_unique_object)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (TypeError, ValueError, json.JSONDecodeError):
        raise Refusal("request-invalid") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "prepare",
            "preview",
            "apply",
            "status",
            "confirm",
            "rollback",
            "recover",
            "boot-recover",
        ),
    )
    args = parser.parse_args()
    request = _request()
    transaction = Transaction(Runtime(Paths.for_root(Path("/"))))
    if args.action in {"prepare", "preview"}:
        if set(request) not in ({"candidate_b64"}, {"candidate_b64", "timeout"}):
            raise Refusal("request-invalid")
        try:
            candidate = base64.b64decode(request["candidate_b64"], validate=True)
        except (KeyError, TypeError, ValueError):
            raise Refusal("request-invalid") from None
        if len(candidate) > MAX_CANDIDATE:
            raise Refusal("request-invalid")
        result = (
            transaction.prepare(candidate, request.get("timeout", 300))
            if args.action == "prepare"
            else transaction.preview(candidate)
        )
    elif args.action in {"apply", "rollback"}:
        if set(request) != {"generation", "nonce", "snapshot_digest", "deadline"}:
            raise Refusal("request-invalid")
        result = getattr(transaction, args.action)(
            request["generation"],
            request["nonce"],
            request["snapshot_digest"],
            request["deadline"],
        )
    elif args.action == "confirm":
        if set(request) != {"generation", "nonce", "snapshot_digest", "deadline"}:
            raise Refusal("request-invalid")
        result = transaction.confirm(
            request["generation"],
            request["nonce"],
            request["snapshot_digest"],
            request["deadline"],
        )
    else:
        if request:
            raise Refusal("request-invalid")
        result = (
            transaction.status()
            if args.action == "status"
            else transaction.recover(boot=args.action == "boot-recover")
        )
    sys.stdout.buffer.write(_json(result))


if __name__ == "__main__":
    try:
        main()
    except Busy:
        sys.stdout.write('{"error":"busy"}\n')
        raise SystemExit(75)
    except Refusal as error:
        sys.stdout.write(
            json.dumps({"error": str(error)}, separators=(",", ":")) + "\n"
        )
        raise SystemExit(1)
    except OSError:
        sys.stdout.write('{"error":"filesystem-unavailable"}\n')
        raise SystemExit(1)
