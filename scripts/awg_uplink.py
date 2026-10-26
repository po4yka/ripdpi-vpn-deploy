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


def networkd_ra_owner(state, interface, index, route, accept_ra):
    """Match the selected kernel route to networkd's typed NDisc authority."""
    if (type(index) is not int or index <= 0
            or not isinstance(state, dict) or state.get('Name') != interface
            or type(state.get('Index')) is not int or state['Index'] != index
            or not isinstance(state.get('Addresses'), list)
            or not isinstance(state.get('Routes'), list)
            or any(not isinstance(row, dict) or not isinstance(row.get('ConfigSource'), str)
                   for row in state['Addresses'] + state['Routes'])):
        raise ValueError('awg-networkd-state-unavailable')
    if not any(row['ConfigSource'] == 'NDisc' for row in state['Addresses'] + state['Routes']):
        return False
    if (accept_ra != '0' or state.get('AdministrativeState') != 'configured'
            or any(state.get(key) != 'routable' for key in
                   ('OperationalState', 'AddressState', 'IPv6AddressState'))):
        raise ValueError('awg-networkd-ra-ownership')

    def address_matches(value, address):
        if (not isinstance(value, list) or len(value) != 16
                or any(type(byte) is not int or not 0 <= byte <= 255 for byte in value)):
            raise ValueError('awg-networkd-address-invalid')
        return bytes(value) == ipaddress.IPv6Address(address).packed

    configured = {'configured', 'configuring,configured'}
    addresses = [row for row in state['Addresses']
                 if row['ConfigSource'] == 'NDisc'
                 and type(row.get('Family')) is int and row['Family'] == 10
                 and type(row.get('Scope')) is int and row['Scope'] == 0
                 and row.get('ConfigState') in configured
                 and type(row.get('PrefixLength')) is int and 0 < row['PrefixLength'] <= 128
                 and address_matches(row.get('Address'), route['prefsrc'])]
    defaults = [row for row in state['Routes']
                if row['ConfigSource'] == 'NDisc'
                and type(row.get('Family')) is int and row['Family'] == 10
                and type(row.get('DestinationPrefixLength')) is int
                and row['DestinationPrefixLength'] == 0
                and type(row.get('Protocol')) is int and row['Protocol'] == 9
                and row.get('ConfigState') in configured
                and type(row.get('LifetimeUSec')) is int and 0 < row['LifetimeUSec'] < 2**64
                and address_matches(row.get('Gateway'), route['gateway'])]
    if len(addresses) != 1 or len(defaults) != 1:
        raise ValueError('awg-networkd-selected-route-unavailable')
    return True


def admit_ra_owner(interface, route, accept_ra):
    active = subprocess.run(['systemctl', 'show', 'systemd-networkd.service',
                             '--property=ActiveState', '--value'], check=True,
                            capture_output=True, text=True, timeout=5).stdout.strip()
    if active == 'active':
        result = subprocess.run(['networkctl', '--json=short', 'status', interface],
                                check=True, capture_output=True, text=True, timeout=5)
        if len(result.stdout) > 1_048_576:
            raise ValueError('awg-networkd-state-oversized')
        index = int(Path('/sys/class/net', interface, 'ifindex').read_text().strip())
        if networkd_ra_owner(json.loads(result.stdout), interface, index, route, accept_ra):
            return
    elif active != 'inactive':
        raise ValueError('awg-networkd-owner-unstable')
    if accept_ra != '2':
        raise ValueError('awg-ipv6-router-advertisement-ownership')


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
                    admit_ra_owner(args.interface, json.loads(result.stdout)[0], value)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        print('awg-dualstack-uplink-unavailable', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
