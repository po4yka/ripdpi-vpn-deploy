"""Real UDP through the complete rendered firewall in owned Linux namespaces."""

import json
import os
from pathlib import Path
import secrets
import select
import subprocess
import sys
import time

import pytest

from template_render import merge_render_vars, render_template

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.native_runtime


def run(*args, data=None):
    return subprocess.run(args, input=data, capture_output=True, text=True,
                          timeout=15, check=True).stdout


RECEIVER = """
import json,os,select,socket,sys
readiness_reported=False
def emit_readiness():
 global readiness_reported
 if not readiness_reported:
  readiness_reported=True
  try:
   print('dhcpv6-readiness:'+json.dumps({'stage':'bind-join','authority_mismatch':0}),file=sys.stderr,flush=True)
  except OSError:pass
def bind_join_failure(kind,error,traceback):
 emit_readiness()
 sys.__excepthook__(kind,error,traceback)
def admit_multicast_membership(interface,receiver):
 if receiver.getsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,16).rstrip(b'\\0')!=interface.encode():
  raise ValueError('dhcpv6-bound-interface-refused')
 with open('/proc/net/igmp6') as groups:
  member=any(len(fields)>=3 and fields[1]==interface and fields[2].lower()=='ff020000000000000000000000010002'
             for fields in (line.split() for line in groups))
 if not member:raise ValueError('dhcpv6-membership-refused')
 print('dhcpv6-membership:yes',file=sys.stderr,flush=True)
sys.excepthook=bind_join_failure
interface,address,port,multicast=sys.argv[1:]
s=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,interface.encode()+b'\\0')
s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind((address,int(port),0,socket.if_nametoindex(interface) if address.startswith('fe80') else 0))
if multicast == 'yes':
 import struct
 s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_JOIN_GROUP,
              socket.inet_pton(socket.AF_INET6,'ff02::1:2')+struct.pack('@I',socket.if_nametoindex(interface)))
 admit_multicast_membership(interface,s)
sys.excepthook=sys.__excepthook__
print('ready',flush=True)
if not select.select([sys.stdin],[],[],20)[0]:
 raise SystemExit('dhcpv6-receiver-send-ack-timeout')
if os.read(sys.stdin.fileno(),14) != b'send-complete\\n':
 raise SystemExit('dhcpv6-receiver-send-ack-invalid')
s.settimeout(.7)
try:
 data,peer=s.recvfrom(128)
 print(json.dumps([data.decode(),peer[0],peer[1]]),flush=True)
except TimeoutError:
 print('null',flush=True)
"""

SENDER = """
import errno,socket,sys
interface,source,sport,target,dport,expected_deny=sys.argv[1:]
s=socket.socket(socket.AF_INET6,socket.SOCK_DGRAM)
index=socket.if_nametoindex(interface)
s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,interface.encode()+b'\\0')
s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_MULTICAST_IF,index)
s.bind((source,int(sport),0,index if source.startswith('fe80') else 0))
try:
 s.sendto(b'dhcpv6-regression',(target,int(dport),0,index if target.startswith(('fe80','ff02')) else 0))
except OSError as error:
 if expected_deny != 'yes' or error.errno != errno.EPERM:
  raise
 print('expected-output-deny',flush=True)
"""


# Observe only the existing synthetic multicast tuple; no rule gives a verdict.
MULTICAST_OBSERVER = """
add table inet dhcpv6_probe
add chain inet dhcpv6_probe before { type filter hook %s priority -301; }
add chain inet dhcpv6_probe after { type filter hook %s priority 301; }
add chain inet dhcpv6_probe transit { type filter hook %s priority %s; }
add rule inet dhcpv6_probe before ip6 saddr fe80::10 ip6 daddr ff02::1:2 udp sport 546 udp dport 547 counter
add rule inet dhcpv6_probe after ip6 saddr fe80::10 ip6 daddr ff02::1:2 udp sport 546 udp dport 547 counter
add rule inet dhcpv6_probe transit ip6 saddr fe80::10 ip6 daddr ff02::1:2 udp sport 546 udp dport 547 counter
"""

MULTICAST_RECEIVER_OBSERVER = """
add chain inet dhcpv6_probe transit_after { type filter hook prerouting priority 301; }
add chain inet dhcpv6_probe expected_iif { type filter hook prerouting priority -301; }
add rule inet dhcpv6_probe transit_after ip6 saddr fe80::10 ip6 daddr ff02::1:2 udp sport 546 udp dport 547 counter
add rule inet dhcpv6_probe expected_iif iifname "peer0" ip6 saddr fe80::10 ip6 daddr ff02::1:2 udp sport 546 udp dport 547 counter
"""


def multicast_counters(namespace):
    table = json.loads(run("ip", "netns", "exec", namespace, "nft", "-j",
                           "list", "table", "inet", "dhcpv6_probe"))
    return {
        row["rule"]["chain"]: min(65535, expression["counter"]["packets"])
        for row in table["nftables"] if "rule" in row
        for expression in row["rule"]["expr"] if "counter" in expression
    }


def multicast_udp_errors(namespace):
    counters = run("ip", "netns", "exec", namespace, "cat", "/proc/net/snmp6")
    expected = {"Udp6InErrors", "Udp6InCsumErrors", "Udp6NoPorts", "Udp6IgnoredMulti",
                "Ip6InNoRoutes", "Ip6InMcastPkts", "Ip6InDiscards", "Ip6InAddrErrors", "Ip6InDelivers"}
    selected = {}
    for line in counters.splitlines():
        key, value = line.split()
        if key in expected:
            if key in selected or int(value) < 0:
                raise ValueError("dhcpv6-observation-metric-unavailable")
            selected[key] = int(value)
    if set(selected) != expected:
        raise ValueError("dhcpv6-observation-metric-unavailable")
    return selected


def multicast_local_routes(namespace):
    """Optional post-NULL SHOW; an unavailable snapshot never means no route."""
    child = None
    try:
        deadline = time.monotonic() + 1
        child = subprocess.Popen(
            ["ip", "-n", namespace, "-j", "-6", "route", "show", "table", "local", "exact", "ff00::/8"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        raw = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([child.stdout], [], [], remaining)[0]:
                raise ValueError("route-show-deadline")
            chunk = os.read(child.stdout.fileno(), 4097 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 4096:
                raise ValueError("route-show-size")
        child.wait(timeout=max(0, deadline - time.monotonic()))
        if child.returncode:
            raise ValueError("route-show-exit")

        def unique_object(pairs):
            value = dict(pairs)
            if len(value) != len(pairs):
                raise ValueError("route-show-duplicate")
            return value

        rows = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        if not isinstance(rows, list) or len(rows) > 2:
            raise ValueError("route-show-rows")
        result = {prefix + "_" + field: False for prefix in ("peer", "other")
                  for field in ("present", "multicast", "linkdown")}
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or not {"dst", "dev", "type", "flags"} <= row.keys()
                    or row["dst"] != "ff00::/8" or type(row["dev"]) is not str
                    or row["dev"] not in {"peer0", "other0"} or row["dev"] in seen
                    or type(row["type"]) is not str or row["type"] not in {"multicast", "unicast", "local"}):
                raise ValueError("route-show-authority")
            flags = row["flags"]
            if (not isinstance(flags, list) or any(type(flag) is not str for flag in flags)
                    or len(set(flags)) != len(flags) or set(flags) - {"linkdown", "dead", "onlink", "pervasive"}):
                raise ValueError("route-show-flags")
            seen.add(row["dev"])
            prefix = {"peer0": "peer", "other0": "other"}[row["dev"]]
            result.update({prefix + "_present": True, prefix + "_multicast": row["type"] == "multicast",
                           prefix + "_linkdown": "linkdown" in flags})
        return result
    except Exception:
        # Preserve the completed packet failure and primary counters without raw child output.
        return None
    finally:
        if child is not None:
            try:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=1)
            except (OSError, subprocess.SubprocessError):
                # Namespace cleanup remains mandatory if this optional child cannot be reaped.
                print("dhcpv6-route-cleanup-unavailable", flush=True)
            child.stdout.close()


def readiness_record(error):
    """Admit one closed refusal marker without retaining private child output."""
    if not isinstance(error, str):
        return None
    try:
        encoded = error.encode("utf-8")
    except UnicodeError:
        return None
    if len(encoded) > 4096:
        return None
    lines = [line for line in error.splitlines() if line.startswith("dhcpv6-readiness:")]
    if len(lines) != 1 or len(lines[0].encode("utf-8")) > 256:
        return None

    def unique_object(pairs):
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError("duplicate-readiness-field")
        return value

    try:
        value = json.loads(lines[0].split(":", 1)[1], object_pairs_hook=unique_object)
    except ValueError:
        return None
    if not isinstance(value, dict) or set(value) != {"stage", "authority_mismatch"}:
        return None
    stage, mask = value["stage"], value["authority_mismatch"]
    if stage != "bind-join" or type(mask) is not int or mask != 0:
        return None
    return value


def packet(sender, receiver, *, source="fe80::20", target="fe80::10",
           sport=547, dport=546, send_interface="peer0", receive_interface="up0",
           expected_output_deny=False, observe_multicast=False, record_property=None):
    observed_namespaces = []
    errors_before = None
    receiver_member = None
    listener = None
    started = time.monotonic()
    diagnostic = {"phase": "readiness", "packet_received": None}
    try:
        if observe_multicast:
            try:
                for namespace, hook, transit, priority in (
                    (sender, "output", "postrouting", 301), (receiver, "input", "prerouting", -301)
                ):
                    run("ip", "netns", "exec", namespace, "nft", "-f", "-",
                        data=(MULTICAST_OBSERVER % (hook, hook, transit, priority)
                              + (MULTICAST_RECEIVER_OBSERVER if namespace == receiver else "")))
                    observed_namespaces.append(namespace)
                errors_before = multicast_udp_errors(receiver)
            except Exception:
                print("dhcpv6-observation-unavailable", flush=True)
        listener = subprocess.Popen(
            ["ip", "netns", "exec", receiver, sys.executable, "-c", RECEIVER,
             receive_interface, "::" if target.startswith("ff02") else target,
             str(dport), "yes" if target.startswith("ff02") else "no"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert select.select([listener.stdout], [], [], 3)[0], "dhcpv6-receiver-timeout"
        assert listener.stdout.readline().strip() == "ready", "dhcpv6-receiver-not-ready"
        diagnostic["ready_ms"] = min(30000, int((time.monotonic() - started) * 1000))
        diagnostic["phase"] = "send"
        try:
            run("ip", "netns", "exec", sender, sys.executable, "-c", SENDER,
                send_interface, source, str(sport), target, str(dport),
                "yes" if expected_output_deny else "no")
        except subprocess.SubprocessError:
            raise AssertionError("dhcpv6-send-result-refused") from None
        diagnostic["send_ms"] = min(30000, int((time.monotonic() - started) * 1000))
        diagnostic["phase"] = "receive"
        try:
            output, _error = listener.communicate(input="send-complete\n", timeout=3)
        except subprocess.SubprocessError:
            raise AssertionError("dhcpv6-receive-result-refused") from None
        assert listener.returncode == 0, "dhcpv6-receiver-control-refused"
        if observe_multicast:
            member_marker = _error.strip()
            if member_marker in {"dhcpv6-membership:yes", "dhcpv6-membership:no"}:
                receiver_member = member_marker == "dhcpv6-membership:yes"
        received = json.loads(output)
        if received is not None:
            assert received[0] == "dhcpv6-regression"
        diagnostic["phase"] = "packet"
        diagnostic["packet_received"] = received is not None
        return received
    finally:
        diagnostic["elapsed_ms"] = min(30000, int((time.monotonic() - started) * 1000))
        print("dhcpv6-probe:" + json.dumps(diagnostic, sort_keys=True), flush=True)
        readiness_error = ""
        if listener is not None and listener.poll() is None:
            listener.kill()
            _unused, readiness_error = listener.communicate(timeout=3)
        elif listener is not None and diagnostic["phase"] == "readiness":
            try:
                _unused, readiness_error = listener.communicate(timeout=3)
            except (subprocess.SubprocessError, OSError, UnicodeError):
                print("dhcpv6-readiness-unavailable", flush=True)
        try:
            if observe_multicast and diagnostic["phase"] == "readiness" and record_property is not None:
                refusal = readiness_record(readiness_error)
                if refusal is not None:
                    record_property("dhcpv6-readiness", json.dumps(refusal, sort_keys=True))
            # Publish only a completed attempt with every observation measured.
            if (observe_multicast and diagnostic["phase"] == "packet"
                    and len(observed_namespaces) == 2 and errors_before is not None
                    and receiver_member is not None):
                sent = multicast_counters(sender)
                received_counts = multicast_counters(receiver)
                errors_after = multicast_udp_errors(receiver)
                error_deltas = {key: errors_after[key] - errors_before[key] for key in errors_before}
                if any(value < 0 for value in error_deltas.values()):
                    raise ValueError("dhcpv6-observation-counter-reset")
                if (type(received_counts["expected_iif"]) is not int
                        or not 0 <= received_counts["expected_iif"] <= received_counts["transit"]):
                    raise ValueError("dhcpv6-observation-interface-refused")
                route_state = None
                if not diagnostic["packet_received"]:
                    try:
                        route_state = multicast_local_routes(receiver)
                    except Exception:
                        # A supplementary SHOW failure must preserve the complete primary observation.
                        print("dhcpv6-route-observation-unavailable", flush=True)
                observation = {
                    "probe_id": "multicast-request", "phase": "packet",
                    "ready_ms": diagnostic["ready_ms"], "send_ms": diagnostic["send_ms"],
                    "elapsed_ms": diagnostic["elapsed_ms"], "receiver_member": receiver_member,
                    "packet_received": diagnostic["packet_received"],
                    "output_before": sent["before"], "output_after": sent["after"],
                    "postrouting_after": sent["transit"], "prerouting_before": received_counts["transit"],
                    "prerouting_after": received_counts["transit_after"],
                    "ingress_expected": received_counts["expected_iif"] > 0,
                    "input_before": received_counts["before"], "input_after": received_counts["after"],
                    "udp_errors": min(65535, error_deltas["Udp6InErrors"]),
                    "udp_checksum_errors": min(65535, error_deltas["Udp6InCsumErrors"]),
                    "udp_no_ports": min(65535, error_deltas["Udp6NoPorts"]),
                    "udp_ignored_multicast": min(65535, error_deltas["Udp6IgnoredMulti"]),
                    "ipv6_no_routes": min(65535, error_deltas["Ip6InNoRoutes"]),
                    "ipv6_multicast": min(65535, error_deltas["Ip6InMcastPkts"]),
                    "ipv6_discards": min(65535, error_deltas["Ip6InDiscards"]),
                    "ipv6_address_errors": min(65535, error_deltas["Ip6InAddrErrors"]),
                    "ipv6_delivers": min(65535, error_deltas["Ip6InDelivers"]),
                    "local_multicast_routes": route_state,
                }
                print("dhcpv6-observation:" + json.dumps(observation, sort_keys=True), flush=True)
        except Exception:
            # Observation failure must not replace the packet outcome.
            print("dhcpv6-observation-unavailable", flush=True)
        finally:
            for namespace in reversed(observed_namespaces):
                try:
                    run("ip", "netns", "exec", namespace, "nft", "delete", "table", "inet", "dhcpv6_probe")
                except Exception:
                    # The required outer namespace cleanup also removes this table.
                    print("dhcpv6-observation-cleanup-unavailable", flush=True)


def test_native_scoped_dhcpv6_bootstrap_rebind_and_legacy_server(record_property):
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
                      dport=547, send_interface="up0", receive_interface="peer0", observe_multicast=True,
                      record_property=record_property)
        run("ip", "-n", peer, "addr", "add", "fe80::21/64", "dev", "peer0", "nodad")
        assert packet(client, peer, source="fe80::10", target="fe80::21", sport=546,
                      dport=547, send_interface="up0", receive_interface="peer0")
        assert packet(peer, client, source="fe80::40", target="fe80::30",
                      send_interface="other0", receive_interface="wrong0") is None
        assert packet(peer, client, sport=548) is None
        assert packet(peer, client, dport=545) is None
        assert packet(client, peer, source="fe80::30", target="fe80::40", sport=546,
                      dport=547, send_interface="wrong0", receive_interface="other0",
                      expected_output_deny=True) is None
        assert packet(peer, client, source="fd42:0::20", target="fd42:0::10") is None
        run("ip", "-n", peer, "addr", "add", "fd42::22/64", "dev", "peer0", "nodad")
        assert packet(client, peer, source="fd42::10", target="fd42::22", sport=546,
                      dport=547, send_interface="up0", receive_interface="peer0",
                      expected_output_deny=True) is None
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


def test_native_established_dhcpv6_tuple_cannot_cross_uplink_scope():
    assert sys.platform == "linux" and os.geteuid() == 0, "isolated-Linux-root-required"
    token = "dh" + secrets.token_hex(4)
    client, peer = token + "c", token + "p"
    namespaces = []
    try:
        for namespace in (client, peer):
            run("ip", "netns", "add", namespace)
            namespaces.append(namespace)
            run("ip", "-n", namespace, "link", "set", "lo", "up")
        for left, right in (("up0", "peer0"), ("wrong0", "other0")):
            run("ip", "-n", client, "link", "add", left, "type", "veth",
                "peer", "name", right, "netns", peer)
            # Link-local scope permits the same address on independent links.
            for namespace, interface, address in (
                (client, left, "fe80::10/64"), (peer, right, "fe80::20/64"),
            ):
                run("ip", "-n", namespace, "addr", "add", address, "dev", interface, "nodad")
                run("ip", "-n", namespace, "link", "set", interface, "up")
        values = merge_render_vars()
        values.update(
            ansible_facts={"default_ipv4": {"interface": "up0"}},
            firewall_egress_policy="strict", firewall_dhcpv6_uplink_interface="",
            firewall_dhcpv6_server_addresses=[], public_listener_contract=[],
            security_controls={"fail2ban": False}, _firewall_effective_check_mode=True,
            _firewall_tailnet_ssh_sets_was_absent=True,
            _firewall_tailnet_initial_fragment=(ROOT / "ansible/roles/firewall/files/vpn-tailnet-ssh-sets.empty.nft").read_text(),
        )
        values["vpn"] = {key: False for key in values["vpn"]}
        rendered = render_template(ROOT / "ansible/roles/firewall/templates/nftables.conf.j2", values)
        run("ip", "netns", "exec", client, "nft", "-c", "-f", "-", data=rendered)
        run("ip", "netns", "exec", client, "nft", "-f", "-", data=rendered)
        # Observe after conntrack attachment and before the canonical filter.
        run("ip", "netns", "exec", client, "nft", "-f", "-", data="""
add table inet dhcpv6_established_probe
add chain inet dhcpv6_established_probe input { type filter hook input priority -1; }
add chain inet dhcpv6_established_probe output { type filter hook output priority -1; }
add rule inet dhcpv6_established_probe input iifname "wrong0" ip6 saddr fe80::20 ip6 daddr fe80::10 udp sport 547 udp dport 546 ct state established counter comment "established-input"
add rule inet dhcpv6_established_probe output oifname "wrong0" ip6 saddr fe80::10 ip6 daddr fe80::20 udp sport 546 udp dport 547 ct state established counter comment "established-output"
""")
        assert packet(peer, client, source="fe80::20", target="fe80::10",
                      send_interface="other0", receive_interface="wrong0") is None
        assert packet(client, peer, source="fe80::10", target="fe80::20", sport=546,
                      dport=547, send_interface="wrong0", receive_interface="other0",
                      expected_output_deny=True) is None
        assert packet(client, peer, source="fe80::10", target="fe80::20", sport=546,
                      dport=547, send_interface="up0", receive_interface="peer0")
        assert packet(peer, client, source="fe80::20", target="fe80::10")
        # Keep both directions in the same conntrack zone and retained tuple.
        assert packet(peer, client, source="fe80::20", target="fe80::10",
                      send_interface="other0", receive_interface="wrong0") is None
        assert packet(client, peer, source="fe80::10", target="fe80::20", sport=546,
                      dport=547, send_interface="wrong0", receive_interface="other0",
                      expected_output_deny=True) is None
        observed = json.loads(run("ip", "netns", "exec", client, "nft", "-j", "list",
                                  "table", "inet", "dhcpv6_established_probe"))
        counts = {row["rule"]["comment"]: expression["counter"]["packets"]
                  for row in observed["nftables"] if "rule" in row
                  for expression in row["rule"]["expr"] if "counter" in expression}
        assert counts == {"established-input": 1, "established-output": 1}
    finally:
        failures = []
        for namespace in reversed(namespaces):
            try:
                run("ip", "netns", "delete", namespace)
            except subprocess.SubprocessError:
                failures.append(namespace)
        if failures:
            raise RuntimeError("dhcpv6-owned-namespace-cleanup-refused")
