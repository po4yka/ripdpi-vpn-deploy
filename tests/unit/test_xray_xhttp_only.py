"""XHTTP-only profile must still run a valid localhost Xray backend."""

from __future__ import annotations

import importlib.util
import json
import os
import copy
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
NGINX_XHTTP_TASKS = (
    REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "tasks" / "main.yml"
)
ROLLBACK_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rollback-xray.yml"

spec = importlib.util.spec_from_file_location("xhttp_only_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_p1_web_renders_only_the_local_xhttp_inbound() -> None:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load(
        (REPO_ROOT / "ansible" / "group_vars" / "vpn-p1-web.yml").read_text()
    )
    variables.update(profile)
    config = json.loads(renderer.render_template(TEMPLATE, variables))

    assert [inbound["tag"] for inbound in config["inbounds"]] == [
        "vless-xhttp-localhost"
    ]
    assert config["inbounds"][0]["listen"] == "127.0.0.1"
    assert config["inbounds"][0]["streamSettings"]["network"] == "xhttp"


def test_p0_profile_inherits_the_shared_reality_shape_model() -> None:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load(
        (REPO_ROOT / "ansible" / "group_vars" / "vpn-p0-minimal.yml").read_text()
    )
    variables.update(profile)

    config = json.loads(renderer.render_template(TEMPLATE, variables))
    primary = next(
        inbound
        for inbound in config["inbounds"]
        if inbound["tag"] == "vless-reality-primary"
    )
    assert primary["settings"]["clients"][0]["flow"] == "xtls-rprx-vision"


@pytest.mark.parametrize(
    ("scenario", "expected_port"), [("cohort", 2443), ("default", 2444)]
)
def test_installed_ansible_smoke_client_uses_the_shared_mux_and_finalmask_shape(
    tmp_path: Path, scenario: str, expected_port: int
) -> None:
    """The live smoke client must not retain a separate Vision-only shape."""
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for smoke shape parity"
    source = yaml.safe_load(
        (REPO_ROOT / "ansible/playbooks/smoke-test.yml").read_text()
    )[0]

    def find_task(tasks: list[dict], name: str) -> dict:
        for task in tasks:
            if task.get("name") == name:
                return task
            for nested in (
                task.get("block", []),
                task.get("rescue", []),
                task.get("always", []),
            ):
                found = find_task(nested, name)
                if found:
                    return found
        return {}

    names = (
        "Select populated REALITY smoke cohorts",
        "Select REALITY smoke cohort",
        "Require valid REALITY smoke cohort",
        "Select REALITY smoke client from cohort",
        "Require REALITY smoke client belongs to selected cohort",
        "Render Xray client config (REALITY)",
    )
    tasks = [copy.deepcopy(find_task(source["tasks"], name)) for name in names]
    assert all(tasks), "smoke playbook must retain cohort selection and render tasks"
    task = tasks[-1]
    destination = tmp_path / "xray-client.json"
    copy_args = task["ansible.builtin.copy"]
    copy_args.update(dest=str(destination))
    copy_args.pop("owner", None)
    copy_args.pop("group", None)
    copy_args.pop("mode", None)
    clients = [{"name": "chosen", "uuid": "fixture-uuid", "short_id": "abcd"}]
    cohorts: list[dict] = []
    vpn = {"xray_flow_mode": "mux-masked"}
    if scenario == "cohort":
        clients.insert(0, {"name": "other", "uuid": "other-uuid", "short_id": "dead"})
        cohorts = [
            {"name": "empty", "port": 2442, "flow_mode": "vision", "clients": []},
            {
                "name": "mux-shaped",
                "port": 2443,
                "flow_mode": "mux",
                "finalmask": True,
                "clients": ["chosen"],
            },
        ]
        vpn = {"xray_flow_mode": "vision", "xray_finalmask": False}

    play = [
        {
            "hosts": "localhost",
            "gather_facts": False,
            "become": False,
            "vars": {
                "ansible_python_interpreter": sys.executable,
                "smoketest_dir": str(tmp_path),
                "xray": {
                    "server_names": ["fixture.example"],
                    "reality_public_key": "fixture-public",
                    "clients": clients,
                    "cohorts": cohorts,
                },
                "xray_port": 2444,
                "vpn": vpn,
                "p0_reality_flow_mode": "vision",
                "p0_reality_shapes": {
                    "vision": {
                        "client_flow": "xtls-rprx-vision",
                        "client_mux": False,
                        "finalmask": False,
                    },
                    "mux": {"client_flow": "", "client_mux": True, "finalmask": False},
                    "mux-masked": {
                        "client_flow": "",
                        "client_mux": True,
                        "finalmask": True,
                    },
                },
            },
            "tasks": tasks,
        }
    ]
    playbook = tmp_path / "smoke-shape.yml"
    playbook.write_text(yaml.safe_dump(play, sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    env.update(
        ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local")
    )
    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(playbook)],
        capture_output=True,
        text=True,
        env=env,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    config_json = json.loads(destination.read_text())
    outbound = config_json["outbounds"][0]
    assert outbound["settings"]["vnext"][0]["port"] == expected_port
    assert outbound["settings"]["vnext"][0]["users"][0]["id"] == "fixture-uuid"
    assert "flow" not in outbound["settings"]["vnext"][0]["users"][0]
    assert outbound["mux"] == {"enabled": True, "concurrency": 8}
    assert outbound["streamSettings"]["sockopt"]["finalmask"] == "Sudoku"


def _run_live_p0_shape_preflight(
    tmp_path: Path,
    profile: str,
    *,
    cohorts: list[dict] | None = None,
    vpn_override: dict | None = None,
) -> subprocess.CompletedProcess:
    """Execute the live role preflight with real profile replacement semantics."""
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for the P0 shape contract"
    root = tmp_path / "ansible"
    group_vars = root / "group_vars"
    group_vars.mkdir(parents=True)
    shutil.copyfile(
        REPO_ROOT / "ansible" / "group_vars" / "all.yml", group_vars / "all.yml"
    )
    shutil.copyfile(
        REPO_ROOT / "ansible" / "group_vars" / f"{profile}.yml",
        group_vars / f"{profile}.yml",
    )
    source = yaml.safe_load(
        (REPO_ROOT / "ansible" / "roles" / "xray" / "tasks" / "main.yml").read_text()
    )
    names = {
        "Resolve the effective P0 REALITY shape",
        "Pre-flight — default P0 REALITY shape must be declared",
        "Pre-flight — cohort P0 REALITY shapes must be declared",
    }
    tasks = [task for task in source if task["name"] in names]
    assert {task["name"] for task in tasks} == names
    play = {
        "hosts": profile,
        "gather_facts": False,
        "become": False,
        "vars": {
            "ansible_python_interpreter": sys.executable,
            "xray": {"version": "fixture", "cohorts": cohorts or []},
        },
        "tasks": [
            *tasks,
            {
                "name": "Report effective P0 shape",
                "ansible.builtin.debug": {
                    "msg": "P0_SHAPE={{ p0_reality_effective_flow_mode }}"
                },
            },
        ],
    }
    playbook = root / "shape.yml"
    playbook.write_text(yaml.safe_dump([play], sort_keys=False))
    inventory = root / "inventory"
    inventory.write_text(f"[{profile}]\nlocalhost ansible_connection=local\n")
    config = root / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_NOCOLOR="1", ANSIBLE_FORCE_COLOR="0")
    command = [executable, "-i", str(inventory), str(playbook)]
    if vpn_override:
        command.extend(["--extra-vars", json.dumps({"vpn": vpn_override})])
    return subprocess.run(command, capture_output=True, text=True, env=env, timeout=40)


@pytest.mark.parametrize("profile", ["vpn-p0-minimal", "vpn-family-standard"])
def test_installed_ansible_profiles_inherit_nonreplaceable_p0_flow_default(
    tmp_path: Path, profile: str
) -> None:
    result = _run_live_p0_shape_preflight(tmp_path, profile)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "P0_SHAPE=vision" in result.stdout


def test_installed_ansible_cohort_without_flow_inherits_profile_shape(
    tmp_path: Path,
) -> None:
    result = _run_live_p0_shape_preflight(
        tmp_path,
        "vpn-p0-minimal",
        cohorts=[{"name": "implicit", "port": 443, "clients": []}],
        vpn_override={"xray_flow_mode": "mux"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "P0_SHAPE=mux" in result.stdout


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
    handlers = yaml.safe_load(
        (REPO_ROOT / "ansible" / "roles" / "xray" / "handlers" / "main.yml").read_text()
    )
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


def _run_xray_tasks(
    tmp_path: Path, play: dict, *, check: bool = False
) -> subprocess.CompletedProcess:
    """Execute source tasks locally; only paths and service effects are sandboxed."""
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for restore-point regressions"
    play.update(hosts="localhost", become=False, gather_facts=False)
    play.setdefault("vars", {})["ansible_python_interpreter"] = sys.executable
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump([play], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    env.update(
        ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local")
    )
    return subprocess.run(
        [
            executable,
            "-i",
            "localhost,",
            "-c",
            "local",
            str(path),
            *(["--check"] if check else []),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "reject-config",
        "same-version",
        "traversal",
        "valid",
        "check-reject",
        "non-executable",
        "symlink-binary",
    ],
)
def test_rollback_validates_before_runtime_change(
    tmp_path: Path, scenario: str
) -> None:
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
    version = {"same-version": "v1.0.0", "traversal": "../v0.9.0"}.get(
        scenario, "v0.9.0"
    )
    play["vars"]["rollback_xray_version"] = version
    for task in play["tasks"]:
        if "ansible.builtin.systemd_service" in task:
            task.pop("ansible.builtin.systemd_service")
            task["ansible.builtin.copy"] = {
                "content": "restarted",
                "dest": str(restart),
            }
        if task["name"] == "Verify Xray active after rollback":
            task["ansible.builtin.command"] = {"cmd": "/bin/echo active"}
    # Keep the actual assertions, command ordering and link operation unchanged.
    source = yaml.safe_dump(play).replace(
        "/usr/local/bin/xray", str(runtime / "current" / "xray")
    )
    play = yaml.safe_load(
        source.replace("/opt/xray", str(runtime)).replace("/etc/xray", str(tmp_path))
    )
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


@pytest.mark.parametrize(
    "scenario",
    ["changed", "unchanged", "first-config", "check", "disabled", "xhttp-only"],
)
def test_rotation_preserves_immediate_restore_point(
    tmp_path: Path, scenario: str
) -> None:
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
    play = {
        "tasks": tasks,
        "vars": {
            "vpn": {
                "enable_xray_reality": scenario not in {"disabled", "xhttp-only"},
                "enable_nginx_xhttp": scenario == "xhttp-only",
            }
        },
    }
    result = _run_xray_tasks(tmp_path, play, check=scenario == "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert current.read_text() == (
        old_bytes if scenario in {"check", "disabled"} else desired
    )
    assert previous.read_text() == (
        old_bytes if scenario in {"changed", "xhttp-only"} else "older restore point\n"
    )
    assert previous.stat().st_mode & 0o777 == 0o640
