"""Private manifest and durable operation journal for executable recovery."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
PATH_FIELDS = {"state_directory", "sops_file", "age_key_file", "ssh_key_file",
               "known_hosts_file", "bootstrap_config", "promotion_configs_file", "migration_plan"}
FIELDS = {"schema_version", "id", "provider", "environment", "source_revision", "account",
          "hostname", "cohort", "inventory", *PATH_FIELDS}


class RecoveryError(ValueError):
    """Categorical errors only; private inputs must not appear in diagnostics."""


class ActionRequired(RecoveryError):
    def __init__(self, action, digest, artifact):
        super().__init__(action)
        self.action, self.digest, self.artifact = action, digest, str(artifact)


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryError("duplicate-key")
        result[key] = value
    return result


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read(path, *, limit=1_048_576, private=True):
    deploy = module("deploy-controller")
    try:
        return deploy.read_input(path, private=private,
                 exact_mode=0o600 if private else None, limit=limit)
    except deploy.DeployError:
        raise RecoveryError("unsafe-or-unreadable-input") from None


def document(path):
    try:
        value = json.loads(read(path), object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise TypeError
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise RecoveryError("invalid-private-document") from None


def load_manifest(path):
    value = document(path)
    try:
        if (set(value) != FIELDS or type(value["schema_version"]) is not int
                or value["schema_version"] != 1 or value["provider"] != "upcloud"
                or any(not NAME.fullmatch(value[key]) for key in ("id", "environment", "cohort"))
                or value["environment"] in {"default", "prod", "staging"}
                or value["environment"].startswith("ci-staging-")
                or not ALIAS.fullmatch(value["hostname"])
                or not re.fullmatch(r"[0-9a-f]{40}", value["source_revision"])
                or not re.fullmatch(r"[!-~]{4,64}", value["account"])):
            raise ValueError
        for key in PATH_FIELDS:
            item = value[key]
            if (not isinstance(item, str) or not Path(item).is_absolute()
                    or str(Path(item)) != item or ".." in Path(item).parts
                    or not re.fullmatch(r"/[A-Za-z0-9_./-]+", item)):
                raise ValueError
        inventory = value["inventory"]
        if not isinstance(inventory, list) or not 3 <= len(inventory) <= 10:
            raise ValueError
        seen = set()
        for row in inventory:
            if (not isinstance(row, dict) or set(row) != {"host", "cohort", "handoff"}
                    or not re.fullmatch(r"(?:upcloud|hetzner|vultr|scaleway):[a-z0-9][a-z0-9-]{0,63}", row["host"])
                    or row["host"].split(":")[1] == "default"
                    or not NAME.fullmatch(row["cohort"]) or row["host"] in seen
                    or (row["handoff"] is not None and
                        (not isinstance(row["handoff"], str) or not Path(row["handoff"]).is_absolute()
                         or str(Path(row["handoff"])) != row["handoff"] or ".." in Path(row["handoff"]).parts
                         or not re.fullmatch(r"/[A-Za-z0-9_./-]+", row["handoff"])))):
                raise ValueError
            seen.add(row["host"])
        target = [row for row in inventory if row["host"] == "upcloud:" + value["environment"]]
        if len(target) != 1 or target[0]["cohort"] != value["cohort"] or target[0]["handoff"] is not None:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise RecoveryError("unsupported-or-invalid-recovery-manifest") from None
    return value


def file_digest(path, *, private=True):
    return hashlib.sha256(read(path, private=private)).hexdigest()


class Journal:
    """Atomic complete records: an old record always retains pre-operation intent."""

    def __init__(self, manifest):
        self.manifest = manifest
        self.directory = Path(manifest["state_directory"])
        self.fd = self.lock = None
        self.state = None

    def __enter__(self):
        try:
            for parent in self.directory.parents:
                info = parent.lstat()
                sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
                if (info.st_uid not in (0, os.geteuid())
                        or not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022 and not sticky_root):
                    raise RecoveryError("unsafe-recovery-parent")
            self.fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(self.fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise RecoveryError("unsafe-recovery-directory")
            self.identity = info.st_dev, info.st_ino
            self.lock = os.open("recovery.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                                0o600, dir_fd=self.fd)
            lock = os.fstat(self.lock)
            if not stat.S_ISREG(lock.st_mode) or lock.st_uid != os.geteuid() or lock.st_nlink != 1 or stat.S_IMODE(lock.st_mode) != 0o600:
                raise RecoveryError("unsafe-recovery-lock")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            named = os.stat("recovery.lock", dir_fd=self.fd, follow_symlinks=False)
            if (lock.st_dev, lock.st_ino) != (named.st_dev, named.st_ino):
                raise RecoveryError("recovery-lock-changed")
            created = False
            try:
                self.state = document(self.directory / "journal.json")
            except RecoveryError:
                if os.path.lexists(self.directory / "journal.json"):
                    raise
                if set(os.listdir(self.fd)) != {"recovery.lock"}:
                    raise RecoveryError("recovery-directory-not-empty")
                created = True
                self.state = {"schema_version": 1, "manifest_sha256": digest(self.manifest),
                              "sequence": 0, "intent": None, "observed": {}, "approvals": {}}
            if (set(self.state) != {"schema_version", "manifest_sha256", "sequence", "intent", "observed", "approvals"}
                    or self.state["schema_version"] != 1 or self.state["manifest_sha256"] != digest(self.manifest)
                    or type(self.state["sequence"]) is not int or self.state["sequence"] < 0
                    or not isinstance(self.state["observed"], dict) or not isinstance(self.state["approvals"], dict)
                    or self.state["intent"] is not None and not isinstance(self.state["intent"], dict)):
                raise RecoveryError("recovery-journal-mismatch")
            if created:
                self.save()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        for name in ("lock", "fd"):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)

    def verify(self):
        info = self.directory.lstat()
        if ((info.st_dev, info.st_ino) != self.identity or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
            raise RecoveryError("recovery-directory-changed")

    def write(self, name, payload):
        self.verify()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
            raise RecoveryError("recovery-artifact-name-invalid")
        temporary = ".pending-" + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self.verify()
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass
        return self.directory / name

    def save(self):
        self.write("journal.json", canonical(self.state))

    def observe(self, key, value):
        self.state["observed"][key] = value
        self.save()

    @contextmanager
    def operation(self, name, binding):
        self.state["sequence"] += 1
        self.state["intent"] = {"name": name, "binding": binding, "sequence": self.state["sequence"]}
        self.save()
        yield self.state["sequence"]
        self.state["intent"] = None
        self.save()

    def approve(self, action, binding, approval):
        challenge = {"action": action, "manifest_sha256": digest(self.manifest), "binding": binding}
        expected = digest(challenge)
        artifact = self.write("review.json", canonical(challenge))
        if self.state["approvals"].get(action) == expected:
            return
        if approval != expected:
            raise ActionRequired(action, expected, artifact)
        self.state["approvals"][action] = expected
        self.save()
