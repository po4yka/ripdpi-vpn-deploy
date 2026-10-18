"""Actual loopback UDP proves receiver timing; Linux firewall remains separate."""

import ast
from contextlib import contextmanager
import json
from pathlib import Path
import select
import socket
import subprocess
import sys
import time

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
