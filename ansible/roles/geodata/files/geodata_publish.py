#!/usr/bin/env python3
"""Verify both pinned geodata inputs before paired ordinary-failure publication."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

MAX_BYTES = 128 * 1024 * 1024


def activate():
    result = subprocess.run(
        ["/usr/local/sbin/vpn-xray-geodata-activate.sh"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("activation")
    if result.stdout.strip() not in {b"active", b"inactive"}:
        raise RuntimeError("activation-status")
    return result.stdout.strip() == b"active"


def verify_file(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
    ):
        raise ValueError("unsafe-file")
    return info


def replace(source, destination, *, mode, uid, gid):
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".geodata-")
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as data:
            os.fchmod(output.fileno(), mode)
            os.fchown(output.fileno(), uid, gid)
            shutil.copyfileobj(data, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(
            destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def digest(path):
    info = verify_file(path)
    if info.st_size > MAX_BYTES:
        raise ValueError("file-size")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(path):
    if not os.path.lexists(path):
        return None
    info = verify_file(path)
    return {
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "sha256": digest(path),
    }


def persist(path, document):
    raw = json.dumps(document, sort_keys=True).encode()
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".journal-")
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_journal(path):
    info = verify_file(path)
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 8192:
        raise ValueError("unsafe-journal")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("unsafe-journal")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=pairs)


def recover(directory, pending):
    if not os.path.lexists(pending):
        return False
    info = pending.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("unsafe-journal")
    journal = read_journal(pending / "snapshot.json")
    names = {"geosite.dat", "geoip.dat"}
    if (
        not isinstance(journal, dict)
        or set(journal) != {"schema", "phase", "previous", "desired"}
        or type(journal["schema"]) is not int
        or journal["schema"] != 1
        or journal["phase"]
        not in {"preparing", "publishing", "activating", "activated", "recovering"}
        or set(journal["previous"]) != names
        or set(journal["desired"]) != names
    ):
        raise ValueError("manual-recovery-required")
    allowed = {"snapshot.json", *names, *("old-" + name for name in names)}
    if any(path.name not in allowed for path in pending.iterdir()):
        raise ValueError("foreign-journal")
    for name in names:
        old = journal["previous"][name]
        desired = journal["desired"][name]
        if not isinstance(desired, str) or not re.fullmatch(r"[0-9a-f]{64}", desired):
            raise ValueError("unsafe-journal")
        if old is not None and (
            not isinstance(old, dict)
            or set(old) != {"mode", "uid", "gid", "sha256"}
            or type(old["mode"]) is not int
            or old["mode"] & ~0o777
            or old["uid"] != os.geteuid()
            or type(old["gid"]) is not int
            or old["gid"] < 0
            or not re.fullmatch(r"[0-9a-f]{64}", old["sha256"])
        ):
            raise ValueError("unsafe-journal")
        current = directory / name
        observed = capture(current)
        expected = {
            "mode": 0o644,
            "uid": os.geteuid(),
            "gid": os.getegid(),
            "sha256": desired,
        }
        if observed != old and observed != expected:
            raise ValueError("foreign-publication")
        if (
            journal["phase"] != "preparing"
            and old is not None
            and digest(pending / ("old-" + name)) != old["sha256"]
        ):
            raise ValueError("unsafe-snapshot")
    if journal["phase"] != "preparing":
        journal["phase"] = "recovering"
        persist(pending / "snapshot.json", journal)
        for name, old in journal["previous"].items():
            current = directory / name
            if old is None:
                current.unlink(missing_ok=True)
                sync_directory(directory)
            else:
                replace(
                    pending / ("old-" + name),
                    current,
                    **{key: old[key] for key in ("mode", "uid", "gid")},
                )
        if all(value is not None for value in journal["previous"].values()):
            activate()
    shutil.rmtree(pending)
    sync_directory(directory)
    return True


def _publish_locked(request):
    directory = Path(request["install_dir"])
    sources = request["sources"]
    if set(sources) != {"geosite.dat", "geoip.dat"}:
        raise ValueError("sources")
    for source in sources.values():
        if not isinstance(source["url"], str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", source["sha256"]
        ):
            raise ValueError("pin")
    pending = directory / ".geodata-pending"
    recovered = recover(directory, pending)
    previous = {}
    desired = {name: source["sha256"].lower() for name, source in sources.items()}
    receipt = directory / ".geodata-activated.json"
    expected_metadata = {"mode": 0o644, "uid": os.geteuid(), "gid": os.getegid()}
    expected_receipt = {"schema": 1, "desired": desired, "metadata": expected_metadata}
    activated = read_journal(receipt) if os.path.lexists(receipt) else None
    if activated is not None:
        if (
            not isinstance(activated, dict)
            or set(activated) != {"schema", "desired", "metadata"}
            or type(activated["schema"]) is not int
            or activated["schema"] != 1
            or not isinstance(activated["desired"], dict)
            or set(activated["desired"]) != set(sources)
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in activated["desired"].values()
            )
            or not isinstance(activated["metadata"], dict)
            or set(activated["metadata"]) != {"mode", "uid", "gid"}
            or any(
                type(value) is not int or value < 0
                for value in activated["metadata"].values()
            )
            or activated["metadata"]["mode"] & ~0o777
        ):
            raise ValueError("unsafe-receipt")
    for name in sources:
        path = directory / name
        if os.path.lexists(path):
            metadata = verify_file(path)
            previous[name] = {
                "mode": stat.S_IMODE(metadata.st_mode),
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
                "sha256": digest(path),
            }
        else:
            previous[name] = None
    stage = Path(tempfile.mkdtemp(prefix=".geodata-stage-", dir=directory))
    journal = {
        "schema": 1,
        "phase": "preparing",
        "previous": previous,
        "desired": desired,
    }
    persist(stage / "snapshot.json", journal)
    os.rename(stage, pending)
    sync_directory(directory)
    publishing = False
    try:
        for name, source in sources.items():
            candidate = pending / name
            result = subprocess.run(
                [
                    "curl",
                    "-fsSL",
                    "--max-time",
                    "120",
                    "-o",
                    str(candidate),
                    source["url"],
                ],
                capture_output=True,
                timeout=125,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("download")
            candidate.chmod(0o600)
            if digest(candidate) != desired[name]:
                raise ValueError("checksum")
            fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            if previous[name] is not None:
                replace(
                    directory / name,
                    pending / ("old-" + name),
                    mode=0o600,
                    uid=os.geteuid(),
                    gid=os.getegid(),
                )
        changed = any(
            old != {**expected_metadata, "sha256": desired[name]}
            for name, old in previous.items()
        )
        if not changed and activated == expected_receipt and not recovered:
            return {"changed": False}
        journal["phase"] = "publishing"
        persist(pending / "snapshot.json", journal)
        publishing = True
        try:
            for name in sources:
                current = directory / name
                observed = capture(current)
                if observed != previous[name]:
                    raise ValueError("file-changed")
                if observed != {**expected_metadata, "sha256": desired[name]}:
                    replace(
                        pending / name,
                        current,
                        mode=0o644,
                        uid=os.geteuid(),
                        gid=os.getegid(),
                    )
            journal["phase"] = "activating"
            persist(pending / "snapshot.json", journal)
            active = activate()
            journal["phase"] = "activated"
            persist(pending / "snapshot.json", journal)
            if active:
                persist(receipt, expected_receipt)
            else:
                receipt.unlink(missing_ok=True)
                sync_directory(directory)
        except Exception:
            try:
                recover(directory, pending)
            except Exception:
                raise RuntimeError("manual-recovery-required") from None
            publishing = False
            raise RuntimeError("publication-compensated") from None
        publishing = False
        return {
            "changed": changed
            or recovered
            or bool(active)
            and activated != expected_receipt
        }
    finally:
        if not publishing and pending.exists():
            shutil.rmtree(pending)
            sync_directory(directory)


def inspect_directory(directory, *, missing=False):
    directory = Path(directory)
    if not directory.is_absolute() or ".." in directory.parts:
        raise ValueError("unsafe-directory")
    current = Path("/")
    for part in directory.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                return
            raise
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in {0, os.geteuid()}
            or info.st_mode & 0o022
        ):
            raise ValueError("unsafe-directory")


def publish(request):
    directory = Path(request["install_dir"])
    inspect_directory(directory)
    descriptor = os.open(
        directory / ".geodata-lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("unsafe-lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _publish_locked(request)
    finally:
        os.close(descriptor)


def main():
    try:
        request = json.load(sys.stdin)
        if sys.argv[1:] == ["--inspect"]:
            if set(request) != {"install_dir"}:
                raise ValueError("request")
            inspect_directory(request["install_dir"], missing=True)
            print(json.dumps({"changed": False}))
        elif sys.argv[1:]:
            raise ValueError("arguments")
        else:
            print(json.dumps(publish(request)))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ):
        print("geodata publication failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
