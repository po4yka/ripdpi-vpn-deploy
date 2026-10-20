"""Execute sender errno classification; real packet admission is a Linux gate."""

import ast
import errno
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "tests/native/transport_acceptance/test_dhcpv6.py"


def sender_source():
    tree = ast.parse(NATIVE.read_text())
    return ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SENDER"
                for target in node.targets)))


@pytest.mark.parametrize("error_number", [0, errno.EPERM, errno.EACCES,
                                          errno.ENETUNREACH, errno.EADDRNOTAVAIL,
                                          errno.EHOSTUNREACH])
@pytest.mark.parametrize("expected_deny", [False, True])
def test_only_explicit_expected_output_drop_accepts_eperm(error_number, expected_deny):
    # Inject a send syscall result, then execute the actual retained sender.
    # This portable test never opens a network socket.
    syscall = f"""
import sys,types
socket=types.ModuleType('socket')
for name in ('AF_INET6','SOCK_DGRAM','SOL_SOCKET','SO_BINDTODEVICE',
             'IPPROTO_IPV6','IPV6_MULTICAST_IF'):
 setattr(socket,name,1)
socket.if_nametoindex=lambda interface:1
class Socket:
 def __init__(self,*args): pass
 def setsockopt(self,*args): pass
 def bind(self,*args): pass
 def sendto(self,data,target):
  if {error_number}:
   raise OSError({error_number},'synthetic-send-refusal')
  return len(data)
socket.socket=Socket
sys.modules['socket']=socket
"""
    result = subprocess.run(
        [sys.executable, "-c", syscall + sender_source(),
         "up0", "fe80::10", "546", "fe80::20", "547",
         "yes" if expected_deny else "no"],
        capture_output=True, text=True, timeout=10,
    )
    accepted = not error_number or (error_number == errno.EPERM and expected_deny)
    assert (result.returncode == 0) is accepted
    assert (result.stdout.strip() == "expected-output-deny") is (
        error_number == errno.EPERM and expected_deny
    )
    if not accepted:
        assert "synthetic-send-refusal" in result.stderr
