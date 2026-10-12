"""Private writer and effective verification admission at process boundaries."""

import fcntl
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def executable(path, body):
    path.write_text(body)
    path.chmod(0o700)


@pytest.mark.parametrize("existing_mode", [None, 0o644])
def test_rotation_lock_admits_next_private_writer_under_public_umask(tmp_path, existing_mode):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("rotate-secrets.sh", "private-operator-lock.py"):
        shutil.copy(ROOT / "scripts" / name, scripts)
    executable(scripts / "audit-log.sh", "#!/bin/sh\nexit 0\n")
    commands = tmp_path / "bin"
    commands.mkdir()
    executable(commands / "sops", "#!/bin/sh\nexit 0\n")
    source = tmp_path / "synthetic.yaml"
    source.write_text("synthetic ciphertext\n")
    source.chmod(0o600)
    lock = Path(str(source) + ".new-client.lock")
    if existing_mode is not None:
        lock.touch()
        lock.chmod(existing_mode)
    result = subprocess.run(
        ["bash", "-c", 'umask 022; exec bash "$1"', "--", str(scripts / "rotate-secrets.sh")],
        cwd=tmp_path, env={**os.environ, "SOPS_FILE": str(source), "PATH": f"{commands}:{os.environ['PATH']}"},
        text=True, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    spec = importlib.util.spec_from_file_location("private_naive_writer", ROOT / "scripts/naive-client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with lock.open("r+") as stream:
        module.private_file(stream.fileno())
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize("authority", ["symlink", "hardlink", "writable"])
def test_rotation_refuses_unsafe_lock_without_changing_target(tmp_path, authority):
    source = tmp_path / "synthetic.yaml"
    source.write_text("synthetic ciphertext\n")
    target = tmp_path / "unrelated"
    target.write_text("preserve this content\n")
    mode = 0o666 if authority == "writable" else 0o644
    target.chmod(mode)
    lock = Path(str(source) + ".new-client.lock")
    if authority == "symlink":
        lock.symlink_to(target)
    elif authority == "hardlink":
        os.link(target, lock)
    else:
        target.rename(lock)
        target = lock
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/rotate-secrets.sh")],
        env={**os.environ, "SOPS_FILE": str(source)}, text=True, capture_output=True, timeout=5,
    )
    assert result.returncode != 0
    assert target.read_text() == "preserve this content\n"
    assert stat.S_IMODE(target.stat().st_mode) == mode


@pytest.mark.parametrize("limit,accepted", [
    ("", True), ("vpn", True), ("node-a", True), ("node-b", True),
    ("observer-a", False), ("all:!vpn", False), ("missing", False),
])
def test_verification_gate_uses_actual_limited_ansible_inventory(tmp_path, limit, accepted):
    inventory = tmp_path / "ansible/inventory/generated.ini"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(
        "[vpn]\nnode-a ansible_connection=local\n"
        "[vpn-child]\nnode-b ansible_connection=local\n"
        "[vpn:children]\nvpn-child\n[observer]\nobserver-a ansible_connection=local\n"
    )
    config = tmp_path / "ansible.cfg"
    config.write_text(f"[defaults]\ninventory = {inventory}\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    environment["ANSIBLE_CONFIG"] = str(config)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/require-vpn-selection.py", scripts)
    # Exercise the actual Make admission recipe without unrelated operator inputs.
    target = (ROOT / "Makefile").read_text().split("require-inventory:", 1)[1].split("\n\n", 1)[0]
    makefile = tmp_path / "Makefile"
    makefile.write_text("ANSIBLE_DIR := ansible\nrequire-inventory:" + target + "\n")
    result = subprocess.run(
        ["make", "--no-print-directory", "require-inventory", f"ANSIBLE_LIMIT={limit}"],
        cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=20,
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


@pytest.mark.parametrize("document", ["", "not-json", "[]", '{"vpn":{"hosts":"node"}}'])
def test_verification_gate_refuses_invalid_inventory(document):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/require-vpn-selection.py")],
        input=document, text=True, capture_output=True, timeout=5,
    )
    assert result.returncode != 0
    assert result.stdout == ""
