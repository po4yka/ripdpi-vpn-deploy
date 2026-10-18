"""Persistent split-hop policy and narrow overlay firewall contracts."""
from pathlib import Path
import os
import re
import subprocess
import sys

import pytest
import yaml

from template_render import merge_render_vars, render_template


ROOT = Path(__file__).resolve().parents[2]
INGRESS = ROOT / "ansible/roles/split-hop-ingress"
FIREWALL = ROOT / "ansible/roles/firewall/templates/nftables.conf.j2"


def output_chain(rendered):
    return rendered.split("  chain output {", 1)[1].split("\n  }", 1)[0]


def test_ingress_policy_loader_is_required_before_tunnel_activation():
    tasks = yaml.safe_load((INGRESS / "tasks/enable.yml").read_text())
    named = {task["name"]: task for task in tasks}
    policy = named["Render split-hop ingress routing policy"]
    dependency = named["Require the recipient boundary before starting WireGuard"]
    loader = named["Load and retain the ingress boundary before tunnel activation"]
    tunnel = named["Enable split-hop ingress"]
    assert tasks.index(policy) < tasks.index(dependency) < tasks.index(loader) < tasks.index(tunnel)
    drop_in = dependency["ansible.builtin.copy"]
    assert "Requires=split-hop-ingress-policy.service" in drop_in["content"]
    assert "After=split-hop-ingress-policy.service" in drop_in["content"]
    assert "wg-quick@{{ split_hop_ingress.wg_interface }}.service.d/" in drop_in["dest"]
    service = loader["ansible.builtin.systemd_service"]
    assert service["name"] == "split-hop-ingress-policy.service"
    assert service["enabled"] is True and service["daemon_reload"] is True
    assert "_split_hop_ingress_policy.changed" in service["state"]
    values = merge_render_vars()
    unit = render_template(INGRESS / "templates/split-hop-ingress-policy.service.j2", values)
    assert f"Before=wg-quick@{values['split_hop_ingress']['wg_interface']}.service" in unit
    assert "RemainAfterExit=yes" in unit and "ExecStop=" not in unit
    assert unit.index("ExecStart=/usr/sbin/nft -c -f ") < unit.index("ExecStart=/usr/sbin/nft -f ")


def test_tunnel_postdown_preserves_the_post_routing_output_guard():
    values = merge_render_vars()
    policy = render_template(INGRESS / "templates/policy.nft.j2", values)
    guard = policy.split("  chain egress_guard {", 1)[1].split("\n  }", 1)[0]
    assert "type filter hook output priority 10;" in guard
    assert "ct direction original meta skuid" in guard
    assert "meta nfproto ipv6" in guard and "admin-prohibited" in guard
    assert f'oifname != {{ "lo", "{values["split_hop_ingress"]["wg_interface"]}" }} reject' in guard
    config = render_template(INGRESS / "templates/split-hop-ingress.conf.j2", values)
    post_down = next(line for line in config.splitlines() if line.startswith("PostDown = "))
    assert "ip rule del fwmark" in post_down and "ip route flush table" in post_down
    assert "nft" not in post_down


@pytest.mark.parametrize("address", ["203.0.113.40", "2001:db8::40"])
@pytest.mark.parametrize("enabled", [False, True])
def test_strict_overlay_only_profile_admits_only_scoped_udp(address, enabled):
    values = merge_render_vars()
    values["vpn"] = {key: False for key in values["vpn"]}
    values["vpn"].update(enable_tailnet_management=enabled, enable_split_hop_egress=enabled)
    values["split_hop_egress_secrets"]["node_a_public_ip"] = address
    values["split_hop_egress"]["peer_listen_port"] = 51821
    values["firewall_egress_policy"] = "strict"
    chain = output_chain(render_template(FIREWALL, values))
    assert "policy drop;" in chain
    assert "meta l4proto udp accept" not in chain
    assert "meta l4proto tcp accept" not in chain
    peer = f'{"ip6" if ":" in address else "ip"} daddr {address} udp dport 51821 accept'
    for rule in ("meta skuid 0 udp sport 41641 accept", "meta skuid 0 udp dport 3478 accept", peer):
        assert (rule in chain) is enabled
    if not enabled:
        udp_rules = [line.strip() for line in chain.splitlines() if re.search(r"\budp\b", line)]
        assert udp_rules == ["udp dport 53 accept", "udp dport 123 accept"]


def test_canonical_firewall_retains_original_traffic_guard_before_established_accept():
    values = merge_render_vars()
    values["vpn"]["enable_split_hop_ingress"] = True
    values["firewall_egress_policy"] = "strict"
    chain = output_chain(render_template(FIREWALL, values))
    assert chain.index("ct direction original meta skuid") < chain.index("ct state established,related accept")
    assert f'oifname != {{ "lo", "{values["split_hop_ingress"]["wg_interface"]}" }} reject' in chain


def test_explicit_ingress_retirement_omits_shared_firewall_guard():
    values = merge_render_vars()
    values["vpn"]["enable_split_hop_ingress"] = True
    values["split_hop_ingress_role_enabled"] = False
    chain = output_chain(render_template(FIREWALL, values))
    assert "split-hop-ingress-boundary" not in chain
    assert "ct direction original meta skuid" not in chain


def test_first_policy_unit_check_mode_predicts_files_without_systemd(tmp_path):
    tasks = yaml.safe_load((INGRESS / "tasks/enable.yml").read_text())
    named = {task["name"]: task for task in tasks}
    template = dict(named["Install split-hop ingress boot policy loader"])
    template["ansible.builtin.template"] = {
        **template["ansible.builtin.template"],
        "src": str(INGRESS / "templates/split-hop-ingress-policy.service.j2"),
        "dest": str(tmp_path / "absent-policy.service"),
        "owner": str(os.getuid()), "group": str(os.getgid()),
    }
    loader = dict(named["Load and retain the ingress boundary before tunnel activation"])
    # Keep the production conditions. Any attempted service action fails locally
    # before systemd is called, including on hosts that have no service manager.
    loader.pop("ansible.builtin.systemd_service")
    loader["ansible.builtin.fail"] = {"msg": "systemd-mutation-sentinel"}
    loader["register"] = "policy_loader_result"
    play = [{"hosts": "all", "gather_facts": False, "vars": {
        "ansible_python_interpreter": sys.executable,
        "split_hop_ingress": {"manage_service": True, "wg_interface": "shop0"},
        "_split_hop_ingress_policy": {"changed": True},
    }, "tasks": [template, loader, {"name": "Check-mode boundary was observed",
        "ansible.builtin.assert": {"that": [
            "policy_loader_result is skipped",
            "_split_hop_ingress_policy_unit.changed",
        ]}}]}]
    playbook = tmp_path / "check-mode.yml"
    playbook.write_text(yaml.safe_dump(play))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nstdout_callback=default\nretry_files_enabled=False\n")
    result = subprocess.run([
        str(Path(sys.executable).parent / "ansible-playbook"), "-i", "localhost,",
        "-c", "local", "--check", str(playbook),
    ], cwd=tmp_path, env={**os.environ, "ANSIBLE_CONFIG": str(config),
                         "ANSIBLE_STDOUT_CALLBACK": "default"},
       text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Check-mode boundary was observed" in result.stdout
    assert not (tmp_path / "absent-policy.service").exists()


def test_retirement_check_mode_does_not_inspect_pre_convergence_rules(tmp_path):
    tasks = yaml.safe_load((INGRESS / "tasks/disable.yml").read_text())
    refusal = next(dict(task) for task in tasks
                   if task["name"] == "Refuse standalone retirement while the canonical firewall retains ingress")
    marker = tmp_path / "unexpected-live-inspection"
    # Keep the production command action and check-mode selection. If inspection
    # runs, the owned sentinel fails without reading host firewall state.
    refusal["ansible.builtin.command"] = {"argv": [sys.executable, "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).touch(); sys.exit(97)", str(marker)]}
    refusal["register"] = "retirement_refusal"
    play = [{"hosts": "all", "gather_facts": False, "vars": {
        "ansible_python_interpreter": sys.executable,
        "_split_hop_retire_nft": {"stat": {"exists": True}},
    }, "tasks": [refusal, {"name": "Retirement remains a prediction",
        "ansible.builtin.assert": {"that": ["retirement_refusal is skipped"]}}]}]
    playbook = tmp_path / "retirement-check.yml"
    playbook.write_text(yaml.safe_dump(play))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nstdout_callback=default\nretry_files_enabled=False\n")
    result = subprocess.run([
        str(Path(sys.executable).parent / "ansible-playbook"), "-i", "localhost,",
        "-c", "local", "--check", str(playbook),
    ], cwd=tmp_path, env={**os.environ, "ANSIBLE_CONFIG": str(config),
                         "ANSIBLE_STDOUT_CALLBACK": "default"},
       text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Retirement remains a prediction" in result.stdout
    assert not marker.exists()
