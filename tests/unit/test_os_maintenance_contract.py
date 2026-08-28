"""Contracts for recurring and rolling operating-system maintenance."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_maintenance_tasks(
    root: Path, names: list[str], *, enabled: bool = False, failed_service: str = "", backlog: int = 0
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    """Run source tasks locally, replacing only their OS command boundaries."""
    root.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    calls_path = root / "calls.jsonl"
    executable = f"#!{sys.executable}\n" + '''
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["MAINTENANCE_CALLS"], "a") as output:
    output.write(json.dumps({"command": name, "args": args, "locale": os.environ.get("LC_ALL")}) + "\\n")
if name == "systemctl":
    assert len(args) == 2 and args[0] == "is-active", args
    failed = args[1] in ("tailscaled", os.environ["MAINTENANCE_FAILED_SERVICE"])
    print("inactive" if failed else "active")
    sys.exit(3 if failed else 0)
assert name == "apt-get" and args == ["-s", "-o", "Debug::NoLocking=true", "dist-upgrade"], args
if os.environ.get("LC_ALL") == "C":
    print(os.environ["MAINTENANCE_BACKLOG"] + " upgraded, 0 newly installed, 0 to remove")
else:
    print("Aucun paquet a mettre a jour, aucun a installer, aucun a supprimer")
'''
    for name in ("systemctl", "apt-get"):
        command = bin_dir / name
        command.write_text(executable)
        command.chmod(0o700)
    tasks = yaml.safe_load((REPO_ROOT / "ansible/playbooks/os-maintenance.yml").read_text())[0]["tasks"]
    selected = [task for task in tasks if task["name"] in names]
    assert [task["name"] for task in selected] == names
    play = [{
        "hosts": "localhost", "gather_facts": False, "become": False,
        "vars": {"ansible_python_interpreter": sys.executable, "vpn": {
            "enable_xray_reality": enabled, "enable_nginx_xhttp": enabled,
            "enable_hysteria": enabled, "enable_amneziawg": False,
        }},
        "environment": {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "LC_ALL": "fr_FR.UTF-8", "MAINTENANCE_CALLS": str(calls_path),
            "MAINTENANCE_FAILED_SERVICE": failed_service, "MAINTENANCE_BACKLOG": str(backlog),
        },
        "tasks": selected,
    }]
    play_path = root / "play.yml"
    play_path.write_text(yaml.safe_dump(play))
    config = root / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    env.update({"ANSIBLE_CONFIG": str(config), "ANSIBLE_HOME": str(root / "ansible-home"),
                "ANSIBLE_BECOME": "false", "ANSIBLE_DEBUG": "false"})
    ansible = shutil.which("ansible-playbook")
    assert ansible, "The real ansible-playbook test prerequisite is required"
    result = subprocess.run(
        [ansible, "-i", "localhost,", "-c", "local", str(play_path)],
        cwd=root, env=env, capture_output=True, text=True, timeout=45, check=False,
    )
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
    return result, calls


def test_maintenance_checks_only_repo_managed_services(tmp_path: Path) -> None:
    for enabled in (False, True):
        result, calls = _run_maintenance_tasks(
            tmp_path / str(enabled), ["Verify enabled transport services after maintenance"], enabled=enabled,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        expected = ["nftables", "prometheus-node-exporter"]
        if enabled:
            expected += ["xray", "nginx", "hysteria-server"]
        assert [call["args"] for call in calls] == [["is-active", name] for name in expected]
        assert all(call["command"] == "systemctl" for call in calls)


def test_maintenance_rejects_inactive_managed_services(tmp_path: Path) -> None:
    for failed_service in ("nftables", "xray"):
        result, calls = _run_maintenance_tasks(
            tmp_path / failed_service, ["Verify enabled transport services after maintenance"],
            enabled=True, failed_service=failed_service,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert ["is-active", failed_service] in [call["args"] for call in calls]
        assert f"(item={failed_service})" in result.stdout
        assert '"rc": 3' in result.stdout


def test_maintenance_localized_zero_backlog_passes(tmp_path: Path) -> None:
    result, calls = _run_maintenance_tasks(
        tmp_path / "zero", ["Simulate another full upgrade", "Reject a residual package backlog"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [{"command": "apt-get", "args": ["-s", "-o", "Debug::NoLocking=true", "dist-upgrade"], "locale": "C"}]


def test_maintenance_localized_residual_backlog_fails(tmp_path: Path) -> None:
    result, calls = _run_maintenance_tasks(
        tmp_path / "residual", ["Simulate another full upgrade", "Reject a residual package backlog"], backlog=1,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "OS package backlog remains after rolling maintenance." in result.stdout
    assert calls == [{"command": "apt-get", "args": ["-s", "-o", "Debug::NoLocking=true", "dist-upgrade"], "locale": "C"}]


def test_vpn_fleet_enables_unattended_security_updates() -> None:
    group_vars = yaml.safe_load((REPO_ROOT / "ansible/group_vars/all.yml").read_text())

    assert group_vars["security_controls"]["unattended_upgrades"] is True
    # The reboot switch lives under package_updates; the security_controls
    # duplicate was a silent no-op and was removed.
    assert group_vars["package_updates"]["automatic_reboot"] is False
    assert group_vars["package_updates"]["security_only"] is True


def test_os_maintenance_is_rolling_and_closes_the_backlog() -> None:
    source = (REPO_ROOT / "ansible/playbooks/os-maintenance.yml").read_text()
    playbook = yaml.safe_load(source)
    play = playbook[0]
    tasks = play["tasks"]
    task_names = {task["name"]: task for task in tasks}

    assert play["hosts"] == "vpn"
    assert play["serial"] == 1
    assert play["any_errors_fatal"] is True
    assert task_names["Apply all pending OS package upgrades"]["ansible.builtin.apt"]["upgrade"] == "dist"
    assert task_names["Reboot after kernel or core-library updates"]["ansible.builtin.reboot"]
    assert task_names["Reject a residual package backlog"]["ansible.builtin.assert"]
    assert task_names["Reject a residual reboot requirement"]["ansible.builtin.assert"]
    assert task_names["Verify enabled transport services after maintenance"]["ansible.builtin.command"]
    assert "prometheus-node-exporter" in source
    assert "'node_exporter'" not in source
    assert "ansible_os_family" not in source


def test_make_exposes_verified_os_maintenance_target() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()

    assert "os-maintenance: require-clean-source require-inventory" in makefile
    assert "playbooks/os-maintenance.yml" in makefile
    assert "$(MAKE) verify" in makefile
    assert "$(MAKE) security-verify" in makefile
