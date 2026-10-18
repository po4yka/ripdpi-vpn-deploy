"""Real zero-checksum DNS traffic through the canonical AWG/NAT policy."""

import json
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import time
import uuid

import pytest

from native_common import ROOT
from awg_client import config, export
from awg_device_binding import resolve_binding
from template_render import merge_render_vars, render_template
from test_awg_device_binding import document
from test_awg_device_binding_native import native_config
from test_awg_dualstack_native import ECHO
from test_transport_semantics_native import command, exact_awg_sources

pytestmark = pytest.mark.native_runtime

QUERY = bytes.fromhex("174201000001000000000000056f776e6564076578616d706c6500001c0001")
SOURCE = "fd42:11::2"
DESTINATION = "fd88::2"


def checksum(port):
    udp = struct.pack("!HHHH", port, 53, 8 + len(QUERY), 0) + QUERY
    packet = (socket.inet_pton(socket.AF_INET6, SOURCE) + socket.inet_pton(socket.AF_INET6, DESTINATION)
              + struct.pack("!I3xB", len(udp), 17) + udp)
    packet += bytes(len(packet) % 2)
    total = sum(struct.unpack("!" + "H" * (len(packet) // 2), packet))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


CAPTURE = r'''
import json,socket,struct,sys,time
query=bytes.fromhex(sys.argv[2]); records=[]
source=socket.inet_pton(socket.AF_INET6,'fd42:11::2')
destination=socket.inet_pton(socket.AF_INET6,'fd88::2')
with socket.socket(socket.AF_PACKET,socket.SOCK_DGRAM,socket.htons(0x86dd)) as capture:
    capture.setsockopt(263,8,1)  # SOL_PACKET, PACKET_AUXDATA
    capture.bind((sys.argv[1],0)); capture.settimeout(.5)
    print('ready',flush=True)
    deadline=time.monotonic()+20
    while len(records)<6 and time.monotonic()<deadline:
        try: packet,auxiliary,flags,peer=capture.recvmsg(65535,1024)
        except socket.timeout: continue
        if (len(packet)<48 or packet[0]>>4!=6 or packet[6]!=17
            or packet[8:24]!=source or packet[24:40]!=destination): continue
        port,dest,length,check=struct.unpack('!HHHH',packet[40:48])
        if port not in (37737,37738) or dest!=53 or packet[48:]!=query: continue
        status=next((struct.unpack_from('=I',value)[0] for level,kind,value in auxiliary if level==263 and kind==8),None)
        assert status is not None and not status&8, 'completed-checksum-required'
        pseudo=source+destination+struct.pack('!I3xB',length,17)+packet[40:]
        pseudo+=bytes(len(pseudo)%2)
        total=sum(struct.unpack('!'+'H'*(len(pseudo)//2),pseudo))
        while total>>16: total=(total&65535)+(total>>16)
        assert total==65535 and check==(65535 if port==37737 else 65534), 'UDP-checksum-invalid'
        records.append({'port':port,'checksum':check,'checksum_not_ready':False})
    assert len(records)==6, 'owned-packet-capture-incomplete'
    print(json.dumps(records),flush=True)
'''

PROBE = r'''
import json,socket,sys
query=bytes.fromhex(sys.argv[1]); received={}
for port in (37737,37738):
    with socket.socket(socket.AF_INET6,socket.SOCK_DGRAM) as stream:
        stream.settimeout(3); stream.bind(('fd42:11::2',port)); stream.connect(('fd88::2',53))
        received[str(port)]=0
        for _ in range(3):
            stream.send(query); response=stream.recv(4096)
            assert response[:2]==query[:2] and response[6:8]==b'\0\1'
            assert response.endswith(socket.inet_pton(socket.AF_INET6,'fd88::2'))
            received[str(port)]+=1
print(json.dumps(received))
'''


def test_computed_zero_udp_checksum_keeps_ffff_and_real_dns_reply(tmp_path):
    assert len(QUERY) == 31 and checksum(37737) == 0 and checksum(37738) == 65534
    go, tools = exact_awg_sources()
    token = uuid.uuid4().hex[:7]
    server, client, uplink = (prefix + token for prefix in ("zs", "zc", "zu"))
    server_tun, client_tun = "zt" + token, "zx" + token
    namespaces, processes = [], []

    def run(namespace, argv, data=None):
        return command(["ip", "netns", "exec", namespace, *map(str, argv)], data=data)

    def address(namespace, interface, value):
        command(["ip", "-n", namespace, "address", "add", value, "dev", interface,
                 *(["nodad"] if ":" in value else [])])

    def veth(left_ns, right_ns, left, right):
        command(["ip", "link", "add", left, "type", "veth", "peer", "name", right])
        for namespace, interface in ((left_ns, left), (right_ns, right)):
            command(["ip", "link", "set", interface, "netns", namespace])
            command(["ip", "-n", namespace, "link", "set", interface, "mtu", "1380", "up"])

    def start(namespace, argv, *, output=False):
        process = subprocess.Popen(["ip", "netns", "exec", namespace, *map(str, argv)],
                                   stdout=subprocess.PIPE if output else subprocess.DEVNULL,
                                   stderr=subprocess.PIPE if output else subprocess.DEVNULL, text=True)
        processes.append(process)
        return process

    def checksum_errors():
        fields = dict(line.split() for line in run(uplink, ["cat", "/proc/net/snmp6"]).splitlines())
        return int(fields["Udp6InCsumErrors"])

    try:
        for namespace in (server, client, uplink):
            command(["ip", "netns", "add", namespace]); namespaces.append(namespace)
            command(["ip", "-n", namespace, "link", "set", "lo", "up"])
        veth(server, uplink, "up0", "echo0")
        veth(server, client, "us0", "uc0")
        for namespace, interface, values in (
            (server, "up0", ("198.18.1.1/30", "fd88::1/64")),
            (uplink, "echo0", ("198.18.1.2/30", "fd88::2/64")),
            (server, "us0", ("192.0.2.1/30",)), (client, "uc0", ("192.0.2.2/30",)),
        ):
            for value in values: address(namespace, interface, value)
        for setting in ("net.ipv4.ip_forward=1", "net.ipv6.conf.all.forwarding=1"):
            run(server, ["sysctl", "-qw", setting])

        doc = document()
        instance = doc["amneziawg_secrets"]["instances"][1]
        instance.update(name=server_tun, mtu=1280, jc=0)
        doc["amneziawg_secrets"]["instances"] = [instance]
        doc["client_registry"] = {"device1": doc["client_registry"]["device1"]}
        doc["client_registry"]["device1"]["awg_binding"]["instance"] = server_tun
        selected = resolve_binding(doc, {}, "device1", "upcloud:fixture", server_tun)
        block = export(doc, {}, "device1", "upcloud:fixture", server_tun, "192.0.2.1")
        values = merge_render_vars(); values["_inst"] = selected.instance
        configs = (
            (server, server_tun, render_template(ROOT / "ansible/roles/amneziawg/templates/awg0.conf.j2", values),
             [instance["address_v4"], instance["address_v6"]]),
            (client, client_tun, config(block).replace("<CLIENT_PRIVATE_KEY>", doc["client_registry"]["device1"]["awg_private_key"]),
             block["address"]),
        )
        for namespace, interface, text, addresses in configs:
            daemon = start(namespace, [go, "-f", interface])
            deadline = time.monotonic() + 10
            while subprocess.run(["ip", "-n", namespace, "link", "show", interface], capture_output=True).returncode:
                assert daemon.poll() is None and time.monotonic() < deadline, "owned-AWG-TUN-unavailable"
                time.sleep(.05)
            candidate = tmp_path / (interface + ".conf")
            candidate.write_text(native_config(text)); candidate.chmod(0o600)
            run(namespace, [tools, "setconf", interface, candidate])
            for value in addresses: address(namespace, interface, value)
            command(["ip", "-n", namespace, "link", "set", interface, "mtu", "1280", "up"])
        command(["ip", "-n", client, "route", "add", "default", "via", "192.0.2.1", "dev", "uc0", "metric", "200"])
        for family in ("-4", "-6"):
            command(["ip", "-n", client, family, "route", "add", "default", "dev", client_tun, "metric", "10"])
        run(client, ["nft", "-f", "-"], f'''table inet lockdown {{ chain output {{
          type filter hook output priority 100; policy drop;
          oifname "lo" accept
          oifname "{client_tun}" accept
          oifname "uc0" ip daddr 192.0.2.1 udp dport {instance['listen_port']} accept
          meta l4proto ipv6-icmp icmpv6 type {{ nd-neighbor-solicit, nd-neighbor-advert }} ip6 hoplimit 255 accept
        }} }}\n''')
        values = merge_render_vars()
        values.update(amneziawg_secrets=doc["amneziawg_secrets"], firewall_awg_uplink_interface="up0",
                      security_controls={"fail2ban": False}, public_listener_contract=[
                          {"name": server_tun, "protocol": "udp", "port": instance["listen_port"], "port_range": None}],
                      _firewall_effective_check_mode=True, _firewall_tailnet_ssh_sets_was_absent=True,
                      _firewall_tailnet_initial_fragment=(ROOT / "ansible/roles/firewall/files/vpn-tailnet-ssh-sets.empty.nft").read_text())
        values["vpn"] = {key: False for key in values["vpn"] if key.startswith("enable_")}
        values["vpn"]["enable_amneziawg"] = True
        firewall = render_template(ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", values)
        run(server, ["nft", "-c", "-f", "-"], firewall)
        run(server, ["nft", "-f", "-"], firewall)
        start(uplink, [sys.executable, "-c", ECHO, DESTINATION])
        deadline = time.monotonic() + 5
        while ":53 " not in run(uplink, ["ss", "-lnu"]):
            assert time.monotonic() < deadline, "owned-DNS-listener-unavailable"
            time.sleep(.05)
        captured = start(server, [sys.executable, "-c", CAPTURE, server_tun, QUERY.hex()], output=True)
        assert select.select([captured.stdout], [], [], 5)[0], "owned-packet-capture-unavailable"
        assert captured.stdout.readline().strip() == "ready"
        errors = checksum_errors()
        observed = json.loads(run(client, [sys.executable, "-c", PROBE, QUERY.hex()]))
        assert observed == {"37737": 3, "37738": 3}
        output, diagnostics = captured.communicate(timeout=5)
        assert captured.returncode == 0, "owned-UDP-checksum-capture-refused: " + diagnostics[-1000:]
        records = json.loads(output)
        assert sorted(row["port"] for row in records) == [37737] * 3 + [37738] * 3
        assert checksum_errors() == errors, "upstream-UDP-checksum-error"
        print(json.dumps({"zero_checksum": "ffff", "control_checksum": "fffe", "replies": observed,
                          "checksum_errors": 0, "completed_packets": len(records)}))
    finally:
        for process in reversed(processes):
            if process.poll() is None: process.terminate()
        for process in reversed(processes):
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        for namespace in reversed(namespaces): command(["ip", "netns", "delete", namespace])
        remaining = command(["ip", "netns", "list"])
        assert all(namespace not in remaining for namespace in namespaces)
