#!/usr/bin/env python3
"""Complete nginx candidate validation and bounded ordinary-failure compensation."""

from __future__ import annotations

import argparse
import base64
import copy
from contextlib import contextmanager
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

LIMIT = 8 * 1024 * 1024
STATE_ROOT = Path("/var/lib/vpn-nginx-publication")
SITE_OWNERS = {"nginx-xhttp", "reality-self-steal"}
DEFAULT_ENABLED = Path("/etc/nginx/sites-enabled/default")
DEFAULT_AVAILABLE = Path("/etc/nginx/sites-available/default")


class TransactionError(RuntimeError):
    """Only categorical failure text may reach Ansible or a journal."""


def command(argv):
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        raise TransactionError("runtime-command") from None
    if result.returncode:
        raise TransactionError("runtime-command")
    return result.stdout.decode("utf-8")


def service_state(unit):
    raw = command(
        ["systemctl", "show", unit, "--property=LoadState,ActiveState,UnitFileState"]
    )
    values = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    load = values.get("LoadState")
    active = values.get("ActiveState")
    enabled = values.get("UnitFileState") or (
        "not-found" if load == "not-found" else ""
    )
    if load not in {"loaded", "not-found", "masked"} or active not in {
        "active",
        "inactive",
        "failed",
    }:
        raise TransactionError("service-state")
    if enabled not in {
        "enabled",
        "enabled-runtime",
        "disabled",
        "static",
        "indirect",
        "not-found",
        "masked",
        "masked-runtime",
    }:
        raise TransactionError("service-state")
    return {
        "active": active == "active",
        "unit_file_state": enabled,
        "exists": load != "not-found",
    }


def process_stat(process):
    with (process / "stat").open("rb") as source:
        raw = source.read(8193)
    if len(raw) > 8192 or b")" not in raw:
        raise TransactionError("runtime-identity")
    fields = raw.rsplit(b")", 1)[1].decode("ascii").split()
    if len(fields) < 20:
        raise TransactionError("runtime-identity")
    return fields


def nginx_master(unit):
    pid = command(["systemctl", "show", unit, "--property=MainPID", "--value"]).strip()
    if not pid.isascii() or not pid.isdigit() or int(pid) <= 0:
        raise TransactionError("runtime-not-ready")
    process = Path("/proc") / pid
    fields = process_stat(process)
    executable = (process / "exe").stat()
    installed = Path("/usr/sbin/nginx").stat()
    if (executable.st_dev, executable.st_ino) != (installed.st_dev, installed.st_ino):
        raise TransactionError("runtime-identity")
    return (pid, fields[19], executable.st_dev, executable.st_ino)


def nginx_workers(master):
    pid, started, device, inode = master
    process = Path("/proc") / pid
    fields = process_stat(process)
    executable = (process / "exe").stat()
    if fields[19] != started or (executable.st_dev, executable.st_ino) != (
        device,
        inode,
    ):
        raise TransactionError("runtime-identity")
    with (process / "task" / pid / "children").open("rb") as source:
        raw = source.read(32769)
    if len(raw) > 32768:
        raise TransactionError("runtime-capacity")
    pool = set()
    for child in raw.decode("ascii").split():
        target = Path("/proc") / child
        try:
            with (target / "cmdline").open("rb") as source:
                title = source.read(4097)
            if len(title) > 4096:
                raise TransactionError("runtime-capacity")
            # Graceful old workers remain alive, but cannot acknowledge adoption.
            if title.rstrip(b"\0 ") != b"nginx: worker process":
                continue
            info = (target / "exe").stat()
            child_fields = process_stat(target)
            if (info.st_dev, info.st_ino) != (device, inode) or child_fields[1] != pid:
                raise TransactionError("runtime-identity")
            pool.add((child, child_fields[19]))
        except FileNotFoundError:
            continue
    return pool


def wait_adoption(unit, previous=None):
    deadline = time.monotonic() + 10
    observed = None
    stable_since = 0.0
    master = previous[0] if previous is not None else None
    while True:
        now = time.monotonic()
        try:
            current_master = nginx_master(unit)
            if previous is not None and current_master != previous[0]:
                raise TransactionError("runtime-identity")
            if current_master != master:
                master, observed = current_master, None
            pool = nginx_workers(master)
        except (OSError, TransactionError):
            if previous is not None:
                raise
            # Type=simple acknowledges start before exec/worker initialization.
            # No receipt exists until one trusted generation becomes stable.
            master, observed, pool = None, None, set()
        fresh = bool(pool) and (previous is None or pool.isdisjoint(previous[1]))
        if fresh:
            if pool != observed:
                observed, stable_since = pool, now
            elif now - stable_since >= 0.1:
                if nginx_master(unit) != master or nginx_workers(master) != pool:
                    raise TransactionError("runtime-identity")
                return master[0]
        else:
            observed = None
        if now >= deadline:
            raise TransactionError("runtime-adoption-timeout")
        time.sleep(0.05)


def boot_clock():
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot):
        raise TransactionError("runtime-clock")
    ticks = (
        time.clock_gettime_ns(time.CLOCK_BOOTTIME) * os.sysconf("SC_CLK_TCK") // 10**9
    )
    return boot, ticks


def inactive_absence_receipt(unit, receipt):
    raw = command(
        ["systemctl", "show", unit, "--property=LoadState,ActiveState,MainPID"]
    )
    values = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    if (
        values.get("LoadState") not in {"loaded", "masked", "not-found"}
        or values.get("ActiveState") != "inactive"
        or values.get("MainPID") != "0"
    ):
        raise TransactionError("runtime-not-inactive")
    boot, ticks = boot_clock()
    return {
        **receipt,
        "active": False,
        "boot_id": boot,
        "inactive_after_ticks": ticks,
    }


def stable_generation(unit, generation):
    if (
        not generation[1]
        or nginx_master(unit) != generation[0]
        or nginx_workers(generation[0]) != generation[1]
    ):
        raise TransactionError("runtime-identity")


def set_enabled(unit, desired):
    current = service_state(unit)["unit_file_state"]
    if (
        desired is None
        or desired
        and current == "enabled"
        or not desired
        and current in {"disabled", "static", "indirect", "not-found"}
    ):
        return False
    if current in {"masked", "masked-runtime"}:
        raise TransactionError("masked-unit")
    command(["systemctl", "enable" if desired else "disable", unit])
    actual = service_state(unit)["unit_file_state"]
    if (
        desired
        and actual not in {"enabled", "enabled-runtime"}
        or not desired
        and actual not in {"disabled", "static", "indirect", "not-found"}
    ):
        raise TransactionError("enablement-failed")
    return True


def restore_enabled(unit, previous):
    state = previous["unit_file_state"]
    observed = service_state(unit)
    if (
        observed["unit_file_state"] == state
        and observed["exists"] == previous["exists"]
    ):
        return
    if state in {"enabled", "enabled-runtime"}:
        command(["systemctl", "disable", unit])
        argv = ["systemctl", "enable"]
        if state == "enabled-runtime":
            argv.append("--runtime")
        command([*argv, unit])
    elif state in {"disabled", "static", "indirect"}:
        command(["systemctl", "disable", unit])
    elif state == "not-found":
        # Unit removal after stopping removes the newly created service graph.
        # Clear only this transaction's newly absent runtime failed record.
        command(["systemctl", "reset-failed", unit])
    elif service_state(unit)["unit_file_state"] != state:
        raise TransactionError("masked-unit")
    actual = service_state(unit)
    if actual["unit_file_state"] != state or actual["exists"] != previous["exists"]:
        raise TransactionError("enablement-restore-failed")


def safe(path, *, missing=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise TransactionError("path")
    current = Path("/")
    for piece in path.parts[1:]:
        current /= piece
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                return
            raise TransactionError("missing-parent") from None
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise TransactionError("unsafe-parent")


def identity(value, *, group=False):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[a-z_][a-z0-9_-]{0,63}", value):
        return grp.getgrnam(value).gr_gid if group else pwd.getpwnam(value).pw_uid
    raise TransactionError("ownership")


def capture(path):
    safe(path.parent, missing=True)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    if info.st_uid != os.geteuid():
        raise TransactionError("foreign-file")
    row = {"uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
    if stat.S_ISLNK(info.st_mode):
        return {**row, "kind": "link", "target": os.readlink(path)}
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > LIMIT
        or info.st_mode & 0o022
    ):
        raise TransactionError("unsafe-file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_nlink) != (
            info.st_dev,
            info.st_ino,
            1,
        ):
            raise TransactionError("file-changed")
        content = os.read(fd, LIMIT + 1)
        after = os.fstat(fd)
        if (
            len(content) > LIMIT
            or len(content) != info.st_size
            or (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            != (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        ):
            raise TransactionError("file-changed")
    finally:
        os.close(fd)
    return {**row, "kind": "file", "content_b64": base64.b64encode(content).decode()}


def apply(path, row, created):
    safe(path.parent, missing=True)
    pending = []
    parent = path.parent
    while not parent.exists():
        pending.append(parent)
        parent = parent.parent
    for parent in reversed(pending):
        parent.mkdir(mode=0o750)
        created.append(str(parent))
    safe(path.parent)
    if row["kind"] == "absent":
        if os.path.lexists(path):
            clear(path)
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".nginx-publish-")
    try:
        if row["kind"] == "link":
            os.close(fd)
            fd = -1
            os.unlink(temporary)
            os.symlink(row["target"], temporary)
            os.lchown(temporary, row["uid"], row["gid"])
        else:
            os.fchmod(fd, row["mode"])
            os.fchown(fd, row["uid"], row["gid"])
            data = memoryview(base64.b64decode(row["content_b64"], validate=True))
            while data:
                written = os.write(fd, data)
                if written <= 0:
                    raise TransactionError("short-write")
                data = data[written:]
            os.fsync(fd)
            os.close(fd)
            fd = -1
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if os.path.lexists(temporary):
            os.unlink(temporary)


def request(document):
    if isinstance(document, dict):
        document.setdefault("prune_releases", None)
    expected = {
        "prune_releases",
        "owner",
        "roots",
        "files",
        "validate_argv",
        "unit",
        "activation",
        "check",
        "credential_root",
        "runtime_directories",
        "activate_inactive",
        "desired_enabled",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise TransactionError("request")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", document["owner"]):
        raise TransactionError("owner")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,95}\.service", document["unit"]):
        raise TransactionError("unit")
    if document["activation"] not in {"reload", "restart"} or any(
        type(document[key]) is not bool for key in ("check", "activate_inactive")
    ):
        raise TransactionError("request")
    if (
        document["desired_enabled"] is not None
        and type(document["desired_enabled"]) is not bool
    ):
        raise TransactionError("enablement")
    roots = [Path(value) for value in document["roots"]]
    if not 1 <= len(roots) <= 4 or len(set(roots)) != len(roots):
        raise TransactionError("roots")
    for root in roots:
        if root == Path("/") or not root.is_absolute() or ".." in root.parts:
            raise TransactionError("roots")
        safe(root, missing=True)
        if any(root != other and root.is_relative_to(other) for other in roots):
            raise TransactionError("roots")
    records = document["files"]
    if not isinstance(records, list) or len(records) > 128:
        raise TransactionError("files")
    seen = set()
    unit_file = Path("/etc/systemd/system") / document["unit"]
    for row in records:
        path = Path(row["path"])
        if (
            path in seen
            or ".." in path.parts
            or not path.is_absolute()
            or not (
                path == unit_file
                or any(path != root and path.is_relative_to(root) for root in roots)
            )
        ):
            raise TransactionError("write-set")
        seen.add(path)
        kind = row["kind"]
        fields = (
            {"path", "kind"}
            if kind == "absent"
            else {"path", "kind", "uid", "gid", "mode"}
        )
        fields |= (
            {"content_b64"}
            if kind == "file"
            else {"target"} if kind == "link" else set()
        )
        if kind not in {"file", "link", "absent"} or set(row) != fields:
            raise TransactionError("file")
        if kind != "absent":
            row["uid"], row["gid"] = identity(row["uid"]), identity(
                row["gid"], group=True
            )
            if type(row["mode"]) is str:
                row["mode"] = int(row["mode"], 8)
            if (
                type(row["mode"]) is not int
                or row["mode"] & ~0o777
                or (kind == "file" and row["mode"] & 0o022)
            ):
                raise TransactionError("mode")
        if (
            kind == "file"
            and len(base64.b64decode(row["content_b64"], validate=True)) > LIMIT
        ):
            raise TransactionError("file-size")
        if kind == "link" and (
            not Path(row["target"]).is_absolute()
            or ".." in Path(row["target"]).parts
            or not any(Path(row["target"]).is_relative_to(root) for root in roots)
        ):
            raise TransactionError("link")
    prune = document["prune_releases"]
    if prune is not None:
        if (
            document["owner"] != "reality-self-steal"
            or not isinstance(prune, dict)
            or set(prune) != {"root", "keep"}
            or not isinstance(prune["root"], str)
            or not Path(prune["root"]).is_absolute()
            or ".." in Path(prune["root"]).parts
            or not any(Path(prune["root"]).is_relative_to(root) for root in roots)
            or prune["keep"] is not None
            and (
                not isinstance(prune["keep"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", prune["keep"])
            )
        ):
            raise TransactionError("release-prune")
    argv = document["validate_argv"]
    if (
        not isinstance(argv, list)
        or not 2 <= len(argv) <= 10
        or argv[0] != "/usr/sbin/nginx"
        or "-t" not in argv
    ):
        raise TransactionError("validator")
    for value in argv:
        if (
            not isinstance(value, str)
            or len(value) > 256
            or any(ord(char) < 32 for char in value)
        ):
            raise TransactionError("validator")
    credential = document["credential_root"]
    if credential and not any(Path(credential).is_relative_to(root) for root in roots):
        raise TransactionError("credential-root")
    for path in document["runtime_directories"]:
        if not re.fullmatch(r"/run/[a-z][a-z0-9_.-]{0,95}", path):
            raise TransactionError("runtime-directory")
    return document, roots


def validate_previous(document, previous):
    prior = copy.deepcopy(document)
    prior["files"] = [{"path": path, **row} for path, row in previous.items()]
    for row in prior["files"]:
        if row["kind"] == "link" and not Path(row["target"]).is_absolute():
            # Preserve the exact captured spelling for restoration; validate its
            # lexical destination under the same owned roots as a desired link.
            row["target"] = os.path.normpath(
                str(Path(row["path"]).parent / row["target"])
            )
    request(prior)


def validate(manifest):
    # This branch runs only after unshare --propagation private. All mounts and
    # transient credential/runtime directories are confined to that namespace.
    for binding in manifest["bindings"]:
        command(["mount", "--bind", binding["source"], binding["target"]])
        command(["mount", "-o", "remount,bind,ro", binding["target"]])
    if manifest["credential_source"]:
        command(
            ["mount", "-t", "tmpfs", "-o", "mode=0755,nosuid,nodev", "tmpfs", "/run"]
        )
        for directory in manifest["runtime_directories"]:
            Path(directory).mkdir(mode=0o755, parents=True, exist_ok=True)
        target = Path("/run/credentials") / manifest["unit"]
        target.mkdir(mode=0o700, parents=True)
        command(["mount", "--bind", manifest["credential_source"], str(target)])
        command(["mount", "-o", "remount,bind,ro", str(target)])
    command(manifest["validate_argv"])


def expand_release_prune(document):
    """Resolve only self-steal's immutable pair namespace under the unit lock."""
    prune = document["prune_releases"]
    if prune is None:
        return document
    result = copy.deepcopy(document)
    root = Path(prune["root"])
    safe(root, missing=True)
    if not root.exists():
        return result
    explicit = {row["path"]: row for row in result["files"]}
    releases = []
    with os.scandir(root) as entries:
        for entry in entries:
            if len(releases) >= 4096:
                raise TransactionError("release-capacity")
            releases.append(Path(entry.path))
    nonempty = 0
    for release in sorted(releases):
        info = release.lstat()
        if (
            not re.fullmatch(r"[0-9a-f]{64}", release.name)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise TransactionError("foreign-release")
        children = []
        with os.scandir(release) as entries:
            for entry in entries:
                if len(children) >= 2:
                    raise TransactionError("foreign-release")
                children.append(Path(entry.path))
        if children:
            nonempty += 1
            if nonempty > 64:
                raise TransactionError("release-capacity")
        for path in sorted(children):
            if path.name not in {"fullchain.pem", "privkey.pem"}:
                raise TransactionError("foreign-release")
            observed = capture(path)
            if observed["kind"] != "file" or observed["mode"] & 0o022:
                raise TransactionError("foreign-release")
            if release.name != prune["keep"]:
                row = {"path": str(path), "kind": "absent"}
                if str(path) in explicit and explicit[str(path)] != row:
                    raise TransactionError("release-prune-conflict")
                if str(path) not in explicit:
                    if len(result["files"]) >= 128:
                        raise TransactionError("release-capacity")
                    result["files"].append(row)
    return result


def compact_empty_releases(document):
    prune = document["prune_releases"]
    if prune is None:
        return
    # Revalidate the whole bounded namespace before any directory deletion.
    expand_release_prune(document)
    root = Path(prune["root"])
    if not root.exists():
        return
    empty = []
    for path in root.iterdir():
        if path.name != prune["keep"] and not any(path.iterdir()):
            empty.append(path)
    for path in empty:
        safe(path)
        path.rmdir()  # Exact owned empty directories only; never recurse.
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def candidate_authority(path):
    if not os.path.lexists(path):
        return
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise TransactionError("foreign-candidate")
    count = 0
    for directory, folders, files in os.walk(path, followlinks=False):
        for name in [*folders, *files]:
            count += 1
            if count > 100000:
                raise TransactionError("candidate-capacity")
            child = Path(directory) / name
            metadata = child.lstat()
            if metadata.st_uid != os.geteuid() or not (
                stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
            ):
                raise TransactionError("foreign-candidate")
            if not stat.S_ISDIR(metadata.st_mode) and metadata.st_nlink != 1:
                raise TransactionError("foreign-candidate")


def remove_candidate(path):
    candidate_authority(path)
    if os.path.lexists(path):
        shutil.rmtree(path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def candidate_workspace(path):
    path.mkdir(mode=0o700)
    try:
        yield path
    finally:
        remove_candidate(path)


def private_json(path):
    row = capture(path)
    if row["kind"] == "absent":
        return None
    if row["kind"] != "file" or row["mode"] != 0o600:
        raise TransactionError("unsafe-journal")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise TransactionError("unsafe-journal")
            result[key] = value
        return result

    return json.loads(base64.b64decode(row["content_b64"]), object_pairs_hook=pairs)


def persist(path, document):
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > LIMIT:
        raise TransactionError("journal-size")
    apply(
        path,
        {
            "kind": "file",
            "uid": os.geteuid(),
            "gid": os.getegid(),
            "mode": 0o600,
            "content_b64": base64.b64encode(raw).decode(),
        },
        [],
    )


def clear(path):
    path.unlink(missing_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fingerprint(document):
    stable = {key: value for key, value in document.items() if key != "check"}
    stable["files"] = sorted(stable["files"], key=lambda row: row["path"])
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def witness(row):
    """Receipts contain typed metadata and digests, never certificate/key bytes."""
    result = {key: value for key, value in row.items() if key != "content_b64"}
    if row["kind"] == "file":
        result["sha256"] = hashlib.sha256(base64.b64decode(row["content_b64"], validate=True)).hexdigest()
    return result


def witness_request(owner, unit, roots, files):
    rows = []
    for path, row in files.items():
        value = dict(row)
        if value.get("kind") == "file":
            digest = value.pop("sha256", None)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise TransactionError("unsafe-receipt")
            value["content_b64"] = ""
        if value.get("kind") == "link" and not Path(value["target"]).is_absolute():
            value["target"] = os.path.normpath(str(Path(path).parent / value["target"]))
        rows.append({"path": path, **value})
    return request({
        "owner": owner, "unit": unit, "roots": roots, "files": rows,
        "validate_argv": ["/usr/sbin/nginx", "-t"], "activation": "reload",
        "check": False, "credential_root": "", "runtime_directories": [],
        "activate_inactive": False, "desired_enabled": None, "prune_releases": None,
    })[0]


def validate_receipt(receipt, owner, unit):
    fields = {"schema", "owner", "unit", "roots", "files", "fingerprint", "active"}
    if isinstance(receipt, dict) and receipt.get("active") is False:
        fields |= {"boot_id", "inactive_after_ticks"}
    if (not isinstance(receipt, dict) or set(receipt) != fields
            or type(receipt.get("schema")) is not int or receipt["schema"] != 2
            or receipt["owner"] != owner or receipt["unit"] != unit
            or type(receipt["active"]) is not bool
            or not isinstance(receipt["files"], dict)
            or not isinstance(receipt["fingerprint"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["fingerprint"])):
        raise TransactionError("unsafe-receipt")
    witness_request(owner, unit, receipt["roots"], receipt["files"])
    if not receipt["active"]:
        if (not isinstance(receipt["boot_id"], str)
                or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", receipt["boot_id"])
                or type(receipt["inactive_after_ticks"]) is not int
                or not 0 <= receipt["inactive_after_ticks"] <= 2**63 - 1):
            raise TransactionError("unsafe-receipt")
        boot, ticks = boot_clock()
        if receipt["boot_id"] == boot and receipt["inactive_after_ticks"] > ticks:
            raise TransactionError("unsafe-receipt")
    return receipt


def validate_receipt_row(row, owner, unit):
    if row == {"kind": "absent"}:
        return
    if (not isinstance(row, dict) or set(row) != {"kind", "uid", "gid", "mode", "content_b64"}
            or row["kind"] != "file" or row["mode"] != 0o600
            or type(row["uid"]) is not int or row["uid"] != os.geteuid()
            or type(row["gid"]) is not int or row["gid"] < 0):
        raise TransactionError("unsafe-receipt")
    raw = base64.b64decode(row["content_b64"], validate=True)
    if len(raw) > LIMIT:
        raise TransactionError("unsafe-receipt")
    validate_receipt(json.loads(raw), owner, unit)


def verify_witnesses(files):
    for path, row in files.items():
        if witness(capture(Path(path))) != row:
            raise TransactionError("foreign-publication")


def owned_receipt(document, files=None, roots=None):
    return {
        "schema": 2, "owner": document["owner"], "unit": document["unit"],
        "roots": roots or document["roots"],
        "files": files if files is not None else {
            row["path"]: witness({k: v for k, v in row.items() if k != "path"})
            for row in document["files"]},
        "fingerprint": fingerprint(document), "active": True,
    }


def merged_roots(roots):
    values = sorted(set(roots))
    return [value for value in values if not any(
        value != other and Path(value).is_relative_to(Path(other)) for other in values)]


@contextmanager
def unit_lock(state):
    safe(state.parent, missing=True)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe(state)
    if stat.S_IMODE(state.stat().st_mode) != 0o700:
        raise TransactionError("unsafe-state")
    descriptor = os.open(state / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise TransactionError("unsafe-lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def site_request(document):
    if (not isinstance(document, dict) or set(document) != {"owners", "check"}
            or type(document["check"]) is not bool or not isinstance(document["owners"], list)
            or len(document["owners"]) != 2):
        raise TransactionError("site-request")
    result = []
    for owner in document["owners"]:
        if (not isinstance(owner, dict) or set(owner) != {"owner", "roots", "paths", "prune_releases"}
                or owner["owner"] not in SITE_OWNERS or not isinstance(owner["paths"], list)):
            raise TransactionError("site-request")
        value = witness_request(owner["owner"], "nginx.service", owner["roots"], {
            path: {"kind": "absent"} for path in owner["paths"]})
        if len(value["files"]) != len(owner["paths"]):
            raise TransactionError("site-request")
        value["prune_releases"] = owner["prune_releases"]
        request(value)
        result.append(value)
    if {value["owner"] for value in result} != SITE_OWNERS:
        raise TransactionError("site-request")
    return result


def read_site(state):
    journal = private_json(state / "site.json")
    if journal is None:
        return None
    if (not isinstance(journal, dict) or set(journal) != {
            "schema", "requests", "files", "receipts", "allowed", "allowed_receipts", "service", "phase"}
            or type(journal["schema"]) is not int or journal["schema"] != 1 or journal["phase"] not in {"open", "restoring"}
            or not isinstance(journal["requests"], list) or len(journal["requests"]) != 2
            or {value.get("owner") for value in journal["requests"]} != SITE_OWNERS):
        raise TransactionError("unsafe-site-journal")
    paths = set()
    for value in journal["requests"]:
        request(value)
        if value["unit"] != "nginx.service" or value["check"]:
            raise TransactionError("unsafe-site-journal")
        paths.update(row["path"] for row in value["files"])
        validate_previous(value, {row["path"]: journal["files"][row["path"]] for row in value["files"]})
    if (set(journal["files"]) != paths or set(journal["allowed"]) != paths
            or set(journal["receipts"]) != SITE_OWNERS
            or set(journal["allowed_receipts"]) != SITE_OWNERS):
        raise TransactionError("unsafe-site-journal")
    for value in journal["requests"]:
        for row in value["files"]:
            choices = journal["allowed"][row["path"]]
            if not isinstance(choices, list) or not 1 <= len(choices) <= 4:
                raise TransactionError("unsafe-site-journal")
            for choice in choices:
                witness_request(value["owner"], value["unit"], value["roots"], {row["path"]: choice})
    for owner in SITE_OWNERS:
        rows = [journal["receipts"][owner], *journal["allowed_receipts"][owner]]
        if not 2 <= len(rows) <= 6:
            raise TransactionError("unsafe-site-journal")
        for row in rows:
            validate_receipt_row(row, owner, "nginx.service")
    prior = journal["service"]
    if (not isinstance(prior, dict) or set(prior) != {"active", "unit_file_state", "exists"}
            or type(prior["active"]) is not bool or type(prior["exists"]) is not bool
            or prior["unit_file_state"] not in {
                "enabled", "enabled-runtime", "disabled", "static", "indirect", "not-found", "masked", "masked-runtime"}):
        raise TransactionError("unsafe-site-journal")
    return journal


def verify_site(state, journal):
    for path, choices in journal["allowed"].items():
        if witness(capture(Path(path))) not in choices:
            raise TransactionError("foreign-publication")
    for owner, choices in journal["allowed_receipts"].items():
        if capture(state / (owner + ".activated.json")) not in choices:
            raise TransactionError("foreign-receipt")


def packaged_default(row):
    if (row.get("kind") != "link" or row.get("uid") != os.geteuid()
            or row.get("gid") != os.getegid() or row.get("mode") != 0o777
            or os.path.normpath(str(DEFAULT_ENABLED.parent / row["target"])) != str(DEFAULT_AVAILABLE)):
        return False
    target = capture(DEFAULT_AVAILABLE)
    if target["kind"] != "file" or target["uid"] != os.geteuid() or target["mode"] != 0o644:
        return False
    return command(["dpkg-query", "--search", str(DEFAULT_AVAILABLE)]).strip() == "nginx-common: " + str(DEFAULT_AVAILABLE)


def admit_packaged_default(state, journal, document):
    name = str(DEFAULT_ENABLED)
    if (journal["files"].get(name) != {"kind": "absent"}
            or not any(row == {"path": name, "kind": "absent"} for row in document["files"])):
        return
    observed = capture(DEFAULT_ENABLED)
    current = witness(observed)
    if current not in journal["allowed"][name] and packaged_default(observed):
        # apt's suppressed-autostart install may create this exact distro link
        # after begin. Admit only its witnessed removal, retaining original
        # absence for site rollback; no other package-created path is adopted.
        journal["allowed"][name].append(current)
        persist(state / "site.json", journal)


def receipt_row(receipt):
    return {"kind": "file", "uid": os.geteuid(), "gid": os.getegid(), "mode": 0o600,
            "content_b64": base64.b64encode(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).decode()}


def site_authorize(state, document, expected_receipt):
    """Extend only the typed site's declared write set before a one-shot writer."""
    journal = read_site(state)
    if journal is None:
        return
    if document["owner"] not in SITE_OWNERS:
        raise TransactionError("site-transaction-busy")
    if journal["phase"] != "open":
        raise TransactionError("recovery-required")
    authorized = next(value for value in journal["requests"] if value["owner"] == document["owner"])
    if not set(row["path"] for row in document["files"]) <= set(row["path"] for row in authorized["files"]):
        raise TransactionError("site-write-set")
    if not all(any(Path(root).is_relative_to(Path(allowed)) for allowed in authorized["roots"])
               for root in document["roots"]):
        raise TransactionError("site-write-set")
    validate_receipt(expected_receipt, document["owner"], document["unit"])
    admit_packaged_default(state, journal, document)
    verify_site(state, journal)
    for row in document["files"]:
        choices = journal["allowed"][row["path"]]
        desired = witness({key: value for key, value in row.items() if key != "path"})
        if desired not in choices:
            choices.append(desired)
            if len(choices) > 4:
                raise TransactionError("site-capacity")
    receipt = receipt_row(expected_receipt)
    choices = journal["allowed_receipts"][document["owner"]]
    if receipt not in choices:
        choices.append(receipt)
    # Inactive one-shot retirement may remove its receipt after publication.
    if {"kind": "absent"} not in choices:
        choices.append({"kind": "absent"})
    persist(state / "site.json", journal)


def site_transaction(action, document):
    requests = site_request(document)
    state = STATE_ROOT / "nginx.service"
    if document["check"]:
        if os.path.lexists(state / "site.json") or os.path.lexists(state / "pending.json"):
            raise TransactionError("recovery-required")
        # Check-only admission uses exactly the receipt validation of begin.
        for value in requests:
            receipt = private_json(state / (value["owner"] + ".activated.json"))
            if receipt is not None:
                validate_receipt(receipt, value["owner"], "nginx.service")
                verify_witnesses(receipt["files"])
        return {"status": "validated", "changed": False}
    if action == "begin":
        # Legacy/foreign receipt authority is refused before even lock creation.
        for value in requests:
            prior = private_json(state / (value["owner"] + ".activated.json"))
            if prior is not None:
                validate_receipt(prior, value["owner"], "nginx.service")
                verify_witnesses(prior["files"])
    with unit_lock(state):
        if action == "begin":
            if os.path.lexists(state / "site.json") or os.path.lexists(state / "pending.json"):
                raise TransactionError("recovery-required")
            files, receipts = {}, {}
            for value in requests:
                path = state / (value["owner"] + ".activated.json")
                prior = private_json(path)
                if prior is not None:
                    validate_receipt(prior, value["owner"], "nginx.service")
                    verify_witnesses(prior["files"])
                    value["roots"] = merged_roots(value["roots"] + prior["roots"])
                    by_path = {row["path"]: row for row in value["files"]}
                    by_path.update({path: {"path": path, "kind": "absent"} for path in prior["files"]})
                    value["files"] = list(by_path.values())
                value = expand_release_prune(value)
                request(value)
                requests[requests.index(next(item for item in requests if item["owner"] == value["owner"]))] = value
                observed = {row["path"]: capture(Path(row["path"])) for row in value["files"]}
                validate_previous(value, observed)
                if prior is None:
                    for name, row in observed.items():
                        default_owned = name == str(DEFAULT_ENABLED) and packaged_default(row)
                        if row["kind"] != "absent" and not default_owned:
                            raise TransactionError("unclaimed-ingress")
                files.update(observed)
                receipts[value["owner"]] = capture(path)
            if sum(len(json.dumps(row)) for row in files.values()) > LIMIT:
                raise TransactionError("snapshot-size")
            journal = {"schema": 1, "phase": "open", "requests": requests, "files": files,
                       "receipts": receipts, "allowed": {path: [witness(row)] for path, row in files.items()},
                       "allowed_receipts": {owner: [row] for owner, row in receipts.items()},
                       "service": service_state("nginx.service")}
            persist(state / "site.json", journal)
            return {"status": "captured", "changed": False}
        journal = read_site(state)
        if journal is None:
            return {"status": "absent", "changed": False}
        pending = private_json(state / "pending.json")
        if pending is not None:
            if action == "commit":
                raise TransactionError("recovery-required")
            staged, _ = request(pending["request"])
            authorized = next((value for value in journal["requests"]
                               if value["owner"] == staged["owner"]), None)
            if (authorized is None or staged["unit"] != "nginx.service"
                    or not {row["path"] for row in staged["files"]}
                    <= {row["path"] for row in authorized["files"]}
                    or not all(any(Path(root).is_relative_to(Path(allowed))
                                   for allowed in authorized["roots"]) for root in staged["roots"])):
                raise TransactionError("site-write-set")
            recover(state / "pending.json", "nginx.service")
        verify_site(state, journal)
        if action == "commit":
            for owner in SITE_OWNERS:
                current = private_json(state / (owner + ".activated.json"))
                if current is not None:
                    validate_receipt(current, owner, "nginx.service")
                    verify_witnesses(current["files"])
            clear(state / "site.json")
            return {"status": "committed", "changed": False}
        journal["phase"] = "restoring"
        persist(state / "site.json", journal)
        prior = journal["service"]
        if not prior["active"]:
            command(["systemctl", "stop", "nginx.service"])
        changed = False
        for path, row in journal["files"].items():
            observed = capture(Path(path))
            if witness(observed) not in journal["allowed"][path]:
                raise TransactionError("foreign-publication")
            if observed != row:
                apply(Path(path), row, [])
                changed = True
        for owner, row in journal["receipts"].items():
            path = state / (owner + ".activated.json")
            if capture(path) not in journal["allowed_receipts"][owner]:
                raise TransactionError("foreign-receipt")
            apply(path, row, [])
        if "/etc/systemd/system/nginx.service" in journal["files"]:
            command(["systemctl", "daemon-reload"])
        if prior["exists"]:
            restore_enabled("nginx.service", prior)
        elif service_state("nginx.service")["exists"]:
            # Fresh role installation may add the distro unit. Retain packages,
            # but never leave a failed first candidate enabled at boot.
            command(["systemctl", "disable", "nginx.service"])
            current = service_state("nginx.service")
            if current["active"] or current["unit_file_state"] not in {"disabled", "static", "indirect"}:
                raise TransactionError("enablement-restore-failed")
        if prior["active"]:
            command(["/usr/sbin/nginx", "-t"])
            command(["systemctl", "reset-failed", "nginx.service"])
            command(["systemctl", "restart", "nginx.service"])
            command(["systemctl", "is-active", "--quiet", "nginx.service"])
            wait_adoption("nginx.service")
        clear(state / "site.json")
        return {"status": "restored", "changed": changed}


def recover(pending, unit):
    journal = private_json(pending)
    if journal is None:
        return False
    if (
        not isinstance(journal, dict)
        or set(journal)
        != {
            "schema",
            "phase",
            "request",
            "files",
            "active",
            "service",
            "owner",
            "candidate",
            "receipt",
            "next_receipt",
        }
        or type(journal["schema"]) is not int
        or journal["schema"] != 2
        or journal["phase"]
        not in {"prepared", "publishing", "activating", "activated", "recovering"}
    ):
        raise TransactionError("manual-recovery-required")
    if not isinstance(journal["candidate"], str) or not re.fullmatch(
        r"candidate-[0-9a-f]{32}", journal["candidate"]
    ):
        raise TransactionError("foreign-candidate")
    candidate = pending.parent / journal["candidate"]
    candidate_authority(candidate)
    original, roots = request(journal["request"])
    if (
        original["unit"] != unit
        or original["check"]
        or original["owner"] != journal["owner"]
    ):
        raise TransactionError("manual-recovery-required")
    previous = journal["files"]
    prior_receipt = journal["receipt"]
    validate_receipt_row(prior_receipt, original["owner"], unit)
    validate_receipt_row(journal["next_receipt"], original["owner"], unit)
    current_receipt = capture(pending.parent / (original["owner"] + ".activated.json"))
    allowed_receipts = [prior_receipt]
    if journal["phase"] in {"activated", "recovering"}:
        allowed_receipts.append(journal["next_receipt"])
        if not journal["active"] and not original["activate_inactive"]:
            allowed_receipts.append({"kind": "absent"})
    if current_receipt not in allowed_receipts:
        raise TransactionError("foreign-receipt")
    prior = journal["service"]
    if (
        not isinstance(previous, dict)
        or set(previous) != {row["path"] for row in original["files"]}
        or not isinstance(prior, dict)
        or set(prior) != {"active", "unit_file_state", "exists"}
        or type(prior["active"]) is not bool
        or type(prior["exists"]) is not bool
        or journal["active"] != prior["active"]
        or prior["unit_file_state"]
        not in {
            "enabled",
            "enabled-runtime",
            "disabled",
            "static",
            "indirect",
            "not-found",
            "masked",
            "masked-runtime",
        }
    ):
        raise TransactionError("manual-recovery-required")
    validate_previous(original, previous)
    desired = {
        row["path"]: {k: v for k, v in row.items() if k != "path"}
        for row in original["files"]
    }
    # Validate the entire write set before touching any runtime or disk state.
    for path, row in previous.items():
        if row["kind"] != "absent" and row["uid"] != os.geteuid():
            raise TransactionError("foreign-journal")
        observed = capture(Path(path))
        if observed != row and observed != desired[path]:
            raise TransactionError("foreign-publication")
    if journal["phase"] != "prepared":
        journal["phase"] = "recovering"
        persist(pending, journal)
        if not prior["active"]:
            command(["systemctl", "stop", unit])
        unit_path = "/etc/systemd/system/" + unit
        if (
            not prior["exists"]
            and unit_path in desired
            and capture(Path(unit_path))["kind"] != "absent"
        ):
            command(["systemctl", "disable", unit])
        for path, row in previous.items():
            if capture(Path(path)) != row:
                apply(Path(path), row, [])
        if unit_path in desired:
            command(["systemctl", "daemon-reload"])
        restore_enabled(unit, prior)
        if prior["active"]:
            command(["systemctl", "reset-failed", unit])
            command(["systemctl", "restart", unit])
            command(["systemctl", "is-active", "--quiet", unit])
            wait_adoption(unit)
    apply(pending.parent / (original["owner"] + ".activated.json"), prior_receipt, [])
    remove_candidate(candidate)
    clear(pending)
    return True


def publish(document):
    document, roots = request(document)
    logical_document = copy.deepcopy(document)
    admission_receipt = private_json(STATE_ROOT / document["unit"] / (document["owner"] + ".activated.json"))
    if admission_receipt is not None:
        validate_receipt(admission_receipt, document["owner"], document["unit"])
        verify_witnesses(admission_receipt["files"])
    previous = {row["path"]: capture(Path(row["path"])) for row in document["files"]}
    total = sum(len(json.dumps(row)) for row in previous.values())
    if total > LIMIT:
        raise TransactionError("snapshot-size")
    validate_previous(document, previous)
    state = STATE_ROOT / document["unit"]
    safe(state.parent, missing=True)
    pending = state / "pending.json"
    if document["check"]:
        document = expand_release_prune(document)
        previous = {
            row["path"]: capture(Path(row["path"])) for row in document["files"]
        }
        changed = any(
            {key: value for key, value in row.items() if key != "path"}
            != previous[row["path"]]
            for row in document["files"]
        )
        if os.path.lexists(pending):
            raise TransactionError("recovery-required")
        return {
            "status": "would-change" if changed else "unchanged",
            "changed": changed,
        }
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe(state)
    if stat.S_IMODE(state.stat().st_mode) != 0o700:
        raise TransactionError("unsafe-state")
    prepared_owned = False
    publication_may_have_occurred = False
    lock_fd = os.open(state / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise TransactionError("unsafe-lock")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recovered = recover(pending, document["unit"])
        document = expand_release_prune(logical_document)
        request(document)
        receipt = state / (document["owner"] + ".activated.json")
        receipt_data = private_json(receipt)
        if receipt_data is not None:
            validate_receipt(receipt_data, document["owner"], document["unit"])
            verify_witnesses(receipt_data["files"])
        prior_receipt = capture(receipt)
        removed = {row["path"] for row in document["files"] if row["kind"] == "absent"}
        retained = {} if receipt_data is None else {
            path: row for path, row in receipt_data["files"].items()
            if row["kind"] != "absent" and path not in removed}
        expected_receipt = owned_receipt(logical_document, {
            **retained,
            **{row["path"]: witness({k: v for k, v in row.items() if k != "path"})
               for row in logical_document["files"]},
        }, merged_roots(document["roots"] + ([] if receipt_data is None else receipt_data["roots"])))
        validate_receipt(expected_receipt, document["owner"], document["unit"])
        activation_due = receipt_data != expected_receipt
        # Re-capture under the shared per-unit writer lock.
        previous = {
            row["path"]: capture(Path(row["path"])) for row in document["files"]
        }
        total = sum(len(json.dumps(row)) for row in previous.values())
        if total > LIMIT:
            raise TransactionError("snapshot-size")
        validate_previous(document, previous)
        changed = any(
            {key: value for key, value in row.items() if key != "path"}
            != previous[row["path"]]
            for row in document["files"]
        )
        previous_service = service_state(document["unit"])
        inactive_adoption = None
        if (
            not changed
            and previous_service["active"]
            and all(row["kind"] == "absent" for row in document["files"])
            and receipt_data is not None
            and receipt_data["active"] is False
            and receipt_data["fingerprint"] == expected_receipt["fingerprint"]
            and receipt_data["boot_id"] == boot_clock()[0]
        ):
            master = nginx_master(document["unit"])
            if int(master[1]) > receipt_data["inactive_after_ticks"]:
                if wait_adoption(document["unit"]) != master[0]:
                    raise TransactionError("runtime-identity")
                inactive_adoption = (master, nginx_workers(master))
                stable_generation(document["unit"], inactive_adoption)
                activation_due = False
        if (
            not changed
            and not document["activate_inactive"]
            and document["desired_enabled"] is None
            and not document["credential_root"]
            and not recovered
        ):
            if not previous_service["active"]:
                if all(row["kind"] == "absent" for row in document["files"]):
                    inactive_receipt = inactive_absence_receipt(document["unit"], expected_receipt)
                    site_authorize(state, document, inactive_receipt)
                    persist(receipt, inactive_receipt)
                compact_empty_releases(logical_document)
                return {"status": "unchanged", "changed": False}
            if not activation_due and inactive_adoption is None:
                compact_empty_releases(logical_document)
                return {"status": "unchanged", "changed": False}
        if previous_service["unit_file_state"] in {"masked", "masked-runtime"} and (
            document["activate_inactive"] or document["desired_enabled"] is not None
        ):
            raise TransactionError("masked-unit")
        snapshot = {
            "schema": 2,
            "candidate": "candidate-" + uuid.uuid4().hex,
            "phase": "prepared",
            "request": document,
            "files": previous,
            "active": previous_service["active"],
            "service": previous_service,
            "owner": document["owner"],
            "receipt": prior_receipt,
            "next_receipt": receipt_row(expected_receipt),
        }
        site_authorize(state, document, expected_receipt)
        prepared_owned = True
        persist(pending, snapshot)
        with candidate_workspace(state / snapshot["candidate"]) as candidate:
            bindings = []
            staged_roots = set()
            for index, root in enumerate(roots):
                if not os.path.lexists(root):
                    # A disabled owner may never have created its payload tree.
                    # Its absence is already the complete candidate: do not
                    # manufacture a host mount point merely to adopt nginx.
                    if any(
                        row["kind"] != "absent"
                        and Path(row["path"]).is_relative_to(root)
                        for row in document["files"]
                    ) or (
                        document["credential_root"]
                        and Path(document["credential_root"]).is_relative_to(root)
                    ):
                        raise TransactionError("missing-root")
                    continue
                safe(root)
                target = candidate / str(index)
                shutil.copytree(root, target, symlinks=True)
                bindings.append({"source": str(target), "target": str(root)})
                staged_roots.add(root)
            for row in document["files"]:
                path = Path(row["path"])
                root = next((root for root in roots if path.is_relative_to(root)), None)
                if root in staged_roots:
                    stage = candidate / str(roots.index(root)) / path.relative_to(root)
                    # A copied symlink may be replaced, never traversed during writes.
                    apply(
                        stage,
                        {key: value for key, value in row.items() if key != "path"},
                        [],
                    )
            credential = document["credential_root"]
            credential_source = ""
            if credential:
                root = next(
                    root for root in roots if Path(credential).is_relative_to(root)
                )
                credential_source = str(
                    candidate
                    / str(roots.index(root))
                    / Path(credential).relative_to(root)
                )
            manifest = {
                "bindings": bindings,
                "credential_source": credential_source,
                "unit": document["unit"],
                "runtime_directories": document["runtime_directories"],
                "validate_argv": document["validate_argv"],
            }
            manifest_path = candidate / "validation.json"
            manifest_path.write_text(json.dumps(manifest))
            manifest_path.chmod(0o600)
            try:
                command(
                    [
                        "unshare",
                        "--mount",
                        "--propagation",
                        "private",
                        sys.executable,
                        __file__,
                        "--validate",
                        str(manifest_path),
                    ]
                )
            except TransactionError:
                raise TransactionError("candidate-invalid") from None
            created = []
            attempted = []
            unit_changed = any(
                row["path"] == "/etc/systemd/system/" + document["unit"]
                and {key: value for key, value in row.items() if key != "path"}
                != previous[row["path"]]
                for row in document["files"]
            )
            publication_may_have_occurred = True
            snapshot["phase"] = "publishing"
            persist(pending, snapshot)
            try:
                for row in document["files"]:
                    path = Path(row["path"])
                    if capture(path) != previous[row["path"]]:
                        raise TransactionError("file-changed")
                    expected = {
                        key: value for key, value in row.items() if key != "path"
                    }
                    if expected != previous[row["path"]]:
                        attempted.append(row)
                        apply(path, expected, created)
                if unit_changed:
                    command(["systemctl", "daemon-reload"])
                enablement_changed = set_enabled(
                    document["unit"], document["desired_enabled"]
                )
                snapshot["phase"] = "activating"
                persist(pending, snapshot)
                if (
                    (changed or activation_due)
                    and snapshot["active"]
                    or not snapshot["active"]
                    and document["activate_inactive"]
                ):
                    reload_previous = None
                    if snapshot["active"] and document["activation"] == "reload":
                        master = nginx_master(document["unit"])
                        reload_previous = (master, nginx_workers(master))
                        if not reload_previous[1]:
                            raise TransactionError("runtime-not-ready")
                    command(
                        [
                            "systemctl",
                            document["activation"] if snapshot["active"] else "start",
                            document["unit"],
                        ]
                    )
                    wait_adoption(document["unit"], reload_previous)
                if snapshot["active"] or document["activate_inactive"]:
                    command(["systemctl", "is-active", "--quiet", document["unit"]])
                    if inactive_adoption is not None:
                        stable_generation(document["unit"], inactive_adoption)
                    main_pid = command(
                        [
                            "systemctl",
                            "show",
                            document["unit"],
                            "--property=MainPID",
                            "--value",
                        ]
                    ).strip()
                    if (
                        not main_pid.isascii()
                        or not main_pid.isdigit()
                        or int(main_pid) <= 0
                    ):
                        raise TransactionError("runtime-not-ready")
                    # Revalidate in the actual unit namespace, including its
                    # loaded credentials and strict writable PID/log paths.
                    command(
                        [
                            "nsenter",
                            "--mount",
                            "--target",
                            main_pid,
                            *document["validate_argv"],
                        ]
                    )
                    command(["systemctl", "is-active", "--quiet", document["unit"]])
                    if inactive_adoption is not None:
                        stable_generation(document["unit"], inactive_adoption)
            except Exception:
                try:
                    if not snapshot["active"]:
                        command(["systemctl", "stop", document["unit"]])
                    if not snapshot["service"]["exists"] and any(
                        row["path"] == "/etc/systemd/system/" + document["unit"]
                        for row in attempted
                    ):
                        # Disable while the newly published unit still exists:
                        # removing it first can leave dangling boot Wants links
                        # that UnitFileState=not-found does not reveal.
                        command(["systemctl", "disable", document["unit"]])
                    for row in reversed(attempted):
                        path = row["path"]
                        observed = capture(Path(path))
                        expected = {
                            key: value for key, value in row.items() if key != "path"
                        }
                        if observed != previous[path] and observed != expected:
                            raise TransactionError("foreign-publication")
                        apply(Path(path), previous[path], [])
                    if unit_changed:
                        command(["systemctl", "daemon-reload"])
                    restore_enabled(document["unit"], snapshot["service"])
                    if snapshot["active"]:
                        # Clear only the failed candidate's unit latch after
                        # restoring known prior authority, then make one recovery
                        # start; never weaken its StartLimit policy.
                        command(["systemctl", "reset-failed", document["unit"]])
                        command(["systemctl", "restart", document["unit"]])
                        command(["systemctl", "is-active", "--quiet", document["unit"]])
                        wait_adoption(document["unit"])
                    for directory in reversed(created):
                        Path(directory).rmdir()
                except Exception:
                    raise TransactionError("manual-recovery-required") from None
                remove_candidate(candidate)
                clear(pending)
                raise TransactionError("publication-compensated") from None
        snapshot["phase"] = "activated"
        persist(pending, snapshot)
        compact_empty_releases(logical_document)
        if snapshot["active"] or document["activate_inactive"]:
            if inactive_adoption is not None:
                stable_generation(document["unit"], inactive_adoption)
            persist(receipt, expected_receipt)
            if inactive_adoption is not None:
                try:
                    stable_generation(document["unit"], inactive_adoption)
                except (OSError, TransactionError):
                    # Keep the prior disk-only witness if runtime changed while
                    # promotion was being committed. The journal remains for
                    # recovery; this call cannot acknowledge that generation.
                    if private_json(receipt) != expected_receipt:
                        raise TransactionError("foreign-receipt") from None
                    apply(receipt, prior_receipt, [])
                    raise TransactionError("runtime-identity") from None
        else:
            clear(receipt)
        clear(pending)
        actual_changed = (
            recovered
            or activation_due
            and snapshot["active"]
            or changed
            or enablement_changed
            or not snapshot["active"]
            and document["activate_inactive"]
        )
        return {
            "status": "committed" if actual_changed else "unchanged",
            "changed": actual_changed,
        }
    finally:
        # Only this invocation's prepared snapshot is disposable before any
        # live publication/activation. Existing or post-publication authority
        # remains available for explicit recovery after an ambiguous failure.
        if prepared_owned and not publication_may_have_occurred:
            remove_candidate(state / snapshot["candidate"])
            clear(pending)
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate")
    parser.add_argument("--site", choices=("begin", "restore", "commit"))
    args = parser.parse_args()
    try:
        if args.validate:
            validate(json.loads(Path(args.validate).read_text()))
            return 0
        data = sys.stdin.buffer.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise TransactionError("request-size")
        document = json.loads(data)
        print(json.dumps(site_transaction(args.site, document) if args.site else publish(document)))
    except (TransactionError, OSError, ValueError, KeyError, TypeError):
        print("nginx publication failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
