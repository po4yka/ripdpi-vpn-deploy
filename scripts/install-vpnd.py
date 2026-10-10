#!/usr/bin/env python3
"""Install a verified Python release, preserving the preceding command on failure."""

import fcntl
import hashlib
import io
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from contextlib import contextmanager
from email.parser import BytesParser
from pathlib import Path

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 64
TARGETS = {
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("Linux", "arm64"): "aarch64-unknown-linux-gnu",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
}


def normalized_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def current_target():
    try:
        return TARGETS[(platform.system(), platform.machine())]
    except KeyError:
        raise ValueError("unsupported vpnd installation platform") from None


def locked_requirements(raw):
    """Only exact package pins and SHA256 hashes belong in an offline lock."""
    logical = []
    pending = ""
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        pending += " " + (line[:-1] if continued else line)
        if not continued:
            logical.append(pending.strip())
            pending = ""
    if pending:
        raise ValueError("unterminated runtime lock entry")
    locked = {}
    hashes = {}
    for line in logical:
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!]+)((?:\s+--hash=sha256:[0-9a-f]{64})+)",
            line,
        )
        if match is None:
            raise ValueError("runtime lock must contain exact hashed package pins")
        name = normalized_name(match[1])
        if name in locked:
            raise ValueError("duplicate runtime lock package")
        locked[name] = match[2]
        hashes[name] = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", match[3]))
    if not locked or "vpnd" in locked or "pip" in locked:
        raise ValueError("invalid runtime dependency inventory")
    return locked, hashes


def wheel_metadata(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if len(names) > 20000 or len(names) != len(set(names)):
            raise ValueError("duplicate wheel member")
        if any(
            name.startswith("/")
            or ".." in Path(name).parts
            or "\\" in name
            or stat.S_IFMT(archive.getinfo(name).external_attr >> 16)
            not in {0, stat.S_IFREG, stat.S_IFDIR}
            or archive.getinfo(name).file_size > MAX_MEMBER_BYTES
            for name in names
        ):
            raise ValueError("unsafe wheel resource")
        if sum(item.file_size for item in archive.infolist()) > MAX_ARCHIVE_BYTES:
            raise ValueError("wheel resources exceed the release size limit")
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("wheel must contain one package metadata document")
        document = BytesParser().parsebytes(archive.read(metadata[0]))
        name, version = document.get("Name"), document.get("Version")
        if not name or not version:
            raise ValueError("wheel package identity is missing")
        assets = {}
        for name in names:
            if name.startswith("vpnd/data/man/") and name.endswith(".1"):
                if Path(name).parent.as_posix() != "vpnd/data/man":
                    raise ValueError("unsafe manual page path")
                page = Path(name).name
                if re.fullmatch(r"vpnd(?:-[a-z0-9-]+)?\.1", page) is None:
                    raise ValueError("invalid manual page name")
                assets[page] = archive.read(name)
        resource_names = set(names)
        return (
            normalized_name(document["Name"]),
            version,
            document.get_all("Requires-Dist", []),
            assets,
            resource_names,
        )


def verified_bundle(artifact):
    if Path(artifact).stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("release archive exceeds the size limit")
    files = {}
    total = 0
    with tarfile.open(artifact, "r:gz") as archive:
        for member in archive:
            if (
                len(files) >= MAX_MEMBERS
                or not member.isfile()
                or re.fullmatch(r"[A-Za-z0-9_.+-]+", member.name) is None
                or member.name in {".", ".."}
                or member.name in files
            ):
                raise ValueError(
                    "release contains an unsafe or duplicate archive member"
                )
            total += member.size
            if (
                member.size < 0
                or member.size > MAX_MEMBER_BYTES
                or total > MAX_ARCHIVE_BYTES
            ):
                raise ValueError("release resources exceed the size limit")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("invalid release member")
            files[member.name] = stream.read()
    manifest = json.loads(files.pop("MANIFEST.json"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "version",
        "target",
        "files",
    }:
        raise ValueError("invalid release manifest")
    version = manifest["version"]
    if (
        not isinstance(version, str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
    ):
        raise ValueError("invalid release version")
    if manifest["target"] != current_target():
        raise ValueError("release target does not match the installation platform")
    expected = manifest["files"]
    if not isinstance(expected, dict) or set(files) != set(expected):
        raise ValueError("release file inventory mismatch")
    for name, content in files.items():
        if (
            not isinstance(expected[name], str)
            or re.fullmatch(r"[0-9a-f]{64}", expected[name]) is None
            or hashlib.sha256(content).hexdigest() != expected[name]
        ):
            raise ValueError("release content checksum mismatch")
    if {name for name in files if not name.endswith(".whl")} != {
        "requirements.txt",
        "install.py",
    }:
        raise ValueError("release contains an unapproved resource")
    locked, hashes = locked_requirements(files["requirements.txt"])
    inventory = {}
    app = None
    pages = {}
    for filename, content in files.items():
        if not filename.endswith(".whl"):
            continue
        name, wheel_version, requires, wheel_pages, resources = wheel_metadata(content)
        if name in inventory:
            raise ValueError("duplicate wheel package")
        inventory[name] = wheel_version
        if name != "vpnd" and hashlib.sha256(content).hexdigest() not in hashes.get(
            name, set()
        ):
            raise ValueError(
                "runtime wheel checksum disagrees with the dependency lock"
            )
        if name == "vpnd":
            if wheel_version != version or not filename.startswith(
                "vpnd-" + version + "-"
            ):
                raise ValueError("application wheel version mismatch")
            declared = {}
            for requirement in requires:
                match = re.fullmatch(
                    r"([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.+!]+)", requirement
                )
                if match is None:
                    raise ValueError(
                        "application dependencies must be exact runtime pins"
                    )
                dependency = normalized_name(match[1])
                if dependency in declared or locked.get(dependency) != match[2]:
                    raise ValueError(
                        "application dependencies disagree with the runtime lock"
                    )
                declared[dependency] = match[2]
            if not declared:
                raise ValueError("application runtime dependencies are missing")
            if (
                "vpnd/data/recipient.html" not in resources
                or not any(
                    name.startswith("vpnd/data/docs/") and name.endswith(".md")
                    for name in resources
                )
                or "vpnd.1" not in wheel_pages
            ):
                raise ValueError(
                    "application templates, documentation or manual pages are missing"
                )
            app, pages = filename, wheel_pages
    if inventory != {**locked, "vpnd": version} or app is None:
        raise ValueError("release wheel inventory disagrees with the runtime lock")
    return version, files, app, locked, pages


@contextmanager
def installation_lock(prefix):
    directory = prefix / "lib/vpnd"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        directory / ".install.lock",
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size != 0
        ):
            raise ValueError("unsafe installation lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def installation_environment():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "__PYVENV_LAUNCHER__"}
        and not key.startswith("PIP_")
    }
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PIP_CONFIG_FILE"] = os.devnull
    return environment


def installed_inventory(python, cwd, environment):
    script = """import importlib.metadata as metadata, json, re
from vpnd.commands.completions import render_page_set
normalize = lambda value: re.sub(r'[-_.]+', '-', value).lower()
rows = [(normalize(item.metadata['Name']), item.version) for item in metadata.distributions()]
if len(rows) != len(dict(rows)):
    raise ValueError('duplicate installed package')
print(json.dumps({'packages': dict(rows), 'pages': {name + '.1': page for name, page in render_page_set()}}))
"""
    environment = {
        key: value
        for key, value in environment.items()
        if key not in {"VPN_ENV", "VPN_PROVIDER", "VPN_DEPLOY_ROOT"}
    }
    return json.loads(
        subprocess.check_output(
            [str(python), "-c", script], text=True, cwd=cwd, env=environment
        )
    )


def stage_file(directory, content):
    handle, name = tempfile.mkstemp(prefix=".vpnd-stage-", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def snapshot(path, directory):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    backup = directory / ("backup-" + str(len(list(directory.iterdir()))))
    if stat.S_ISLNK(metadata.st_mode):
        backup.symlink_to(os.readlink(path))
    elif stat.S_ISREG(metadata.st_mode):
        shutil.copy2(path, backup)
    else:
        raise ValueError(
            "existing installation output is not a regular file or symlink"
        )
    return backup


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish(prefix, command, pages):
    """Roll back only outputs still carrying this transaction's staged inode."""
    binary, manuals = prefix / "bin", prefix / "share/man/man1"
    binary.mkdir(parents=True, exist_ok=True)
    manuals.mkdir(parents=True, exist_ok=True)
    changes = []
    with tempfile.TemporaryDirectory(
        prefix=".publish-", dir=prefix / "lib/vpnd"
    ) as temporary:
        backups = Path(temporary)
        staged = []
        try:
            for name, content in sorted(pages.items()):
                staged.append((manuals / name, stage_file(manuals, content)))
            handle, name = tempfile.mkstemp(prefix=".vpnd-stage-", dir=binary)
            os.close(handle)
            launcher = Path(name)
            launcher.unlink()
            launcher.symlink_to(command)
            staged.append((binary / "vpnd", launcher))
            for destination, source in staged:
                backup = snapshot(destination, backups)
                identity = source.lstat()
                # Record before replace: interruption can be delivered after the
                # rename syscall completed but before Python returns from it.
                changes.append((destination, backup, identity.st_dev, identity.st_ino))
                os.replace(source, destination)
            sync_directory(manuals)
            sync_directory(binary)
        except BaseException:
            previous_mask = signal.pthread_sigmask(
                signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM}
            )
            try:
                for destination, backup, device, inode in reversed(changes):
                    try:
                        current = destination.lstat()
                    except FileNotFoundError:
                        continue
                    if (current.st_dev, current.st_ino) != (device, inode):
                        continue
                    if backup is None:
                        destination.unlink()
                    else:
                        os.replace(backup, destination)
                sync_directory(manuals)
                sync_directory(binary)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            raise
        finally:
            for _, source in staged:
                source.unlink(missing_ok=True)


def install(artifact, prefix):
    if sys.version_info[:2] != (3, 12):
        raise ValueError("vpnd installation requires Python 3.12")
    if os.geteuid() == 0 and os.environ.get("ALLOW_ROOT") != "1":
        raise ValueError("refusing to run as root; set ALLOW_ROOT=1 to override")
    version, files, app, locked, pages = verified_bundle(artifact)
    prefix = Path(prefix).absolute()
    with installation_lock(prefix):
        releases = prefix / "lib/vpnd/releases"
        releases.mkdir(parents=True, exist_ok=True)
        candidate = Path(tempfile.mkdtemp(prefix=version + "-", dir=releases))
        command = candidate / "bin/vpnd"
        try:
            with tempfile.TemporaryDirectory(prefix="vpnd-install-") as scratch:
                wheelhouse = Path(scratch)
                for name, content in files.items():
                    (wheelhouse / name).write_bytes(content)
                venv.EnvBuilder(with_pip=True).create(candidate)
                python = candidate / "bin/python"
                environment = installation_environment()
                subprocess.run(
                    [
                        str(python),
                        "-m",
                        "pip",
                        "install",
                        "--no-index",
                        "--no-deps",
                        "--require-hashes",
                        "--find-links",
                        str(wheelhouse),
                        "-r",
                        str(wheelhouse / "requirements.txt"),
                    ],
                    check=True,
                    env=environment,
                )
                subprocess.run(
                    [
                        str(python),
                        "-m",
                        "pip",
                        "install",
                        "--no-index",
                        "--no-deps",
                        str(wheelhouse / app),
                    ],
                    check=True,
                    env=environment,
                )
                subprocess.run(
                    [str(python), "-m", "pip", "check"], check=True, env=environment
                )
                inventory = installed_inventory(python, scratch, environment)
                installed = inventory["packages"]
                bootstrap = installed.pop("pip", None)
                if not bootstrap or installed != {**locked, "vpnd": version}:
                    raise ValueError(
                        "installed runtime dependency closure disagrees with the release lock"
                    )
                generated = inventory["pages"]
                if set(generated) != set(pages) or any(
                    generated[name].encode() != pages[name] for name in pages
                ):
                    raise ValueError(
                        "packaged manual pages disagree with the installed parser"
                    )
                result = subprocess.check_output(
                    [str(command), "--version"], text=True, cwd=scratch, env=environment
                ).strip()
                if result != "vpnd " + version:
                    raise ValueError("installed command version mismatch")
                subprocess.run(
                    [str(command), "completions", "bash"],
                    check=True,
                    cwd=scratch,
                    stdout=subprocess.DEVNULL,
                    env=environment,
                )
            publish(prefix, command, pages)
        except BaseException:
            # If an external writer obstructed rollback, retain an active verified
            # environment instead of deleting a command that is still referenced.
            active = prefix / "bin/vpnd"
            try:
                published = (
                    active.is_symlink() and active.resolve() == command.resolve()
                )
            except OSError:
                published = False
            if not published:
                shutil.rmtree(candidate)
            raise
    return prefix / "bin/vpnd"


class InstallationInterrupted(BaseException):
    pass


def terminate_installation(signum, _frame):
    raise InstallationInterrupted(signum)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate_installation)
    if len(sys.argv) != 3:
        raise SystemExit("usage: install-vpnd.py VERIFIED-ARCHIVE PREFIX")
    try:
        print("Installed:", install(sys.argv[1], sys.argv[2]))
    except InstallationInterrupted as error:
        raise SystemExit(128 + error.args[0]) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        raise SystemExit("vpnd installation failed: " + str(error)) from None
