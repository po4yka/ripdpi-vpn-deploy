"""Actual pinned ECH runtimes in an owned network namespace; no fleet inputs."""

from __future__ import annotations
from contextlib import contextmanager
import ctypes
import hashlib
import io
import os
from pathlib import Path
import platform
import socket
import subprocess
import tarfile
import time
import urllib.request

from hysteria_ech import PINS


def command(argv, timeout=30):
    result = subprocess.run(argv, capture_output=True, timeout=timeout)
    if result.returncode:
        raise AssertionError("native-ech-command-refused:" + Path(argv[0]).name)
    return result.stdout


def binaries(cache):
    architecture = {"aarch64": "arm64", "x86_64": "amd64"}[platform.machine()]
    selected = {}
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, repo, version, filename in (
        (
            "hysteria",
            "HyNetworks/hysteria",
            "app/v2.13.0",
            "hysteria-linux-" + architecture,
        ),
        (
            "sing_box",
            "SagerNet/sing-box",
            "v1.14.3",
            "sing-box-1.14.3-linux-" + architecture + ".tar.gz",
        ),
    ):
        archive = cache / filename
        if not archive.exists():
            with urllib.request.urlopen(
                "https://github.com/"
                + repo
                + "/releases/download/"
                + version
                + "/"
                + filename,
                timeout=30,
            ) as response:
                data = response.read(120_000_001)
            assert len(data) <= 120_000_000, "runtime-size-bound"
        else:
            data = archive.read_bytes()
        assert (
            hashlib.sha256(data).hexdigest()
            == PINS[name]["sha256"]["linux-" + architecture]
        ), "runtime-checksum-refused"
        if not archive.exists():
            archive.write_bytes(data)
        executable = cache / (name + "-verified")
        if name == "sing_box":
            with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
                data = bundle.extractfile(
                    "sing-box-1.14.3-linux-" + architecture + "/sing-box"
                ).read()
        executable.write_bytes(data)
        executable.chmod(0o755)
        expected = "v2.13.0" if name == "hysteria" else "1.14.3"
        assert expected.encode() in command([str(executable), "version"])
        selected[name] = executable
    return selected


@contextmanager
def socket_ceilings(receive, send):
    # Linux 6.8 exposes these host-wide bounds only in the initial netns.
    assert (os.uname().sysname == "Linux" and os.geteuid() == 0
            and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"), "isolated-linux-root-required"
    keys = ("net.core.rmem_max", "net.core.wmem_max")
    original = command(["sysctl", "-n", *keys]).decode().split()
    assert len(original) == 2 and all(value.isdigit() for value in original)
    try:
        command(["sysctl", "-w", *[key + "=" + str(value)
                                 for key, value in zip(keys, (receive, send))]])
        observed = [int(value) for value in command(["sysctl", "-n", *keys]).split()]
        assert observed == [receive, send], "socket-ceiling-application-unconfirmed"
        yield observed
    finally:
        command(["sysctl", "-w", *[key + "=" + value for key, value in zip(keys, original)]])
        assert command(["sysctl", "-n", *keys]).decode().split() == original, "socket-ceiling-restoration-unconfirmed"


@contextmanager
def namespace():
    assert (
        os.uname().sysname == "Linux"
        and os.geteuid() == 0
        and os.environ.get("TRANSPORT_NATIVE_ISOLATED") == "1"
    ), "isolated-linux-root-required"
    original = os.open("/proc/self/ns/net", os.O_RDONLY)
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        assert libc.unshare(0x40000000) == 0, "owned-network-namespace-required"
        command(["ip", "link", "set", "lo", "up"])
        # Every mode sees the same bounded technical path, never a live interface.
        command(
            [
                "tc",
                "qdisc",
                "add",
                "dev",
                "lo",
                "root",
                "netem",
                "delay",
                "5ms",
                "loss",
                "0.1%",
            ]
        )
        yield
    finally:
        restored = libc.setns(original, 0x40000000)
        os.close(original)
        assert restored == 0, "native-network-restoration-unconfirmed"


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def private(path, value):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as target:
        target.write(value)
    return path


@contextmanager
def process(argv, directory, label):
    path = private(directory / (label + ".log"), "")
    with path.open("wb") as output:
        child = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT)
        try:
            yield child, path
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


def tcp_transfer(port, expected, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1) as sock:
                sock.settimeout(2)
                sock.sendall(b"GET / HTTP/1.0\r\nHost: payload.example\r\n\r\n")
                result = b""
                while True:
                    data = sock.recv(65536)
                    if not data:
                        break
                    result += data
                if result.split(b"\r\n\r\n", 1)[-1] == expected:
                    return
        except OSError:
            pass
        time.sleep(0.05)
    raise AssertionError("authenticated-tcp-delivery-refused")


def udp_transfer(port, packet):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.sendto(packet, ("127.0.0.1", port))
        return sock.recv(65535)
