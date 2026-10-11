"""Publication cannot queue a second frontend lifecycle owner after admission."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml
from jinja2 import DictLoader
from template_render import merge_render_vars, template_environment

ROOT = Path(__file__).resolve().parents[2]
ROLES = ROOT / "ansible/roles"


def tasks(role):
    return yaml.safe_load((ROLES / role / "tasks/enable.yml").read_text())


def rotation():
    play = yaml.safe_load((ROOT / "ansible/playbooks/rotate-credentials.yml").read_text())[0]
    block = next(task for task in play["tasks"] if task["name"] ==
                 "Reconcile protected credential rotation through authoritative roles")
    return play, block


@pytest.mark.parametrize("role,label,publication", [
    ("xray", "Xray", "Render and validate Xray config"),
    ("hysteria", "Hysteria", "Drop TLS material"),
])
def test_frontend_validation_and_quiescence_precede_single_owner_activation(role, label, publication):
    source = tasks(role)
    names = [task["name"] for task in source]
    assert names.index(f"Validate {label} candidate before quiescing the accepted route") < names.index(
        f"Quiesce accepted topology before changed {label} publication") < names.index(publication)
    assert names.index(publication) < names.index("Activate guarded standalone frontend generation")
    assert all("notify" not in task for task in source)
    assert yaml.safe_load((ROLES / role / "handlers/main.yml").read_text()) == []
    candidate = next(task for task in source if task["name"].startswith(f"Validate {label} candidate"))
    validate = next(task for task in candidate["block"] if "ansible.builtin.template" in task)
    assert "validate" in validate["ansible.builtin.template"] and validate["no_log"] is True
    main = yaml.safe_load((ROLES / role / "tasks/main.yml").read_text())[0]
    restore = next(task for task in main["rescue"] if "ansible.builtin.include_role" in task)
    assert restore["ansible.builtin.include_role"] == {"name": "transport-egress", "tasks_from": "rollback"}


@pytest.mark.parametrize("reality,xhttp,hysteria,selected", [
    (False, True, False, [True, False]),
    (False, False, True, [False, True]),
    (True, True, True, [True, True]),
    (False, False, False, [False, False]),
])
def test_rotation_selects_canonical_roles_then_one_shared_activation(reality, xhttp, hysteria, selected):
    play, block = rotation()
    environment = template_environment(DictLoader({}))
    values = {"vpn": {"enable_xray_reality": reality, "enable_nginx_xhttp": xhttp,
                      "enable_hysteria": hysteria}, "vpn_subscription_only": False}
    assert bool(environment.compile_expression(block["when"])(**values)) is any(selected)
    assert block["vars"] == {"transport_egress_site_staging": True}
    stages = block["block"]
    assert [task.get("ansible.builtin.include_role") for task in stages[:3]] == [
        {"name": "transport-egress", "tasks_from": "prepare-site"},
        {"name": "xray"}, {"name": "hysteria"},
    ]
    assert [bool(environment.compile_expression(task["when"])(**values)) for task in stages[1:3]] == selected
    assert stages[3]["ansible.builtin.import_tasks"] == "tasks/transport-egress-activate.yml"
    assert not any(task.get("name") in {"Restart xray", "Restart hysteria"} for task in play["handlers"])
    assert all("ansible.builtin.template" not in task for task in stages)
    assert play["tasks"][0]["ansible.builtin.import_tasks"] == "tasks/transport-input-preflight.yml"
    assert any(task.get("name") == "Re-render AmneziaWG peers" for task in play["tasks"])
    assert any(task.get("name") == "Re-render Snell users" for task in play["tasks"])
    assert any(task.get("ansible.builtin.include_role") == {"name": "naive"} for task in play["tasks"])
    values["vpn_subscription_only"] = True
    assert environment.compile_expression(block["when"])(**values) is False


def test_actual_ansible_publication_and_flush_cannot_dispatch_frontend_handlers(tmp_path):
    """Actual notification reporting only; no daemon or protocol proof is claimed."""
    executable = shutil.which("ansible-playbook")
    assert executable, "genuine pinned Ansible is required"
    for role in ("xray", "hysteria"):
        assert yaml.safe_load((ROLES / role / "handlers/main.yml").read_text()) == []
    marker = tmp_path / "retained-generation-marker"
    marker.write_text("opaque retained authority\n"); marker.chmod(0o600)
    before = (marker.stat().st_ino, marker.stat().st_mtime_ns, hashlib.sha256(marker.read_bytes()).hexdigest())
    context = merge_render_vars()
    context.pop("item", None)
    context.update({"hysteria_config_dir": str(tmp_path), "ansible_python_interpreter": sys.executable})
    context["hysteria"].update(cert_pem="synthetic-ownership-certificate", key_pem="synthetic-ownership-key")
    unit = copy.deepcopy(next(task for task in tasks("xray") if task["name"] == "Install xray systemd unit"))
    unit["ansible.builtin.template"].update(src=str(ROLES / "xray/templates/xray.service.j2"),
        dest=str(tmp_path / "xray.service"), owner=str(os.getuid()), group=str(os.getgid()))
    tls = copy.deepcopy(next(task for task in tasks("hysteria") if task["name"] == "Drop TLS material"))
    tls["ansible.builtin.copy"].update(owner=str(os.getuid()), group=str(os.getgid()))
    assert "notify" not in unit and "notify" not in tls
    play = tmp_path / "ownership.yml"
    play.write_text(yaml.safe_dump([{"hosts": "localhost", "connection": "local", "become": False,
        "gather_facts": False, "vars": context, "tasks": [unit, tls,
            {"name": "Flush pending source notifications", "ansible.builtin.meta": "flush_handlers"}],
        "handlers": []}], sort_keys=False))
    play.chmod(0o600)
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\ncallback_result_format=json\n")
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
    environment.update(ANSIBLE_CONFIG=str(config), ANSIBLE_HOME=str(tmp_path / "home"),
        ANSIBLE_LOCAL_TEMP=str(tmp_path / "local"), ANSIBLE_BECOME="false", ANSIBLE_NOCOLOR="1",
        ANSIBLE_STDOUT_CALLBACK="default", ANSIBLE_LOAD_CALLBACK_PLUGINS="false")
    result = subprocess.run([executable, "-i", "localhost,", str(play)], cwd=tmp_path,
                            env=environment, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RUNNING HANDLER" not in result.stdout
    assert "synthetic-ownership-key" not in result.stdout + result.stderr
    assert (tmp_path / "xray.service").is_file() and (tmp_path / "server.fullchain.pem").is_file()
    assert (marker.stat().st_ino, marker.stat().st_mtime_ns, hashlib.sha256(marker.read_bytes()).hexdigest()) == before
