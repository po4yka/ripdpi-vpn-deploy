"""Split-hop family scope admission and identity resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"
GUARD = "Guard — split-hop family egress leaves no recipient path on Node A"


def _site_guard() -> dict:
    play = yaml.safe_load((ANSIBLE / "playbooks/site.yml").read_text())[0]
    return next(task for task in play["pre_tasks"] if task.get("name") == GUARD)


def _admitted(vpn: dict) -> tuple[bool, list[str]]:
    task = _site_guard()
    templar = Templar(loader=DataLoader(), variables={"vpn": vpn})
    if not templar.template(trust_as_template("{{ " + task["when"] + " }}")):
        return True, []
    direct = templar.template(trust_as_template(task["vars"]["_family_direct_egress"]))
    templar.available_variables = {"vpn": vpn, "_family_direct_egress": direct}
    passed = all(templar.template(trust_as_template("{{ " + condition + " }}"))
                 for condition in task["ansible.builtin.assert"]["that"])
    return passed, direct


def test_family_scope_requires_the_ingress_responder():
    assert _admitted({"split_hop_family_egress": True, "enable_split_hop_ingress": False}) == (False, [])
    assert _admitted({"split_hop_family_egress": True, "enable_split_hop_ingress": True,
                      "enable_xray_reality": True, "enable_amneziawg": True}) == (True, [])


@pytest.mark.parametrize("toggle", [
    "enable_naive", "enable_snell", "enable_dns_morph_bridge", "enable_hysteria_realm",
    "enable_warp_outbound", "enable_split_hop_egress",
])
def test_family_scope_refuses_transports_with_their_own_direct_egress(toggle):
    vpn = {"split_hop_family_egress": True, "enable_split_hop_ingress": True, toggle: True}
    assert _admitted(vpn) == (False, [toggle])
    assert _admitted({**vpn, "split_hop_family_egress": False}) == (True, [])


def test_identity_resolution_keeps_only_requested_users_and_their_uids():
    tasks = yaml.safe_load((ANSIBLE / "roles/split-hop-ingress/tasks/enable.yml").read_text())
    publish = next(task for task in tasks if task["name"] == "Publish family recipient egress UIDs")
    expression = publish["ansible.builtin.set_fact"]["split_hop_ingress_family_uids"]
    variables = {
        "split_hop_ingress_family_users": ["transport-normalizer", "transport-gateway"],
        "_split_hop_family_identity": {"stdout_lines": [
            "transport-normalizer:x:991:991::/nonexistent:/usr/sbin/nologin",
            "transport-gateway:x:992:992::/nonexistent:/usr/sbin/nologin",
        ]},
    }
    uids = Templar(loader=DataLoader(), variables=variables).template(trust_as_template(expression))
    assert uids == [991, 992]
    # getent prints only present users; an absent one leaves the list short for the refusal.
    variables["_split_hop_family_identity"]["stdout_lines"].pop()
    uids = Templar(loader=DataLoader(), variables=variables).template(trust_as_template(expression))
    assert uids == [991]


def test_family_users_name_the_transport_egress_recipient_identities():
    egress = yaml.safe_load((ANSIBLE / "roles/transport-egress/defaults/main.yml").read_text())
    expected = [egress["transport_egress_normalizer_user"], egress["transport_egress_gateway_user"]]
    for role in ("split-hop-ingress", "firewall"):
        defaults = yaml.safe_load((ANSIBLE / f"roles/{role}/defaults/main.yml").read_text())
        assert defaults["split_hop_ingress_family_users"] == expected, role
