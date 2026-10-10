"""Actual Unbound retirement compensation for explicit include and failed restart."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize(
    "failure", ["explicit-include", "restart", "unsafe-mode", "symlink-parent"]
)
def test_failed_fragment_retirement_restores_bytes_metadata_and_running_service(
    tmp_path, failure
):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires owned root Linux systemd fixture host")
    if (
        not all(
            shutil.which(tool)
            for tool in ("unbound", "unbound-checkconf", "ansible-playbook")
        )
        or not Path("/run/systemd/system").exists()
    ):
        pytest.skip("requires actual Unbound and systemd")
    name = "p2-dns-retire-" + uuid.uuid4().hex[:7]
    directory = Path("/etc/unbound") / name
    directory.mkdir(mode=0o755)
    fragment_parent = directory / "owned"
    if failure == "symlink-parent":
        target = directory / "real-owned"
        target.mkdir()
        fragment_parent.symlink_to(target, target_is_directory=True)
    else:
        fragment_parent.mkdir()
    fragment = fragment_parent / "fragment.conf"
    shared = directory / "unbound.conf"
    marker = directory / "fail-once"
    unit = name + ".service"
    unit_path = Path("/etc/systemd/system") / unit
    original = 'server:\n    local-zone: "p2-test.invalid." static\n    local-data: "answer.p2-test.invalid. 60 IN A 192.0.2.123"\n'
    fragment.write_text(original)
    fragment.chmod(0o666 if failure == "unsafe-mode" else 0o640)
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    include = (
        str(fragment)
        if failure == "explicit-include"
        else str(fragment_parent / "fragment*.conf")
    )
    shared.write_text(
        f'include: "{include}"\nserver:\n    interface: 127.0.0.1@{port}\n    username: ""\n    chroot: ""\n    pidfile: ""\n    use-syslog: no\n'
    )
    unit_path.write_text(
        f'[Unit]\nDescription=Owned Unbound retirement fixture\n[Service]\nExecStartPre=/bin/sh -c "if test -e {marker}; then rm {marker}; exit 1; fi"\nExecStart=/usr/sbin/unbound -d -c {shared}\n'
    )

    def command(*argv, check=True):
        result = subprocess.run(argv, text=True, capture_output=True, timeout=10)
        if check:
            assert result.returncode == 0, result.stderr
        return result

    def replace(value):
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, str):
            return (
                value.replace(
                    "/etc/unbound/unbound.conf.d/dns-morph-bridge-fwd.conf",
                    str(fragment),
                )
                .replace("/etc/unbound/unbound.conf", str(shared))
                .replace("unbound.service", unit)
            )
        return value

    try:
        command("unbound-checkconf", str(shared))
        command("systemctl", "daemon-reload")
        command("systemctl", "start", unit)
        if failure == "restart":
            marker.touch()
        tasks = yaml.safe_load(
            (ROOT / "ansible/roles/dns-morph-bridge/tasks/disable.yml").read_text()
        )
        tasks = replace(
            [task for task in tasks if "ansible.builtin.include_role" not in task]
        )
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "ansible_become": False,
                    "ansible_python_interpreter": sys.executable,
                    "role_path": str(ROOT / "ansible/roles/dns-morph-bridge"),
                },
                "tasks": tasks,
            }
        ]
        path = tmp_path / "retire.yml"
        path.write_text(yaml.safe_dump(play, sort_keys=False))
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", str(path)],
            text=True,
            capture_output=True,
            timeout=30,
            env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
        )
        assert result.returncode != 0, result.stdout + result.stderr
        if failure in {"unsafe-mode", "symlink-parent"}:
            assert "Validate fragment and ancestor authority" in result.stdout
            assert "Capture prior owned Unbound fragment" not in result.stdout
        else:
            assert "prior shared Unbound authority was restored" in result.stdout
        assert fragment.read_text() == original
        assert (
            fragment.stat().st_mode & 0o777
            == (0o666 if failure == "unsafe-mode" else 0o640)
            and fragment.stat().st_uid == 0
            and fragment.stat().st_gid == 0
        )
        command("unbound-checkconf", str(shared))
        command("systemctl", "is-active", "--quiet", unit)
        assert shared.read_text().startswith(
            f'include: "{include}"'
        ), "global input must remain unchanged"
    finally:
        command("systemctl", "stop", unit, check=False)
        unit_path.unlink(missing_ok=True)
        command("systemctl", "daemon-reload", check=False)
        shutil.rmtree(directory)
