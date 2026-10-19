"""Actual loopback UDP proves receiver timing; Linux firewall remains separate."""

import ast
import json
import os
import select
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "tests/native/transport_acceptance/test_dhcpv6.py"


def observation_source():
    tree = ast.parse(NATIVE.read_text())
    source = ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RECEIVER"
                for target in node.targets)))
    # Keep the exact observation protocol after Linux-only bind and group setup.
    # The child gets a real, already-bound IPv6 loopback UDP descriptor instead.
    multicast = next(node for node in ast.parse(source).body
                     if isinstance(node, ast.If)
                     and isinstance(node.test, ast.Compare)
                     and isinstance(node.test.left, ast.Name)
                     and node.test.left.id == "multicast")
    return "\n".join(source.splitlines()[multicast.end_lineno:])


@contextmanager
def receiver():
    with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as bound:
        bound.bind(("::1", 0))
        address = bound.getsockname()
        source = "import json,os,select,socket,sys,time\ns=socket.socket(fileno=int(sys.argv[1]))\n"
        process = subprocess.Popen(
            [sys.executable, "-c", source + observation_source(), str(bound.fileno())],
            pass_fds=(bound.fileno(),), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    try:
        assert select.select([process.stdout], [], [], 3)[0], "receiver-ready-deadline"
        assert process.stdout.readline().strip() == "ready"
        yield process, address
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=3)


@pytest.mark.parametrize("deliver", [False, True])
def test_delayed_sender_cannot_expire_positive_or_negative_observation(deliver):
    with receiver() as (process, address):
        # Deliberately exceed the complete historical 0.7-second observation.
        time.sleep(1.0)
        if deliver:
            with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as sender:
                sender.sendto(b"dhcpv6-regression", address)
        acknowledged = time.monotonic()
        output, error = process.communicate(input="send-complete\n", timeout=3)
        assert process.returncode == 0, error
        packet = json.loads(output)
        if deliver:
            assert packet is not None, "receiver-expired-before-completed-send"
            assert packet[0] == "dhcpv6-regression"
        else:
            assert packet is None
            assert time.monotonic() - acknowledged >= .7, "negative-observation-ended-before-send"


@pytest.mark.parametrize("acknowledgement", ["", "invalid\n"])
def test_missing_or_invalid_send_acknowledgement_refuses(acknowledgement):
    with receiver() as (process, _address):
        output, error = process.communicate(input=acknowledgement, timeout=3)
        assert process.returncode != 0, "unacknowledged-receiver-reported-success"
        assert "dhcpv6-receiver-send-ack" in error
        assert not output.strip()


def setup_branch_source(groups, *, bound="peer0", join_error=False):
    """Run actual membership admission with controlled socket/proc boundaries.

    Real child execution proves readiness ordering and refusal. This portable
    boundary fixture does not prove Linux socket or multicast acceptance.
    """
    tree = ast.parse(NATIVE.read_text())
    source = ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RECEIVER"
                for target in node.targets)))
    receiver_tree = ast.parse(source)
    group = next(node for node in receiver_tree.body if isinstance(node, ast.If)
                 and isinstance(node.test, ast.Compare)
                 and isinstance(node.test.left, ast.Name) and node.test.left.id == "multicast")
    ready = next(node for node in receiver_tree.body if isinstance(node, ast.Expr)
                 and isinstance(node.value, ast.Call) and node.value.args
                 and isinstance(node.value.args[0], ast.Constant)
                 and node.value.args[0].value == "ready")
    assert group.end_lineno < ready.lineno
    helpers = [node for node in receiver_tree.body if isinstance(node, ast.FunctionDef)
               or isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                   and target.id == "readiness_reported" for target in node.targets)]

    class ProcBoundary(ast.NodeTransformer):
        def visit_Constant(self, node):
            if node.value == "/proc/net/igmp6":
                return ast.copy_location(ast.Constant(str(groups)), node)
            return node

    program = ast.fix_missing_locations(ProcBoundary().visit(
        ast.Module(body=[*helpers, group, ready], type_ignores=[])))
    return (
        "import json,os,select,socket,struct,sys\n"
        "interface,multicast=sys.argv[1:]\n"
        "socket.if_nametoindex=lambda interface:7\n"
        "class SocketBoundary:\n"
        " def setsockopt(self,level,option,value):\n"
        "  assert (level,option)==(socket.IPPROTO_IPV6,socket.IPV6_JOIN_GROUP)\n"
        "  assert value==socket.inet_pton(socket.AF_INET6,'ff02::1:2')+struct.pack('@I',7)\n"
        f"  if {join_error!r}:raise OSError('private-join-error')\n"
        " def getsockopt(self,level,option,size):\n"
        "  assert (level,option,size)==(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,16)\n"
        f"  return {bound.encode() + bytes([0])!r}\n"
        "s=SocketBoundary()\n"
        + ast.unparse(program).replace("if multicast == 'yes':", "sys.excepthook=bind_join_failure\nif multicast == 'yes':")
    )


def execute_multicast_setup(tmp_path, *, bound="peer0", groups=None, join_error=False,
                            unreadable=False, multicast="yes"):
    membership = tmp_path / "igmp6"
    if not unreadable:
        membership.write_text(groups if groups is not None else
                              "7 peer0 ff020000000000000000000000010002 1 0\n")
    executable, invoked = tmp_path / "ip", tmp_path / "route-invoked"
    executable.write_text("#!" + sys.executable + "\nimport sys\nfrom pathlib import Path\n"
                          + "Path(" + repr(str(invoked)) + ").write_text('unexpected')\n"
                          + "sys.stderr.write('RTNETLINK answers: Message too long\\n');raise SystemExit(2)\n")
    executable.chmod(0o700)
    result = subprocess.run(
        [sys.executable, "-c", setup_branch_source(membership, bound=bound, join_error=join_error),
         "peer0", multicast], check=False, capture_output=True, text=True, timeout=3,
        env={**os.environ, "PATH": str(tmp_path)},
    )
    assert not invoked.exists(), "local-multicast-admission-invoked-forwarding-query"
    return result


def test_verified_local_socket_membership_is_ready_without_multicast_fib_query(tmp_path):
    result = execute_multicast_setup(tmp_path)
    assert result.returncode == 0 and result.stdout == "ready\n"
    assert result.stderr == "dhcpv6-membership:yes\n"


@pytest.mark.parametrize("changes", [
    {"bound": "other0"}, {"bound": ""}, {"join_error": True}, {"unreadable": True},
    {"groups": ""}, {"groups": "7 other0 ff020000000000000000000000010002 1 0\n"},
    {"groups": "7 peer0 ff020000000000000000000000000002 1 0\n"},
])
def test_local_multicast_setup_refusal_never_reports_ready(tmp_path, changes):
    result = execute_multicast_setup(tmp_path, **changes)
    assert result.returncode != 0 and result.stdout == ""
    assert result.stderr.count("dhcpv6-readiness:") == 1
    assert '"stage": "bind-join"' in result.stderr


def test_unicast_readiness_does_not_require_multicast_membership(tmp_path):
    result = execute_multicast_setup(tmp_path, unreadable=True, join_error=True, multicast="no")
    assert result.returncode == 0 and result.stdout == "ready\n" and result.stderr == ""
