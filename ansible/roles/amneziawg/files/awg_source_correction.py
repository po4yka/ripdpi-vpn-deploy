#!/usr/bin/env python3
"""Apply only the reviewed AWG UDP checksum correction to exact pinned trees."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

ASSETS = Path(os.path.abspath(__file__)).parent
MANIFEST = "awg-source-correction.json"
PATCH = "awg-udp-checksum-zero.patch.json"
TARGET = "tun/offload_linux.go"
MAX_SOURCE_FILE = 4 * 1024 * 1024


def _refuse(category: str) -> None:
    raise ValueError("awg-source-correction:" + category)


def _read(path: Path, limit: int = MAX_SOURCE_FILE) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        _refuse("unsafe-file")
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid not in (0, os.geteuid()) or info.st_mode & 0o022
                or info.st_size > limit):
            _refuse("unsafe-file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        _refuse("oversize-file")
    return data


def _ancestry(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for parent in reversed((path, *path.parents)):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode):
            _refuse("unsafe-source-directory")
        if info.st_uid not in (0, os.geteuid()):
            _refuse("foreign-directory")
        if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            _refuse("writable-directory")
    return path


def _assets(commit: str) -> tuple[dict, dict, dict]:
    _ancestry(ASSETS)
    manifest_bytes = _read(ASSETS / MANIFEST)
    patch_bytes = _read(ASSETS / PATCH)
    helper_bytes = _read(Path(__file__))
    manifest = json.loads(manifest_bytes)
    patch = json.loads(patch_bytes)
    if (manifest.get("schema") != 1 or patch.get("schema") != 1
            or patch.get("path") != TARGET
            or hashlib.sha256(patch_bytes).hexdigest() != manifest.get("patch_sha256")):
        _refuse("asset-digest")
    selected = manifest.get("commits", {}).get(commit)
    if selected is None:
        _refuse("unsupported-commit")
    identity = {
        "schema": 1, "name": manifest["name"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "helper_sha256": hashlib.sha256(helper_bytes).hexdigest(),
        "patch_sha256": manifest["patch_sha256"],
        "profile": selected["profile"],
    }
    # One asset-set digest qualifies source and binary paths for all reviewed pins.
    identity["digest"] = hashlib.sha256(json.dumps(
        {key: value for key, value in identity.items() if key != "profile"},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return identity, selected, patch


def describe(commit: str) -> dict:
    return _assets(commit)[0]


def _git(source: Path, *args: str) -> bytes:
    # These plumbing commands do not read worktree filters or execute hooks.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0")
    completed = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull,
         "--no-optional-locks", "-C", str(source), *args], env=environment,
        capture_output=True, timeout=20, check=False,
    )
    if completed.returncode:
        _refuse("git-metadata")
    return completed.stdout


def _snapshot(source: Path, commit: str, selected: dict, identity: dict) -> tuple[str, bytes | None]:
    if not (source / ".git").is_dir() or (source / ".git").is_symlink():
        _refuse("unsafe-git-directory")
    _ancestry(source / ".git")
    if _git(source, "rev-parse", "--verify", "HEAD").decode().strip() != commit:
        _refuse("head-mismatch")
    if _git(source, "rev-parse", "HEAD^{tree}").decode().strip() != selected["tree"]:
        _refuse("tree-mismatch")
    tracked = {}
    for record in _git(source, "ls-tree", "-rz", "HEAD").split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        name = raw_path.decode()
        if mode not in ("100644", "100755") or kind != "blob":
            _refuse("unsupported-tree-node")
        tracked[name] = (mode, oid)
    indexed = {}
    for record in _git(source, "ls-files", "--stage", "-z").split(b"\0"):
        if record:
            metadata, raw_path = record.split(b"\t", 1)
            mode, oid, stage = metadata.decode().split()
            if stage != "0":
                _refuse("index-diff")
            indexed[raw_path.decode()] = (mode, oid)
    if indexed != tracked:
        _refuse("index-diff")
    digest = identity["digest"]
    outputs = {"amneziawg-go", f".ripdpi-build/{digest}/amneziawg-go", f".ripdpi-build/{digest}/receipt.json"}
    allowed_dirs = {"."}
    for name in (*tracked, *outputs):
        allowed_dirs.update(str(p) for p in Path(name).parents)
    seen = set()
    target_bytes = None
    state = "post" if selected["profile"] == "synthetic-no-tun" else None
    for directory, dirs, files in os.walk(source, followlinks=False):
        relative = Path(directory).relative_to(source)
        if relative == Path("."):
            dirs[:] = [name for name in dirs if name != ".git"]
        for name in dirs:
            path = relative / name
            if (source / path).is_symlink() or str(path) not in allowed_dirs:
                _refuse("extra-directory")
            _ancestry(source / path)
        for name in files:
            relative_file = str(relative / name)
            path = source / relative_file
            if relative_file in outputs:
                if path.is_symlink():
                    if relative_file != "amneziawg-go" or os.readlink(path) != f".ripdpi-build/{digest}/amneziawg-go":
                        _refuse("output-alias")
                else:
                    _read(path, 128 * 1024 * 1024 if name == "amneziawg-go" else 65536)
                continue
            if relative_file not in tracked:
                _refuse("extra-file")
            seen.add(relative_file)
            data = _read(path)
            mode, oid = tracked[relative_file]
            if bool(path.stat().st_mode & 0o111) != (mode == "100755"):
                _refuse("source-mode")
            sha256 = hashlib.sha256(data).hexdigest()
            if selected["profile"] == "synthetic-no-tun":
                if sha256 != selected["files_sha256"].get(relative_file):
                    _refuse("fixture-file")
            elif relative_file == TARGET:
                target_bytes = data
                state = "pre" if sha256 == selected["preimage_sha256"] else "post" if sha256 == selected["postimage_sha256"] else None
                if state is None:
                    _refuse("target-image")
            elif relative_file == "version.go" and sha256 in selected["generated_version_sha256"]:
                continue
            elif hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != oid:
                _refuse("extra-source-diff")
    if seen != set(tracked):
        _refuse("missing-source-file")
    return state, target_bytes


def verify(source: Path, commit: str) -> dict:
    identity, selected, _ = _assets(commit)
    if _snapshot(_ancestry(Path(source)), commit, selected, identity)[0] != "post":
        _refuse("correction-required")
    return {**identity, "changed": False}


def apply(source: Path, commit: str) -> dict:
    identity, selected, patch = _assets(commit)
    source = _ancestry(Path(source))
    state, before = _snapshot(source, commit, selected, identity)
    if state == "post":
        return {**identity, "changed": False}
    after = before.decode()
    for replacement in patch["replacements"]:
        if after.count(replacement["before"]) != 1:
            _refuse("replacement-image")
        after = after.replace(replacement["before"], replacement["after"])
    encoded = after.encode()
    if hashlib.sha256(encoded).hexdigest() != selected["postimage_sha256"]:
        _refuse("postimage-digest")
    target = source / TARGET
    if _read(target) != before:
        _refuse("source-race")
    fd, temporary = tempfile.mkstemp(prefix=".awg-correction-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            os.fchmod(stream.fileno(), stat.S_IMODE(target.stat().st_mode))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    verify(source, commit)
    return {**identity, "changed": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "apply", "verify"))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--identity-digest")
    args = parser.parse_args()
    try:
        if args.identity_digest is not None and describe(args.commit)["digest"] != args.identity_digest:
            _refuse("identity-digest")
        if args.action == "describe":
            result = describe(args.commit)
        elif args.source is None:
            _refuse("missing-source")
        else:
            result = globals()[args.action](args.source, args.commit)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
