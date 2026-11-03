"""Private input admission and bounded, process-group-owned byte capture."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time

MAX_BYTES = 256 * 1024 * 1024


class Refusal(ValueError):
    """Only fixed categories may cross the public diagnostic boundary."""


def require(condition, category):
    if not condition:
        raise Refusal(category)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def trusted_directory(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        require(info.st_uid == 0 and str(path) in ("/var", "/tmp") and
                path.resolve(strict=True) == Path("/private") / path.name, "unsafe-directory")
        return
    sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
    require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid()) and
            (not info.st_mode & 0o022 or sticky), "unsafe-directory")


def read_owned(path, *, private=True, limit=MAX_BYTES, with_identity=False):
    path = Path(path).absolute()
    try:
        require(not path.is_symlink(), "unsafe-file")
        # Check lexical ancestry before resolve() can hide an untrusted alias.
        for parent in path.parents:
            trusted_directory(parent)
        path = path.resolve(strict=True)
        for parent in path.parents:
            trusted_directory(parent)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                    info.st_uid in ((os.getuid(),) if private else (0, os.getuid())) and
                    (stat.S_IMODE(info.st_mode) == 0o600 if private else not info.st_mode & 0o022),
                    "unsafe-file")
            require(info.st_size <= limit, "file-limit")
            data = stream.read(limit + 1)
            require(len(data) <= limit and fingerprint(info) == fingerprint(os.fstat(stream.fileno()))
                    and fingerprint(info) == fingerprint(path.stat()), "file-changed")
            return (data, fingerprint(info)) if with_identity else data
    except OSError:
        raise Refusal("unreadable-file") from None


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _value: (_ for _ in ()).throw(Refusal("invalid-json")))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refusal("invalid-json") from None


def document(raw):
    value = decode(raw)
    require(isinstance(value, dict) and type(value.get("schema_version")) is int
            and value["schema_version"] == 1, "invalid-plan")
    return value


def resolve_pointer(value, path):
    import re
    require(isinstance(path, str) and path.startswith("/") and
            not re.search(r"~(?![01])", path), "invalid-catalog-pointer")
    try:
        for part in path[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            value = value[int(part)] if isinstance(value, list) and part.isdecimal() else value[part]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        raise Refusal("invalid-catalog-reference") from None


def fields(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= value.keys() <= set(required) | set(optional),
            "invalid-fields")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def environment(names=()):
    value = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
             "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
    for name in names:
        require(name in os.environ, "missing-environment-input")
        value[name] = os.environ[name]
    return value


def process_states(group):
    result = subprocess.run(["/bin/ps", "-eo", "pid=,pgid=,stat="],
                            capture_output=True, timeout=2, check=False, env=environment())
    require(result.returncode == 0, "process-state-unavailable")
    return {int(row[0]): row[2] for line in result.stdout.splitlines()
            if len(row := line.split()) == 3 and int(row[1]) == group}


@contextmanager
def cancellation():
    """Defer normal cancellation signals until owned group cleanup is complete."""
    interrupted = [False]
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {number: signal.getsignal(number) for number in signals}
    def remember(_number, _frame):
        interrupted[0] = True
    try:
        for number in signals:
            signal.signal(number, remember)
        yield interrupted
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def capture(argv, *, timeout=60, limit=16 * 1024 * 1024, data=b"", env=None):
    """Keep the leader unreaped until all owned foreground processes are stopped."""
    require(0 < timeout <= 3600 and 0 < limit <= MAX_BYTES * 2 and len(data) <= MAX_BYTES * 2,
            "capture-limit")
    with cancellation() as cancelled:
        try:
            child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=env if env is not None else environment(),
                                     start_new_session=True)
        except OSError:
            raise Refusal("command-unavailable") from None
        stdout, stderr = bytearray(), bytearray()
        reason, sent = "complete", 0
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as selector:
                for stream, target in ((child.stdout, stdout), (child.stderr, stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, target)
                if data:
                    os.set_blocking(child.stdin.fileno(), False)
                    selector.register(child.stdin, selectors.EVENT_WRITE)
                else:
                    child.stdin.close()
                while selector.get_map():
                    if cancelled[0]:
                        reason = "cancelled"
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        reason = "timeout"
                        break
                    for key, events in selector.select(min(remaining, 0.1)):
                        if events & selectors.EVENT_WRITE:
                            try:
                                sent += os.write(key.fd, data[sent:sent + 65536])
                            except BrokenPipeError:
                                reason = "stdin-incomplete"
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                            except BlockingIOError:
                                continue
                            else:
                                if sent == len(data):
                                    selector.unregister(key.fileobj)
                                    key.fileobj.close()
                        else:
                            try:
                                chunk = os.read(key.fd, 65536)
                            except BlockingIOError:
                                continue
                            if not chunk:
                                selector.unregister(key.fileobj)
                            else:
                                available = limit - len(stdout) - len(stderr)
                                key.data.extend(chunk[:available])
                                if len(chunk) > available:
                                    reason = "output-limit"
                    if reason != "complete":
                        break
            # A command may close its descriptors before it exits. Do not reap it:
            # its reserved PID also reserves the process-group identity for cleanup.
            while reason == "complete":
                if cancelled[0]:
                    reason = "cancelled"
                    break
                states = process_states(child.pid)
                if child.pid in states and states[child.pid].startswith(b"Z"):
                    break
                if time.monotonic() >= deadline:
                    reason = "timeout"
                    break
                time.sleep(0.02)
        except KeyboardInterrupt:
            reason = "cancelled"
        finally:
            cleanup_deadline = time.monotonic() + 3
            try:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    # The group can already be empty after command exit. The
                    # state check below still verifies that no live member remains.
                    pass
                except PermissionError:
                    # Darwin refuses signals to a zombie-only group. Confirm that
                    # state while the unreaped leader still reserves its identity.
                    states = process_states(child.pid)
                    require(states and all(state.startswith(b"Z") for state in states.values()),
                            "process-cleanup-unverified")
                while any(not state.startswith(b"Z") for state in process_states(child.pid).values()):
                    require(time.monotonic() < cleanup_deadline, "process-cleanup-unverified")
                    time.sleep(0.02)
            finally:
                child.wait(timeout=3)
                for stream in (child.stdin, child.stdout, child.stderr):
                    stream.close()
        if cancelled[0]:
            reason = "cancelled"
        return {"stdout": bytes(stdout), "stderr": bytes(stderr),
                "exit_code": child.returncode, "capture": reason}


def checked(argv, **kwargs):
    result = capture(argv, **kwargs)
    require(result["capture"] == "complete" and result["exit_code"] == 0, "command-failed")
    return result["stdout"]
