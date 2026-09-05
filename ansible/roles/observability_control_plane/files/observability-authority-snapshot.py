#!/usr/bin/env python3
"""Bounded ordinary-failure rollback of the role's fixed authority write-set."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

CONFIG = "etc/observability-control-plane"
CREDENTIALS = CONFIG + "/credentials/"
DEADMAN_METRIC = "var/lib/node_exporter/textfile/observability-deadman.prom"
NAMES = [
    "telegram-bot-token",
    "telegram-relay-auth-token",
    "deadman-pulse-token",
    "deadman-pulse-ca.pem",
    "deadman-canary-auth-token",
    "silence-policy.json",
    "silence-auth.json",
    "silence-sender-token",
    "silence-backend-ca.pem",
    "silence-backend-server.crt",
    "silence-backend-server.key",
    "silence-backend-client.crt",
    "silence-backend-client.key",
]
PIPELINE_STATE = [
    "var/lib/observability-pipeline/generation.json",
    "var/lib/observability-pipeline/canary.json",
    "var/lib/observability-pipeline/primary-canary.json",
    "var/lib/observability-pipeline/pulse-state.json",
    "var/lib/observability-pipeline/reverse-state.json",
]
SERVICES = [
    "observability-alertmanager.service",
    "observability-telegram-relay.service",
    "observability-silence-gateway.service",
    "observability-prometheus.service",
    "observability-deadman-pipeline.service",
    "observability-deadman-pulse.service",
    "observability-primary-canary.service",
    "observability-deadman-pulse.timer",
    "observability-primary-canary.timer",
]
FIXED = (
    [CREDENTIALS + name for name in NAMES]
    + [
        CONFIG + "/alertmanager-web.yml",
        "etc/systemd/system/observability-alertmanager.service",
        "etc/systemd/system/observability-telegram-relay.service",
        "etc/systemd/system/observability-silence-gateway.service",
        "etc/systemd/system/observability-deadman-pipeline.service",
        "etc/systemd/system/observability-deadman-pulse.service",
        "etc/systemd/system/observability-deadman-pulse.timer",
        "etc/systemd/system/observability-primary-canary.service",
        "etc/systemd/system/observability-primary-canary.timer",
        "usr/local/libexec/observability-silence-gateway",
        "usr/local/libexec/observability-telegram-relay",
        "usr/local/libexec/observability-deadman-pipeline.py",
        CONFIG + "/alertmanager-current.yml",
        CONFIG + "/alertmanager-previous.yml",
        DEADMAN_METRIC,
    ]
    + PIPELINE_STATE
)
LINKS = {CONFIG + "/alertmanager-current.yml", CONFIG + "/alertmanager-previous.yml"}
ALIAS = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
SAFE_FAILURE_CATEGORIES = {
    "root": "root",
    "owner-set": "request",
    "service-state": "request",
    "manual-recovery-required": "recovery",
    "untracked-owner-token": "namespace",
    "unsafe-parent": "unsafe_parent",
    "config-parent": "config_parent",
    "systemd-parent": "systemd_parent",
    "libexec-parent": "libexec_parent",
    "pipeline-parent": "pipeline_parent",
    "textfile-parent": "textfile_parent",
    "foreign-file": "unsafe_file",
    "unsafe-link": "unsafe_file",
    "unsupported-entry": "unsafe_file",
    "unsafe-file": "unsafe_file",
    "credential-mode": "credential_mode",
    "textfile-mode": "textfile_mode",
    "file-size": "file_size",
    "snapshot-size": "snapshot_size",
    "snapshot-mode": "snapshot",
    "snapshot-file": "snapshot",
    "snapshot-identity": "snapshot",
    "snapshot-foreign-entry": "snapshot",
    "action": "request",
}


def owners(values, limit=32):
    if (
        not isinstance(values, list)
        or len(values) > limit
        or any(
            not isinstance(value, str) or not ALIAS.fullmatch(value) for value in values
        )
        or len(set(values)) != len(values)
    ):
        raise ValueError("owner-set")
    return values


def safe_failure_category(error):
    """Expose a fixed failure class without paths, bytes, or exception details."""
    if isinstance(error, FileNotFoundError):
        return "missing_parent"
    if isinstance(error, (PermissionError, OSError)):
        return "filesystem"
    if isinstance(error, (json.JSONDecodeError, KeyError, TypeError)):
        return "request"
    if isinstance(error, ValueError):
        return SAFE_FAILURE_CATEGORIES.get(str(error), "invalid_state")
    return "internal"


def prepare_parent_category(relative):
    """Classify only fixed write-set surfaces; never emit a filesystem path."""
    if relative == DEADMAN_METRIC:
        return "textfile-parent"
    if relative in PIPELINE_STATE:
        return "pipeline-parent"
    if relative.startswith(CONFIG + "/"):
        return "config-parent"
    if relative.startswith("etc/systemd/"):
        return "systemd-parent"
    if relative.startswith("usr/local/libexec/"):
        return "libexec-parent"
    return "unsafe-parent"


class Snapshot:
    def __init__(self, root):
        self.root = Path(root)
        if (
            not self.root.is_absolute()
            or self.root.resolve() != self.root
            or (self.root == Path("/") and os.geteuid() != 0)
        ):
            raise ValueError("root")
        self.directory = self.root / CONFIG / ".authority-rollback"
        self.path = self.directory / "snapshot.json"

    def parent(
        self,
        path,
        *,
        allow_missing=False,
        allow_final_sticky=False,
        failure_category="unsafe-parent",
    ):
        relative = path.parent.relative_to(self.root)
        current = self.root
        for part in ("", *relative.parts):
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                if allow_missing and current != self.root:
                    return False
                raise
            mode = stat.S_IMODE(info.st_mode)
            shared_textfile = (
                allow_final_sticky
                and current == path.parent
                and mode == 0o3775
                and info.st_uid in {0, os.geteuid()}
            )
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or (mode & 0o022 and not shared_textfile)
            ):
                raise ValueError(failure_category)
        return True

    def read(
        self,
        relative,
        limit=262144,
        *,
        allow_missing=False,
        prepare_capture=False,
    ):
        path = self.root / relative
        if not self.parent(
            path,
            allow_missing=allow_missing,
            allow_final_sticky=relative == DEADMAN_METRIC,
            failure_category=(
                prepare_parent_category(relative)
                if prepare_capture
                else "unsafe-parent"
            ),
        ):
            return {"kind": "absent"}
        try:
            info = path.lstat()
        except FileNotFoundError:
            return {"kind": "absent"}
        if info.st_uid != os.geteuid():
            raise ValueError("foreign-file")
        metadata = {
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode),
        }
        if relative in LINKS and stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            if not re.fullmatch(
                re.escape(str(self.root / CONFIG / "generations"))
                + r"/alertmanager-[a-f0-9]{64}\.yml",
                target,
            ):
                raise ValueError("unsafe-link")
            return {**metadata, "kind": "link", "target": target}
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("unsupported-entry")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                or metadata["mode"] & 0o022
            ):
                raise ValueError("unsafe-file")
            if (
                relative.startswith(CREDENTIALS) or relative in PIPELINE_STATE
            ) and metadata["mode"] != 0o600:
                raise ValueError("credential-mode")
            if relative == DEADMAN_METRIC and metadata["mode"] != 0o644:
                raise ValueError("textfile-mode")
            content = stream.read(limit + 1)
        if len(content) > limit:
            raise ValueError("file-size")
        return {
            **metadata,
            "kind": "file",
            "content": base64.b64encode(content).decode(),
        }

    def save(self, state, *, failure_category="unsafe-parent"):
        payload = json.dumps(state, sort_keys=True).encode()
        if len(payload) > 8388608:
            raise ValueError("snapshot-size")
        self.parent(self.path, failure_category=failure_category)
        descriptor, temporary = tempfile.mkstemp(
            dir=self.directory, prefix=".snapshot-"
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.lexists(temporary):
                os.unlink(temporary)

    def load(self, identifier):
        self.parent(self.path)
        info = self.directory.lstat()
        if stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("snapshot-mode")
        row = self.read(str(self.path.relative_to(self.root)), limit=8388608)
        if row["kind"] != "file" or row["mode"] != 0o600:
            raise ValueError("snapshot-file")
        state = json.loads(base64.b64decode(row["content"]))
        expected = set(
            FIXED
            + [
                CREDENTIALS + "silence-owner-" + owner + "-token"
                for owner in owners(state["owners"], limit=64)
            ]
        )
        if state["id"] != identifier or set(state["files"]) != expected:
            raise ValueError("snapshot-identity")
        return state

    def prepare(self, request, *, inspect_only=False):
        if os.path.lexists(self.directory):
            raise ValueError("manual-recovery-required")
        candidate = owners(request["owners"])
        old_auth = self.read(
            CREDENTIALS + "silence-auth.json",
            allow_missing=inspect_only,
            prepare_capture=True,
        )
        previous = (
            owners(
                [
                    row["owner"]
                    for row in json.loads(base64.b64decode(old_auth["content"]))[
                        "owners"
                    ]
                ]
            )
            if old_auth["kind"] == "file"
            else []
        )
        known = set(previous + candidate)
        credential_directory = self.root / CREDENTIALS
        for path in (
            credential_directory.iterdir() if credential_directory.exists() else []
        ):
            if path.name.startswith("silence-owner-") and path.name not in {
                "silence-owner-" + owner + "-token" for owner in known
            }:
                raise ValueError("untracked-owner-token")
        services = request["services"]
        if set(services) != set(SERVICES) or any(
            set(row) != {"exists", "active", "enabled"}
            or any(type(value) is not bool for value in row.values())
            for row in services.values()
        ):
            raise ValueError("service-state")
        paths = FIXED + [
            CREDENTIALS + "silence-owner-" + owner + "-token" for owner in sorted(known)
        ]
        state = {
            "id": None if inspect_only else uuid.uuid4().hex,
            "phase": "prepared",
            "owners": sorted(known),
            "previous_owners": previous,
            "services": services,
            "files": {
                path: self.read(
                    path,
                    allow_missing=(
                        inspect_only or path in PIPELINE_STATE or path == DEADMAN_METRIC
                    ),
                    prepare_capture=True,
                )
                for path in paths
            },
        }
        if inspect_only and len(json.dumps(state, sort_keys=True).encode()) > 8388608:
            raise ValueError("snapshot-size")
        if not inspect_only:
            self.parent(self.directory, failure_category="config-parent")
            self.directory.mkdir(mode=0o700)
            self.save(state, failure_category="config-parent")
        return {key: state[key] for key in ("id", "previous_owners", "services")}

    def restore(self, state):
        state["phase"] = "restoring"
        self.save(state)
        for relative, row in state["files"].items():
            path = self.root / relative
            self.read(
                relative, allow_missing=row["kind"] == "absent"
            )  # Refuse foreign/symlink replacement before any overwrite.
            if row["kind"] == "absent":
                if os.path.lexists(path):
                    path.unlink()
                continue
            descriptor, temporary = tempfile.mkstemp(
                dir=path.parent, prefix=".authority-"
            )
            try:
                if row["kind"] == "link":
                    os.close(descriptor)
                    os.unlink(temporary)
                    os.symlink(row["target"], temporary)
                    os.lchown(temporary, row["uid"], row["gid"])
                else:
                    with os.fdopen(descriptor, "wb") as stream:
                        os.fchmod(stream.fileno(), row["mode"])
                        os.fchown(stream.fileno(), row["uid"], row["gid"])
                        stream.write(base64.b64decode(row["content"], validate=True))
                        stream.flush()
                        os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.lexists(temporary):
                    os.unlink(temporary)
        state["phase"] = "restored"
        self.save(state)

    def finish(self, state):
        if set(path.name for path in self.directory.iterdir()) != {"snapshot.json"}:
            raise ValueError("snapshot-foreign-entry")
        self.path.unlink()
        self.directory.rmdir()


def main():
    action, root, *identifiers = sys.argv[1:]
    snapshot = Snapshot(root)
    if action in ("prepare", "inspect"):
        print(
            json.dumps(
                snapshot.prepare(json.load(sys.stdin), inspect_only=action == "inspect")
            )
        )
        return
    state = snapshot.load(identifiers[0])
    try:
        if action == "restore":
            snapshot.restore(state)
        elif action == "finish":
            snapshot.finish(state)
        elif action == "mark":
            state["phase"] = "manual-recovery"
            snapshot.save(state)
        else:
            raise ValueError("action")
    except Exception:
        state["phase"] = "manual-recovery"
        snapshot.save(state)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(safe_failure_category(error))
        raise SystemExit(1) from None
