"""Apply the complete canonical firewall twice while retaining real Hysteria traffic."""
from copy import deepcopy
from pathlib import Path
import time

import pytest

from scripts.template_render import render_template
from test_xhttp_endpoint_contract_native import fixture

pytestmark = pytest.mark.native_runtime
ROOT = Path(__file__).resolve().parents[2]


def test_complete_firewall_range_retirement_preserves_foreign_rules_and_listener():
    stack = fixture.NativeStack()
    try:
        stack.start()
        stack.start_hysteria()
        client = stack.start_client("hysteria")
        time.sleep(.5)
        stack.run_driver(client)
        values = deepcopy(stack.values)
        values["vpn"] = {key: False for key in values["vpn"]}
        values["vpn"].update(enable_hysteria=True, enable_transport_egress=True)
        values["security_controls"]["fail2ban"] = False
        values.update(hysteria_port_range="46000-46015", firewall_egress_policy="permissive",
            _firewall_effective_check_mode=True, _firewall_tailnet_ssh_sets_was_absent=True,
            _firewall_tailnet_initial_fragment=("set vpn_tailnet_ssh_v4 { type ipv4_addr; flags interval; }\n"
                                               "set vpn_tailnet_ssh_v6 { type ipv6_addr; flags interval; }"))
        prefix = ["ip", "netns", "exec", stack.namespace, "nft"]
        fixture.command(prefix + ["add", "table", "inet", "foreign_retained"])
        def converge():
            config = stack.file("complete-firewall.nft", render_template(
                ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", values))
            fixture.command(prefix + ["--check", "--file", str(config)])
            fixture.command(prefix + ["--file", str(config)])
            return fixture.command(prefix + ["list", "ruleset"])
        active = converge()
        assert 'comment "hysteria-port-hopping"' in active
        values["hysteria_port_range"] = ""
        for _ in range(2):
            retired = converge()
            assert "hysteria-port-hopping" not in retired
            assert "table inet foreign_retained" in retired
            stack.run_driver(client)
    finally:
        stack.close()
