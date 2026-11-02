"""Exercise the loaded guard with real sockets in the disposable role container."""
import json
import socket
import subprocess

rows = json.loads(subprocess.check_output(
    ["nft", "-j", "list", "chain", "inet", "filter", "ipv4_tcp_options_guard"]
))["nftables"]
chain = next(row["chain"] for row in rows if "chain" in row)
assert (chain["hook"], chain["prio"], chain["policy"]) == ("input", -310, "accept")
rule = next(row["rule"] for row in rows if "rule" in row)
assert [e for e in rule["expr"] if "counter" not in e] == [
    {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "protocol"}}, "right": "tcp"}},
    {"match": {"op": ">", "left": {"payload": {"protocol": "ip", "field": "hdrlength"}}, "right": 5}},
    {"drop": None},
]
with socket.socket() as server:
    server.bind(("127.0.0.1", 0))
    server.listen(2)
    with socket.create_connection(server.getsockname(), timeout=1):
        pass
    with socket.socket() as client:
        client.settimeout(0.5)
        client.setsockopt(socket.IPPROTO_IP, socket.IP_OPTIONS, b"\x01\x01\x00\x00")
        try:
            client.connect(server.getsockname())
        except TimeoutError:
            pass
        else:
            raise AssertionError("IPv4 TCP IP options bypassed the early guard")
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1)
    sender.setsockopt(socket.IPPROTO_IP, socket.IP_OPTIONS, b"\x01\x01\x00\x00")
    sender.sendto(b"udp-with-ip-options", receiver.getsockname())
    assert receiver.recv(64) == b"udp-with-ip-options"
rows = json.loads(subprocess.check_output(
    ["nft", "-j", "list", "chain", "inet", "filter", "ipv4_tcp_options_guard"]
))["nftables"]
assert any(e.get("counter", {}).get("packets", 0) > 0
           for row in rows for e in row.get("rule", {}).get("expr", []))
print("IPv4 TCP IP options drop; ordinary TCP and UDP IP options pass")
