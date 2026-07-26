#!/usr/bin/env python3
"""Build the sentinel AWG toolchain from immutable offline inputs."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
BASE = Path("/opt/ripdpi-real-vps-awg-nat/toolchains")
ACTIVE_LINK = BASE.parent / "active-bin"
COMMAND_DIR = Path("/usr/local/bin")
LOCK_DIR = Path("/run/lock/ripdpi-real-vps-awg-nat")
LOCK_FILE = LOCK_DIR / "lane.lock"
BINARY_NAMES = ("amneziawg-go", "awg", "awg-quick")
MAX_VENDOR_BYTES = 256 * 1024 * 1024
MAX_VENDOR_MEMBERS = 50_000
ROOT_UID = 0
ROOT_GID = 0
MANIFEST_SCHEMA = 1


def validate_secure_directory(path: Path, mode: int, label: str) -> None:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or stat.S_IMODE(info.st_mode) != mode
    ):
        raise ValueError(f"{label} is unsafe")


def validate_owned_directory(path: Path, label: str) -> None:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise ValueError(f"{label} is unsafe")


@contextmanager
def lane_lock():
    LOCK_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    validate_secure_directory(LOCK_DIR, 0o700, "shared lane lock directory")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(LOCK_FILE, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or info.st_nlink != 1
        ):
            raise ValueError("shared lane lock file is unsafe")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("real-VPS AWG/NAT lane is already running") from exc
        yield
    finally:
        os.close(descriptor)


def digest(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            state.update(chunk)
    return state.hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def secure_input(path: Path, expected: str) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("toolchain input must be an absolute regular file")
    info = path.stat()
    if (
        info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise ValueError("toolchain input must be owner-only")
    if digest(path) != expected:
        raise ValueError("toolchain input digest mismatch")


def validate_vendor(members: list[tarfile.TarInfo]) -> None:
    if len(members) > MAX_VENDOR_MEMBERS:
        raise ValueError("vendor archive has too many members")
    total = 0
    seen: set[PurePosixPath] = set()
    for member in members:
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or not path.parts
            or path in seen
            or any(part in {"", ".", ".."} for part in path.parts)
            or not (member.isfile() or member.isdir())
        ):
            raise ValueError("vendor archive contains an unsafe member")
        seen.add(path)
        if path.parts[0] != "vendor":
            raise ValueError("vendor archive must contain only vendor/")
        total += member.size
        if total > MAX_VENDOR_BYTES:
            raise ValueError("vendor archive exceeds size limit")


def extract_vendor(archive: tarfile.TarFile, destination: Path) -> None:
    """Extract regular vendor files without delegating path handling to tarfile."""
    members = archive.getmembers()
    validate_vendor(members)
    for member in members:
        relative = PurePosixPath(member.name)
        target = destination.joinpath(*relative.parts)
        current = destination
        for part in relative.parts[:-1] if member.isfile() else relative.parts:
            current /= part
            if os.path.lexists(current):
                info = current.lstat()
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError("vendor archive directory is unsafe")
            else:
                current.mkdir(mode=0o755)
        if member.isdir():
            continue
        if os.path.lexists(target):
            raise ValueError("vendor archive would overwrite an existing path")
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("vendor archive file has no payload")
        try:
            with target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
        finally:
            source.close()
        os.chmod(target, 0o500 if member.mode & 0o111 else 0o400)


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    ).stdout.strip()


def verify_checkout(path: Path, commit: str) -> None:
    if git("rev-parse", "HEAD", cwd=path) != commit:
        raise ValueError("offline source resolved to the wrong commit")
    if git("status", "--porcelain", "--untracked-files=all", cwd=path):
        raise ValueError("offline source checkout is dirty before build")
    git("fsck", "--full", "--strict", cwd=path)


def run_offline_make(path: Path) -> None:
    env = {
        **os.environ,
        "GONOSUMDB": "*",
        "GOPROXY": "off",
        "GOSUMDB": "off",
        "GOTOOLCHAIN": "local",
        "GOFLAGS": "-mod=vendor",
    }
    subprocess.run(
        ["unshare", "--net", "--", "make"],
        cwd=path,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1800,
    )


def freeze_tree(root: Path) -> None:
    paths = [
        *sorted(root.rglob("*"), key=lambda value: value.as_posix(), reverse=True),
        root,
    ]
    for path in paths:
        info = path.lstat()
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("toolchain tree contains an unsupported entry")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError("toolchain tree contains a hard-linked file")
        mode = (
            0o500
            if stat.S_ISDIR(info.st_mode)
            else (0o500 if info.st_mode & 0o111 else 0o400)
        )
        os.chown(path, ROOT_UID, ROOT_GID, follow_symlinks=False)
        os.chmod(path, mode)


def validate_tree_metadata(root: Path, *, owner_only: bool = True) -> None:
    directory_mode = 0o500 if owner_only else 0o555
    file_modes = {0o400, 0o500} if owner_only else {0o444, 0o555}
    root_info = root.lstat()
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != ROOT_UID
        or root_info.st_gid != ROOT_GID
        or stat.S_IMODE(root_info.st_mode) != directory_mode
    ):
        raise ValueError("existing toolchain root metadata is invalid")
    for path in sorted(root.rglob("*"), key=lambda value: value.as_posix()):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (
            stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
        ):
            raise ValueError("toolchain tree contains an unsupported entry")
        mode = stat.S_IMODE(info.st_mode)
        mode_is_valid = (
            mode == directory_mode
            if stat.S_ISDIR(info.st_mode)
            else mode in file_modes and info.st_nlink == 1
        )
        if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID or not mode_is_valid:
            raise ValueError("existing toolchain entry metadata is invalid")


def tree_digest(root: Path) -> str:
    state = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda value: value.as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        info = path.lstat()
        metadata = (
            f"{info.st_uid}:{info.st_gid}:{stat.S_IMODE(info.st_mode):04o}".encode()
        )
        if stat.S_ISDIR(info.st_mode):
            state.update(b"D\0" + relative + b"\0" + metadata + b"\0")
        elif stat.S_ISREG(info.st_mode) and path != root / "manifest.json":
            state.update(
                b"F\0" + relative + b"\0" + metadata + b"\0" + path.read_bytes()
            )
        elif stat.S_ISREG(info.st_mode):
            continue
        else:
            raise ValueError("toolchain tree contains an unsupported entry")
    return state.hexdigest()


def validate_existing(
    target: Path, inputs: dict[str, str], *, owner_only: bool = True
) -> dict[str, str]:
    validate_tree_metadata(target, owner_only=owner_only)
    manifest_path = target / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("existing toolchain lacks a manifest")
    if manifest_path.stat().st_size > 64 * 1024:
        raise ValueError("existing toolchain manifest is too large")
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != canonical(manifest):
        raise ValueError("existing toolchain manifest is not canonical")
    if set(manifest) != {"schemaVersion", "inputs", "binaries", "treeSha256"}:
        raise ValueError("existing toolchain manifest shape is invalid")
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA:
        raise ValueError("existing toolchain manifest schema is invalid")
    if manifest.get("inputs") != inputs:
        raise ValueError("existing toolchain inputs differ")
    if manifest.get("treeSha256") != tree_digest(target):
        raise ValueError("existing immutable toolchain was modified")
    binaries = manifest.get("binaries")
    if not isinstance(binaries, dict) or set(binaries) != set(BINARY_NAMES):
        raise ValueError("existing toolchain binary manifest is invalid")
    for name, expected in binaries.items():
        if not SHA256.fullmatch(expected) or digest(target / "bin" / name) != expected:
            raise ValueError("existing toolchain binary digest mismatch")
    return binaries


def harden_legacy_tree(target: Path, inputs: dict[str, str]) -> dict[str, str]:
    binaries = validate_existing(target, inputs, owner_only=False)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    freeze_tree(target)
    manifest["treeSha256"] = tree_digest(target)
    os.chmod(manifest_path, 0o600)
    manifest_path.write_bytes(canonical(manifest))
    os.chmod(manifest_path, 0o400)
    if validate_existing(target, inputs) != binaries:
        raise ValueError("hardened toolchain binary manifest changed")
    return binaries


def replace_symlink(target: str, destination: Path) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.close(fd)
        temporary.unlink()
        os.symlink(target, temporary)
        os.chown(temporary, ROOT_UID, ROOT_GID, follow_symlinks=False)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def verify_binary(path: Path, expected: str, mode: int) -> None:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_nlink != 1
        or digest(path) != expected
    ):
        raise ValueError("AWG command metadata or digest mismatch")


def valid_command_link(name: str) -> bool:
    try:
        path = COMMAND_DIR / name
        info = path.lstat()
        return (
            stat.S_ISLNK(info.st_mode)
            and info.st_uid == ROOT_UID
            and info.st_gid == ROOT_GID
            and os.readlink(path) == str(ACTIVE_LINK / name)
        )
    except OSError:
        return False


def active_toolchain_is_valid(target: Path, binaries: dict[str, str]) -> bool:
    try:
        info = ACTIVE_LINK.lstat()
        if (
            not stat.S_ISLNK(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or os.readlink(ACTIVE_LINK)
            != str(target.relative_to(ACTIVE_LINK.parent) / "bin")
            or ACTIVE_LINK.resolve(strict=True) != (target / "bin").resolve(strict=True)
        ):
            return False
        for name, expected in binaries.items():
            verify_binary(ACTIVE_LINK / name, expected, 0o500)
        return all(valid_command_link(name) for name in BINARY_NAMES)
    except (OSError, ValueError):
        return False


def activate_toolchain(target: Path, binaries: dict[str, str]) -> bool:
    COMMAND_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
    validate_secure_directory(COMMAND_DIR, 0o755, "AWG command directory")
    if active_toolchain_is_valid(target, binaries):
        return False
    for name in BINARY_NAMES:
        if not valid_command_link(name):
            replace_symlink(str(ACTIVE_LINK / name), COMMAND_DIR / name)
    relative_target = str(target.relative_to(ACTIVE_LINK.parent) / "bin")
    replace_symlink(relative_target, ACTIVE_LINK)
    if not active_toolchain_is_valid(target, binaries):
        raise ValueError("activated AWG toolchain failed verification")
    return True


def build_locked(args: argparse.Namespace) -> dict[str, object]:
    if os.geteuid() != ROOT_UID:
        raise ValueError("toolchain installer must run as root")
    inputs = {
        "goBundleSha256": args.go_bundle_sha256,
        "goCommit": args.go_commit,
        "toolsBundleSha256": args.tools_bundle_sha256,
        "toolsCommit": args.tools_commit,
        "vendorSha256": args.vendor_sha256,
    }
    for value, pattern in (
        (args.go_commit, SHA1),
        (args.tools_commit, SHA1),
        (args.go_bundle_sha256, SHA256),
        (args.tools_bundle_sha256, SHA256),
        (args.vendor_sha256, SHA256),
    ):
        if pattern.fullmatch(value) is None:
            raise ValueError("invalid toolchain pin")
    for path, expected in (
        (args.go_bundle, args.go_bundle_sha256),
        (args.tools_bundle, args.tools_bundle_sha256),
        (args.vendor_archive, args.vendor_sha256),
    ):
        secure_input(path, expected)
    toolchain_id = hashlib.sha256(canonical(inputs)).hexdigest()
    BASE.mkdir(parents=True, exist_ok=True, mode=0o755)
    validate_owned_directory(BASE.parent, "toolchain parent directory")
    validate_owned_directory(BASE, "toolchain base directory")
    target = BASE / toolchain_id
    changed = False
    if os.path.lexists(target):
        if target.is_symlink() or not target.is_dir():
            raise ValueError("existing toolchain target is unsafe")
        try:
            binaries = validate_existing(target, inputs)
        except ValueError:
            binaries = harden_legacy_tree(target, inputs)
            changed = True
    else:
        staging = Path(tempfile.mkdtemp(prefix=".build-", dir=BASE))
        try:
            go_source = staging / "amneziawg-go"
            tools_source = staging / "amneziawg-tools"
            git("clone", "--no-checkout", str(args.go_bundle), str(go_source))
            git("bundle", "verify", str(args.go_bundle), cwd=go_source)
            git("checkout", "--detach", args.go_commit, cwd=go_source)
            verify_checkout(go_source, args.go_commit)
            with tarfile.open(args.vendor_archive, mode="r:*") as archive:
                extract_vendor(archive, go_source)
            run_offline_make(go_source)
            git("clone", "--no-checkout", str(args.tools_bundle), str(tools_source))
            git("bundle", "verify", str(args.tools_bundle), cwd=tools_source)
            git("checkout", "--detach", args.tools_commit, cwd=tools_source)
            verify_checkout(tools_source, args.tools_commit)
            run_offline_make(tools_source / "src")
            binary_dir = staging / "bin"
            binary_dir.mkdir()
            shutil.copy2(go_source / "amneziawg-go", binary_dir / "amneziawg-go")
            shutil.copy2(tools_source / "src/awg", binary_dir / "awg")
            shutil.copy2(
                tools_source / "src/awg-quick/linux.bash",
                binary_dir / "awg-quick",
            )
            for path in binary_dir.iterdir():
                os.chmod(path, 0o700)
            binaries = {name: digest(binary_dir / name) for name in BINARY_NAMES}
            manifest = {
                "schemaVersion": MANIFEST_SCHEMA,
                "inputs": inputs,
                "binaries": binaries,
            }
            (staging / "manifest.json").write_bytes(b"{}\n")
            freeze_tree(staging)
            manifest["treeSha256"] = tree_digest(staging)
            os.chmod(staging / "manifest.json", 0o600)
            (staging / "manifest.json").write_bytes(canonical(manifest))
            os.chown(staging / "manifest.json", ROOT_UID, ROOT_GID)
            os.chmod(staging / "manifest.json", 0o400)
            os.replace(staging, target)
            changed = True
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    if activate_toolchain(target, binaries):
        changed = True
    result = {"toolchainId": toolchain_id, "binaries": binaries, "changed": changed}
    return result


def build(args: argparse.Namespace) -> dict[str, object]:
    with lane_lock():
        return build_locked(args)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--go-bundle", type=Path, required=True)
    parser.add_argument("--go-bundle-sha256", required=True)
    parser.add_argument("--go-commit", required=True)
    parser.add_argument("--tools-bundle", type=Path, required=True)
    parser.add_argument("--tools-bundle-sha256", required=True)
    parser.add_argument("--tools-commit", required=True)
    parser.add_argument("--vendor-archive", type=Path, required=True)
    parser.add_argument("--vendor-sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), sort_keys=True, separators=(",", ":")))
        return 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"install-real-vps-awg-client-tools: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
