"""Real UDP through the complete rendered firewall in owned Linux namespaces."""

import json
import os
from pathlib import Path
import secrets
import select
import subprocess
import sys

import pytest

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.native_runtime


def run(*args, data=None):
    return subprocess.run(args, input=data, capture_output=True, text=True,
                          timeout=15, check=True).stdout


RECEIVER = """
import json,socket,sys
interface,address,port,multicast=sys.argv[1:]
s=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,interface.encode()+b'\\0')
s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind((address,int(port),0,socket.if_nametoindex(interface) if address.startswith('fe80') else 0))
if multicast == 'yes':
 import struct
 s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_JOIN_GROUP,
              socket.inet_pton(socket.AF_INET6,'ff02::1:2')+struct.pack('@I',socket.if_nametoindex(interface)))
s.settimeout(.7)
print('ready',flush=True)
try:
 data,peer=s.recvfrom(128)
 print(json.dumps([data.decode(),peer[0],peer[1]]),flush=True)
except TimeoutError:
 print('null',flush=True)
"""

SENDER = """
import socket,sys
interface,source,sport,target,dport=sys.argv[1:]
s=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM)
index=socket.if_nametoindex(interface)
s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,interface.encode()+b'\\0')
s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_MULTICAST_IF,index)
s.bind((source,int(sport),0,index if source.startswith('fe80') else 0))
s.sendto(b'dhcpv6-regression',(target,int(dport),0,index if target.startswith(('fe80','ff02')) else 0))
"""


def packet(sender, receiver, *, source="fe80::20", target="fe80::10",
           sport=547, dport=546, send_interface="peer0", receive_interface="up0"):
    listener = subprocess.Popen(
        ["ip", "netns", "exec", receiver, sys.executable, "-c", RECEIVER,
         receive_interface, "::" if target.startswith("ff02") else target,
         str(dport), "yes" if target.startswith("ff02") else "no"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert select.select([listener.stdout], [], [], 3)[0], "dhcpv6-receiver-timeout"
        assert listener.stdout.readline().strip() == "ready", "dhcpv6-receiver-not-ready"
        run("ip", "netns", "exec", sender, sys.executable, "-c", SENDER,
            send_interface, source, str(sport), target, str(dport))
        output, error = listener.communicate(timeout=3)
        assert listener.returncode == 0, error
        received = json.loads(output)
        if received is not None:
            assert received[0] == "dhcpv6-regression"
        return received
    finally:
        if listener.poll() is None:
            listener.kill()
            listener.communicate(timeout=3)


def test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server():
    assert sys.platform == "linux" and os.geteuid() == 0, "isolated-Linux-root-required"
    token = "dh" + secrets.token_hex(4)
    client, peer = token + "c", token + "p"
    namespaces = []
    try:
        for namespace in (client, peer):
            run("ip", "netns", "add", namespace)
            namespaces.append(namespace)
            run("ip", "-n", namespace, "link", "set", "lo", "up")
        for index, (left, right) in enumerate((("up0", "peer0"), ("wrong0", "other0"))):
            run("ip", "-n", client, "link", "add", left, "type", "veth",
                "peer", "name", right, "netns", peer)
            for namespace, name, local in (
                (client, left, "10" if index == 0 else "30"),
                (peer, right, "20" if index == 0 else "40"),
            ):
                run("ip", "-n", namespace, "addr", "add", "fe80::" + local + "/64", "dev", name, "nodad")
                run("ip", "-n", namespace, "addr", "add", "fd42:" + str(index) + "::" + local + "/64", "dev", name, "nodad")
                run("ip", "-n", namespace, "link", "set", name, "up")
        run("ip", "-n", client, "-6", "route", "add", "ff02::/16", "dev", "up0")
        values = merge_render_vars()
        values.update(
            ansible_facts={"default_ipv4": {"interface": "up0"}},
            firewall_egress_policy="strict",
            firewall_dhcpv6_uplink_interface="",
            firewall_dhcpv6_server_addresses=[],
            public_listener_contract=[], security_controls={"fail2ban": False},
            _firewall_effective_check_mode=True,
            _firewall_tailnet_ssh_sets_was_absent=True,
            _firewall_tailnet_initial_fragment=(ROOT / "ansible/roles/firewall/files/vpn-tailnet-ssh-sets.empty.nft").read_text(),
        )
        values["vpn"] = {key: False for key in values["vpn"]}

        def publish():
            rendered = render_template(ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", values)
            run("ip", "netns", "exec", client, "nft", "-c", "-f", "-", data=rendered)
            run("ip", "netns", "exec", client, "nft", "-f", "-", data=rendered)

        publish()
        # Reply has no matching multicast reverse tuple and must pass independently.
        assert packet(peer, client)
        assert packet(client, peer, source="fe80::10", target="ff02::1:2", sport=546,
                      dport=547, send_interface="up0", receive_interface="peer0")
        run("ip", "-n", peer, "addr", "add", "fe80::21/64", "dev", "peer0", "nodad")
        assert packet(client, peer, source="fe80::10", target="fe80::21", sport=546,
                      dport=547, send_interface="up0", receive_interface="peer0")
        assert packet(peer, client, source="fe80::40", target="fe80::30",
                      send_interface="other0", receive_interface="wrong0") is None
        assert packet(peer, client, sport=548) is None
        assert packet(peer, client, dport=545) is None
        assert packet(client, peer, source="fe80::30", target="fe80::40", sport=546,
                      dport=547, send_interface="wrong0", receive_interface="other0") is None
        assert packet(peer, client, source="fd42:0::20", target="fd42:0::10") is None
        run("ip", "-n", peer, "addr", "add", "fd42::22/64", "dev", "peer0", "nodad")
        assert packet(client, peer, source="fd42::10", target="fd42::22", sport=546,
                      dport=547, send_interface="up0", receive_interface="peer0") is None
        values["firewall_dhcpv6_server_addresses"] = ["fd42::20", "fd42::22"]
        publish()
        assert packet(peer, client, source="fd42:0::20", target="fd42:0::10")
        assert packet(client, peer, source="fd42:0::10", target="fd42::22", sport=546,
                      dport=547, send_interface="up0", receive_interface="peer0")
        # Another global source on the same uplink does not inherit that authority.
        run("ip", "-n", peer, "addr", "add", "fd42::21/64", "dev", "peer0", "nodad")
        assert packet(peer, client, source="fd42::21", target="fd42::10") is None
    finally:
        failures = []
        for namespace in reversed(namespaces):
            try:
                run("ip", "netns", "delete", namespace)
            except subprocess.SubprocessError:
                failures.append(namespace)
        if failures:
            raise RuntimeError("dhcpv6-owned-namespace-cleanup-refused")
