"""XHTTP-only profile must still run a valid localhost Xray backend."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "xray" / "templates" / "config.json.j2"
SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "site.yml"
ROTATION_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rotate-credentials.yml"
VERIFY_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "verify.yml"
NGINX_XHTTP_TASKS = REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "tasks" / "main.yml"
ROLLBACK_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rollback-xray.yml"

spec = importlib.util.spec_from_file_location("xhttp_only_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_p1_web_renders_only_the_local_xhttp_inbound() -> None:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load((REPO_ROOT / "ansible" / "group_vars" / "vpn-p1-web.yml").read_text())
    variables.update(profile)
    config = json.loads(renderer.render_template(TEMPLATE, variables))

    assert [inbound["tag"] for inbound in config["inbounds"]] == ["vless-xhttp-localhost"]
    assert config["inbounds"][0]["listen"] == "127.0.0.1"
    assert config["inbounds"][0]["streamSettings"]["network"] == "xhttp"


def test_site_playbook_runs_xray_for_reality_or_xhttp() -> None:
    playbook = SITE_PLAYBOOK.read_text()
    xray_role = playbook.split("- role: xray", 1)[1].split("- role: nginx-xhttp", 1)[0]
    assert "enable_xray_reality" in xray_role
    assert "enable_nginx_xhttp" in xray_role
    assert ") or\n" in xray_role


def test_rotation_playbook_updates_xhttp_only_xray() -> None:
    playbook = ROTATION_PLAYBOOK.read_text()
    xray_task = playbook.split("- name: Re-render Xray config", 1)[1].split(
        "- name: Re-render Hysteria config",
        1,
    )[0]

    assert "enable_xray_reality" in xray_task
    assert "enable_nginx_xhttp" in xray_task
    assert "xray_log_path: /var/log/xray" in playbook


def test_xray_restart_chain_is_inert_in_check_mode() -> None:
    handlers = yaml.safe_load((REPO_ROOT / "ansible" / "roles" / "xray" / "handlers" / "main.yml").read_text())
    restart_chain = [task for task in handlers if task.get("listen") == "Restart xray"]
    assert len(restart_chain) == 3
    assert all(task.get("when") == "not ansible_check_mode" for task in restart_chain)


def test_p1_hostname_self_resolution_is_managed_and_verified() -> None:
    role_tasks = yaml.safe_load(NGINX_XHTTP_TASKS.read_text())
    role_by_name = {task["name"]: task for task in role_tasks}

    pin = role_by_name["Pin public hostname for node-local resolution"]
    assert pin["ansible.builtin.blockinfile"]["path"] == "/etc/hosts"
    assert "vpn_service_address" in pin["ansible.builtin.blockinfile"]["block"]
    assert "nginx_xhttp.server_name" in pin["ansible.builtin.blockinfile"]["block"]
    assert pin["ansible.builtin.blockinfile"]["unsafe_writes"] is True
    assert pin["no_log"] is True
    assert pin["diff"] is False

    role_probe = role_by_name["Verify node-local public hostname resolution"]
    assert role_probe["changed_when"] is False
    assert role_probe["no_log"] is True

    verify_tasks = yaml.safe_load(VERIFY_PLAYBOOK.read_text())[0]["tasks"]
    verify_by_name = {task["name"]: task for task in verify_tasks}
    verify_probe = verify_by_name["P1 public hostname resolves to its service address"]
    assert verify_probe["changed_when"] is False
    assert verify_probe["no_log"] is True
    assert "vpn.enable_nginx_xhttp | default(true)" in verify_probe["when"]

    ipv6_probe = verify_by_name["P1 public hostname exposes its IPv6 service address"]
    assert ipv6_probe["changed_when"] is False
    assert ipv6_probe["no_log"] is True
    assert "vpn.enable_nginx_xhttp | default(true)" in ipv6_probe["when"]
    assert "server_ipv6" in ipv6_probe["failed_when"]


def _run_xray_tasks(tmp_path: Path, play: dict, *, check: bool = False) -> subprocess.CompletedProcess:
    """Execute source tasks locally; only paths and service effects are sandboxed."""
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for restore-point regressions"
    play.update(hosts="localhost", become=False, gather_facts=False)
    play.setdefault("vars", {})["ansible_python_interpreter"] = sys.executable
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump([play], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
    env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"))
    return subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(path), *(["--check"] if check else [])],
        env=env, capture_output=True, text=True, timeout=45,
    )


@pytest.mark.parametrize("scenario", [
    "reject-config", "same-version", "traversal", "valid", "check-reject",
    "non-executable", "symlink-binary",
])
def test_rollback_validates_before_runtime_change(tmp_path: Path, scenario: str) -> None:
    play = yaml.safe_load(ROLLBACK_PLAYBOOK.read_text())[0]
    runtime = tmp_path / "runtime"
    current_release = runtime / "releases" / "v1.0.0"
    candidate = runtime / "releases" / "v0.9.0"
    current_release.mkdir(parents=True)
    candidate.mkdir()
    (runtime / "v0.9.0").symlink_to(candidate)
    trace = tmp_path / "validated"
    rejects = scenario in {"reject-config", "check-reject"}
    for directory, code in ((current_release, 0), (candidate, 1 if rejects else 0)):
        binary = directory / "xray"
        binary.write_text(f"#!/bin/sh\nprintf checked > '{trace}'\nexit {code}\n")
        binary.chmod(0o755)
    if scenario == "non-executable":
        (candidate / "xray").chmod(0o644)
    if scenario == "symlink-binary":
        (candidate / "xray").unlink()
        (candidate / "xray").symlink_to(current_release / "xray")
    link = runtime / "current"
    link.symlink_to(current_release)
    restart = tmp_path / "restarted"
    version = {"same-version": "v1.0.0", "traversal": "../v0.9.0"}.get(scenario, "v0.9.0")
    play["vars"]["rollback_xray_version"] = version
    for task in play["tasks"]:
        if "ansible.builtin.systemd_service" in task:
            task.pop("ansible.builtin.systemd_service")
            task["ansible.builtin.copy"] = {"content": "restarted", "dest": str(restart)}
        if task["name"] == "Verify Xray active after rollback":
            task["ansible.builtin.command"] = {"cmd": "/bin/echo active"}
    # Keep the actual assertions, command ordering and link operation unchanged.
    source = yaml.safe_dump(play).replace("/usr/local/bin/xray", str(runtime / "current" / "xray"))
    play = yaml.safe_load(source.replace("/opt/xray", str(runtime)).replace("/etc/xray", str(tmp_path)))
    result = _run_xray_tasks(tmp_path, play, check=scenario == "check-reject")
    if scenario == "valid":
        assert result.returncode == 0, result.stdout + result.stderr
        assert link.resolve() == candidate
        assert trace.exists() and restart.exists()
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert link.resolve() == current_release
        assert not restart.exists()
        assert trace.exists() == rejects


@pytest.mark.parametrize("scenario", ["changed", "unchanged", "first-config", "check", "disabled", "xhttp-only"])
def test_rotation_preserves_immediate_restore_point(tmp_path: Path, scenario: str) -> None:
    source = yaml.safe_load(ROTATION_PLAYBOOK.read_text())[0]
    tasks = [task for task in source["tasks"] if "Xray" in task["name"]]
    current = tmp_path / "config.json"
    previous = tmp_path / "config.json.prev"
    old_bytes = '{"credential":"outgoing"}\n'
    if scenario != "first-config":
        current.write_text(old_bytes)
        current.chmod(0o640)
    previous.write_text("older restore point\n")
    previous.chmod(0o640)
    desired = old_bytes if scenario == "unchanged" else '{"credential":"incoming"}\n'
    template = tmp_path / "candidate.j2"
    template.write_text(desired)
    for task in tasks:
        task.pop("notify", None)
        module = task.get("ansible.builtin.template", task.get("ansible.builtin.copy"))
        if module is not None:
            module.update(owner=str(os.getuid()), group=str(os.getgid()))
        if "ansible.builtin.template" in task:
            module["src"] = str(template)
            module["validate"] = "/bin/cat %s"
    tasks = yaml.safe_load(yaml.safe_dump(tasks).replace("/etc/xray", str(tmp_path)))
    play = {"tasks": tasks, "vars": {"vpn": {
        "enable_xray_reality": scenario not in {"disabled", "xhttp-only"},
        "enable_nginx_xhttp": scenario == "xhttp-only",
    }}}
    result = _run_xray_tasks(tmp_path, play, check=scenario == "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert current.read_text() == (old_bytes if scenario in {"check", "disabled"} else desired)
    assert previous.read_text() == (old_bytes if scenario in {"changed", "xhttp-only"} else "older restore point\n")
    assert previous.stat().st_mode & 0o777 == 0o640
