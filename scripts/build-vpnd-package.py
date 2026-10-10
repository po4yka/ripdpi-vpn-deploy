#!/usr/bin/env python3
"""Build deterministic vpnd artifacts from explicit source and locked dependencies."""

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(argv, **kwargs):
    subprocess.run(argv, check=True, **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_source(destination):
    project = ROOT / "vpnd"
    shutil.copy2(project / "pyproject.toml", destination / "pyproject.toml")
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")
    reviewed = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z", "vpnd/src/vpnd"]
    )
    sources = [Path(os.fsdecode(item)) for item in reviewed.split(b"\0") if item]
    if not sources or not any(path.name == "__main__.py" for path in sources):
        raise ValueError("stage reviewed Python source before packaging")
    for relative in sources:
        source = ROOT / relative
        if source.resolve() != source or not source.is_file() or source.suffix != ".py":
            raise ValueError("unapproved source input")
        target = destination / relative.relative_to("vpnd")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
    data = destination / "src/vpnd/data"
    data.mkdir()
    sys.path.insert(0, str(project / "src"))
    from vpnd.commands.completions import write_man_pages

    names = ("VPN_ENV", "VPN_PROVIDER", "VPN_DEPLOY_ROOT")
    previous = {name: os.environ.pop(name, None) for name in names}
    try:
        write_man_pages(data / "man")
    finally:
        for name, value in previous.items():
            if value is not None:
                os.environ[name] = value
    shutil.copy2(project / "templates/recipient.html", data / "recipient.html")
    # Git's reviewed file list excludes ignored operator content and local caches.
    files = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z", "docs"],
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    for item in files.split(b"\0"):
        if not item:
            continue
        relative = Path(os.fsdecode(item))
        source = ROOT / relative
        if source.is_symlink():
            continue
        if source.suffix != ".md":
            continue
        target = data / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def normalize_wheel(source):
    contents = {}
    with zipfile.ZipFile(source) as wheel:
        for item in wheel.infolist():
            contents[item.filename] = (item.external_attr, wheel.read(item))
    temporary = source.with_suffix(".tmp")
    with zipfile.ZipFile(
        temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as wheel:
        for name, (mode, data) in sorted(contents.items()):
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.external_attr = mode
            item.compress_type = zipfile.ZIP_DEFLATED
            wheel.writestr(item, data)
    os.replace(temporary, source)


def normalize_tar(source):
    with tarfile.open(source, "r:gz") as archive:
        members = [
            (item.name, item.mode, archive.extractfile(item).read())
            for item in archive
            if item.isfile()
        ]
    source.write_bytes(tar_bytes(members))


def tar_bytes(members):
    buffer = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, filename="") as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, mode, content in sorted(members):
            info = tarfile.TarInfo(name)
            info.mode = mode
            info.mtime = 0
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def build(output, bundle_target=None):
    if bundle_target:
        import platform

        targets = {
            ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
            ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
            ("Darwin", "x86_64"): "x86_64-apple-darwin",
            ("Darwin", "arm64"): "aarch64-apple-darwin",
        }
        if targets.get((platform.system(), platform.machine())) != bundle_target:
            raise ValueError("bundle target does not match the native wheel platform")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vpnd-build-") as scratch:
        stage = stage_source(Path(scratch))
        run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(output),
                str(stage),
            ],
            env={**os.environ, "SOURCE_DATE_EPOCH": "0", "PYTHONHASHSEED": "0"},
        )
    wheels = sorted(output.glob("vpnd-*.whl"))
    sources = sorted(output.glob("vpnd-*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError(
            "output must contain exactly one application wheel and source archive"
        )
    normalize_wheel(wheels[0])
    normalize_tar(sources[0])
    if bundle_target:
        with tempfile.TemporaryDirectory(prefix="vpnd-wheelhouse-") as scratch:
            wheelhouse = Path(scratch)
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "--no-deps",
                    "-r",
                    str(ROOT / "vpnd/requirements.txt"),
                    "-d",
                    str(wheelhouse),
                ]
            )
            shutil.copy2(wheels[0], wheelhouse / wheels[0].name)
            shutil.copy2(
                ROOT / "vpnd/requirements.txt", wheelhouse / "requirements.txt"
            )
            shutil.copy2(ROOT / "scripts/install-vpnd.py", wheelhouse / "install.py")
            manifest = {
                "version": tomllib.loads((ROOT / "vpnd/pyproject.toml").read_text())[
                    "project"
                ]["version"],
                "target": bundle_target,
                "files": {
                    path.name: digest(path) for path in sorted(wheelhouse.iterdir())
                },
            }
            (wheelhouse / "MANIFEST.json").write_text(
                json.dumps(manifest, sort_keys=True) + "\n"
            )
            artifact = output / ("vpnd-" + bundle_target + ".tar.gz")
            artifact.write_bytes(
                tar_bytes(
                    [
                        (path.name, 0o644, path.read_bytes())
                        for path in wheelhouse.iterdir()
                    ]
                )
            )
    return wheels[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "vpnd/dist")
    parser.add_argument(
        "--bundle-target",
        choices=[
            "x86_64-unknown-linux-gnu",
            "aarch64-unknown-linux-gnu",
            "x86_64-apple-darwin",
            "aarch64-apple-darwin",
        ],
    )
    args = parser.parse_args()
    build(args.output, args.bundle_target)


if __name__ == "__main__":
    main()
