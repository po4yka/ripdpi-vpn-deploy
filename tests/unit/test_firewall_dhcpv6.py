"""Execute DHCPv6 admission and inspect the canonical firewall render."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/firewall"


def render(*, servers=(), facts=None, interface="", policy="strict"):
    values = merge_render_vars()
    values.update(
        firewall_dhcpv6_uplink_interface=interface,
        firewall_dhcpv6_server_addresses=list(servers),
        firewall_egress_policy=policy,
        public_listener_contract=[],
    )
    values["ansible_facts"] = facts or {"default_ipv4": {"interface": "uplink0"}}
    values["vpn"] = {key: False for key in values["vpn"]}
    return render_template(ROLE / "templates/nftables.conf.j2", values)


@pytest.mark.parametrize("facts,override,expected", [
    ({"default_ipv4": {"interface": "v4up"}}, "", "v4up"),
    ({"default_ipv6": {"interface": "v6up"}, "default_ipv4": {"interface": "v4up"}}, "", "v6up"),
    ({"default_ipv6": {"interface": "v6up"}}, "other0", "other0"),
])
def test_render_scopes_both_port_pairs_to_one_effective_uplink(facts, override, expected):
    result = render(facts=facts, interface=override)
    assert f'iifname "{expected}" ip6 saddr fe80::/10 fib daddr type local udp sport 547 udp dport 546 counter accept' in result
    assert f'oifname "{expected}" ip6 saddr fe80::/10 ip6 daddr {{ ff02::1:2, fe80::/10 }} udp sport 546 udp dport 547 counter accept' in result
    assert 'comment "dhcpv6-approved-server' not in result
    assert 'meta l4proto udp accept' not in result
    assert '\n    udp dport 546 accept' not in result


@pytest.mark.parametrize("policy", ["permissive", "logged", "strict"])
def test_exact_legacy_servers_never_create_a_global_prefix_accept(policy):
    result = render(servers=["2001:db8::20"], policy=policy)
    assert 'ip6 saddr { 2001:db8::20 } fib daddr type local udp sport 547 udp dport 546' in result
    assert ('ip6 daddr { 2001:db8::20 } udp sport 546 udp dport 547' in result) is (policy == "strict")
    assert '::/0' not in result


@pytest.mark.parametrize("override,facts,servers,accepted", [
    ("", {"default_ipv4": {"interface": "up0"}, "interfaces": ["up0"]}, [], True),
    ("", {"default_ipv6": {"interface": "up0"}, "interfaces": ["up0"]}, ["2001:db8::20"], True),
    ("", {"interfaces": ["up0"]}, [], False),
    ("missing", {"interfaces": ["up0"]}, [], False),
    ("lo", {"interfaces": ["lo"]}, [], False),
    ("tailscale0", {"interfaces": ["tailscale0"]}, [], False),
    ("awg0", {"interfaces": ["awg0"]}, [], False),
    ('up0" accept', {"interfaces": ['up0" accept']}, [], False),
    (True, {"interfaces": ["up0"]}, [], False),
    ("up0", {"interfaces": ["up0"]}, "2001:db8::20", False),
    ("up0", {"interfaces": ["up0"]}, ["::/0"], False),
    ("up0", {"interfaces": ["up0"]}, ["::"], False),
    ("up0", {"interfaces": ["up0"]}, ["::1"], False),
    ("up0", {"interfaces": ["up0"]}, ["ff02::1:2"], False),
    ("up0", {"interfaces": ["up0"]}, ["192.0.2.2"], False),
    ("up0", {"interfaces": ["up0"]}, ["::ffff:c000:202"], False),
    ("up0", {"interfaces": ["up0"]}, ["fe80::20%up0"], False),
    ("up0", {"interfaces": ["up0"]}, [True], False),
    ("up0", {"interfaces": ["up0"]}, ["2001:DB8::20"], False),
    ("up0", {"interfaces": ["up0"]}, ["2001:db8::20"] * 2, False),
    ("up0", {"interfaces": ["up0"]}, [f"2001:db8::{value:x}" for value in range(17)], False),
])
@pytest.mark.parametrize("check", [False, True])
def test_real_ansible_admission_refuses_before_mutation(tmp_path, override, facts, servers, accepted, check):
    marker = tmp_path / "mutation"
    play = [{
        "hosts": "localhost", "connection": "local", "gather_facts": False,
        "become": False,
        "vars": {
            "ansible_python_interpreter": sys.executable,
            "ansible_facts": facts,
            "amneziawg_secrets": {"instances": [{"name": "awg0"}]},
            "firewall_dhcpv6_uplink_interface": override,
            "firewall_dhcpv6_server_addresses": servers,
        },
        "tasks": [
            {"name": "Admit real DHCPv6 inputs", "ansible.builtin.import_tasks": str(ROLE / "tasks/dhcpv6-admission.yml")},
            {"name": "Observe mutation boundary", "ansible.builtin.copy": {
                "dest": str(marker), "mode": "0600",
                "content": "{{ {'uplink': firewall_effective_dhcpv6_uplink_interface, 'servers': firewall_effective_dhcpv6_server_addresses} | to_json }}",
            }},
        ],
    }]
    path = tmp_path / "admission.yml"
    path.write_text(yaml.safe_dump(play))
    command = ["ansible-playbook", "-i", "localhost,", str(path)]
    if check:
        command.append("--check")
    result = subprocess.run(command, capture_output=True, text=True, timeout=30,
        env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")})
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    assert marker.exists() is (accepted and not check)
    if accepted and not check:
        import json
        assert json.loads(marker.read_text()) == {"uplink": "up0", "servers": servers}
    if not accepted:
        assert "dhcpv6-invalid-" in result.stdout


def test_dhcpv6_admission_is_first_before_consumer_installation():
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    assert tasks[0]["ansible.builtin.import_tasks"] == "dhcpv6-admission.yml"


def test_synthetic_awg_default_route_cannot_move_fixture_dhcpv6_on_second_gather():
    scenario = yaml.safe_load((ROLE / "molecule/default/converge.yml").read_text())[0]
    before = {"default_ipv4": {"interface": "eth0"}, "default_ipv6": {}}
    after = {"default_ipv4": {"interface": "eth0"},
             "default_ipv6": {"interface": "awg-test-up"}}
    # The real preparation adds a default route after the first gather. New
    # gathered facts must change auto selection, but not this explicit fixture.
    assert render(facts=before) != render(facts=after)
    uplink = scenario["vars"]["firewall_dhcpv6_uplink_interface"]
    assert uplink == "eth0"
    assert render(facts=before, interface=uplink) == render(facts=after, interface=uplink)
    assert 'iifname "eth0" ip6 saddr fe80::/10' in render(facts=after, interface=uplink)


@pytest.mark.parametrize("servers", [(), ("2001:db8::20",)])
@pytest.mark.parametrize("policy", ["permissive", "logged", "strict"])
def test_dhcpv6_reply_scope_precedes_generic_conntrack(servers, policy):
    chain = render(servers=servers, policy=policy).split("  chain input {", 1)[1].split("  chain forward {", 1)[0]
    invalid = chain.index("ct state invalid drop")
    allowed = chain.index('comment "dhcpv6-client-reply"')
    refused = chain.index('meta nfproto ipv6 udp sport 547 udp dport 546 counter drop comment "dhcpv6-client-reply-denied"')
    established = chain.index("ct state established,related accept")
    assert invalid < allowed < refused < established
    if servers:
        assert allowed < chain.index('comment "dhcpv6-approved-server-reply"') < refused


@pytest.mark.parametrize("servers", [(), ("2001:db8::20",)])
def test_dhcpv6_request_scope_precedes_generic_conntrack(servers):
    chain = render(servers=servers).split("  chain output {", 1)[1]
    invalid = chain.index("ct state invalid drop")
    allowed = chain.index('comment "dhcpv6-client-request"')
    refused = chain.index('meta nfproto ipv6 udp sport 546 udp dport 547 counter drop comment "dhcpv6-client-request-denied"')
    established = chain.index("ct state established,related accept")
    assert invalid < allowed < refused < established
    if servers:
        assert allowed < chain.index('comment "dhcpv6-approved-server-request"') < refused


@pytest.mark.parametrize("policy", ["permissive", "logged"])
def test_permissive_output_keeps_existing_dhcpv6_policy(policy):
    chain = render(policy=policy).split("  chain output {", 1)[1]
    assert "policy accept;" in chain
    assert 'comment "dhcpv6-client-request-denied"' not in chain
