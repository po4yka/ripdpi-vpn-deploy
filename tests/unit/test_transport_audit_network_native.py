"""Actual overlay-only strict egress in owned Linux network namespaces."""
from __future__ import annotations

import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import uuid

import pytest

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


@pytest.mark.parametrize("family", [4, 6])
def test_overlay_only_strict_udp_packets_and_disabled_control(family):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires disposable Linux root network namespaces")
    if not all(shutil.which(tool) for tool in ("ip", "nft")):
        pytest.skip("requires real iproute2 and nftables")
    stem = "aud" + uuid.uuid4().hex[:8]
    source, peer = stem + "s", stem + "p"
    created = []
    echo = None

    def command(*args, data=None):
        result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=15)
        assert result.returncode == 0, result.stderr
        return result.stdout

    def ns(namespace, *args, data=None):
        return command("ip", "netns", "exec", namespace, *args, data=data)

    def probe(destination, port, source_port, *, allowed, uid=0):
        # Distinct tuples prevent an earlier accepted datagram from granting
        # an established conntrack exemption to a later negative case.
        script = """
import os,socket,sys
family,address,port,source_port,uid=sys.argv[1:]
os.setgid(int(uid));os.setuid(int(uid))
s=socket.socket(socket.AF_INET6 if family=='6' else socket.AF_INET,socket.SOCK_DGRAM)
s.bind(('::' if family=='6' else '0.0.0.0',int(source_port)));s.settimeout(2)
try:
 s.sendto(b'owned-overlay-packet',(address,int(port)))
 data,remote=s.recvfrom(64)
 assert data==b'owned-overlay-packet'
 assert remote[0]==address, 'unexpected echo source: '+remote[0]
except OSError:
 raise SystemExit(3)
"""
        result = subprocess.run(
            ["ip", "netns", "exec", source, sys.executable, "-c", script,
             str(family), destination, str(port), str(source_port), str(uid)],
            text=True, capture_output=True, timeout=5,
        )
        assert result.returncode == (0 if allowed else 3), result.stderr

    try:
        for namespace in (source, peer):
            command("ip", "netns", "add", namespace)
            created.append(namespace)
            ns(namespace, "ip", "link", "set", "lo", "up")
        ns(source, "ip", "link", "add", "uplink", "type", "veth", "peer", "name", "peerlink", "netns", peer)
        addresses = ("198.18.0.1", "198.18.0.2", "198.18.0.3") if family == 4 else (
            "fd91::1", "fd91::2", "fd91::3")
        for namespace, interface, address in ((source, "uplink", addresses[0]),
                                               (peer, "peerlink", addresses[1]),
                                               (peer, "peerlink", addresses[2])):
            argv = ["ip", "addr", "add", address + ("/29" if family == 4 else "/64"), "dev", interface]
            if family == 6:
                argv.append("nodad")
            ns(namespace, *argv)
            ns(namespace, "ip", "link", "set", interface, "up")
        server = """
import select,socket,sys
family=int(sys.argv[1]);sockets=[]
for address in sys.argv[2:]:
 for port in (3478,51821,18081,18082,18083,18084):
  s=socket.socket(socket.AF_INET6 if family==6 else socket.AF_INET,socket.SOCK_DGRAM)
  s.bind((address,port));sockets.append(s)
print('ready',flush=True)
while True:
 for s in select.select(sockets,[],[])[0]:
  data,remote=s.recvfrom(4096);s.sendto(data,remote)
"""
        echo = subprocess.Popen(
            ["ip", "netns", "exec", peer, sys.executable, "-c", server,
             str(family), *addresses[1:]],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert select.select([echo.stdout], [], [], 5)[0], "owned UDP listeners unavailable"
        assert echo.stdout.readline().strip() == "ready"
        # Prove both listeners retain their destination as the reply source.
        probe(addresses[1], 51821, 40999, allowed=True)
        probe(addresses[2], 51821, 41000, allowed=True)
        values = merge_render_vars()
        values["vpn"] = {key: False for key in values["vpn"] if key.startswith("enable_")}
        values.update(
            firewall_egress_policy="strict", security_controls={"fail2ban": False},
            _firewall_effective_check_mode=True,
            _firewall_tailnet_ssh_sets_was_absent=True,
            _firewall_tailnet_initial_fragment=(
                ROOT / "ansible/roles/firewall/files/vpn-tailnet-ssh-sets.empty.nft"
            ).read_text(),
        )
        values["ansible_facts"]["default_ipv4"]["interface"] = "uplink"
        values["ansible_facts"]["default_ipv6"] = {"interface": "uplink"}
        values["split_hop_egress_secrets"]["node_a_public_ip"] = addresses[1]
        values["split_hop_egress"]["peer_listen_port"] = 51821

        def load(enabled):
            values["vpn"].update(enable_tailnet_management=enabled, enable_split_hop_egress=enabled)
            rendered = render_template(ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", values)
            ns(source, "nft", "-c", "-f", "-", data=rendered)
            ns(source, "nft", "-f", "-", data=rendered)

        load(True)
        probe(addresses[1], 18081, 41641, allowed=True)
        probe(addresses[1], 3478, 41001, allowed=True)
        probe(addresses[1], 51821, 41002, allowed=True)
        probe(addresses[1], 18084, 41003, allowed=False)
        probe(addresses[2], 51821, 41004, allowed=False)
        probe(addresses[1], 18083, 41641, allowed=False, uid=65532)
        probe(addresses[1], 3478, 41005, allowed=False, uid=65532)
        load(False)
        probe(addresses[1], 18082, 41641, allowed=False)
        probe(addresses[1], 3478, 41006, allowed=False)
        probe(addresses[1], 51821, 41007, allowed=False)
        assert echo.poll() is None, "owned UDP listeners exited during refusal checks"
    finally:
        if echo is not None:
            echo.terminate()
            try:
                echo.wait(timeout=3)
            except subprocess.TimeoutExpired:
                echo.kill()
                echo.wait(timeout=3)
        for namespace in reversed(created):
            command("ip", "netns", "delete", namespace)
