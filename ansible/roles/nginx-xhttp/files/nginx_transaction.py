#!/usr/bin/env python3
"""Complete nginx candidate validation and bounded ordinary-failure compensation."""

from __future__ import annotations

import argparse
import base64
import fcntl
import grp
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

LIMIT = 8 * 1024 * 1024


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
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT:
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
            path.unlink()
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
    expected = {
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


def publish(document):
    document, roots = request(document)
    previous = {row["path"]: capture(Path(row["path"])) for row in document["files"]}
    total = sum(len(json.dumps(row)) for row in previous.values())
    if total > LIMIT:
        raise TransactionError("snapshot-size")
    changed = any(
        {key: value for key, value in row.items() if key != "path"}
        != previous[row["path"]]
        for row in document["files"]
    )
    state = Path("/var/lib/vpn-nginx-publication") / document["unit"]
    safe(state.parent, missing=True)
    pending = state / "pending.json"
    if os.path.lexists(pending):
        raise TransactionError("manual-recovery-required")
    if document["check"]:
        return {
            "status": "would-change" if changed else "unchanged",
            "changed": changed,
        }
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe(state)
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
        if os.path.lexists(pending):
            raise TransactionError("manual-recovery-required")
        # Re-capture under the shared per-unit writer lock.
        previous = {
            row["path"]: capture(Path(row["path"])) for row in document["files"]
        }
        total = sum(len(json.dumps(row)) for row in previous.values())
        if total > LIMIT:
            raise TransactionError("snapshot-size")
        changed = any(
            {key: value for key, value in row.items() if key != "path"}
            != previous[row["path"]]
            for row in document["files"]
        )
        if (
            not changed
            and not document["activate_inactive"]
            and document["desired_enabled"] is None
        ):
            return {"status": "unchanged", "changed": False}
        previous_service = service_state(document["unit"])
        if previous_service["unit_file_state"] in {"masked", "masked-runtime"} and (
            document["activate_inactive"] or document["desired_enabled"] is not None
        ):
            raise TransactionError("masked-unit")
        snapshot = {
            "phase": "prepared",
            "files": previous,
            "active": previous_service["active"],
            "service": previous_service,
            "owner": document["owner"],
        }
        prepared_owned = True
        apply(
            pending,
            {
                "kind": "file",
                "uid": os.geteuid(),
                "gid": os.getegid(),
                "mode": 0o600,
                "content_b64": base64.b64encode(json.dumps(snapshot).encode()).decode(),
            },
            [],
        )
        with tempfile.TemporaryDirectory(prefix="candidate-", dir=state) as temporary:
            candidate = Path(temporary)
            bindings = []
            for index, root in enumerate(roots):
                target = candidate / str(index)
                shutil.copytree(root, target, symlinks=True)
                bindings.append({"source": str(target), "target": str(root)})
            for row in document["files"]:
                path = Path(row["path"])
                root = next((root for root in roots if path.is_relative_to(root)), None)
                if root is not None:
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
                pending.unlink()
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
                if (
                    changed
                    and snapshot["active"]
                    or not snapshot["active"]
                    and document["activate_inactive"]
                ):
                    command(
                        [
                            "systemctl",
                            document["activation"] if snapshot["active"] else "start",
                            document["unit"],
                        ]
                    )
                if snapshot["active"] or document["activate_inactive"]:
                    command(["systemctl", "is-active", "--quiet", document["unit"]])
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
                    for directory in reversed(created):
                        Path(directory).rmdir()
                except Exception:
                    raise TransactionError("manual-recovery-required") from None
                pending.unlink()
                raise TransactionError("publication-compensated") from None
        pending.unlink()
        actual_changed = (
            changed
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
            pending.unlink(missing_ok=True)
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate")
    args = parser.parse_args()
    try:
        if args.validate:
            validate(json.loads(Path(args.validate).read_text()))
            return 0
        data = sys.stdin.buffer.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise TransactionError("request-size")
        print(json.dumps(publish(json.loads(data))))
    except (TransactionError, OSError, ValueError, KeyError, TypeError):
        print("nginx publication failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
