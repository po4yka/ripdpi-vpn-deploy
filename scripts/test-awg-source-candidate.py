#!/usr/bin/env python3
"""Run exact-source AWG acceptance in a private local Docker Linux lab."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "contract/awg-source-candidate.json",
    "tests/integration/awg_source_candidate/Dockerfile",
    "tests/integration/awg_source_candidate/build.py",
    "tests/integration/awg_source_candidate/acceptance.py",
    "ansible/roles/runtime-release/files/runtime_build_receipt.py",
    "ansible/roles/amneziawg/templates/awg-quick@.service.j2",
)
WAIT_SYSTEMD = """
import socket, time
deadline = time.monotonic() + 30
while True:
    with socket.socket(socket.AF_UNIX) as bus:
        bus.settimeout(1)
        try:
            bus.connect('/run/systemd/private')
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if time.monotonic() >= deadline:
                raise SystemExit('systemd private bus did not become ready')
            time.sleep(0.05)
"""


def run(*args, timeout=3600, **kwargs):
    return subprocess.run(args, check=True, timeout=timeout, **kwargs)


def prepare_sources(work):
    """Transfer only public Git objects, never the workstation's SSH authority."""
    pins = json.loads((ROOT / FILES[0]).read_text())
    cache = ROOT / ".cache/awg-source-candidate"
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = cache.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
    ):
        raise RuntimeError("source bundle cache has unsafe ownership")
    bundles = work / "sources"
    bundles.mkdir(mode=0o700)
    for pair in ("baseline", "candidate"):
        for component in ("go", "tools"):
            source = pins[pair][component]
            cached = cache / f"{component}-{source['commit']}.bundle"
            if not cached.exists():
                with tempfile.TemporaryDirectory(
                    dir=cache, prefix="checkout-"
                ) as temporary:
                    checkout = Path(temporary) / "source.git"
                    run(
                        "git",
                        "clone",
                        "--bare",
                        "--single-branch",
                        "--branch",
                        source["tag"],
                        f"git@github.com:amnezia-vpn/amneziawg-{component}",
                        str(checkout),
                        env={
                            **os.environ,
                            "GIT_SSH_COMMAND": "ssh -oHostName=github.com -p22 -oBatchMode=yes -oConnectTimeout=20 -oStrictHostKeyChecking=yes -oForwardAgent=no",
                        },
                        timeout=300,
                    )
                    actual = subprocess.check_output(
                        [
                            "git",
                            "-C",
                            str(checkout),
                            "rev-parse",
                            source["tag"] + "^{commit}",
                        ],
                        text=True,
                        timeout=30,
                    ).strip()
                    if actual != source["commit"]:
                        raise RuntimeError(
                            "upstream tag moved from its reviewed commit"
                        )
                    staged = Path(temporary) / "source.bundle"
                    run(
                        "git",
                        "-C",
                        str(checkout),
                        "bundle",
                        "create",
                        str(staged),
                        "--all",
                        timeout=300,
                    )
                    try:
                        os.link(staged, cached)
                    except FileExistsError:
                        pass  # Another owned invocation completed this immutable cache entry.
            info = cached.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or info.st_mode & 0o022
            ):
                raise RuntimeError("source bundle cache has unsafe ownership")
            shutil.copyfile(cached, bundles / f"{pair}-{component}.bundle")


def main():
    if os.environ.get("BUILD_GATE_HELD") != "1":
        raise SystemExit("Run through build-gate -- make test-awg-source-candidate")
    # A Docker context may point at a remote daemon; this target is local-only.
    context = json.loads(
        subprocess.check_output(["docker", "context", "inspect"], text=True, timeout=30)
    )[0]
    endpoint = context["Endpoints"]["docker"]["Host"]
    if (
        not endpoint.startswith("unix://")
        or os.environ.get("DOCKER_HOST", endpoint) != endpoint
    ):
        raise SystemExit(
            "AWG candidate acceptance requires a local Unix-socket Docker context"
        )
    name = context["Name"]
    inspection = subprocess.check_output(
        ["docker", "buildx", "inspect", name], text=True, timeout=30
    )
    fields = {
        key.strip(): value.strip()
        for line in inspection.splitlines()
        if ":" in line
        for key, value in [line.split(":", 1)]
        if key.strip() in {"Driver", "Endpoint"}
    }
    if fields != {"Driver": "docker", "Endpoint": name}:
        raise SystemExit(
            "AWG candidate builds require the admitted local Docker engine builder"
        )
    docker = ("docker", "--context", name)
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="awg-source-candidate-") as temporary:
        work = Path(temporary)
        for relative in FILES:
            source = ROOT / relative
            digest.update(relative.encode() + b"\0" + source.read_bytes())
            destination = work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        prepare_sources(work)
        for bundle in sorted((work / "sources").glob("*.bundle")):
            digest.update(bundle.name.encode() + b"\0")
            with bundle.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        image = "ripdpi-awg-source-candidate:" + digest.hexdigest()[:16]
        run(
            *docker,
            "build",
            "--builder",
            name,
            "-t",
            image,
            "-f",
            str(work / FILES[1]),
            str(work),
        )
    # Retain an owned identity even if startup times out before returning its ID.
    container = "ripdpi-awg-source-" + uuid.uuid4().hex
    try:
        allocated = subprocess.check_output(
            [
                *docker,
                "run",
                "-d",
                "--name",
                container,
                "--privileged",
                "--cgroupns=host",
                "--network=none",
                "--tmpfs",
                "/run",
                "--tmpfs",
                "/tmp",
                "--volume",
                "/sys/fs/cgroup:/sys/fs/cgroup:rw",
                image,
            ],
            text=True,
            timeout=60,
        ).strip()
        if not allocated:
            raise RuntimeError("Docker startup returned no owned container identity")
        container = allocated
        # systemctl --wait handles boot states only after its bus is listening.
        run(*docker, "exec", container, "python3", "-c", WAIT_SYSTEMD, timeout=45)
        run(
            *docker,
            "exec",
            container,
            "systemctl",
            "is-system-running",
            "--wait",
            timeout=60,
        )
        run(*docker, "exec", container, "python3", "-u", "/lab/acceptance.py")
    finally:
        run(*docker, "rm", "-f", container, timeout=60)


if __name__ == "__main__":
    main()
