#!/usr/bin/env python3
"""Serialize generation installation and probing behind one fixed root CLI.

Library root/callback arguments exist for isolated filesystem tests. The installed
CLI accepts neither a root override nor an arbitrary command/configuration path.
Receipts are private operational state; only public_receipt() may leave the host.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import sys
from uuid import UUID, uuid4


ROOT = Path("/etc/vpn-liveness")
BOOTSTRAP = (
    Path("/usr/local/lib/vpn-liveness/liveness_generation.py"),
    Path("/usr/local/sbin/vpn-protocol-liveness"),
    Path("/etc/sudoers.d/vpn-protocol-liveness"),
)
PROFILES = {"p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"}
PUBLIC_FIELDS = {"controller_revision", "runner_sha256", "client_generation_id", "public_profile_digest", "vantage"}
MAX_FILE = 1024 * 1024
JOB_TIMEOUT_SECONDS = 600
RECEIPT_TIMEOUT = 660


class GenerationError(Exception):
    """A categorical error; never include profile or subprocess content."""


def probe_deadline(timeout, required_profiles):
    """Cover control/profile HTTP stages plus bounded setup and cleanup work."""
    if (type(timeout) is not int or not 1 <= timeout <= 60
            or not isinstance(required_profiles, (list, tuple)) or not required_profiles
            or any(not isinstance(profile, str) or profile not in PROFILES for profile in required_profiles)
            or len(required_profiles) != len(set(required_profiles))):
        raise GenerationError("probe-deadline-invalid")
    return timeout * (1 + len(required_profiles)) + 240


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise GenerationError("generation-invalid") from None
    return value


def _directory(path, *, private=False):
    for parent in (path, *path.parents):
        info = parent.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & 0o022 and not sticky_root):
            raise GenerationError("directory-unsafe")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & (0o077 if private else 0o022):
        raise GenerationError("directory-unsafe")


def _read(path, *, private=True):
    _directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise GenerationError("file-unavailable") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & (0o077 if private else 0o022) or info.st_size > MAX_FILE:
            raise GenerationError("file-unsafe")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            content = handle.read(MAX_FILE + 1)
        if len(content) > MAX_FILE:
            raise GenerationError("file-too-large")
        return content, stat.S_IMODE(info.st_mode)
    finally:
        os.close(fd)


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _parents(path):
    missing = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            raise GenerationError("directory-unsafe")
        missing.append(cursor)
        cursor = cursor.parent
    _directory(cursor)
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        _sync(directory.parent)
    _directory(path)


def _write(path, content, mode=0o600):
    _parents(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".generation-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _json(path):
    try:
        value = json.loads(_read(path)[0])
    except (OSError, ValueError):
        raise GenerationError("state-invalid") from None
    if not isinstance(value, dict):
        raise GenerationError("state-invalid")
    return value


def _save(path, value):
    content = (json.dumps(value, sort_keys=True) + "\n").encode()
    if len(content) > MAX_FILE:
        raise GenerationError("state-too-large")
    _write(path, content)


def _host_path(root, path):
    return path if root == ROOT else root / "host" / path.relative_to("/")


@contextmanager
def _locked(root):
    _directory(root, private=True)
    fd = os.open(root / "generation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise GenerationError("lock-unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GenerationError("busy") from None
        yield
    finally:
        os.close(fd)


def _current(root):
    path = root / "current"
    if not os.path.lexists(path):
        return None
    info = path.lstat()
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid():
        raise GenerationError("current-invalid")
    target = path.readlink()
    if len(target.parts) != 2 or target.parts[0] != "generations":
        raise GenerationError("current-invalid")
    return _uuid(target.parts[1])


def _activate(root, generation):
    if generation is None:
        (root / "current").unlink(missing_ok=True)
    else:
        temporary = root / f".current-{uuid4()}"
        try:
            temporary.symlink_to(Path("generations") / _uuid(generation))
            os.replace(temporary, root / "current")
        finally:
            temporary.unlink(missing_ok=True)
    _sync(root)


def _provenance(value, runner_digest):
    if not isinstance(value, dict) or set(value) != PUBLIC_FIELDS:
        raise GenerationError("provenance-invalid")
    for field, length in (("controller_revision", 40), ("runner_sha256", 64), ("public_profile_digest", 64)):
        if not isinstance(value[field], str) or re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value[field]) is None:
            raise GenerationError("provenance-invalid")
    _uuid(value["client_generation_id"])
    if value["runner_sha256"] != runner_digest or value["vantage"] not in ("external", "filtered"):
        raise GenerationError("provenance-invalid")


def _configuration(root, generation, config, metadata, profile_files):
    required = set(metadata["required_profiles"])
    if not isinstance(config.get("sentinel"), str) or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", config["sentinel"]) is None or config.get("provenance") != metadata["provenance"]:
        raise GenerationError("candidate-config-identity")
    runtime = config.get("expected_runtime")
    required_runtime = set()
    if required & {"p0-reality", "p2-hysteria2"}:
        required_runtime.add("sing_box")
    if "p1-xhttp" in required:
        required_runtime.add("xray")
    if "p2-amneziawg" in required:
        required_runtime.update(("awg", "awg_toolchain"))
    if not isinstance(runtime, dict) or set(runtime) != required_runtime:
        raise GenerationError("candidate-runtime")
    for name, value in runtime.items():
        pattern = r"[0-9a-f]{64}" if name == "awg_toolchain" else r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?"
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            raise GenerationError("candidate-runtime")
    bindings = (("sing_box", "sing-box.json", {"p0-reality", "p2-hysteria2"}, "sing_box"), ("xray", "xray.json", {"p1-xhttp"}, "xray"), ("amneziawg", "awg.conf", {"p2-amneziawg"}, "awg"))
    for section, filename, logical, runtime_name in bindings:
        selected = required & logical
        if not selected:
            if section in config or filename in profile_files:
                raise GenerationError("candidate-unrequired-profile")
            continue
        settings = config.get(section)
        if filename not in profile_files or runtime_name not in runtime or not isinstance(settings, dict):
            raise GenerationError("candidate-profile-missing")
        if settings.get("config") != str(root / "generations" / generation / "profiles" / filename):
            raise GenerationError("candidate-profile-path")
        if section != "amneziawg":
            profiles = settings.get("profiles")
            if not isinstance(profiles, dict) or set(profiles) != selected or any(not isinstance(ports, list) or not ports or any(type(p) is not int or not 1 <= p <= 65535 for p in ports) for ports in profiles.values()):
                raise GenerationError("candidate-profiles-invalid")


def _candidate(root, generation, directory):
    _directory(directory, private=True)
    expected = {"runner.py", "config.json", "metadata.json", "profiles"}
    if {p.name for p in directory.iterdir()} != expected:
        raise GenerationError("candidate-layout")
    _directory(directory / "profiles", private=True)
    profiles = {p.name for p in (directory / "profiles").iterdir()}
    if not profiles <= {"sing-box.json", "xray.json", "awg.conf"}:
        raise GenerationError("candidate-layout")
    contents = {}
    for name in sorted(expected - {"profiles"} | {f"profiles/{p}" for p in profiles}):
        contents[name] = _read(directory / name)[0]
    try:
        metadata = json.loads(contents["metadata.json"])
        config = json.loads(contents["config.json"])
    except ValueError:
        raise GenerationError("candidate-json") from None
    if not isinstance(metadata, dict) or not isinstance(config, dict):
        raise GenerationError("candidate-json")
    required = metadata.get("required_profiles")
    user = metadata.get("ssh_user")
    if set(metadata) - {"generation_id", "required_profiles", "ssh_user", "provenance"} or metadata.get("generation_id") != generation or not isinstance(required, list) or not required or any(not isinstance(p, str) or p not in PROFILES for p in required) or len(set(required)) != len(required):
        raise GenerationError("candidate-metadata")
    if not isinstance(user, str) or re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user) is None:
        raise GenerationError("candidate-user")
    _provenance(metadata.get("provenance"), hashlib.sha256(contents["runner.py"]).hexdigest())
    _configuration(root, generation, config, metadata, profiles)
    digest = hashlib.sha256()
    for name, content in contents.items():
        digest.update(name.encode() + b"\0" + len(content).to_bytes(8, "big") + content)
    return metadata, contents, digest.hexdigest()


def _command(command, timeout):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"})
    try:
        output = bytearray()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise GenerationError("command-timeout")
                if not selector.select(remaining):
                    raise GenerationError("command-timeout")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    selector.unregister(process.stdout)
                    break
                output.extend(chunk)
                if len(output) > MAX_FILE:
                    raise GenerationError("command-output-limit")
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode != 0:
            raise GenerationError("command-failed")
        return bytes(output)
    except subprocess.TimeoutExpired:
        raise GenerationError("command-timeout") from None
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        process.stdout.close()


def _validate_sudoers(path):
    _command(["/usr/sbin/visudo", "-cf", str(path)], 10)


def _bootstrap(root, user):
    source = _read(Path(__file__).absolute(), private=False)[0]
    launcher = b'#!/bin/sh\nset -eu\n[ "$#" -eq 0 ] || exit 2\nexec /usr/bin/python3 -I -B -S /usr/local/lib/vpn-liveness/liveness_generation.py run\n'
    sudoers = f'{user} ALL=(root) NOPASSWD: /usr/local/sbin/vpn-protocol-liveness ""\n'.encode()
    fd, temporary = tempfile.mkstemp(prefix=".sudoers-", dir=root)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(sudoers)
        _validate_sudoers(Path(temporary))
    finally:
        Path(temporary).unlink(missing_ok=True)
    return ((source, 0o644), (launcher, 0o755), (sudoers, 0o440))


def _snapshot(root):
    snapshots = []
    for target in BOOTSTRAP:
        path = _host_path(root, target)
        if os.path.lexists(path):
            content, mode = _read(path, private=False)
            snapshots.append({"data": base64.b64encode(content).decode(), "mode": mode})
        else:
            snapshots.append(None)
    return snapshots


def _pending(root):
    value = _json(root / "pending.json")
    if set(value) != {"version", "generation_id", "previous", "bootstrap"} or value["version"] != 1:
        raise GenerationError("pending-invalid")
    _uuid(value["generation_id"])
    if value["previous"] is not None:
        _uuid(value["previous"])
    snapshots = value["bootstrap"]
    if not isinstance(snapshots, list) or len(snapshots) != len(BOOTSTRAP):
        raise GenerationError("pending-invalid")
    for snapshot in snapshots:
        if snapshot is not None:
            if not isinstance(snapshot, dict) or set(snapshot) != {"data", "mode"} or type(snapshot["mode"]) is not int or snapshot["mode"] & ~0o755 or snapshot["mode"] & 0o022:
                raise GenerationError("pending-invalid")
            try:
                base64.b64decode(snapshot["data"], validate=True)
            except (ValueError, TypeError):
                raise GenerationError("pending-invalid") from None
    return value


def _recover(root):
    if not os.path.lexists(root / "pending.json"):
        return
    pending = _pending(root)
    if _current(root) not in {pending["previous"], pending["generation_id"]}:
        raise GenerationError("pending-current-conflict")
    for target, snapshot in zip(BOOTSTRAP, pending["bootstrap"]):
        path = _host_path(root, target)
        if snapshot is None:
            path.unlink(missing_ok=True)
            if path.parent.exists():
                _sync(path.parent)
        else:
            _write(path, base64.b64decode(snapshot["data"]), snapshot["mode"])
    _activate(root, pending["previous"])
    receipt = root / "receipts" / f'{pending["generation_id"]}.json'
    receipt.unlink(missing_ok=True)
    if receipt.parent.exists():
        _sync(receipt.parent)
    (root / "pending.json").unlink()
    _sync(root)


def recover_pending(root):
    with _locked(root):
        _recover(root)


def _report_identity(report, config, metadata):
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 1 or report.get("sentinel") != config["sentinel"] or report.get("runtime") != config["expected_runtime"] or report.get("provenance") != metadata["provenance"]:
        raise GenerationError("probe-identity-invalid")
    observed = report.get("observed_at")
    now = time.time()
    if type(observed) is not int or not now - 300 <= observed <= now:
        raise GenerationError("probe-time-invalid")


def _successful(report, config, metadata):
    _report_identity(report, config, metadata)
    required = metadata["required_profiles"]
    if not isinstance(report, dict) or not isinstance(report.get("control"), dict) or report["control"].get("verdict") not in {"ok", "throttled"}:
        raise GenerationError("probe-control-failed")
    profiles = report.get("profiles")
    if not isinstance(profiles, list) or any(not isinstance(p, dict) or p.get("profile") not in required for p in profiles):
        raise GenerationError("probe-profiles-invalid")
    if len(profiles) != len(required) or {p["profile"] for p in profiles} != set(required) or any(p.get("verdict") not in {"ok", "throttled"} for p in profiles):
        raise GenerationError("probe-profiles-failed")


def public_receipt(receipt):
    return {k: receipt[k] for k in ("generation_id", "status", "runner_sha256", "provenance")}


def _receipt(root, generation, digest, provenance):
    receipt = _json(root / "receipts" / f"{generation}.json")
    if set(receipt) != {"generation_id", "status", "candidate_digest", "runner_sha256", "provenance"} or receipt.get("generation_id") != generation or receipt.get("candidate_digest") != digest or receipt.get("status") != "committed" or not isinstance(receipt.get("runner_sha256"), str) or re.fullmatch(r"[0-9a-f]{64}", receipt["runner_sha256"]) is None or not isinstance(receipt.get("provenance"), dict) or set(receipt["provenance"]) - PUBLIC_FIELDS:
        raise GenerationError("receipt-invalid")
    _provenance(receipt["provenance"], receipt["runner_sha256"])
    if receipt["provenance"] != provenance:
        raise GenerationError("receipt-identity-invalid")
    return receipt


def committed_receipt(root, generation_id):
    generation = _uuid(generation_id)
    with _locked(root):
        _recover(root)
        current = _current(root)
        if current != generation:
            if current is not None:
                old_metadata, _, old_digest = _candidate(root, current, root / "generations" / current)
                _receipt(root, current, old_digest, old_metadata["provenance"])
            if os.path.lexists(root / "receipts" / f"{generation}.json"):
                raise GenerationError("generation-not-current")
            raise GenerationError("generation-uncommitted")
        metadata, contents, digest = _candidate(root, generation, root / "generations" / generation)
        receipt = _receipt(root, generation, digest, metadata["provenance"])
        if receipt["runner_sha256"] != hashlib.sha256(contents["runner.py"]).hexdigest() or receipt["provenance"] != metadata["provenance"]:
            raise GenerationError("receipt-identity-invalid")
        return public_receipt(receipt)


def install_generation(root, generation_id, staged_dir, probe_callback):
    generation = _uuid(generation_id)
    with _locked(root):
        _recover(root)
        if Path(staged_dir) != root / "staging" / generation:
            raise GenerationError("stage-path-invalid")
        _directory(root / "staging", private=True)
        metadata, contents, digest = _candidate(root, generation, Path(staged_dir))
        receipt_path = root / "receipts" / f"{generation}.json"
        if os.path.lexists(receipt_path):
            receipt = _receipt(root, generation, digest, metadata["provenance"])
            _, _, installed_digest = _candidate(root, generation, root / "generations" / generation)
            if installed_digest != digest or _current(root) != generation:
                raise GenerationError("generation-conflict")
            return public_receipt(receipt)
        bootstrap = _bootstrap(root, metadata["ssh_user"])
        previous = _current(root)
        if previous is not None:
            previous_metadata, _, previous_digest = _candidate(root, previous, root / "generations" / previous)
            _receipt(root, previous, previous_digest, previous_metadata["provenance"])
        snapshots = _snapshot(root)
        destination = root / "generations" / generation
        _parents(destination.parent)
        if os.path.lexists(destination):
            _, _, installed_digest = _candidate(root, generation, destination)
            if digest != installed_digest:
                raise GenerationError("generation-conflict")
        else:
            temporary = Path(tempfile.mkdtemp(prefix=".candidate-", dir=destination.parent))
            try:
                for name, content in contents.items():
                    _write(temporary / name, content, 0o500 if name == "runner.py" else 0o400)
                (temporary / "profiles").chmod(0o500)
                temporary.chmod(0o500)
                temporary.rename(destination)
                _sync(destination.parent)
            except BaseException as exc:
                if temporary.exists():
                    temporary.chmod(0o700)
                    if (temporary / "profiles").exists():
                        (temporary / "profiles").chmod(0o700)
                    shutil.rmtree(temporary)
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                raise GenerationError("candidate-copy-failed") from None
        try:
            _save(root / "pending.json", {"version": 1, "generation_id": generation, "previous": previous, "bootstrap": snapshots})
            for target, (content, mode) in zip(BOOTSTRAP, bootstrap):
                _write(_host_path(root, target), content, mode)
            _activate(root, generation)
            report = probe_callback(destination)
            _successful(report, json.loads(contents["config.json"]), metadata)
            receipt = {"generation_id": generation, "status": "committed", "candidate_digest": digest, "runner_sha256": hashlib.sha256(contents["runner.py"]).hexdigest(), "provenance": metadata.get("provenance", {})}
            _save(receipt_path, receipt)
            (root / "pending.json").unlink()
            _sync(root)
            return public_receipt(receipt)
        except BaseException as exc:
            _recover(root)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise GenerationError("installation-failed") from None


def _probe(directory):
    config = _json(directory / "config.json")
    metadata = _json(directory / "metadata.json")
    deadline = probe_deadline(config.get("timeout_seconds"), metadata.get("required_profiles"))
    try:
        return json.loads(_command(["/usr/bin/python3", "-I", "-B", "-S", str(directory / "runner.py"), "--config", str(directory / "config.json")], deadline))
    except ValueError:
        raise GenerationError("probe-json-invalid") from None


def run_current(root, probe_callback):
    with _locked(root):
        _recover(root)
        generation = _current(root)
        if generation is None:
            raise GenerationError("no-current-generation")
        directory = root / "generations" / generation
        metadata, contents, digest = _candidate(root, generation, directory)
        _receipt(root, generation, digest, metadata["provenance"])
        report = probe_callback(directory)
        _report_identity(report, json.loads(contents["config.json"]), metadata)
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "run", "recover", "receipt"))
    parser.add_argument("generation", nargs="?")
    args = parser.parse_args()
    if os.geteuid() != 0 or (args.action in {"install", "receipt"}) != (args.generation is not None):
        parser.error("root is required; install/receipt require a generation")
    try:
        if args.action == "install":
            result = install_generation(ROOT, args.generation, ROOT / "staging" / _uuid(args.generation), _probe)
        elif args.action == "run":
            result = run_current(ROOT, _probe)
        elif args.action == "receipt":
            result = committed_receipt(ROOT, args.generation)
        else:
            recover_pending(ROOT)
            result = {"status": "recovered"}
        print(json.dumps(result, sort_keys=True))
        return 0
    except GenerationError as exc:
        # Only positively identified absence permits controller re-preparation.
        # Busy is retriable polling; corruption and recovery failures are refusal.
        if args.action == "receipt" and str(exc) == "generation-uncommitted":
            return 3
        if args.action == "receipt" and str(exc) == "busy":
            return 75
        print("liveness-generation: operation failed", file=sys.stderr)
        return 1
    except OSError:
        print("liveness-generation: operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
