"""Local synthetic command fixtures; never access operator state or providers."""

import os
from pathlib import Path
import subprocess
import sys
from vpnd.config import Context

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "vpnd/src"
SAMPLE = (REPO / "tests/fixtures/secrets-sample.yml").read_text()


def private(path, content):
    path.write_text(content)
    path.chmod(0o600)
    return path


def scaffold(root):
    for name in ["ansible/inventory", "terraform/providers/upcloud", "runtime", "bin"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "Makefile").touch()
    return root


def context(root, explain=False):
    return Context(
        root,
        root / "ansible",
        root / "terraform/providers/upcloud",
        "test",
        "upcloud",
        root / "encrypted",
        root / "runtime/vpn-test.secrets.yaml",
        root / "config",
        explain,
        True,
    )


def environment(root, **extra):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ["MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "MAKEFILES"]
    }
    env.update(
        HOME=str(root / "home"),
        XDG_CONFIG_HOME=str(root / "home/.config"),
        XDG_RUNTIME_DIR=str(root / "runtime"),
        VPN_ENV="test",
        VPN_PROVIDER="upcloud",
        PYTHONPATH=str(SOURCE),
        PATH=str(root / "bin") + os.pathsep + env["PATH"],
    )
    env.update(extra)
    return env


def command(root, *args):
    return [
        sys.executable,
        "-m",
        "vpnd",
        "--root",
        str(root),
        "--env",
        "test",
        "--provider",
        "upcloud",
        *map(str, args),
    ]


def cli(root, *args, input=None, **extra):
    return subprocess.run(
        command(root, *args),
        env=environment(root, **extra),
        input=input,
        text=True,
        capture_output=True,
        timeout=12,
    )


def executable(root, name, text):
    path = root / "bin" / name
    path.write_text(text)
    path.chmod(0o700)
    return path
