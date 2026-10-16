#!/usr/bin/env python3
"""Read-only admission of the exact public dual-stack AWG uplink."""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys


def admit(routes, interface, version):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}', interface):
        raise ValueError('invalid-awg-uplink')
    if not isinstance(routes, list) or len(routes) != 1:
        raise ValueError('awg-uplink-route-unavailable')
    route = routes[0]
    if route.get('dev') != interface or route.get('type', 'unicast') != 'unicast':
        raise ValueError('awg-uplink-route-mismatch')
    source = ipaddress.ip_address(route['prefsrc'])
    if (source.version != version or source.is_unspecified or source.is_multicast
            or source.is_loopback or source.is_link_local or (version == 6 and not source.is_global)):
        raise ValueError('awg-uplink-public-source-unavailable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', required=True)
    args = parser.parse_args()
    try:
        for version, target in ((4, '1.1.1.1'), (6, '2606:4700:4700::1111')):
            result = subprocess.run(['ip', '-j', f'-{version}', 'route', 'get', target],
                                    check=True, capture_output=True, text=True, timeout=5)
            admit(json.loads(result.stdout), args.interface, version)
            if version == 6:
                defaults = subprocess.run(['ip', '-j', '-6', 'route', 'show', 'default', 'dev', args.interface],
                                          check=True, capture_output=True, text=True, timeout=5)
                routes = json.loads(defaults.stdout)
                if not routes:
                    raise ValueError('awg-ipv6-default-route-unavailable')
                if any(route.get('protocol') == 'ra' for route in routes):
                    value = Path('/proc/sys/net/ipv6/conf', args.interface, 'accept_ra').read_text().strip()
                    if value != '2':
                        raise ValueError('awg-ipv6-router-advertisement-ownership')
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print('awg-dualstack-uplink-unavailable', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
