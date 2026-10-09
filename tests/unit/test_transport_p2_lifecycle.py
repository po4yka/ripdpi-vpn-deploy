"""Controller execution of transport activation, staging and selector contracts."""

from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def tasks(role):
    return yaml.safe_load(
        (ROOT / "ansible/roles" / role / "tasks/enable.yml").read_text()
    )


def run(play, path):
    file = path / "play.yml"
    file.write_text(yaml.safe_dump(play, sort_keys=False))
    return subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(file)],
        capture_output=True,
        text=True,
        env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
        timeout=30,
    )


@pytest.mark.parametrize("changed", ["amneziawg-go", "amneziawg-tools", None])
def test_awg_published_runtime_change_queues_every_current_instance(tmp_path, changed):
    signal = next(
        task
        for task in tasks("amneziawg")
        if task["name"] == "Apply changed AmneziaWG runtimes to current instances"
    )
    actual = next(
        task
        for task in yaml.safe_load(
            (ROOT / "ansible/roles/amneziawg/handlers/main.yml").read_text()
        )
        if task["name"] == "Restart amneziawg"
    )
    handler = copy.deepcopy(actual)
    handler.pop("ansible.builtin.systemd_service")
    handler["ansible.builtin.copy"] = {
        "dest": str(tmp_path / "{{ item.name }}"),
        "content": "restart",
    }
    play = [
        {
            "hosts": "localhost",
            "gather_facts": False,
            "connection": "local",
            "become": False,
            "vars": {
                "ansible_become": False,
                "ansible_python_interpreter": sys.executable,
                "amneziawg_role_enabled": True,
                "_awg_instances": [{"name": "p2awg-a"}, {"name": "p2awg-b"}],
                "runtime_build_results": {
                    name: {"changed": name == changed}
                    for name in ("amneziawg-go", "amneziawg-tools")
                },
            },
            "tasks": [signal],
            "handlers": [handler],
        }
    ]
    result = run(play, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "p2awg-a").exists() == (changed is not None)
    assert (tmp_path / "p2awg-b").exists() == (changed is not None)


@pytest.mark.parametrize("changed", ["probe-matrix-xray", "probe-matrix-mtg", None])
def test_probe_unit_change_queues_only_affected_runtime(tmp_path, changed):
    signals = [
        task
        for task in tasks("probe-matrix-target")
        if task["name"].startswith("Apply changed probe matrix")
    ]
    handlers = []
    for item in yaml.safe_load(
        (ROOT / "ansible/roles/probe-matrix-target/handlers/main.yml").read_text()
    ):
        if item["name"].startswith("Restart probe matrix"):
            handler = copy.deepcopy(item)
            handler.pop("ansible.builtin.systemd_service")
            component = item["name"].rsplit(" ", 1)[1]
            handler["ansible.builtin.copy"] = {
                "dest": str(tmp_path / component),
                "content": "restart",
            }
            handlers.append(handler)
    play = [
        {
            "hosts": "localhost",
            "gather_facts": False,
            "connection": "local",
            "become": False,
            "vars": {
                "ansible_become": False,
                "ansible_python_interpreter": sys.executable,
                "probe_matrix_target_role_enabled": True,
                "probe_matrix_target": {"manage_services": True},
                "_probe_matrix_service_units": {
                    "results": [
                        {"item": name, "changed": name == changed}
                        for name in ("probe-matrix-xray", "probe-matrix-mtg")
                    ]
                },
            },
            "tasks": signals,
            "handlers": handlers,
        }
    ]
    result = run(play, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for component in ("xray", "mtg"):
        assert (tmp_path / component).exists() == (
            changed == "probe-matrix-" + component
        )


@pytest.mark.parametrize(
    "environment,success", [("staging", True), ("prod", False), ("", False)]
)
def test_realm_exact_prerelease_guard_is_before_any_mutation(
    tmp_path, environment, success
):
    guard = tasks("hysteria-realm")[0]
    play = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "become": False,
            "vars": {
                "env": environment,
                "hysteria_realm": {"version": "v1.14.0-alpha.22", "max_realms": 16},
            },
            "tasks": [
                guard,
                {
                    "name": "Observe mutation admission",
                    "ansible.builtin.copy": {
                        "dest": str(tmp_path / "admitted"),
                        "content": "admitted",
                    },
                },
            ],
        }
    ]
    result = run(play, tmp_path)
    assert (result.returncode == 0) is success
    assert (tmp_path / "admitted").exists() is success


@pytest.mark.parametrize(
    "role",
    [
        "hysteria-realm",
        "amneziawg",
        "naive",
        "warp-outbound",
        "probe-matrix-target",
        "split-hop-ingress",
        "split-hop-egress",
        "dns-morph-bridge",
    ],
)
def test_transport_selector_is_unique_and_enters_disable_before_input_guard(role):
    variable = role.replace("-", "_") + "_role_enabled"
    defaults = yaml.safe_load(
        (ROOT / "ansible/roles" / role / "defaults/main.yml").read_text()
    )
    assert defaults[variable] is True
    entry = yaml.safe_load(
        (ROOT / "ansible/roles" / role / "tasks/main.yml").read_text()
    )
    assert len(entry) == 1 and variable in entry[0]["ansible.builtin.include_tasks"]
    assert (ROOT / "ansible/roles" / role / "tasks/disable.yml").exists()


@pytest.mark.parametrize(
    "version,success",
    [
        ("2026.8.2100.0", True),
        ("", False),
        ("latest", False),
        ("2026.8.2100.0-beta", False),
    ],
)
def test_warp_exact_stable_version_guard_precedes_mutation(tmp_path, version, success):
    play = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": {
                "ansible_become": False,
                "warp_outbound": {"package_version": version},
            },
            "tasks": [
                tasks("warp-outbound")[0],
                {
                    "ansible.builtin.copy": {
                        "dest": str(tmp_path / "admitted"),
                        "content": "admitted",
                    }
                },
            ],
        }
    ]
    result = run(play, tmp_path)
    assert (result.returncode == 0) is success
    assert (tmp_path / "admitted").exists() is success


@pytest.mark.parametrize(
    "actual,success", [("2026.8.2100.0", True), ("2026.8.2099.0", False)]
)
def test_warp_installed_dpkg_identity_gates_registration(tmp_path, actual, success):
    guard = next(
        task
        for task in tasks("warp-outbound")
        if task["name"] == "Require installed WARP identity to match the approved pin"
    )
    play = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": {
                "ansible_become": False,
                "warp_outbound": {"package_version": "2026.8.2100.0"},
                "_warp_installed_version": {"stdout": actual},
            },
            "tasks": [
                guard,
                {
                    "ansible.builtin.copy": {
                        "dest": str(tmp_path / "registration-admitted"),
                        "content": "admitted",
                    }
                },
            ],
        }
    ]
    result = run(play, tmp_path)
    assert (result.returncode == 0) is success
    assert (tmp_path / "registration-admitted").exists() is success


def test_probe_complete_nginx_candidate_contains_tls_vhost_and_exact_link():
    enabled = next(
        task
        for task in tasks("probe-matrix-target")
        if task["name"]
        == "Publish probe TLS and control listener as one complete nginx candidate"
    )
    assert enabled["ansible.builtin.include_role"] == {
        "name": "nginx-xhttp",
        "tasks_from": "transaction",
    }
    files = enabled["vars"]["nginx_transaction_files"]
    assert {row["path"] for row in files} == {
        "/etc/probe-matrix/tls.crt",
        "/etc/probe-matrix/tls.key",
        "/etc/nginx/sites-available/probe-matrix-tls.conf",
        "/etc/nginx/sites-enabled/probe-matrix-tls.conf",
    }
    assert (
        next(row for row in files if row["path"].endswith("tls.key"))["mode"] == "0640"
    )
    assert (
        next(row for row in files if row["kind"] == "link")["target"]
        == "/etc/nginx/sites-available/probe-matrix-tls.conf"
    )
    disabled = yaml.safe_load(
        (ROOT / "ansible/roles/probe-matrix-target/tasks/disable.yml").read_text()
    )
    remove = next(
        task
        for task in disabled
        if task["name"]
        == "Remove only the probe listener through complete nginx publication"
    )
    assert remove["vars"]["nginx_transaction_desired_enabled"] is None
    assert remove["vars"]["nginx_transaction_activate_inactive"] is False
    assert all(
        set(row) == {"path", "kind"} and row["kind"] == "absent"
        for row in remove["vars"]["nginx_transaction_files"]
    )
