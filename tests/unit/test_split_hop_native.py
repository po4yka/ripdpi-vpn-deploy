"""Real WireGuard packet paths in disposable Linux network namespaces."""

from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import select
import subprocess
import sys
import time
import uuid

import pytest

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def command(*argv, data=None):
    return subprocess.run(
        argv, input=data, text=True, capture_output=True, check=True, timeout=15
    ).stdout


def test_ipv4_exits_b_replies_a_and_owned_ipv6_cannot_leak(tmp_path):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires owned root Linux network namespaces")
    for tool in ("ip", "wg", "nft", "curl"):
        if not shutil.which(tool):
            pytest.skip(f"requires {tool}")
    stem = "p2-hop-" + uuid.uuid4().hex[:7]
    names = {n: stem + n for n in "abce"}
    children = []

    def ns(n, *argv, data=None):
        return command("ip", "netns", "exec", names[n], *argv, data=data)

    def link(left, right, laddr, raddr, l6=None, r6=None):
        # Interface names are local to their namespace after the first move.
        command(
            "ip", "link", "add", stem + "l", "type", "veth", "peer", "name", stem + "r"
        )
        for node, interface, target, address, ipv6 in (
            (left, stem + "l", right, laddr, l6),
            (right, stem + "r", left, raddr, r6),
        ):
            command("ip", "link", "set", interface, "netns", names[node])
            ns(node, "ip", "link", "set", interface, "name", "to" + target)
            ns(node, "ip", "addr", "add", address, "dev", "to" + target)
            if ipv6:
                ns(node, "ip", "-6", "addr", "add", ipv6, "dev", "to" + target, "nodad")
            ns(node, "ip", "link", "set", "to" + target, "up")

    def serve(node, address, port, uid=None):
        log = tmp_path / f"{node}-{port}.jsonl"
        ready = tmp_path / f"{node}-{port}.ready"
        script = """
import http.server,json,os,socket,socketserver,sys
address,port,log,ready,uid=sys.argv[1:]
if uid: os.setgid(int(uid));os.setuid(int(uid))
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  with open(log,'a') as f:f.write(json.dumps(self.client_address[0])+'\\n')
  self.send_response(200);self.end_headers();self.wfile.write(self.client_address[0].encode())
 def log_message(self,*args):pass
class Server(http.server.HTTPServer):
 address_family=socket.AF_INET6 if ':' in address else socket.AF_INET
 def server_bind(self):
  socketserver.TCPServer.server_bind(self);self.server_name=address;self.server_port=int(port)
server=Server((address,int(port)),Handler)
open(ready,'w').close()
server.serve_forever()
"""
        proc = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                names[node],
                sys.executable,
                "-c",
                script,
                address,
                str(port),
                str(log),
                str(ready),
                str(uid or ""),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        children.append(proc)
        for _ in range(100):
            if ready.exists():
                return log
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read().decode())
            time.sleep(0.02)
        raise AssertionError("namespace listener did not start")

    def request(node, url, uid=None):
        script = "import os,subprocess,sys;uid=sys.argv[1];os.setgid(int(uid));os.setuid(int(uid));raise SystemExit(subprocess.run(sys.argv[2:]).returncode)"
        argv = [
            "curl",
            "--noproxy",
            "*",
            "--silent",
            "--show-error",
            "--max-time",
            "4",
            url,
        ]
        if uid is not None:
            argv = [sys.executable, "-c", script, str(uid), *argv]
        return subprocess.run(
            ["ip", "netns", "exec", names[node], *argv],
            text=True,
            capture_output=True,
            timeout=6,
        )

    try:
        # Only private namespaces and their links are mutated.
        for name in names.values():
            command("ip", "netns", "add", name)
            command("ip", "-n", name, "link", "set", "lo", "up")
        link("a", "b", "192.0.2.1/30", "192.0.2.2/30")
        link(
            "a",
            "c",
            "198.51.100.1/30",
            "198.51.100.2/30",
            "fd00:2::1/64",
            "fd00:2::2/64",
        )
        link("b", "e", "203.0.113.1/30", "203.0.113.2/30")
        ns("a", "ip", "route", "add", "default", "via", "198.51.100.2")
        ns("b", "sysctl", "-q", "-w", "net.ipv4.ip_forward=1")
        keys = {n: command("wg", "genkey").strip() for n in "ab"}
        pubs = {n: command("wg", "pubkey", data=keys[n]).strip() for n in "ab"}
        for node, address in (("a", "10.200.0.1/30"), ("b", "10.200.0.2/30")):
            file = tmp_path / (node + ".key")
            file.write_text(keys[node])
            file.chmod(0o600)
            ns(node, "ip", "link", "add", "shop0", "type", "wireguard")
            ns(node, "wg", "set", "shop0", "private-key", str(file))
            ns(node, "ip", "addr", "add", address, "dev", "shop0")
            ns(node, "ip", "link", "set", "shop0", "up")
        ns(
            "a",
            "wg",
            "set",
            "shop0",
            "listen-port",
            "51821",
            "peer",
            pubs["b"],
            "allowed-ips",
            "0.0.0.0/0",
        )
        ns(
            "b",
            "wg",
            "set",
            "shop0",
            "peer",
            pubs["a"],
            "allowed-ips",
            "10.200.0.1/32",
            "endpoint",
            "192.0.2.1:51821",
            "persistent-keepalive",
            "1",
        )
        ns("a", "ip", "route", "add", "default", "dev", "shop0", "table", "200")
        ns("a", "ip", "rule", "add", "fwmark", "1", "table", "200")
        values = {
            "split_hop_ingress": {
                "fwmark": 1,
                "wg_interface": "shop0",
                "node_a_address": "10.200.0.1/30",
                "listen_port": 51821,
                "routing_table": 200,
            },
            "split_hop_ingress_secrets": {
                "node_a_private_key": keys["a"], "node_b_public_key": pubs["b"],
            },
            "probe_matrix_runtime_users": {"xray_uid": 65532, "mtg_uid": 65533},
        }
        ingress = render_template(
            ROOT / "ansible/roles/split-hop-ingress/templates/policy.nft.j2",
            dict(**values),
        )
        egress = render_template(
            ROOT / "ansible/roles/split-hop-egress/templates/split-hop-egress.nft.j2",
            dict(split_hop_egress={"wg_interface": "shop0", "forward_iface": "toe"}),
        )
        shared_values = merge_render_vars()
        shared_values.update(values)
        shared_values["vpn"]["enable_split_hop_ingress"] = True
        shared_values["split_hop_ingress_role_enabled"] = True
        canonical = render_template(
            ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", shared_values,
        )
        ipv6_guard = next(line for line in canonical.splitlines()
                          if 'comment "split-hop-ingress-boundary-v6"' in line)
        chain_start = "  chain split_hop_ingress_egress_guard {"
        ipv4_chain = chain_start + canonical.split(chain_start, 1)[1].split("\n  }", 1)[0] + "\n  }\n"
        shared_guard = (
            "table inet owned_shared_guard {\n"
            "  chain output {\n    type filter hook output priority 0; policy accept;\n"
            + ipv6_guard + "\n  }\n" + ipv4_chain + "}\n"
        )
        # The unprivileged listener can write only its private test evidence.
        tmp_path.chmod(0o777)
        for parent in tmp_path.parents:
            if str(parent).startswith("/tmp/pytest"):
                parent.chmod(0o755)
        serve("a", "198.51.100.1", 18080, 65532)
        serve("e", "203.0.113.2", 18080)
        serve("a", "fd00:2::1", 18083, 65532)
        ipv6_log = serve("c", "fd00:2::2", 18081)
        ipv4_log = serve("c", "198.51.100.2", 18084)
        # Establish an owned IPv6 original before installing the policy.
        # Its later packets must not escape through the previous public path.
        stream_log = tmp_path / "ipv6-stream.log"
        stream_ready = tmp_path / "ipv6-stream.ready"
        stream_server = """
import socket,sys
s=socket.socket(socket.AF_INET6,socket.SOCK_STREAM);s.bind(('fd00:2::2',18082));s.listen()
open(sys.argv[2],'w').close()
c,_=s.accept()
while True:
 data=c.recv(32)
 if not data:break
 with open(sys.argv[1],'ab') as f:f.write(data)
 c.sendall(data)
"""
        server = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                names["c"],
                sys.executable,
                "-c",
                stream_server,
                str(stream_log),
                str(stream_ready),
            ],
            stderr=subprocess.PIPE,
        )
        children.append(server)
        for _ in range(100):
            if stream_ready.exists():
                break
            time.sleep(0.02)
        assert stream_ready.exists()
        ns(
            "a",
            "nft",
            "-f",
            "-",
            data="table inet p2_previous { chain output { type filter hook output priority 0; policy accept; ct state established counter; }; }",
        )
        stream_client = """
import os,socket,sys
os.setgid(65532);os.setuid(65532)
s=socket.socket(socket.AF_INET6,socket.SOCK_STREAM);s.settimeout(2);s.connect(('fd00:2::2',18082));s.sendall(b'before');assert s.recv(32)==b'before'
print('established',flush=True);sys.stdin.read(1)
s.sendall(b'after');assert s.recv(32)==b'after'
"""
        client = subprocess.Popen(
            ["ip", "netns", "exec", names["a"], sys.executable, "-c", stream_client],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(client)
        assert select.select([client.stdout], [], [], 3)[
            0
        ], "pre-policy IPv6 connection must establish"
        assert client.stdout.readline().strip() == "established"
        ns("a", "nft", "-f", "-", data=ingress)
        # Retain both source-owned boundaries together. The complete canonical
        # IPv4 chain must also permit the final marked route while it is up.
        ns("a", "nft", "-f", "-", data=shared_guard)

        def ingress_rules():
            loaded = json.loads(ns("a", "nft", "-j", "list", "table", "inet", "split_hop_ingress"))
            return [(row["rule"]["chain"], row["rule"]["expr"])
                    for row in loaded["nftables"] if "rule" in row]

        accepted_rules = ingress_rules()
        assert accepted_rules, "actual ingress policy must contain rules"
        for _ in range(2):
            ns("a", "nft", "-f", "-", data=ingress)
            assert ingress_rules() == accepted_rules, "repeated policy loading must replace rules without duplication"
        changed_values = {**values, "split_hop_ingress": {
            **values["split_hop_ingress"], "node_a_address": "10.200.0.9/30",
        }}
        changed_policy = render_template(
            ROOT / "ansible/roles/split-hop-ingress/templates/policy.nft.j2", changed_values,
        )
        ns("a", "nft", "-f", "-", data=changed_policy)
        changed_rules = ingress_rules()
        assert len(changed_rules) == len(accepted_rules)
        snat_addresses = [expression["snat"]["addr"]
                          for _, expressions in changed_rules for expression in expressions
                          if "snat" in expression]
        assert snat_addresses == ["10.200.0.9"], "changed policy must replace the previous owned SNAT address"
        ns("a", "nft", "-f", "-", data=ingress)
        assert ingress_rules() == accepted_rules
        ns("b", "nft", "-f", "-", data=egress)
        client.communicate("x", timeout=4)
        assert client.returncode != 0, "established owned IPv6 original must be fenced"
        assert (
            stream_log.read_bytes() == b"before"
        ), "post-policy original must not leak"
        for uid in (65532, 65533):
            result = request("a", "http://203.0.113.2:18080/", uid)
            assert result.returncode == 0, (
                result.stderr + ns("a", "ip", "route", "get", "203.0.113.2", "mark", "1")
                + ns("a", "nft", "list", "table", "inet", "split_hop_ingress")
            )
            assert result.stdout == "203.0.113.1", "egress must be Node B"
        assert (
            request("c", "http://198.51.100.1:18080/").stdout == "198.51.100.2"
        ), "accepted-client reply must remain on A"
        reply6 = request("c", "http://[fd00:2::1]:18083/")
        assert (
            reply6.returncode == 0 and reply6.stdout == "fd00:2::2"
        ), "accepted IPv6 replies must remain on A"
        for uid in (65532, 65533):
            denied = request("a", "http://[fd00:2::2]:18081/", uid)
            assert denied.returncode != 0, "owned IPv6 original must be refused"
        assert (
            not ipv6_log.exists()
        ), "refused IPv6 must never reach public-side listener"
        allowed = request("a", "http://[fd00:2::2]:18081/")
        assert allowed.returncode == 0 and allowed.stdout == "fd00:2::1", allowed.stderr
        received = int(ns("b", "wg", "show", "shop0", "transfer").split()[1])
        assert received > 0, "real encrypted WG transport must carry the request"
        configuration = render_template(
            ROOT / "ansible/roles/split-hop-ingress/templates/split-hop-ingress.conf.j2",
            values,
        )
        post_down = next(line.split(" = ", 1)[1] for line in configuration.splitlines()
                         if line.startswith("PostDown = "))
        ns("a", "sh", "-c", post_down)
        ns("a", "ip", "link", "set", "shop0", "down")
        assert "egress_guard" in ns("a", "nft", "list", "table", "inet", "split_hop_ingress")
        direct_before = {path: path.read_bytes() if path.exists() else b""
                         for path in (ipv4_log, ipv6_log)}
        for uid in (65532, 65533):
            for url in ("http://198.51.100.2:18084/", "http://[fd00:2::2]:18081/"):
                denied = request("a", url, uid)
                assert denied.returncode != 0, "stopped tunnel must not expose owned direct egress"
        assert all((path.read_bytes() if path.exists() else b"") == before
                   for path, before in direct_before.items()), "owned originals reached a direct listener"
        for url, address in (("http://198.51.100.2:18084/", "198.51.100.1"),
                             ("http://[fd00:2::2]:18081/", "fd00:2::1")):
            control = request("a", url)
            assert control.returncode == 0 and control.stdout == address, control.stderr
        for url, address in (("http://198.51.100.1:18080/", "198.51.100.2"),
                             ("http://[fd00:2::1]:18083/", "fd00:2::2")):
            reply = request("c", url)
            assert reply.returncode == 0 and reply.stdout == address, reply.stderr
        ns("a", "ip", "link", "set", "shop0", "up")
        ns("a", "ip", "route", "add", "default", "dev", "shop0", "table", "200")
        ns("a", "ip", "rule", "add", "fwmark", "1", "table", "200")
        for uid in (65532, 65533):
            recovered = request("a", "http://203.0.113.2:18080/", uid)
            assert recovered.returncode == 0 and recovered.stdout == "203.0.113.1", recovered.stderr
        assert int(ns("b", "wg", "show", "shop0", "transfer").split()[1]) > received
    finally:
        for proc in children:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        for name in names.values():
            subprocess.run(
                ["ip", "netns", "delete", name], capture_output=True, timeout=5
            )
