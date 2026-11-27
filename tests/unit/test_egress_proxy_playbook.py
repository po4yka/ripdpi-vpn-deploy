"""Contract of the egress node playbook; it cannot run offline, so assert its structure."""

from pathlib import Path

import yaml

PLAY = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "ansible/playbooks/egress-proxy.yml").read_text()
)[0]


def test_egress_playbook_runs_exactly_the_four_roles_on_the_egress_group() -> None:
    roles = [t["ansible.builtin.include_role"]["name"] for t in PLAY["tasks"] if "ansible.builtin.include_role" in t]

    assert PLAY["hosts"] == "egress"
    assert roles == ["baseline", "firewall", "tailnet-management", "egress-proxy"]


def test_egress_playbook_opens_only_the_proxy_port_and_no_vpn_toggle() -> None:
    vpn = PLAY["vars"]["vpn"]

    assert PLAY["vars"]["firewall_tailnet_extra_tcp_ports"] == [3128]
    assert PLAY["vars"]["firewall_egress_policy"] == "strict"
    # Tailnet management is the one toggle the Tailnet role and strict firewall require.
    assert [k for k, v in vpn.items() if v is not False] == ["enable_tailnet_management"]
    assert vpn["enable_tailnet_management"] is True


def test_egress_tag_is_read_and_required_exactly_before_any_role() -> None:
    names = [t["name"] for t in PLAY["pre_tasks"]]
    read = next(t for t in PLAY["pre_tasks"] if "argv" in t.get("ansible.builtin.command", {}) and "tailscale" in t["ansible.builtin.command"]["argv"])
    gate = next(t for t in PLAY["pre_tasks"] if "ansible.builtin.assert" in t and "egress_tailnet_tags" in str(t))

    assert read["ansible.builtin.command"]["argv"][:3] == ["tailscale", "status", "--json"]
    assert names.index(read["name"]) < names.index(gate["name"])
    assert "egress_tailnet_tags == ['tag:egress']" in gate["ansible.builtin.assert"]["that"]
    assert not any("tailscale" in str(t) for t in PLAY["tasks"])
