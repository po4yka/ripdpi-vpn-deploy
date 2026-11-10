"""The failsafe ruleset keeps management reachable and nothing else."""

from pathlib import Path

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/firewall"


def render(*, tailnet):
    values = merge_render_vars()
    values.update(allowed_ssh_cidrs=["203.0.113.7/32", "2001:db8::7/128"], firewall_effective_ssh_ports=[2222])
    values["vpn"] = {**values["vpn"], "enable_tailnet_management": tailnet}
    return render_template(ROLE / "templates/nftables-failsafe.nft.j2", values)


def test_failsafe_drops_inbound_and_accepts_only_the_management_path():
    result = render(tailnet=False)
    rules = [line.strip() for line in result.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert "policy drop;" in rules
    assert "tcp dport 2222 ip saddr { 203.0.113.7/32 } accept" in rules
    assert "tcp dport 2222 ip6 saddr { 2001:db8::7/128 } accept" in rules
    assert "tailscale0" not in result
    # No listener port, forward or output chain: only SSH and control traffic is admitted.
    assert [rule for rule in rules if "dport" in rule and "2222" not in rule] == [
        "udp sport 67 udp dport 68 accept", "ip6 saddr fe80::/10 udp sport 547 udp dport 546 accept"]
    assert result.count("chain ") == 1


def test_failsafe_keeps_tailnet_ssh_when_tailnet_management_is_enabled():
    result = render(tailnet=True)
    assert 'iifname "tailscale0" tcp dport 2222 ip saddr 100.64.0.0/10 accept' in result
    assert 'iifname "tailscale0" tcp dport 2222 ip6 saddr fd7a:115c:a1e0::/48 accept' in result


def test_failed_load_triggers_the_failsafe_and_a_successful_load_removes_it():
    drop_in = (ROLE / "files/nftables-preserve-policy.conf").read_text().splitlines()
    assert "OnFailure=vpn-nftables-failsafe.service" in drop_in
    unit = (ROLE / "files/vpn-nftables-failsafe.service").read_text().splitlines()
    assert "ExecStart=/usr/sbin/nft -f /etc/nftables-failsafe.nft" in unit
    main = (ROLE / "templates/nftables.conf.j2").read_text().splitlines()
    assert "destroy table inet vpn_failsafe" in main
    assert main.index("destroy table inet vpn_failsafe") < main.index("destroy table inet nat")
