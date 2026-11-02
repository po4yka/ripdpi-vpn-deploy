#!/usr/bin/env python3
"""Wait for the exact private listener address before nginx starts."""
import errno
import ipaddress
from pathlib import Path
import re
import socket
import sys
import time


CONFIG = Path('/etc/nginx/conf.d/observability-kuma.conf')


def listener_address(path):
    listeners = re.findall(r'^\s*listen\s+(?:\[([^]\s]+)\]|([^:\s]+)):[0-9]+\s+ssl;\s*$',
                           Path(path).read_text(), re.MULTILINE)
    if len(listeners) != 1:
        raise ValueError('one-private-listener-required')
    address = ipaddress.ip_address(listeners[0][0] or listeners[0][1])
    if address.is_unspecified:
        raise ValueError('exact-private-address-required')
    return str(address)


def wait_address(address):
    address = ipaddress.ip_address(address)
    family = socket.AF_INET if address.version == 4 else socket.AF_INET6
    deadline = time.monotonic() + 60
    while True:
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.bind((str(address), 0))
            return
        except OSError as error:
            if error.errno != errno.EADDRNOTAVAIL:
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError('private-address-unavailable') from None
            time.sleep(0.25)


def main():
    try:
        wait_address(listener_address(CONFIG))
    except (ValueError, OSError):
        print('private ingress address unavailable', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
