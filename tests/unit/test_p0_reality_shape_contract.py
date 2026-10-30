"""One rendered P0 shape contract shared by Xray and watchdog."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jinja2 import UndefinedError

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "ansible/templates/p0-reality-shape.json.j2"
XRAY = ROOT / "ansible/roles/xray/templates/config.json.j2"
WATCHDOG = ROOT / "ansible/roles/watchdog/templates/reality-probe.json.j2"
ROTATE = ROOT / "ansible/playbooks/rotate-credentials.yml"
SMOKE = ROOT / "ansible/playbooks/smoke-test.yml"


def _shape(variables: dict, value: dict) -> dict:
    context = deepcopy(variables)
    context["p0_reality_shape_input"] = value
    return json.loads(render_template(SHARED, context))


@pytest.mark.parametrize(
    ("vpn", "value", "expected"),
    [
        ({}, {}, ("vision", "xtls-rprx-vision", False, False)),
        ({"xray_flow_mode": "mux"}, {}, ("mux", "", True, False)),
        (
            {"xray_finalmask": True},
            {},
            ("vision", "xtls-rprx-vision", False, True),
        ),
        (
            {"xray_flow_mode": "mux", "xray_finalmask": True},
            {"flow_mode": "vision", "finalmask": False},
            ("vision", "xtls-rprx-vision", False, False),
        ),
        (
            {"xray_finalmask": True},
            {"finalmask": False},
            ("vision", "xtls-rprx-vision", False, False),
        ),
    ],
)
def test_shared_shape_resolves_all_override_levels(
    vpn: dict, value: dict, expected: tuple[str, str, bool, bool]
) -> None:
    variables = merge_render_vars()
    variables["vpn"].update(vpn)

    shape = _shape(variables, value)

    assert (
        shape["flow_mode"],
        shape["client_flow"],
        shape["client_mux"],
        shape["finalmask"],
    ) == expected


def test_shared_shape_refuses_unknown_mode() -> None:
    with pytest.raises(UndefinedError, match="unknown-shape"):
        _shape(merge_render_vars(), {"flow_mode": "unknown-shape"})


@pytest.mark.parametrize("alternate", [False, True])
def test_canonical_fixture_renders_watchdog_through_shared_shape(alternate: bool) -> None:
    variables = merge_render_vars()
    expected_ports = [443]
    if alternate:
        fallback = deepcopy(variables["watchdog_reality_probes"][0])
        fallback.update(name="fallback", port=2053)
        variables["watchdog_reality_probes"].append(fallback)
        expected_ports.append(2053)
    config = json.loads(render_template(WATCHDOG, variables))

    reality = [outbound for outbound in config['outbounds']
               if outbound['streamSettings']['security'] == 'reality']
    assert [outbound["settings"]["vnext"][0]["port"] for outbound in reality] == expected_ports
    assert len(config['outbounds']) == len(expected_ports) + 1  # REALITY plus XHTTP.
    assert all(
        outbound["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"
        for outbound in reality
    )


def test_installed_ansible_nested_lookup_uses_raw_input_precedence(
    tmp_path: Path,
) -> None:
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for the shared P0 contract"
    destination = tmp_path / "shape.json"
    playbook = tmp_path / "shared-shape.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        "p0_reality_shape_template": str(SHARED),
                        "p0_reality_shape_input": {
                            "flow_mode": "vision",
                            "finalmask": False,
                        },
                        "vpn": {
                            "xray_flow_mode": "mux",
                            "xray_finalmask": True,
                        },
                        "p0_reality_flow_mode": "vision",
                        "p0_reality_shapes": {
                            "vision": {
                                "client_flow": "xtls-rprx-vision",
                                "client_mux": False,
                                "finalmask": False,
                            },
                            "mux": {
                                "client_flow": "",
                                "client_mux": True,
                                "finalmask": False,
                            },
                        },
                    },
                    "tasks": [
                        {
                            "name": "Render shared P0 shape through Ansible lookup",
                            "ansible.builtin.set_fact": {
                                "rendered_p0_shape": "{{ lookup('ansible.builtin.template', p0_reality_shape_template, template_vars={'p0_reality_shape_input': p0_reality_shape_input}) | from_json }}"
                            },
                        },
                        {
                            "name": "Persist rendered fixture result",
                            "ansible.builtin.copy": {
                                "content": "{{ rendered_p0_shape | to_json }}",
                                "dest": str(destination),
                                "mode": "0600",
                            },
                        },
                    ],
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n", encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    environment["ANSIBLE_CONFIG"] = str(config)

    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(playbook)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "flow_mode": "vision",
        "client_flow": "xtls-rprx-vision",
        "client_mux": False,
        "finalmask": False,
    }


def test_installed_ansible_rotation_uses_shared_shape_from_playbook_context(
    tmp_path: Path,
) -> None:
    """The rotation playbook's relative template paths must preserve P0 shape."""
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for the shared P0 contract"
    rotation = yaml.safe_load(ROTATE.read_text(encoding="utf-8"))[0]
    stages = next(task["block"] for task in rotation["tasks"]
                  if task["name"] == "Reconcile protected credential rotation through authoritative roles")
    assert any(task.get("ansible.builtin.include_role") == {"name": "xray"} for task in stages)
    role_tasks = yaml.safe_load((ROOT / "ansible/roles/xray/tasks/enable.yml").read_text())
    validation = next(task for task in role_tasks if task["name"] == "Validate Xray candidate before quiescing the accepted route")
    task = next(task for task in validation["block"] if "ansible.builtin.template" in task)
    task = deepcopy(task)
    destination = tmp_path / "xray-config.json"
    template_args = task["ansible.builtin.template"]
    template_args["src"] = "../roles/xray/templates/config.json.j2"
    template_args["dest"] = str(destination)
    for key in ("owner", "group", "mode", "validate"):
        template_args.pop(key, None)

    # Keep the source task's ../roles and ../templates relationships intact.
    fixture_ansible = tmp_path / "ansible"
    fixture_playbooks = fixture_ansible / "playbooks"
    fixture_playbooks.mkdir(parents=True)
    (fixture_ansible / "roles").symlink_to(
        ROOT / "ansible" / "roles", target_is_directory=True
    )
    (fixture_ansible / "templates").symlink_to(
        ROOT / "ansible" / "templates", target_is_directory=True
    )
    playbook = fixture_playbooks / "rotation-shape.yml"
    playbook.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "become": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        "role_path": str(fixture_ansible / "roles/xray"),
                        "transport_egress_secrets": merge_render_vars()[
                            "transport_egress_secrets"
                        ],
                        "p0_reality_shape_template": rotation["vars"][
                            "p0_reality_shape_template"
                        ],
                        "xray_log_path": str(tmp_path / "xray-log"),
                        "xray_api_listen": "127.0.0.1:10086",
                        "xray_port": 2444,
                        "xray_fallback_port": 0,
                        "xray_reality_max_time_diff_ms": 90000,
                        "nginx_xhttp_port": 10085,
                        "p0_reality_flow_mode": "vision",
                        "p0_reality_shapes": {
                            "vision": {
                                "client_flow": "xtls-rprx-vision",
                                "client_mux": False,
                                "finalmask": False,
                            },
                            "mux": {
                                "client_flow": "",
                                "client_mux": True,
                                "finalmask": False,
                            },
                        },
                        "vpn": {
                            "enable_xray_reality": True,
                            "enable_nginx_xhttp": False,
                            "xray_flow_mode": "mux",
                            "xray_finalmask": True,
                        },
                        "xray": {
                            "target": "fixture.example:443",
                            "server_names": ["fixture.example"],
                            "reality_private_key": "fixture-private-key",
                            "clients": [
                                {
                                    "name": "fixture",
                                    "uuid": "fixture-uuid",
                                    "short_id": "abcd",
                                }
                            ],
                            "cohorts": [],
                        },
                    },
                    "tasks": [task],
                }
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n", encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    environment["ANSIBLE_CONFIG"] = str(config)

    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(playbook)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    inbound = json.loads(destination.read_text(encoding="utf-8"))["inbounds"][0]
    assert "flow" not in inbound["settings"]["clients"][0]
    assert inbound["streamSettings"]["finalmask"] == {"tcp": [{"type": "sudoku", "settings": {}}]}


def test_xray_and_watchdog_consume_identical_shape_semantics() -> None:
    variables = merge_render_vars()
    variables["vpn_service_address"] = "192.0.2.50"
    variables["xray"]["cohorts"] = [
        {
            "name": "shared",
            "port": 443,
            "flow_mode": "mux",
            "finalmask": True,
            "clients": [client["name"] for client in variables["xray"]["clients"]],
        }
    ]
    variables["watchdog_reality_probes"] = [
        {
            "name": "shared",
            "port": 443,
            "p0_reality_shape_input": {
                "flow_mode": "mux",
                "finalmask": True,
            },
        }
    ]

    server = json.loads(render_template(XRAY, variables))["inbounds"][0]
    probe = json.loads(render_template(WATCHDOG, variables))["outbounds"][0]

    server_user = server["settings"]["clients"][0]
    probe_user = probe["settings"]["vnext"][0]["users"][0]
    assert "flow" not in server_user
    assert "flow" not in probe_user
    assert server["streamSettings"]["finalmask"] == {"tcp": [{"type": "sudoku", "settings": {}}]}
    assert probe["streamSettings"]["finalmask"] == {"tcp": [{"type": "sudoku", "settings": {}}]}
    assert probe["mux"] == {"enabled": True, "concurrency": 8}


def test_consumers_do_not_reimplement_the_shape_table() -> None:
    for template in (XRAY, WATCHDOG):
        source = template.read_text()
        assert "p0_reality_shapes[" not in source
        assert "p0_reality_shape_template" in source

    watchdog_tasks = (ROOT / "ansible/roles/watchdog/tasks/enable.yml").read_text(
        encoding="utf-8"
    )
    assert "p0_reality_shape_input" in watchdog_tasks
    assert "'finalmask': (" not in watchdog_tasks
    assert "p0_reality_shape_template" in ROTATE.read_text(encoding="utf-8")
    smoke = SMOKE.read_text(encoding="utf-8")
    assert "p0_reality_shape_template" in smoke
    assert "_smoke_shape_name" not in smoke


def test_every_reality_inbound_bounds_the_client_time_window() -> None:
    variables = merge_render_vars()
    names = [client["name"] for client in variables["xray"]["clients"]]
    variables["xray"]["cohorts"] = [
        {"name": "primary", "port": 443, "clients": names[:1]},
        {"name": "alternate", "port": 2053, "clients": names[1:]},
    ]

    inbounds = json.loads(render_template(XRAY, variables))["inbounds"]

    reality = [i for i in inbounds if i.get("streamSettings", {}).get("security") == "reality"]
    assert [i["port"] for i in reality] == [443, 2053]
    assert {i["streamSettings"]["realitySettings"]["maxTimeDiff"] for i in reality} == {90000}


@pytest.mark.parametrize(("value", "admitted"), [(90000, True), (1, True), (0, False), (-1, False), ("90000", False)])
def test_replay_window_preflight_refuses_disabled_or_untyped_values(value: object, admitted: bool) -> None:
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    tasks = yaml.safe_load((ROOT / "ansible/roles/xray/tasks/enable.yml").read_text())
    task = next(t for t in tasks if t["name"] == "Pre-flight — REALITY replay window must be bounded")
    templar = Templar(loader=DataLoader(), variables={"xray_reality_max_time_diff_ms": value})

    assert all(templar.template(trust_as_template("{{ " + c + " }}"))
               for c in task["ansible.builtin.assert"]["that"]) is admitted


def test_probes_present_the_configured_recipient_fingerprint() -> None:
    from ansible.parsing.dataloader import DataLoader
    from ansible.plugins.loader import init_plugin_loader
    from ansible.template import Templar, trust_as_template

    init_plugin_loader()
    variables = merge_render_vars()
    variables["vpn_service_address"] = "192.0.2.50"
    variables["xray_utls_fingerprint"] = "firefox"
    probe = json.loads(render_template(WATCHDOG, variables))
    fingerprints = [o["streamSettings"].get("realitySettings", o["streamSettings"].get("tlsSettings"))["fingerprint"]
                    for o in probe["outbounds"]]
    assert sorted(o["streamSettings"]["security"] for o in probe["outbounds"]) == ["reality", "tls"]
    assert fingerprints == ["firefox", "firefox"]

    tasks = yaml.safe_load((ROOT / "ansible/playbooks/tasks/smoke-reality.yml").read_text())
    render = next(t for t in tasks[0]["block"] if t["name"] == "Render Xray client config (REALITY)")
    client = variables["xray"]["clients"][0]
    variables.update(smoketest_reality_cohort={"name": "", "port": 443, "clients": [client["name"]]},
                     smoketest_client=client, smoketest_dir="/unused")
    smoke = json.loads(Templar(loader=DataLoader(), variables=variables).template(
        trust_as_template(render["ansible.builtin.copy"]["content"])))
    assert smoke["outbounds"][0]["streamSettings"]["realitySettings"]["fingerprint"] == "firefox"
