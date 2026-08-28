"""Private, non-mutating plans for the known global SSH 10/20/50 layout."""

import base64
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import stat
import subprocess
import tempfile
import time


OWNER_UID = 0
SSHD = "/usr/sbin/sshd"
SCRATCH_ROOT = Path("/run/vpn-sshd-validation")
MAX_FILE = 256 * 1024
MAX_GRAPH = 1024 * 1024
MAX_PLAN = 2 * 1024 * 1024
MAX_OUTPUT = 256 * 1024
COMMAND_TIMEOUT = 10
EFFECTIVE_TIMEOUT = 30
BOOT = "sshd_config.d/10-cloud-init-hardening.conf"
MANAGED = "sshd_config.d/20-ansible-hardening.conf"
CLOUD = "sshd_config.d/50-cloud-init.conf"
FILES = (BOOT, MANAGED, CLOUD)
AUTH = {"passwordauthentication": "no", "kbdinteractiveauthentication": "no",
        "permitrootlogin": "no", "pubkeyauthentication": "yes"}
TUNABLE = {"x11forwarding", "allowtcpforwarding", "allowagentforwarding", "permittunnel",
           "permituserenvironment", "permitemptypasswords", "ignorerhosts", "loglevel",
           "clientaliveinterval", "clientalivecountmax", "maxauthtries", "maxsessions",
           "maxstartups", "logingracetime", "requiredrsasize", "allowusers", "subsystem",
           "ciphers", "macs", "kexalgorithms"}
OWNED = TUNABLE | AUTH.keys() | {"port"}


class OwnershipError(ValueError):
    """A categorical failure; never include configuration or subprocess output."""

    def __init__(self, code, relative_path=None):
        super().__init__(code)
        self.relative_path = relative_path


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def _directory(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise OwnershipError("unsafe-directory")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid not in {0, OWNER_UID} or info.st_mode & 0o022:
                raise OwnershipError("unsafe-directory")
        yield fd
    finally:
        os.close(fd)


def _read(directory_fd, name, relative):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != OWNER_UID or before.st_mode & 0o022:
            raise OwnershipError("unsafe-file")
        if before.st_size > MAX_FILE:
            raise OwnershipError("file-too-large")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_FILE + 1)
        after = os.fstat(fd)
        if len(raw) > MAX_FILE or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise OwnershipError("read-race")
        metadata = {"relative_path": relative, "sha256": _sha(raw), "size": len(raw),
                    "uid": before.st_uid, "gid": before.st_gid, "mode": stat.S_IMODE(before.st_mode),
                    "dev": before.st_dev, "ino": before.st_ino}
        return raw, metadata
    finally:
        os.close(fd)


def _lines(raw):
    try:
        text = raw.decode("ascii")
        if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
            raise ValueError
        result = []
        for index, line in enumerate(text.splitlines(keepends=True)):
            fields = shlex.split(line, comments=True)
            if not fields:
                continue
            match = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)[\s=]+(.*)", line.strip())
            if not match:
                raise ValueError
            key = match[1].lower()
            values = shlex.split(match[2], comments=True)
            if not values or key == "match":
                raise ValueError
            result.append((index, key, values))
        return result
    except (UnicodeError, ValueError):
        raise OwnershipError("unsupported-directive") from None


def _capture(config_dir):
    root = Path(config_dir)
    with _directory(root) as fd, _directory(root / "sshd_config.d") as fragments_fd:
        names = []
        with os.scandir(fragments_fd) as entries:
            for count, entry in enumerate(entries):
                if count >= 256:
                    raise OwnershipError("unsupported-membership")
                if entry.name.endswith(".conf") and not entry.name.startswith("."):
                    names.append(entry.name)
        names.sort()
        if len(names) > 64 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.conf", name) for name in names):
            raise OwnershipError("unsupported-membership")
        captures = {"sshd_config": _read(fd, "sshd_config", "sshd_config")}
        for name in names:
            relative = "sshd_config.d/" + name
            captures[relative] = _read(fragments_fd, name, relative)
        if sum(len(raw) for raw, _ in captures.values()) > MAX_GRAPH:
            raise OwnershipError("graph-too-large")
    include_count = 0
    for relative, (raw, _) in captures.items():
        for _, key, values in _lines(raw):
            if key == "include":
                if relative != "sshd_config" or values != [str(root / "sshd_config.d/*.conf")]:
                    raise OwnershipError("unsupported-include")
                include_count += 1
            elif relative not in FILES and key in OWNED:
                raise OwnershipError("unmanaged-owned-directive", relative)
    if include_count != 1 or BOOT not in captures or MANAGED not in captures:
        raise OwnershipError("unsupported-layout")
    return captures, [{"relative_directory": "sshd_config.d", "matched_names": names}]


def _directives(raw, allowed):
    values = {}
    for index, key, words in _lines(raw):
        if key not in allowed or key in values:
            raise OwnershipError("unsupported-owned-directive")
        values[key] = (index, words)
    return values


def _remove(raw, indexes):
    return b"".join(line for index, line in enumerate(raw.splitlines(keepends=True)) if index not in indexes)


def _candidates(captures):
    boot, managed = captures[BOOT][0], captures[MANAGED][0]
    b = _directives(boot, AUTH.keys() | {"port", "x11forwarding"})
    m = _directives(managed, AUTH.keys() | TUNABLE)
    if any(b.get(key, (None, None))[1] != [value] for key, value in AUTH.items()):
        raise OwnershipError("unsupported-authentication")
    port = b.get("port", (None, []))[1]
    if len(port) != 1 or not port[0].isascii() or not port[0].isdigit() or not 1 <= int(port[0]) <= 65535:
        raise OwnershipError("unsupported-port")
    for key in AUTH.keys() & m.keys():
        if m[key][1] != b[key][1]:
            raise OwnershipError("conflicting-authentication")
    if "x11forwarding" not in b and "x11forwarding" not in m:
        raise OwnershipError("missing-x11-owner")
    if any(values[1] != ["no"] for key, values in [*b.items(), *m.items()] if key == "x11forwarding"):
        raise OwnershipError("unsupported-x11")
    changed_managed = _remove(managed, {m[key][0] for key in AUTH.keys() & m.keys()})
    if "x11forwarding" not in m:
        if changed_managed and not changed_managed.endswith(b"\n"):
            changed_managed += b"\n"
        changed_managed += boot.splitlines(keepends=True)[b["x11forwarding"][0]]
    result = {BOOT: _remove(boot, {b["x11forwarding"][0]} if "x11forwarding" in b else set()), MANAGED: changed_managed}
    if CLOUD in captures:
        cloud = captures[CLOUD][0]
        c = _directives(cloud, {"passwordauthentication"})
        if c and c["passwordauthentication"][1] != ["no"]:
            raise OwnershipError("conflicting-authentication")
        result[CLOUD] = _remove(cloud, {c["passwordauthentication"][0]} if c else set())
    return result


def _contexts(contexts):
    if not isinstance(contexts, list) or not 1 <= len(contexts) <= 8:
        raise OwnershipError("invalid-context")
    result = []
    for context in contexts:
        if not isinstance(context, dict) or set(context) != {"user", "host", "addr", "laddr", "lport"}:
            raise OwnershipError("invalid-context")
        for key in ("user", "host"):
            if not isinstance(context[key], str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", context[key]):
                raise OwnershipError("invalid-context")
        for key in ("addr", "laddr"):
            if not isinstance(context[key], str) or "%" in context[key]:
                raise OwnershipError("invalid-context")
            try:
                ipaddress.ip_address(context[key])
            except ValueError:
                raise OwnershipError("invalid-context") from None
        if type(context["lport"]) is not int or not 1 <= context["lport"] <= 65535:
            raise OwnershipError("invalid-context")
        if context in result:
            raise OwnershipError("invalid-context")
        result.append(dict(context))
    return result


def _command(arguments, budget):
    if budget <= 0:
        raise OwnershipError("sshd-timeout")
    deadline = time.monotonic() + min(COMMAND_TIMEOUT, budget)
    with subprocess.Popen([SSHD, *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}) as process:
        output = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise OwnershipError("sshd-timeout")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            output.extend(chunk)
                            if len(output) > MAX_OUTPUT:
                                raise OwnershipError("sshd-output-too-large")
            try:
                result = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise OwnershipError("sshd-timeout") from None
            if result:
                raise OwnershipError("sshd-rejected")
            return bytes(output)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def _assemble(captures, replacements):
    fragments = [relative for relative in captures if relative != "sshd_config"]
    main = captures["sshd_config"][0]
    include = next(index for index, key, _ in _lines(main) if key == "include")
    lines = main.splitlines(keepends=True)
    lines[include] = b"".join(replacements.get(relative, captures[relative][0]).rstrip(b"\n") + b"\n" for relative in fragments)
    return b"".join(lines)


def _scratch_parent():
    if os.path.lexists(SCRATCH_ROOT):
        with _directory(SCRATCH_ROOT) as fd:
            info = os.fstat(fd)
            if info.st_uid != OWNER_UID or info.st_mode & 0o022:
                raise OwnershipError("unsafe-scratch")
        return SCRATCH_ROOT
    # Only the fixed system temporary directory is eligible for local fallback.
    # Ambient TMPDIR and tempfile's process-wide cache are not trust roots.
    parent = Path("/tmp").resolve(strict=True)
    for directory in (parent, *parent.parents):
        info = directory.lstat()
        sticky = directory == parent and bool(info.st_mode & stat.S_ISVTX)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or (info.st_mode & 0o022 and not sticky):
            raise OwnershipError("unsafe-scratch")
    return parent


def _effective(captures, replacements, contexts):
    deadline = time.monotonic() + EFFECTIVE_TIMEOUT
    with tempfile.TemporaryDirectory(prefix="sshd-ownership-", dir=_scratch_parent()) as directory:
        path = Path(directory) / "sshd_config"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(_assemble(captures, replacements))
        _command(["-t", "-f", str(path)], deadline - time.monotonic())
        result = []
        for context in [None, *contexts]:
            arguments = ["-T", "-f", str(path)]
            if context is not None:
                arguments += ["-C", ",".join(f"{key}={context[key]}" for key in ("user", "host", "addr", "laddr", "lport"))]
            result.append(_sha(_command(arguments, deadline - time.monotonic())))
        return result


def _record(raw=None, metadata=None):
    if raw is None:
        return {"exists": False, "data_b64": None, "sha256": None, "mode": None, "uid": None, "gid": None}
    return {"exists": True, "data_b64": base64.b64encode(raw).decode(), "sha256": _sha(raw),
            **{key: metadata[key] for key in ("mode", "uid", "gid")}}


def _snapshot(captures):
    return [metadata for _, metadata in captures.values()]


def _check_plan(plan):
    try:
        fields = {"schema_version", "operation", "changed", "read_set", "include_inventory", "files", "effective", "snapshot_digest"}
        if not isinstance(plan, dict) or set(plan) != fields or len(_canonical(plan)) > MAX_PLAN or type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or plan["operation"] != "sshd-ownership":
            raise ValueError
        if type(plan["changed"]) is not bool or not isinstance(plan["read_set"], list) or not isinstance(plan["include_inventory"], list) or not isinstance(plan["files"], dict) or set(plan["files"]) != set(FILES):
            raise ValueError
        if plan.get("snapshot_digest") != _sha(_canonical({key: value for key, value in plan.items() if key != "snapshot_digest"})):
            raise ValueError
        if not isinstance(plan["effective"], list) or not plan["effective"] or plan["effective"][0]["context"] is not None:
            raise ValueError
        contexts = _contexts([entry["context"] for entry in plan["effective"][1:]])
        for entry in plan["effective"]:
            for key in ("before_sha256", "after_sha256"):
                if not isinstance(entry[key], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[key]):
                    raise ValueError
        return contexts
    except (KeyError, TypeError, ValueError):
        raise OwnershipError("invalid-plan") from None


def build_plan(config_dir=Path("/etc/ssh"), *, contexts):
    """Return private before/after records; only temporary parser inputs are written."""
    try:
        contexts = _contexts(contexts)
        captures, inventory = _capture(config_dir)
        candidates = _candidates(captures)
        before = _effective(captures, {}, contexts)
        after = _effective(captures, candidates, contexts)
        if before != after:
            raise OwnershipError("effective-policy-changed")
        files = {relative: {"before": _record(*captures[relative]) if relative in captures else _record(),
                            "after": _record(candidates[relative], captures[relative][1]) if relative in candidates else _record()}
                 for relative in FILES}
        plan = {"schema_version": 1, "operation": "sshd-ownership", "changed": any(value["before"] != value["after"] for value in files.values()),
                "read_set": _snapshot(captures), "include_inventory": inventory, "files": files,
                "effective": [{"context": context, "before_sha256": old, "after_sha256": new}
                              for context, old, new in zip([None, *contexts], before, after)]}
        plan["snapshot_digest"] = _sha(_canonical(plan))
        _check_plan(plan)
        assert_snapshot(plan, config_dir)
        return plan
    except (OSError, UnicodeError):
        raise OwnershipError("configuration-unavailable") from None


def assert_snapshot(plan, config_dir=Path("/etc/ssh")):
    """Refuse changed bytes, file identity, metadata, or Include membership."""
    try:
        _check_plan(plan)
        captures, inventory = _capture(config_dir)
        if plan["read_set"] != _snapshot(captures) or plan["include_inventory"] != inventory:
            raise OwnershipError("snapshot-changed")
    except (OSError, UnicodeError):
        raise OwnershipError("snapshot-unavailable") from None


def assert_effective(plan, config_dir=Path("/etc/ssh")):
    """Check installed full policy, without requiring the original inode snapshot."""
    try:
        contexts = _check_plan(plan)
        captures, _ = _capture(config_dir)
        actual = _effective(captures, {}, contexts)
        if actual != [entry["after_sha256"] for entry in plan["effective"]]:
            raise OwnershipError("effective-policy-changed")
    except (OSError, UnicodeError):
        raise OwnershipError("configuration-unavailable") from None
