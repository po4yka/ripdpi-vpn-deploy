#!/usr/bin/env python3
"""Read actual host address and management listener authority without mutation."""
import json
import re
import shutil
import subprocess
import sys
from transport_destination_policy import normalize_address


def capture(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise ValueError('host-context-unavailable')
    return result.stdout


def discover(declared):
    if not isinstance(declared, list) or len(declared) > 64:
        raise ValueError('invalid-declared-addresses')
    owned = {str(normalize_address(value)) for value in declared if value is not None and value != ''}
    addresses = json.loads(capture(['ip', '-j', 'address', 'show']))
    for interface in addresses:
        for address in interface.get('addr_info', []):
            if address.get('family') in ('inet', 'inet6'):
                owned.add(str(normalize_address(address['local'])))
    tcp, udp = set(), set()
    if shutil.which('sshd'):
        config = capture(['sshd', '-T'])
        tcp.update(int(match.group(1)) for line in config.splitlines() if (match := re.fullmatch(r'port ([0-9]+)', line)))
        if not tcp:
            raise ValueError('ssh-authority-unavailable')
    # Recovery and existing control listeners are identified by actual owning process, not guessed ports.
    listeners = capture(['ss', '-H', '-l', '-n', '-p', '-t', '-u'])
    for line in listeners.splitlines():
        fields = line.split()
        if len(fields) < 6:
            raise ValueError('listener-authority-unavailable')
        if re.search(r'\("(?:sshd|sshd-session|vpnd)",', line):
            port = int(fields[4].rsplit(':', 1)[1])
            (tcp if fields[0] == 'tcp' else udp).add(port)
    return {'owned_addresses': sorted(owned), 'management_tcp_ports': sorted(tcp), 'management_udp_ports': sorted(udp)}


if __name__ == '__main__':
    try:
        data = sys.stdin.buffer.read(8193)
        if len(data) > 8192:
            raise ValueError('oversized-context')
        print(json.dumps(discover(json.loads(data)), separators=(',', ':')))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError):
        print('transport-egress-host-context-refused', file=sys.stderr)
        raise SystemExit(1)
