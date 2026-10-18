"""Real, disconnected Linux source-pair, wire and warm-adoption acceptance.

This lab owns its generated keys, units and namespaces. It does not exercise a
physical Android runtime or mutate the operator's VPN configuration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import struct
import subprocess
import sys
import time
import unittest
from pathlib import Path

import runtime_build_receipt as publisher

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corrected_build

ROOT = Path("/lab")
PINS = json.loads((ROOT / "sources.json").read_text())
RECEIPTS = Path("/var/lib/ripdpi/runtime-build-receipts")
STAGE = Path("/var/lib/ripdpi/runtime-build-staging/awg-candidate")
LIVE = Path("/usr/local/lib/awg-candidate")


def command(*argv, data=None, timeout=30):
    result = subprocess.run(
        argv, input=data, text=True, check=False, capture_output=True, timeout=timeout
    )
    if result.returncode:
        # Config/key-bearing commands never enter the assertion text.
        raise AssertionError("local AWG command failed: " + argv[0])
    return result.stdout.strip()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def descriptor(pair):
    source = Path("/opt") / pair
    build = corrected_build.verify(source / "go", PINS[pair]["go"]["commit"], ROOT / "awg-source-correction")
    if build["correction"]["profile"] != "upstream":
        raise AssertionError("native-AWG-source-profile-unqualified")
    outputs = [
        ("amneziawg-go", source / "go/amneziawg-go"),
        ("awg", source / "tools/src/wg"),
        ("awg-quick", source / "tools/src/wg-quick/linux.bash"),
    ]
    return {
        "schema_version": 1,
        "name": "awg-candidate",
        "source": {
            "pair": PINS[pair],
            "patches": build["correction"],
            "go_toolchain": PINS["go_toolchain"],
            "go_module_proxy": PINS["go_module_proxy"],
            "package_sources_sha256": digest("/etc/apt/sources.list.d/ubuntu.sources"),
        },
        "steps": [
            {
                "argv": [
                    "/usr/bin/install",
                    "-m",
                    "0755",
                    str(path),
                    str(STAGE / name),
                ],
                "chdir": "/lab",
                "environment": {},
                "timeout_seconds": 30,
            }
            for name, path in outputs
        ],
        "outputs": [
            {"name": name, "staged_path": str(STAGE / name), "path": str(LIVE / name)}
            for name, _ in outputs
        ],
    }


# Both directions carry generated application data. DNS uses a real UDP query
# and response rather than interpreting an open port as resolver acceptance.
ECHO = r"""
import socket, threading, sys
address = sys.argv[1]
def udp(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((address, port))
    while True:
        data, peer = s.recvfrom(65535)
        if port == 53:
            data = data[:2] + b'\x81\x80' + b'\x00\x01\x00\x01\x00\x00\x00\x00' + data[12:] + b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x00\x00\x04\xc0\x00\x02\x63'
        s.sendto(data, peer)
for port in (32000, 53): threading.Thread(target=udp, args=(port,), daemon=True).start()
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind((address, 32000)); s.listen()
while True:
    c, _ = s.accept()
    with c:
        while True:
            data = c.recv(65536)
            if not data: break
            c.sendall(data)
"""
PROBE = r"""
import os, socket, struct, sys, time
address = sys.argv[1]
for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.settimeout(3); s.connect((address, 32000))
        deadline = time.monotonic() + 1
        i = 0
        while i < 128 or time.monotonic() < deadline:
            i += 1
            payload = os.urandom(16384 if kind == socket.SOCK_STREAM else 1000)
            s.sendall(payload); reply = b''
            while len(reply) < len(payload):
                part = s.recv(len(payload) - len(reply))
                if not part: raise SystemExit(2)
                reply += part
            if reply != payload: raise SystemExit(3)
query = os.urandom(2) + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03awg\x07example\x00\x00\x01\x00\x01'
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.settimeout(3); s.sendto(query, (address, 53)); data, peer = s.recvfrom(512)
    if peer[0] != address or data[:2] != query[:2] or data[-4:] != b'\xc0\x00\x02\x63': raise SystemExit(4)
"""


class Tunnel:
    def __init__(self, index, server_pair, client_pair, shape):
        self.index = index
        self.names = [f"awglab{index}s", f"awglab{index}c"]
        self.units = [name + ".service" for name in self.names]
        self.processes = []
        self.configs = []
        self.shape = shape
        self.server_pair = server_pair
        self.client_pair = client_pair
        self.initiator = 0

    def start(self):
        i = self.index
        for name in self.names:
            command("ip", "netns", "add", name)
            command("ip", "-n", name, "link", "set", "lo", "up")
        command(
            "ip", "link", "add", f"left{i}", "type", "veth", "peer", "name", f"right{i}"
        )
        for name, interface, last in zip(self.names, (f"left{i}", f"right{i}"), (1, 2)):
            command("ip", "link", "set", interface, "netns", name)
            command(
                "ip",
                "-n",
                name,
                "addr",
                "add",
                f"192.0.2.{last}/24",
                "dev",
                interface,
            )
            command("ip", "-n", name, "link", "set", interface, "up")
        tools = "/opt/candidate/tools/src/wg"
        private = [command(tools, "genkey") for _ in self.names]
        public = [command(tools, "pubkey", data=key) for key in private]
        psk = command(tools, "genpsk")
        for side, name in enumerate(self.names):
            pair = self.server_pair if side == 0 else self.client_pair
            binary = (
                str(LIVE / "amneziawg-go")
                if pair == "live"
                else f"/opt/{pair}/go/amneziawg-go"
            )
            unit = (ROOT / "awg-quick@.service").read_text()
            unit = unit.replace("Type=oneshot", "Type=simple").replace(
                "RemainAfterExit=yes", "RemainAfterExit=no"
            )
            unit = "\n".join(
                line
                for line in unit.splitlines()
                if not line.startswith(
                    ("ExecStart=", "ExecStop=", "ExecReload=", "PartOf=")
                )
            )
            unit = unit.replace(
                "[Service]",
                f"[Service]\nNetworkNamespacePath=/run/netns/{name}\nExecStart={binary} -f {name}",
            )
            Path("/etc/systemd/system", self.units[side]).write_text(unit + "\n")
            config = Path("/lab", name + ".conf")
            jc, jmin, jmax, s1, s2, h1, h2, h3, h4 = self.shape
            config.write_text(
                f"[Interface]\nPrivateKey = {private[side]}\nListenPort = 51900\nJc = {jc}\nJmin = {jmin}\nJmax = {jmax}\nS1 = {s1}\nS2 = {s2}\nH1 = {h1}\nH2 = {h2}\nH3 = {h3}\nH4 = {h4}\n[Peer]\nPublicKey = {public[1 - side]}\nPresharedKey = {psk}\nAllowedIPs = 10.{i}.0.{2 - side}/32\nEndpoint = 192.0.2.{2 - side}:51900\n"
            )
            config.chmod(0o600)
            self.configs.append(config)
        command("systemctl", "daemon-reload")
        for side in range(2):
            self.restart(side)
            echo = subprocess.Popen(
                [
                    "ip",
                    "netns",
                    "exec",
                    self.names[side],
                    sys.executable,
                    "-c",
                    ECHO,
                    f"10.{i}.0.{side + 1}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.processes.append(echo)
        time.sleep(0.15)

    def restart(self, side=0):
        name = self.names[side]
        command("systemctl", "restart", self.units[side])
        deadline = time.monotonic() + 10
        while subprocess.run(
            ["ip", "-n", name, "link", "show", name],
            check=False,
            capture_output=True,
            timeout=5,
        ).returncode:
            if time.monotonic() >= deadline:
                raise AssertionError("real AWG daemon failed to establish TUN")
            time.sleep(0.05)
        self.configure(side)
        command(
            "ip",
            "-n",
            name,
            "addr",
            "replace",
            f"10.{self.index}.0.{side + 1}/24",
            "dev",
            name,
        )
        command("ip", "-n", name, "link", "set", name, "up")
        self.initiator = side

    def tools(self, side):
        pair = self.server_pair if side == 0 else self.client_pair
        return str(LIVE / "awg") if pair == "live" else f"/opt/{pair}/tools/src/wg"

    def configure(self, side):
        command(
            "ip",
            "netns",
            "exec",
            self.names[side],
            self.tools(side),
            "setconf",
            self.names[side],
            str(self.configs[side]),
        )
        observed = command(
            "ip",
            "netns",
            "exec",
            self.names[side],
            self.tools(side),
            "showconf",
            self.names[side],
        )
        for line in observed.splitlines():
            key, separator, value = line.partition("=")
            if (
                separator
                and key.strip().lower().replace("_", "")
                in {
                    "s3",
                    "s4",
                    "randomtrailers",
                    "disablecookies",
                }
                and value.strip().lower() not in {"0", "false", "off"}
            ):
                raise AssertionError("excluded AWG packet mode became active")

    def pid(self, side=0):
        return int(
            command("systemctl", "show", "-p", "MainPID", "--value", self.units[side])
        )

    def probe(self):
        # The freshly reconnected peer initiates the new handshake; the retained
        # peer may still hold the previous transport session until it receives it.
        for side in (self.initiator, 1 - self.initiator):
            name = self.names[side]
            command(
                "ip",
                "netns",
                "exec",
                name,
                sys.executable,
                "-c",
                PROBE,
                f"10.{self.index}.0.{2 - side}",
                timeout=20,
            )
        for side, name in enumerate(self.names):
            observed = command(
                "ip",
                "netns",
                "exec",
                name,
                self.tools(side),
                "show",
                name,
                "latest-handshakes",
            )
            assert int(observed.split()[-1]) > 0, "authenticated handshake missing"

    def close(self):
        for unit in self.units:
            subprocess.run(
                ["systemctl", "stop", unit],
                check=False,
                capture_output=True,
                timeout=15,
            )
            Path("/etc/systemd/system", unit).unlink(missing_ok=True)
        for process in self.processes:
            process.terminate()
            process.wait(timeout=5)
        for name in reversed(self.names):
            subprocess.run(
                ["ip", "netns", "delete", name],
                check=False,
                capture_output=True,
                timeout=10,
            )
        for path in self.configs:
            path.unlink(missing_ok=True)


def capture_headers(tunnel):
    capture = Path("/lab/capture.pcap")
    process = subprocess.Popen(
        [
            "ip",
            "netns",
            "exec",
            tunnel.names[0],
            "tcpdump",
            "-U",
            "-c",
            "512",
            "-s",
            "2048",
            "-i",
            f"left{tunnel.index}",
            "-w",
            str(capture),
            "udp",
            "port",
            "51900",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.3)
        # Restart both peers so capture contains a fresh authenticated handshake.
        tunnel.restart(0)
        tunnel.restart(1)
        tunnel.probe()
        time.sleep(0.2)
    finally:
        process.terminate()
        process.wait(timeout=5)
    data = capture.read_bytes()
    assert data[:4] == b"\xd4\xc3\xb2\xa1", "unsupported capture encoding"
    offset = 24
    packets = []
    while offset < len(data):
        size = struct.unpack_from("<IIII", data, offset)[2]
        offset += 16
        frame = data[offset : offset + size]
        offset += size
        if len(frame) < 42 or frame[12:14] != b"\x08\x00":
            continue
        header = (frame[14] & 15) * 4
        packets.append(frame[14 + header + 8 :])
    _, _, _, s1, s2, h1, h2, _, h4 = tunnel.shape
    for size, padding, header in ((148 + s1, s1, h1), (92 + s2, s2, h2)):
        assert any(
            len(packet) == size
            and packet[padding : padding + 4] == struct.pack("<I", header)
            for packet in packets
        ), "handshake packet bytes/offset changed"
    assert any(packet[:4] == struct.pack("<I", h4) for packet in packets), (
        "transport header changed"
    )
    capture.unlink()


class Acceptance(unittest.TestCase):
    def test_exact_pairs_wire_and_warm_adoption(self):
        self.assertEqual(sys.platform, "linux")
        self.assertEqual(os.geteuid(), 0)
        self.assertTrue(Path("/dev/net/tun").is_char_device())
        self.assertEqual(command("ip", "route", "show", "default"), "")
        print(f"local Linux architecture: {platform.machine()}", flush=True)
        for directory in (RECEIPTS, STAGE.parent, LIVE):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        baseline, candidate = descriptor("baseline"), descriptor("candidate")
        self.assertTrue(publisher.converge(RECEIPTS, baseline)["changed"])
        shapes = [
            tuple(
                shape[key]
                for key in ("jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4")
            )
            for shape in PINS["wire_shapes"]
        ]
        index = 10
        for server, client in (
            ("baseline", "candidate"),
            ("candidate", "baseline"),
            ("candidate", "candidate"),
        ):
            for shape in shapes:
                print(f"matrix: {server}/{client} shape={shape}", flush=True)
                tunnel = Tunnel(index, server, client, shape)
                index += 1
                try:
                    tunnel.start()
                    capture_headers(tunnel)
                    for _ in range(3):
                        tunnel.restart(1)
                        tunnel.probe()
                finally:
                    tunnel.close()
        owned = [Tunnel(index + i, "live", "baseline", shapes[i]) for i in range(2)]
        foreign = Tunnel(index + 2, "baseline", "baseline", shapes[0])
        try:
            for tunnel in [*owned, foreign]:
                tunnel.start()
                tunnel.probe()
            foreign_pid = foreign.pid()
            before = [tunnel.pid() for tunnel in owned]
            failed = copy.deepcopy(candidate)
            Path("/lab/rejected.go").write_text(
                "package main\nfunc main() { invalid source }\n"
            )
            failed["steps"].insert(
                0,
                {
                    "argv": [
                        "/usr/local/go/bin/go",
                        "build",
                        "-o",
                        "/lab/rejected",
                        "/lab/rejected.go",
                    ],
                    "chdir": "/lab",
                    "environment": {
                        "GOTOOLCHAIN": "local",
                        "GOMAXPROCS": "2",
                        "GOFLAGS": "-p=2",
                    },
                    "timeout_seconds": 60,
                },
            )
            old_receipt = (RECEIPTS / "awg-candidate.json").read_bytes()
            with self.assertRaises(publisher.UnsafeState):
                publisher.converge(RECEIPTS, failed)
            self.assertEqual(
                old_receipt, (RECEIPTS / "awg-candidate.json").read_bytes()
            )
            for tunnel in [*owned, foreign]:
                tunnel.probe()
            self.assertTrue(publisher.converge(RECEIPTS, candidate)["changed"])
            for tunnel in owned:
                tunnel.restart()
                tunnel.probe()
                self.assertEqual(
                    digest(f"/proc/{tunnel.pid()}/exe"), digest(LIVE / "amneziawg-go")
                )
            self.assertNotEqual(before, [tunnel.pid() for tunnel in owned])
            # A rejected authenticated readiness probe restores the complete pair
            # through the same publisher, then restarts both owned instances.
            config = owned[0].configs[0]
            original = config.read_text()
            config.write_text(original.replace("H1 = 11", "H1 = 99"))
            owned[0].restart()
            with self.assertRaises(AssertionError):
                owned[0].probe()
            config.write_text(original)
            self.assertTrue(publisher.converge(RECEIPTS, baseline)["changed"])
            for tunnel in owned:
                tunnel.restart()
                tunnel.probe()
            self.assertEqual(
                digest(LIVE / "amneziawg-go"), digest("/opt/baseline/go/amneziawg-go")
            )
            self.assertTrue(publisher.converge(RECEIPTS, candidate)["changed"])
            for tunnel in owned:
                tunnel.restart()
                tunnel.probe()
                unit = Path("/etc/systemd/system", tunnel.units[0])
                unit.write_text(
                    unit.read_text().replace(
                        "[Service]", "[Service]\nProtectHostname=yes"
                    )
                )
            command("systemctl", "daemon-reload")
            for tunnel in owned:
                tunnel.restart()
                tunnel.probe()
                self.assertEqual(
                    command(
                        "systemctl",
                        "show",
                        "-p",
                        "ProtectHostname",
                        "--value",
                        tunnel.units[0],
                    ),
                    "yes",
                )
                self.assertNotEqual(
                    os.readlink(f"/proc/{tunnel.pid()}/ns/uts"),
                    os.readlink("/proc/1/ns/uts"),
                )
            pids = [tunnel.pid() for tunnel in owned]
            self.assertFalse(publisher.converge(RECEIPTS, candidate)["changed"])
            self.assertEqual(pids, [tunnel.pid() for tunnel in owned])
            self.assertEqual(foreign_pid, foreign.pid())
            foreign.probe()
        finally:
            for tunnel in [*owned, foreign]:
                tunnel.close()
        print(
            "PASS: exact pairs, six wire matrices, reconnects, TCP/UDP/DNS both directions, warm pair/unit adoption, build/readiness compensation, unchanged repeat and foreign tunnel"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
