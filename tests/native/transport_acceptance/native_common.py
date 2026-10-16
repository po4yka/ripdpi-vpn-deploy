"""Reuse the canonical native adapters without a second configuration model."""

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/unit"))
spec = importlib.util.spec_from_file_location(
    "four_transport_stack",
    ROOT / "tests/integration/transport_destination_boundary/fixture.py",
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def wait_client(namespace, port):
    """Bound native listener admission before issuing the one-shot traffic probe."""
    source = (
        "import socket,sys,time\n"
        "deadline=time.monotonic()+10\n"
        "while True:\n"
        " try:\n"
        "  with socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=.5) as s:\n"
        "   s.sendall(b'\\x05\\x01\\x00')\n"
        "   if s.recv(2)!=b'\\x05\\x00': raise RuntimeError('SOCKS-admission-refused')\n"
        "  break\n"
        " except OSError:\n"
        "  if time.monotonic()>=deadline: raise RuntimeError('native-listener-unavailable')\n"
        "  time.sleep(.05)\n"
    )
    fixture.command(
        ["ip", "netns", "exec", namespace, sys.executable, "-c", source, str(port)],
        timeout=15,
    )
