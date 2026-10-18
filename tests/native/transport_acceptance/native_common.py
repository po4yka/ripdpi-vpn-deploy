"""Reuse the canonical native adapters without a second configuration model."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/unit"))
spec = importlib.util.spec_from_file_location(
    "four_transport_stack",
    ROOT / "tests/integration/transport_destination_boundary/fixture.py",
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


SOCKS_READINESS_PROBE = r"""
import socket,sys,time
deadline=time.monotonic()+10
stage='connect'
def refuse(reason):
 print(reason,flush=True)
 raise SystemExit(1)
def budget():
 remaining=deadline-time.monotonic()
 if remaining<=0: refuse(stage+'-deadline')
 return min(.5,remaining)
while time.monotonic()<deadline:
 try:
  stage='connect'
  with socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=budget()) as stream:
   stage='reply'
   stream.settimeout(budget());stream.sendall(b'\x05\x01\x00')
   reply=b''
   while len(reply)<2:
    stream.settimeout(budget())
    part=stream.recv(2-len(reply))
    if not part: refuse('eof')
    reply+=part
    if reply[:1]!=b'\x05': refuse('wrong-version')
   if reply[1:]!=b'\x00': refuse('wrong-method')
  print('ready',flush=True)
  raise SystemExit(0)
 except OSError:
  time.sleep(min(.05,max(0,deadline-time.monotonic())))
refuse(stage+'-deadline')
"""
READINESS_REASONS = frozenset({
    "connect-deadline", "reply-deadline", "eof", "wrong-version", "wrong-method",
    "process-timeout", "probe-error",
})
UNIT_STATES = frozenset({"active", "activating", "inactive", "deactivating", "failed"})


def unit_state(unit):
    if unit is not None:
        try:
            result = subprocess.run(
                ["systemctl", "show", "--property=ActiveState", "--value", "--", unit],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=2, check=False,
            )
            value = result.stdout.strip()
            if result.returncode == 0 and value in UNIT_STATES:
                return value
        except (OSError, subprocess.TimeoutExpired):
            # Optional state inspection retains the closed unknown category.
            pass
    return "unknown"


def wait_client(namespace, port, *, unit=None, record_property=None,
                family=None, phase=None, cycle=None):
    """Require a complete SOCKS reply within the original ten-second deadline."""
    try:
        result = subprocess.run(
            ["ip", "netns", "exec", namespace, sys.executable, "-c", SOCKS_READINESS_PROBE, str(port)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode == 0 and result.stdout == "ready\n":
            return
        value = result.stdout.strip()
        reason = value if result.returncode != 0 and value in READINESS_REASONS else "probe-error"
    except subprocess.TimeoutExpired:
        reason = "process-timeout"
    except OSError:
        reason = "probe-error"
    if (record_property is not None and type(family) is int and family in {4, 6}
            and type(phase) is str and phase in {"hopping", "retirement"}
            and ((phase == "hopping" and cycle is None)
                 or (phase == "retirement" and type(cycle) is int and cycle in {0, 1}))):
        record_property("native-socks-readiness", json.dumps({
            "family": "ipv" + str(family), "phase": phase, "cycle": cycle,
            "reason": reason, "unit_state": unit_state(unit),
        }, separators=(",", ":")))
    raise RuntimeError("native-SOCKS-readiness-" + reason)
