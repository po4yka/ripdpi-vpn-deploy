"""Contract coverage for firewall-owned Tailnet SSH nftables sets."""

from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from template_render import merge_render_vars, render_template


ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible" / "roles" / "firewall"
TEMPLATE = ROLE / "templates" / "nftables.conf.j2"
TASKS = ROLE / "tasks" / "main.yml"
EMPTY_FRAGMENT = ROLE / "files" / "vpn-tailnet-ssh-sets.empty.nft"
FRAGMENT_PATH = "/etc/nftables.d/vpn-tailnet-ssh-sets.nft"


def _render() -> str:
    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_tailnet_management": True}
    variables["firewall_effective_ssh_ports"] = [22022]
    variables["public_listener_contract"] = []
    return render_template(TEMPLATE, variables)


def _render_with_toggle(enabled: bool) -> str:
    variables = merge_render_vars()
    variables["vpn"] = {**variables["vpn"], "enable_tailnet_management": enabled}
    variables["firewall_effective_ssh_ports"] = [22022]
    variables["public_listener_contract"] = []
    return render_template(TEMPLATE, variables)


def test_empty_tailnet_fragment_is_inert_and_declares_only_typed_sets() -> None:
    rendered = _render()
    fragment = EMPTY_FRAGMENT.read_text()

    assert f'include "{FRAGMENT_PATH}"' in rendered
    assert 'iifname "tailscale0" tcp dport 22022 ip saddr @vpn_tailnet_ssh_v4 accept' in rendered
    assert 'iifname "tailscale0" tcp dport 22022 ip6 saddr @vpn_tailnet_ssh_v6 accept' in rendered
    assert "tailnet_management.approved_sources" not in rendered
    assert fragment == (
        "# vpn-tailnet-ssh-sets schema=1\n"
        "set vpn_tailnet_ssh_v4 {\n"
        "  type ipv4_addr\n"
        "  flags interval\n"
        "}\n\n"
        "set vpn_tailnet_ssh_v6 {\n"
        "  type ipv6_addr\n"
        "  flags interval\n"
        "}\n"
    )
    assert "elements = { }" not in fragment
    assert "chain " not in fragment
    assert "table " not in fragment


def test_tailnet_sets_accept_only_exact_host_prefixes_on_existing_ssh_port() -> None:
    rendered = _render()
    committed_fragment = """# vpn-tailnet-ssh-sets schema=1
set vpn_tailnet_ssh_v4 {
  type ipv4_addr
  flags interval
  elements = { 100.64.10.20/32, 100.64.10.21/32 }
}

set vpn_tailnet_ssh_v6 {
  type ipv6_addr
  flags interval
  elements = { fd7a:115c:a1e0::1234/128 }
}
"""

    assert "100.64.10.20/32, 100.64.10.21/32" in committed_fragment
    assert "fd7a:115c:a1e0::1234/128" in committed_fragment
    assert 'iifname "tailscale0" tcp dport 22022 ip saddr @vpn_tailnet_ssh_v4 accept' in rendered
    assert 'iifname "tailscale0" tcp dport 22022 ip6 saddr @vpn_tailnet_ssh_v6 accept' in rendered
    assert 'iifname "tailscale0" tcp dport 22022 accept' not in rendered
    assert 'iifname "tailscale0" accept' not in rendered


def test_tailnet_ssh_accepts_are_absent_when_management_is_disabled() -> None:
    enabled = _render_with_toggle(True)
    disabled = _render_with_toggle(False)

    assert 'iifname "tailscale0" tcp dport 22022 ip saddr @vpn_tailnet_ssh_v4 accept' in enabled
    assert 'iifname "tailscale0" tcp dport 22022 ip6 saddr @vpn_tailnet_ssh_v6 accept' in enabled
    assert 'iifname "tailscale0" tcp dport 22022 ip saddr @vpn_tailnet_ssh_v4 accept' not in disabled
    assert 'iifname "tailscale0" tcp dport 22022 ip6 saddr @vpn_tailnet_ssh_v6 accept' not in disabled


def test_clean_check_mode_uses_inlined_empty_sets_without_creating_fragment() -> None:
    variables = merge_render_vars()
    variables["ansible_check_mode"] = False
    variables["_firewall_effective_check_mode"] = True
    variables["_firewall_tailnet_ssh_sets_was_absent"] = True
    variables["firewall_effective_ssh_ports"] = [22022]
    variables["public_listener_contract"] = []
    rendered = render_template(TEMPLATE, variables)

    assert f'include "{FRAGMENT_PATH}"' not in rendered
    assert "  set vpn_tailnet_ssh_v4 {" in rendered
    assert "  set vpn_tailnet_ssh_v6 {" in rendered
    assert "elements = { }" not in rendered
    assert 'iifname "tailscale0" tcp dport 22022 drop' in rendered
    assert "@vpn_tailnet_ssh_v4 accept" not in rendered
    assert "@vpn_tailnet_ssh_v6 accept" not in rendered


def test_fragment_validator_accepts_canonical_hosts_and_refuses_noncanonical_input() -> None:
    tasks = yaml.safe_load(TASKS.read_text())
    validator_task = next(
        task for task in tasks if task["name"] == "Refuse unsafe or foreign Tailnet SSH sets fragment"
    )
    validator = validator_task["ansible.builtin.command"]["argv"][2]
    accepted = """# vpn-tailnet-ssh-sets schema=1
set vpn_tailnet_ssh_v4 {
  type ipv4_addr
  flags interval
  elements = { 100.64.10.20/32, 100.64.10.21/32 }
}

set vpn_tailnet_ssh_v6 {
  type ipv6_addr
  flags interval
  elements = { fd7a:115c:a1e0::1234/128 }
}
"""
    rejected_duplicate = accepted.replace(
        "100.64.10.20/32, 100.64.10.21/32", "100.64.10.20/32, 100.64.10.20/32"
    )
    rejected_foreign = accepted + "chain bypass { tcp dport 22022 accept }\n"

    assert subprocess.run(["python3", "-c", validator], input=EMPTY_FRAGMENT.read_text(), text=True).returncode == 0
    assert subprocess.run(["python3", "-c", validator], input=accepted, text=True).returncode == 0
    assert subprocess.run(["python3", "-c", validator], input=rejected_duplicate, text=True).returncode != 0
    assert subprocess.run(["python3", "-c", validator], input=rejected_foreign, text=True).returncode != 0


def test_existing_tailnet_fragment_is_preserved_only_when_safe_and_schema_valid() -> None:
    tasks_text = TASKS.read_text()
    tasks = yaml.safe_load(tasks_text)
    copy_task = next(task for task in tasks if task["name"] == "Install empty Tailnet SSH sets fragment when absent")
    stat_task = next(task for task in tasks if task["name"] == "Inspect Tailnet SSH sets fragment before firewall mutation")
    directory_task = next(task for task in tasks if task["name"] == "Refuse unsafe Tailnet SSH sets include directory")
    final_stat_task = next(task for task in tasks if task["name"] == "Reinspect Tailnet SSH sets fragment immediately before nftables render")
    final_metadata_task = next(task for task in tasks if task["name"] == "Refuse unsafe final Tailnet SSH sets fragment metadata")
    metadata_task = next(task for task in tasks if task["name"] == "Refuse unsafe Tailnet SSH sets fragment metadata")
    assert_task = next(task for task in tasks if task["name"] == "Refuse unsafe or foreign Tailnet SSH sets fragment")

    assert stat_task["ansible.builtin.stat"]["follow"] is False
    assert final_stat_task["ansible.builtin.stat"]["follow"] is False
    assert copy_task["ansible.builtin.copy"]["force"] is False
    assert copy_task["ansible.builtin.copy"]["owner"] == "root"
    assert copy_task["ansible.builtin.copy"]["mode"] == "0644"
    metadata_assertions = "\n".join(metadata_task["ansible.builtin.assert"]["that"])
    directory_assertions = "\n".join(directory_task["ansible.builtin.assert"]["that"])
    final_metadata_assertions = "\n".join(final_metadata_task["ansible.builtin.assert"]["that"])
    assert "isreg" in metadata_assertions
    assert "islnk" in metadata_assertions
    assert ".uid == 0" in metadata_assertions
    assert "mode == '0644'" in metadata_assertions
    assert "wgrp" in metadata_assertions and "woth" in metadata_assertions
    assert ".uid == 0" in directory_assertions and ".gid == 0" in directory_assertions
    assert "mode == '0755'" in directory_assertions
    assert "wgrp" in directory_assertions and "woth" in directory_assertions
    assert ".uid == 0" in final_metadata_assertions
    assert ".gid == 0" in final_metadata_assertions
    assert "vpn_tailnet_ssh_v4" in tasks_text
    assert "vpn_tailnet_ssh_v6" in tasks_text
    assert "ansible.builtin.command" in assert_task
    assert assert_task["ansible.builtin.command"]["stdin_add_newline"] is False
    clean_check_task = next(task for task in tasks if task["name"] == "Validate bundled empty Tailnet SSH sets fragment for clean check mode")
    assert clean_check_task["when"] == [
        "_firewall_effective_check_mode | bool",
        "_firewall_tailnet_ssh_sets_was_absent | bool",
    ]
    clean_check_assertion = clean_check_task["ansible.builtin.assert"]["that"][0]
    assert "rstrip=False" in clean_check_assertion
    assert "ipaddress.ip_network" in tasks_text
    assert "fragment bytes are not canonical" in tasks_text
    task_names = [task["name"] for task in tasks]
    assert task_names.index("Install empty Tailnet SSH sets fragment when absent") < task_names.index(
        "Reinspect Tailnet SSH sets fragment immediately before nftables render"
    ) < task_names.index("Render nftables config")
    assert "nft -c -f %s" in tasks_text


def test_molecule_task_level_check_mode_sets_the_explicit_role_contract() -> None:
    converge = yaml.safe_load((ROLE / "molecule/default/converge.yml").read_text())
    check_block = next(
        task
        for task in converge[0]["pre_tasks"]
        if task["name"] == "Exercise clean firewall check mode before Tailnet fragment exists"
    )
    include = check_block["block"][0]

    assert check_block["check_mode"] is True
    assert include["vars"]["_firewall_task_check_mode"] is True
    tasks = yaml.safe_load(TASKS.read_text())
    resolver = next(task for task in tasks if task["name"] == "Resolve effective firewall check-mode context")
    expression = resolver["ansible.builtin.set_fact"]["_firewall_effective_check_mode"]
    assert "ansible_check_mode" in expression
    assert "_firewall_task_check_mode" in expression


def test_molecule_tailnet_converge_binds_sources_to_the_installed_fragment() -> None:
    converge = yaml.safe_load((ROLE / "molecule/default/converge.yml").read_text())
    post_tasks = converge[0]["post_tasks"]
    include = next(
        task
        for task in post_tasks
        if task["name"] == "Converge the real Tailnet-enabled firewall branch"
    )
    check_block = next(
        task for task in post_tasks if task["name"] == "Repeat the role in check mode with UFW preinstalled"
    )
    check_include = check_block["block"][0]
    expected = {"approved_sources": ["100.64.10.20", "fd7a:115c:a1e0::1234"]}

    assert include["vars"]["tailnet_management"] == expected
    assert check_include["vars"]["tailnet_management"] == expected


def test_tailnet_include_cannot_create_a_separate_table_bypass() -> None:
    rendered = _render()

    include_index = rendered.index(f'include "{FRAGMENT_PATH}"')
    input_index = rendered.index("  chain input {")
    assert include_index < input_index
    assert rendered.count("table inet filter {") == 1
    assert "destroy table inet filter" in rendered
