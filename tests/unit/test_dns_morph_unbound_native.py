"""Actual Unbound parser and authoritative-only loopback boundary."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time
import uuid

import pytest

from template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_forwarded_loopback_query_cannot_recurse_but_local_authority_works(tmp_path):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires owned root Linux network namespace")
    if not all(shutil.which(p) for p in ("ip", "unbound", "unbound-checkconf", "nft")):
        pytest.skip("requires Unbound and namespace tooling")
    ns = "p2-dns-" + uuid.uuid4().hex[:8]
    # The distro AppArmor profile admits configuration under /etc/unbound.
    # Use an exact disposable role test file without changing that profile.
    config = Path("/etc/unbound") / (ns + ".conf")
    config.write_text(
        render_template(
            ROOT / "ansible/roles/dns-morph-bridge/templates/unbound-fwd.conf.j2",
            dict(
                dns_morph_bridge={
                    "listen_addr": "0.0.0.0",
                    "listen_port": 53,
                    "recursor_addr": "127.0.0.1",
                    "recursor_port": 15353,
                }
            ),
        )
        + '\n    username: ""\n    chroot: ""\n    pidfile: ""\n    use-syslog: no\n    local-zone: "p2-test.invalid." static\n    local-data: "answer.p2-test.invalid. 60 IN A 192.0.2.123"\n'
    )
    proc = None

    def cmd(*args, data=None):
        result = subprocess.run(
            args, input=data, text=True, capture_output=True, timeout=10
        )
        assert result.returncode == 0, result.stderr
        return result

    try:
        cmd("ip", "netns", "add", ns)
        cmd("ip", "-n", ns, "link", "set", "lo", "up")
        # Count every non-loopback output. Even a refused query must not launch
        # resolver traffic; the isolated namespace has no reachable upstream.
        cmd(
            "ip",
            "netns",
            "exec",
            ns,
            "nft",
            "-f",
            "-",
            data='table inet p2_dns { chain output { type filter hook output priority 0; policy accept; oifname != "lo" counter; }; }',
        )
        cmd("unbound-checkconf", str(config))
        proc = subprocess.Popen(
            ["ip", "netns", "exec", ns, "unbound", "-d", "-c", str(config)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        query = """
import socket,struct,sys
name=sys.argv[1]
wire=struct.pack('!6H',123,0x100,1,0,0,0)+b''.join(bytes([len(label)])+label.encode() for label in name.split('.'))+b'\\0'+struct.pack('!HH',1,1)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(.2);s.sendto(wire,('127.0.0.1',15353));answer=s.recv(4096)
print(answer.hex())
"""
        for _ in range(40):
            result = subprocess.run(
                [
                    "ip",
                    "netns",
                    "exec",
                    ns,
                    sys.executable,
                    "-c",
                    query,
                    "answer.p2-test.invalid",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                break
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read().decode())
            time.sleep(0.025)
        assert result.returncode == 0, result.stderr
        answer = bytes.fromhex(result.stdout.strip())
        assert struct.unpack("!6H", answer[:12])[3] == 1
        assert answer.endswith(socket.inet_aton("192.0.2.123"))
        for name in ("outside.example", "example.com"):
            denied = cmd("ip", "netns", "exec", ns, sys.executable, "-c", query, name)
            packet = bytes.fromhex(denied.stdout.strip())
            header = struct.unpack("!6H", packet[:12])
            assert (
                header[1] & 15 == 5 and header[3] == 0
            ), "ordinary forwarded recursion must be REFUSED"
        counts = cmd(
            "ip", "netns", "exec", ns, "nft", "-j", "list", "table", "inet", "p2_dns"
        ).stdout
        import json

        counters = [
            expr["counter"]["packets"]
            for item in json.loads(counts)["nftables"]
            if "rule" in item
            for expr in item["rule"]["expr"]
            if "counter" in expr
        ]
        assert counters == [
            0
        ], "forwarded ordinary queries must not trigger external recursion"
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        subprocess.run(["ip", "netns", "delete", ns], capture_output=True, timeout=5)
        config.unlink(missing_ok=True)
