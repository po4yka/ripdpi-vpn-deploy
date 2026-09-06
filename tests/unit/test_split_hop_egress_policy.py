"""Split-hop egress must validate and reconcile its scoped nft policy."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/split-hop-egress"


def test_wireguard_config_delegates_policy_ownership_to_ansible() -> None:
    variables = merge_render_vars()
    rendered = render_template(ROLE / "templates/split-hop-egress.conf.j2", variables)

    assert "PostUp" not in rendered
    assert "PostDown" not in rendered
    assert "nft " not in rendered


def test_policy_is_validated_then_loaded_when_changed_missing_or_drifted() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    names = [task["name"] for task in tasks]

    render_index = names.index("Render validated split-hop egress policy")
    inspect_index = names.index("Inspect loaded split-hop egress policy")
    load_index = names.index("Load split-hop egress policy")
    tunnel_index = names.index("Render WireGuard config for Node B")
    assert render_index < inspect_index < load_index < tunnel_index

    render = tasks[render_index]["ansible.builtin.template"]
    assert render["src"] == "split-hop-egress.nft.j2"
    assert render["validate"] == "nft -c -f %s"
    assert tasks[render_index]["register"] == "split_hop_egress_policy_render"

    inspect = tasks[inspect_index]
    assert inspect["changed_when"] is False
    assert inspect["failed_when"] is False
    assert (
        "-j list table inet split_hop_egress"
        in inspect["ansible.builtin.command"]["cmd"]
    )

    shape = tasks[names.index("Check exact split-hop egress policy shape")]
    shape_command = shape["ansible.builtin.command"]
    assert shape_command["stdin"] == "{{ split_hop_egress_policy_state.stdout }}"
    shape_source = shape_command["argv"][2]
    assert "len(metainfo) > 1" in shape_source
    assert 'rule.get("expr") != expected' in shape_source

    drift = tasks[names.index("Detect split-hop egress policy drift")]
    assert drift["changed_when"] is False
    drift_fact = drift["ansible.builtin.set_fact"]["split_hop_egress_policy_drifted"]
    assert "split_hop_egress_policy_shape.rc != 0" in drift_fact

    loader = tasks[load_index]
    assert (
        loader["ansible.builtin.command"]["cmd"]
        == "nft -f {{ split_hop_egress.policy_path }}"
    )
    assert loader["when"] == [
        "split_hop_egress_policy_render.changed or split_hop_egress_policy_state.rc != 0 or split_hop_egress_policy_drifted"
    ]


def test_validated_policy_loader_is_enabled_for_boot_before_wireguard() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    names = [task["name"] for task in tasks]
    install = tasks[names.index("Install split-hop egress boot policy loader")]
    enable = tasks[names.index("Enable split-hop egress boot policy loader")]

    assert install["ansible.builtin.template"] == {
        "src": "split-hop-egress-policy.service.j2",
        "dest": "/etc/systemd/system/split-hop-egress-policy.service",
        "owner": "root",
        "group": "root",
        "mode": "0644",
    }
    service = enable["ansible.builtin.systemd_service"]
    assert service == {
        "name": "split-hop-egress-policy.service",
        "enabled": True,
        "daemon_reload": True,
    }
    assert names.index("Enable split-hop egress boot policy loader") < names.index(
        "Enable + start wg-quick for the tunnel"
    )

    unit = (ROLE / "templates/split-hop-egress-policy.service.j2").read_text()
    assert "ExecStart=/usr/sbin/nft -c -f {{ split_hop_egress.policy_path }}" in unit
    assert "ExecStart=/usr/sbin/nft -f {{ split_hop_egress.policy_path }}" in unit
    assert "After=local-fs.target systemd-sysctl.service nftables.service" in unit
    assert "Before=wg-quick@{{ split_hop_egress.wg_interface }}.service" in unit
    assert "WantedBy=multi-user.target" in unit


def test_scoped_policy_replaces_only_its_table_and_nat_path() -> None:
    variables = merge_render_vars()
    rendered = render_template(ROLE / "templates/split-hop-egress.nft.j2", variables)

    assert rendered.startswith("destroy table inet split_hop_egress\n")
    assert 'iifname "shop0" oifname "eth0" masquerade' in rendered
    assert "flush ruleset" not in rendered


def test_existing_wrong_table_is_reconciled_once_then_becomes_idempotent(
    tmp_path: Path,
) -> None:
    """Run the live render/inspect/drift/load task slice against fake nft."""
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    names = [task["name"] for task in tasks]
    selected = copy.deepcopy(
        tasks[
            names.index("Render validated split-hop egress policy") : names.index(
                "Install split-hop egress boot policy loader"
            )
        ]
    )
    selected[0]["ansible.builtin.template"]["src"] = str(
        ROLE / "templates/split-hop-egress.nft.j2"
    )
    # The live task owns the destination as root. The localhost fixture runs
    # unprivileged, so remove only ownership metadata from its copied task.
    selected[0]["ansible.builtin.template"].pop("owner")
    selected[0]["ansible.builtin.template"].pop("group")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state = tmp_path / "nft-state"
    correct_rule = {
        "family": "inet",
        "table": "split_hop_egress",
        "chain": "postrouting",
        "handle": 7,
        "expr": [
            {
                "match": {
                    "op": "==",
                    "left": {"meta": {"key": "iifname"}},
                    "right": "shop0",
                }
            },
            {
                "match": {
                    "op": "==",
                    "left": {"meta": {"key": "oifname"}},
                    "right": "eth0",
                }
            },
            {"masquerade": None},
        ],
    }
    expected_policy = {
        "nftables": [
            {
                "metainfo": {
                    "version": "1.0.9",
                    "release_name": "fixture",
                    "json_schema_version": 1,
                }
            },
            {
                "table": {
                    "family": "inet",
                    "name": "split_hop_egress",
                    "handle": 5,
                }
            },
            {
                "chain": {
                    "family": "inet",
                    "table": "split_hop_egress",
                    "name": "postrouting",
                    "type": "nat",
                    "hook": "postrouting",
                    "prio": 100,
                    "policy": "accept",
                    "handle": 6,
                }
            },
            {"rule": correct_rule},
        ]
    }
    # The desired NAT rule is present, but an extra counter/accept rule is
    # drift and must force one validated reload.
    state.write_text(
        json.dumps(
            expected_policy
            | {
                "nftables": expected_policy["nftables"]
                + [
                    {
                        "rule": {
                            "family": "inet",
                            "table": "split_hop_egress",
                            "chain": "postrouting",
                            "expr": [{"counter": None}, {"accept": None}],
                        }
                    }
                ]
            }
        )
    )
    nft = fake_bin / "nft"
    nft.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'case "$*" in\n'
        '  "-c -f "*) exit 0 ;;\n'
        '  "-j list table inet split_hop_egress") cat "$NFT_STATE" ;;\n'
        '  "-f "*)\n'
        '    printf %s "$NFT_EXPECTED" > "$NFT_STATE" ;;\n'
        "  *) exit 64 ;;\n"
        "esac\n"
    )
    nft.chmod(0o755)

    play = tmp_path / "play.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "connection": "local",
                    "become": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        "split_hop_egress": {
                            "wg_interface": "shop0",
                            "forward_iface": "eth0",
                            "policy_path": str(tmp_path / "policy.nft"),
                        },
                    },
                    "tasks": selected,
                }
            ],
            sort_keys=False,
        )
    )
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")
    }
    environment.update(
        {
            "ANSIBLE_CONFIG": str(config),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "NFT_STATE": str(state),
            "NFT_EXPECTED": json.dumps(expected_policy),
        }
    )
    command = [
        sys.executable,
        "-m",
        "ansible.cli.playbook",
        "-i",
        "localhost,",
        str(play),
    ]

    first = subprocess.run(command, capture_output=True, text=True, env=environment)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "changed=2" in first.stdout
    assert json.loads(state.read_text()) == expected_policy

    second = subprocess.run(command, capture_output=True, text=True, env=environment)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "changed=0" in second.stdout
