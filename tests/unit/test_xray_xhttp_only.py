"""XHTTP-only profile must still run a valid localhost Xray backend."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "xray" / "templates" / "config.json.j2"
SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "site.yml"
ROTATION_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rotate-credentials.yml"
VERIFY_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "verify.yml"
NGINX_XHTTP_TASKS = REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "tasks" / "main.yml"

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
    assert "enable_nginx_xhttp" in verify_probe["when"]
