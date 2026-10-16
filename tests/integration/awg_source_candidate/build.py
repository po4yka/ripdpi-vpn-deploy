"""Build both exact upstream pairs with a checksum-pinned, bounded toolchain."""

import hashlib
import json
import os
import platform
import subprocess
import urllib.request
from pathlib import Path


def run(*argv, **kwargs):
    subprocess.run(argv, check=True, timeout=1800, **kwargs)


def verify_digest(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("toolchain checksum mismatch")


def verify_source(directory, expected):
    actual = subprocess.check_output(
        ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True, timeout=30
    ).strip()
    if actual != expected:
        raise ValueError("moved upstream tag")
    run("git", "diff", "--exit-code", cwd=directory)
    run("git", "diff", "--cached", "--exit-code", cwd=directory)


def main():
    pins = json.loads(Path("/lab/sources.json").read_text())
    arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
    archive = Path("/lab/go.tar.gz")
    with urllib.request.urlopen(
        f"https://go.dev/dl/go{pins['go_toolchain']}.linux-{arch}.tar.gz", timeout=120
    ) as response:
        archive.write_bytes(response.read())
    verify_digest(archive, pins["go_toolchain_sha256"][arch])
    run("tar", "-C", "/usr/local", "-xzf", str(archive))
    archive.unlink()
    env = {
        **os.environ,
        "PATH": "/usr/local/go/bin:" + os.environ["PATH"],
        "GOTOOLCHAIN": "local",
        "GOPROXY": pins["go_module_proxy"],
        "GOWORK": "off",
        "GOMAXPROCS": "2",
        "CGO_ENABLED": "0",
        "GOFLAGS": "-mod=readonly -p=2",
    }
    for pair in ("baseline", "candidate"):
        for component in ("go", "tools"):
            source = pins[pair][component]
            directory = Path("/opt") / pair / component
            run(
                "git",
                "clone",
                "--branch",
                source["tag"],
                f"/sources/{pair}-{component}.bundle",
                str(directory),
            )
            verify_source(directory, source["commit"])
            run(
                "make",
                "-j2",
                cwd=directory if component == "go" else directory / "src",
                env=env,
            )
            run("git", "diff", "--exit-code", cwd=directory)
            run("git", "diff", "--cached", "--exit-code", cwd=directory)
    run("/usr/local/go/bin/go", "version")


if __name__ == "__main__":
    main()
