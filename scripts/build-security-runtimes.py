#!/usr/bin/env python3
"""Build fixed stable sources with the patched compiler, outside managed nodes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request


SOURCES = Path(__file__).with_name("security-runtime-sources.json")


def download_source(component, destination):
    url = ("https://codeload.github.com/" + component["repository"]
           + "/tar.gz/" + component["commit"])
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != component["sha256"]:
        raise ValueError("source archive checksum or size mismatch")
    destination.write_bytes(data)


def build(output):
    pins = json.loads(SOURCES.read_text())
    if platform.system() != "Linux" or shutil.which("dpkg-deb") is None:
        raise ValueError("build requires Linux and dpkg-deb")
    environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    environment.update(GOENV="off", GOWORK="off", GOTOOLCHAIN="local")
    if subprocess.check_output(["go", "env", "GOVERSION"], text=True, env=environment).strip() != "go" + pins["go_version"]:
        raise ValueError("build requires the exact pinned Go compiler")
    if not output.is_absolute() or output.exists():
        raise ValueError("output must be a new absolute directory")
    output.mkdir(mode=0o700)
    work = output / "work"
    work.mkdir(mode=0o700)
    temporary = work / "tmp"
    temporary.mkdir(mode=0o700)
    home = work / "home"
    home.mkdir(mode=0o700)
    cache = output.parent / "security-runtime-go-cache"
    cache.mkdir(mode=0o700, exist_ok=True)
    environment.update(
        HOME=str(home),
        CGO_ENABLED="0", GOOS="linux", GOTOOLCHAIN="local", GOMAXPROCS="2",
        GOENV="off", GOWORK="off",
        GOFLAGS="-mod=readonly -p=2", GOPROXY="https://proxy.golang.org,direct",
        GOSUMDB="sum.golang.org", GOPATH=str(cache / "gopath"),
        GOCACHE=str(cache / "go-cache"), TMPDIR=str(temporary),
        SOURCE_DATE_EPOCH=str(pins["source_date_epoch"]),
    )
    artifacts = {}
    for name in ("hysteria", "rclone"):
        component = pins[name]
        archive = work / (name + ".tar.gz")
        download_source(component, archive)
        source = work / name
        source.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        roots = list(source.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise ValueError("unexpected source archive root")
        source = roots[0]
        for arch in ("amd64", "arm64"):
            executable = output / (name + "-linux-" + arch)
            flags = "-s -w -buildid="
            if name == "hysteria":
                package = "github.com/apernet/hysteria/app/v2/cmd."
                values = dict(appVersion=component["version"], appCommit=component["commit"],
                              appDate="2026-11-02T00:00:00Z", appType="release",
                              appToolchain="go" + pins["go_version"],
                              appPlatform="linux", appArch=arch)
                flags += " " + " ".join("-X " + package + key + "=" + value for key, value in values.items())
                cwd = source / "app"
            else:
                flags += " -X github.com/rclone/rclone/fs.Version=" + component["version"]
                cwd = source
            subprocess.run(["go", "build", "-trimpath", "-buildvcs=false", "-ldflags", flags,
                            "-o", str(executable), "."], cwd=cwd,
                           env={**environment, "GOARCH": arch}, check=True)
            info = subprocess.check_output(["go", "version", "-m", str(executable)], text=True)
            if "go" + pins["go_version"] not in info or "GOARCH=" + arch not in info or "CGO_ENABLED=0" not in info:
                raise ValueError("binary compiler or target mismatch")
            native = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
            if arch == native:
                version = subprocess.check_output([str(executable), "version"], text=True)
                if component["version"] not in version or "go" + pins["go_version"] not in version:
                    raise ValueError("native executable version mismatch")
            artifacts[executable.name] = hashlib.sha256(executable.read_bytes()).hexdigest()
            if name == "rclone":
                package_root = work / ("rclone-deb-" + arch)
                (package_root / "DEBIAN").mkdir(parents=True)
                (package_root / "usr/bin").mkdir(parents=True)
                shutil.copyfile(executable, package_root / "usr/bin/rclone")
                (package_root / "usr/bin/rclone").chmod(0o755)
                control = ("Package: rclone\nVersion: " + component["package_version"]
                           + "\nArchitecture: " + arch
                           + "\nMaintainer: ripdpi-vpn-deploy maintainers <noreply@github.com>"
                           + "\nDepends: ca-certificates\nSection: net\nPriority: optional"
                           + "\nDescription: Stable rclone rebuilt with the patched Go compiler\n")
                (package_root / "DEBIAN/control").write_text(control)
                license_dir = package_root / "usr/share/doc/rclone"
                license_dir.mkdir(parents=True)
                shutil.copyfile(source / "COPYING", license_dir / "copyright")
                for path in sorted(package_root.rglob("*"), reverse=True):
                    os.utime(path, (pins["source_date_epoch"], pins["source_date_epoch"]))
                deb = output / ("rclone-" + component["package_version"] + "-linux-" + arch + ".deb")
                subprocess.run(["dpkg-deb", "--build", "--root-owner-group", "--threads-max=1", "-Zxz", "-z9",
                                str(package_root), str(deb)], env=environment, check=True)
                fields = subprocess.check_output(["dpkg-deb", "--field", str(deb), "Package", "Version", "Architecture"], text=True)
                if fields.splitlines() != ["Package: rclone", "Version: " + component["package_version"], "Architecture: " + arch]:
                    raise ValueError("built package identity mismatch")
                artifacts[deb.name] = hashlib.sha256(deb.read_bytes()).hexdigest()
        license_name = "LICENSE.md" if name == "hysteria" else "COPYING"
        shutil.copyfile(source / license_name, output / (name + "-LICENSE"))
    receipt = dict(sources=pins, artifacts=artifacts, native_architecture=native,
                   compiler_and_native_versions_verified=True)
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (output / "SHA256SUMS").write_text("".join(value + "  " + key + "\n" for key, value in sorted(artifacts.items())))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o022)
    result = build(args.output)
    print(json.dumps({"artifacts": result["artifacts"], "native_versions_verified": True}))


if __name__ == "__main__":
    main()
