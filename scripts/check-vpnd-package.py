#!/usr/bin/env python3
"""Verify reproducible artifacts and real isolated offline vpnd installation."""

import argparse
import hashlib
import importlib.util
import platform
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_installed_parser(command, environment, directory):
    sys.path.insert(0, str(ROOT / "vpnd/src"))
    from vpnd.cli import build_parser

    def visit(parser, arguments):
        result = subprocess.run(
            [str(command), *arguments, "--help"],
            check=True, cwd=directory, env=environment,
            capture_output=True, text=True,
        )
        if result.stdout != parser.format_help():
            raise ValueError("installed parser help differs: " + " ".join(arguments))
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    visit(child, [*arguments, name])

    visit(build_parser(), [])
    for arguments in (
        ["--json", "host", "list"],
        ["host", "list", "--json", "--json"],
        ["doctor", "--json"], ["doctor", "--clip"],
        ["deploy", "--json"], ["update", "--json"],
        ["--explain", "--explain", "deploy"],
        ["--env", "one", "--env", "two", "--explain", "deploy"],
    ):
        result = subprocess.run(
            [str(command), *arguments], cwd=directory, env=environment,
            capture_output=True, check=False,
        )
        if result.returncode != 2:
            raise ValueError("installed parser accepted an invalid baseline scope")


def verify(release_tag=None):
    project = tomllib.loads((ROOT / "vpnd/pyproject.toml").read_text())["project"]
    if sys.version_info[:2] != (3, 12):
        raise ValueError("package gate requires the supported Python 3.12 runtime")
    if release_tag is not None and release_tag != "vpnd-v" + project["version"]:
        raise ValueError("release tag and package version differ")
    spec = importlib.util.spec_from_file_location(
        "vpnd_package_builder", ROOT / "scripts/build-vpnd-package.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    target = {
        ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
        ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
        ("Darwin", "x86_64"): "x86_64-apple-darwin",
        ("Darwin", "arm64"): "aarch64-apple-darwin",
    }[(platform.system(), platform.machine())]
    installer_spec = importlib.util.spec_from_file_location(
        "vpnd_package_installer", ROOT / "scripts/install-vpnd.py"
    )
    installer = importlib.util.module_from_spec(installer_spec)
    installer_spec.loader.exec_module(installer)
    environment = installer.installation_environment()
    with tempfile.TemporaryDirectory(prefix="vpnd-package-check-") as scratch:
        temporary = Path(scratch)
        first, second = temporary / "first", temporary / "second"
        wheel = builder.build(first, target)
        builder.build(second, target)
        for path in sorted(first.glob("vpnd-*")):
            if (
                hashlib.sha256(path.read_bytes()).digest()
                != hashlib.sha256((second / path.name).read_bytes()).digest()
            ):
                raise ValueError("non-reproducible package: " + path.name)
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            if not any(
                name.startswith("vpnd/data/docs/") and name.endswith(".md")
                for name in names
            ):
                raise ValueError("missing packaged documentation")
            if "vpnd/data/recipient.html" not in names:
                raise ValueError("missing packaged recipient template")
            if any(
                ".rs" == Path(name).suffix or "secrets/local" in name for name in names
            ):
                raise ValueError("unapproved packaged input")
        artifact = first / ("vpnd-" + target + ".tar.gz")
        prefix = temporary / "prefix"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/install-vpnd.py"),
                str(artifact),
                str(prefix),
            ],
            check=True,
            cwd=temporary,
            env=environment,
        )
        command = prefix / "bin/vpnd"
        verify_installed_parser(command, environment, temporary)
        for shell in ("bash", "zsh", "fish", "powershell", "pwsh"):
            subprocess.run(
                [str(command), "completions", shell],
                check=True,
                cwd=temporary,
                env=environment,
                stdout=subprocess.DEVNULL,
            )
        subprocess.run([str(command), "--version"], check=True, cwd=temporary, env=environment)
        isolated = temporary / "checkout"
        isolated.mkdir()
        (isolated / "Makefile").write_text("")
        for directory in ("ansible", "terraform/providers/upcloud"):
            (isolated / directory).mkdir(parents=True)
        output = temporary / "docs-output"
        subprocess.run(
            [str(command), "--root", str(isolated), "ai-docs", "--out", str(output)],
            check=True,
            cwd=temporary,
            env=environment,
        )
        if (
            not (output / "llms.txt").is_file()
            or not (output / "llms-full.txt").is_file()
        ):
            raise ValueError("installed documentation export did not work")
        previous = command.readlink()
        broken = temporary / "broken.tar.gz"
        broken.write_bytes(b"not an archive")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/install-vpnd.py"),
                str(broken),
                str(prefix),
            ],
            cwd=temporary,
            env=environment,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0 or command.readlink() != previous:
            raise ValueError("failed upgrade replaced the previous installation")
        subprocess.run([str(command), "--version"], check=True, cwd=temporary, env=environment)
    print(
        "Reproducible wheel/source, locked offline install, resources and rollback passed"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-tag")
    args = parser.parse_args()
    verify(args.release_tag)
