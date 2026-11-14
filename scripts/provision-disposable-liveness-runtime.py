#!/usr/bin/env python3
"""Install the pinned sentinel runtimes into one live disposable liveness executor.

The disposable sentinel runner needs pinned sing-box and Xray on PATH and the
immutable source-built AWG toolchain beneath /opt/ripdpi-real-vps-awg-nat.
This command installs them into the exact Colima profile named by a live
executor manifest from ``make prepare-disposable-liveness`` and prints the
``expected_runtime`` block for the predeployment liveness configuration.

The operator machine downloads and verifies every input; the executor builds
AWG offline through the canonical ``install-real-vps-awg-client-tools.py``.
No client credentials, secrets or provider calls are involved.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from disposable_liveness_executor import (
    ExecutorError,
    _run_command,
    executor_command,
    load_live_executor,
)

ROLE = ROOT / "ansible/roles/real-vps-awg-nat"
CORRECTION_SOURCE = ROOT / "ansible/roles/amneziawg/files"
CORRECTION_FILES = ("awg_source_correction.py", "awg-source-correction.json", "awg-udp-checksum-zero.patch.json")
INSTALLER = ROOT / "scripts/install-real-vps-awg-client-tools.py"
BUNDLER = ROOT / "scripts/build-real-vps-awg-nat-source-bundle.sh"
ARCHITECTURES = {"aarch64": "arm64", "x86_64": "amd64"}
# Update a version and all of its archive digests together after upstream
# release review. The liveness-sentinel role reads the same file.
PINS = json.loads((ROOT / "ansible/roles/liveness-sentinel/files/runtime-pins.json").read_text())
ENGINES = {
    name: {**engine, "archives": {arch: (item["name"], item["sha256"]) for arch, item in engine["archives"].items()}}
    for name, engine in PINS["engines"].items()
}
AWG_REPOSITORIES = PINS["awg_repositories"]
# Ubuntu 24.04's default golang (1.22.2) is older than amneziawg-go's go.mod
# floor; the builder runs with GOTOOLCHAIN=local, so it needs this package.
GO_PACKAGE = PINS["go_package"]
GO_BIN = PINS["go_bin"]
VM_INPUTS = "/var/tmp/ripdpi-liveness-runtime"
MAX_DOWNLOAD = 128 * 1024 * 1024


class ProvisionError(Exception):
    """A refused or failed provisioning step, named without secret material."""


def role_inputs() -> tuple[list[str], dict[str, str]]:
    """Read the sentinel package list and AWG commit pins from the role."""
    tasks = yaml.safe_load((ROLE / "tasks/sentinel.yml").read_text())
    install = next(task for task in tasks if task.get("name") == "Install sentinel build and runtime prerequisites")
    packages = list(install["ansible.builtin.apt"]["name"])
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    commits = {"go": defaults["real_vps_awg_nat_awg_go_commit"], "tools": defaults["real_vps_awg_nat_awg_tools_commit"]}
    if any(re.fullmatch(r"[0-9a-f]{40}", value) is None for value in commits.values()):
        raise ProvisionError("awg-commit-pin")
    return sorted({*packages, "curl", GO_PACKAGE}), commits


def engine_binary(name: str, archive_name: str, payload: bytes, arch: str) -> bytes:
    """Return the engine executable from a verified release archive."""
    member = ENGINES[name]["member"].format(arch=arch)
    try:
        if archive_name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                return archive.read(member)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            source = archive.extractfile(member)
            if source is None:
                raise KeyError(member)
            return source.read()
    except (KeyError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise ProvisionError(f"{name}-archive-member") from exc


def verified_download(url: str, expected_sha256: str, destination: Path) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = response.read(MAX_DOWNLOAD + 1)
    if len(payload) > MAX_DOWNLOAD or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ProvisionError("download-digest")
    destination.write_bytes(payload)
    return payload


def vendor_archive(source: Path, output: Path) -> str:
    """Write a deterministic tar holding only ``vendor/`` and return its digest."""
    root = source / "vendor"
    if not root.is_dir():
        raise ProvisionError("vendor-tree")
    paths = sorted([root, *root.rglob("*")], key=lambda path: path.relative_to(source).as_posix())
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        for path in paths:
            info = path.lstat()
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ProvisionError("vendor-member")
            member = tarfile.TarInfo(path.relative_to(source).as_posix())
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            member.mtime = 0
            if stat.S_ISDIR(info.st_mode):
                member.type, member.mode = tarfile.DIRTYPE, 0o755
                archive.addfile(member)
            else:
                member.mode = 0o755 if info.st_mode & 0o111 else 0o644
                member.size = info.st_size
                with path.open("rb") as handle:
                    archive.addfile(member, handle)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def private_work_directory(path: Path) -> Path:
    path = path.expanduser()
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or any(path.iterdir())):
        raise ProvisionError("work-directory")
    return path.resolve(strict=True)


def local(*argv: str, cwd: Path | None = None, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(list(argv), cwd=cwd, env=environment, capture_output=True, text=True, timeout=900, check=False)
    if result.returncode != 0:
        raise ProvisionError(f"local-command: {argv[0]} {argv[1] if len(argv) > 1 else ''}".strip())
    return result.stdout


def awg_sources(work: Path, commits: dict[str, str]) -> dict[str, object]:
    """Materialize the pinned AWG bundles and the vendor archive on this machine."""
    result: dict[str, object] = {}
    for name, url in AWG_REPOSITORIES.items():
        checkout = work / f"amneziawg-{name}"
        local("git", "clone", "--quiet", "--no-checkout", url, str(checkout))
        local("git", "-C", str(checkout), "checkout", "--quiet", "--detach", commits[name])
        bundle = json.loads(local(str(BUNDLER), "--repo", str(checkout), "--output", str(work / f"amneziawg-{name}.bundle")))
        if bundle["sourceSha"] != commits[name]:
            raise ProvisionError("awg-bundle-commit")
        result[f"{name}_bundle_sha256"] = bundle["sourceBundleSha256"]
    go_checkout = work / "amneziawg-go"
    environment = {**os.environ, "GOFLAGS": "-mod=mod", "GOWORK": "off"}
    local("go", "mod", "vendor", cwd=go_checkout, environment=environment)
    result["vendor_sha256"] = vendor_archive(go_checkout, work / "amneziawg-go-vendor.tar")
    correction = json.loads(local(sys.executable, "-Es", str(CORRECTION_SOURCE / CORRECTION_FILES[0]),
                                  "describe", "--commit", commits["go"]))
    if re.fullmatch(r"[0-9a-f]{64}", str(correction.get("digest"))) is None:
        raise ProvisionError("awg-correction-digest")
    result["correction_digest"] = correction["digest"]
    return result


class Executor:
    """Run fixed root commands inside the exact live Colima profile."""

    def __init__(self, profile: str):
        self.profile = profile

    def run(self, command: str, *, input_bytes: bytes = b"", timeout: int = 120) -> str:
        result = subprocess.run(list(executor_command(self.profile, command)), input=input_bytes,
                                capture_output=True, timeout=timeout, check=False,
                                env={key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ})
        if result.returncode != 0:
            tail = result.stderr.decode(errors="replace").strip().splitlines()[-3:]
            raise ProvisionError("executor-command: " + " | ".join(tail)[:400])
        return result.stdout.decode()

    def install(self, path: str, payload: bytes, mode: str) -> None:
        quoted = shlex.quote(path)
        self.run(f"sudo -n sh -c 'umask 077; cat > {quoted}.new && chown root:root {quoted}.new "
                 f"&& chmod {mode} {quoted}.new && mv -f {quoted}.new {quoted}'", input_bytes=payload, timeout=300)


def version_of(output: str) -> str:
    match = re.search(r"v?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)", output)
    if match is None:
        raise ProvisionError("runtime-version")
    return match.group(1)


def provision(manifest_path: Path, work: Path) -> dict[str, object]:
    work = private_work_directory(work)
    packages, commits = role_inputs()
    manifest = load_live_executor(manifest_path, home=Path.home(), now=int(time.time()), runner=_run_command)
    executor = Executor(manifest["profile"])
    arch = ARCHITECTURES.get(executor.run("uname -m").strip())
    if arch is None:
        raise ProvisionError("executor-architecture")
    executor.run("sudo -n env DEBIAN_FRONTEND=noninteractive apt-get update -qq && sudo -n env "
                 "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "
                 + " ".join(shlex.quote(name) for name in packages), timeout=1800)
    runtime: dict[str, str] = {}
    for name, engine in ENGINES.items():
        archive_name, digest = engine["archives"][arch]
        payload = verified_download(engine["url"].format(version=engine["version"], archive=archive_name),
                                    digest, work / archive_name)
        executor.install(f"/usr/local/bin/{name}", engine_binary(name, archive_name, payload, arch), "0755")
        installed = version_of(executor.run(f"{name} version"))
        if installed != engine["version"]:
            raise ProvisionError(f"{name}-version")
        runtime["sing_box" if name == "sing-box" else "xray"] = installed
    sources = awg_sources(work, commits)
    correction_dir = f"/usr/local/libexec/ripdpi/awg-source-{sources['correction_digest']}"
    executor.run(f"sudo -n install -d -o root -g root -m 0700 {VM_INPUTS} && sudo -n install -d -o root -g root "
                 f"-m 0755 /usr/local/libexec/ripdpi {shlex.quote(correction_dir)} && sudo -n install -d -o root "
                 "-g root -m 0700 /run/lock/ripdpi-real-vps-awg-nat")
    for name in CORRECTION_FILES:
        executor.install(f"{correction_dir}/{name}", (CORRECTION_SOURCE / name).read_bytes(), "0644")
    executor.install("/usr/local/libexec/install-real-vps-awg-client-tools", INSTALLER.read_bytes(), "0755")
    for name in ("amneziawg-go.bundle", "amneziawg-tools.bundle", "amneziawg-go-vendor.tar"):
        executor.install(f"{VM_INPUTS}/{name}", (work / name).read_bytes(), "0600")
    argv = [
        "/usr/local/libexec/install-real-vps-awg-client-tools",
        "--go-bundle", f"{VM_INPUTS}/amneziawg-go.bundle", "--go-bundle-sha256", str(sources["go_bundle_sha256"]),
        "--go-commit", commits["go"],
        "--tools-bundle", f"{VM_INPUTS}/amneziawg-tools.bundle",
        "--tools-bundle-sha256", str(sources["tools_bundle_sha256"]), "--tools-commit", commits["tools"],
        "--vendor-archive", f"{VM_INPUTS}/amneziawg-go-vendor.tar", "--vendor-sha256", str(sources["vendor_sha256"]),
        "--correction-directory", correction_dir, "--correction-digest", str(sources["correction_digest"]),
    ]
    built = json.loads(executor.run(f"sudo -n env PATH={GO_BIN}:/usr/sbin:/usr/bin:/sbin:/bin "
                                    + " ".join(shlex.quote(part) for part in argv), timeout=1800))
    executor.run(f"sudo -n rm -rf {VM_INPUTS}")
    toolchain = built.get("toolchainId")
    if not isinstance(toolchain, str) or re.fullmatch(r"[0-9a-f]{64}", toolchain) is None:
        raise ProvisionError("awg-toolchain-result")
    # The immutable toolchain tree is root-only (0500); the sentinel runner is root.
    runtime["awg"] = version_of(
        executor.run(f"sudo -n /opt/ripdpi-real-vps-awg-nat/toolchains/{toolchain}/bin/awg --version"))
    runtime["awg_toolchain"] = toolchain
    return {"profile": manifest["profile"], "architecture": arch, "expected_runtime": runtime}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install pinned sentinel runtimes into a disposable executor.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(provision(args.manifest, args.work_dir), sort_keys=True))
        return 0
    except (ProvisionError, ExecutorError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"provision-disposable-liveness-runtime: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
