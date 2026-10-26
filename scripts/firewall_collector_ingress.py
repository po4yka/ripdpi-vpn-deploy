"""One bounded private collector contract for operator and role admission."""

import ipaddress
import json
import sys


def validate(policy):
    try:
        if not isinstance(policy, dict):
            raise ValueError
        if not policy:
            return
        if (set(policy) != {'address', 'sources'} or not isinstance(policy['sources'], list)
                or not 1 <= len(policy['sources']) <= 10):
            raise ValueError
        network = ipaddress.IPv4Network('100.64.0.0/10')
        for value in [policy['address'], *policy['sources']]:
            if (not isinstance(value, str) or str(ipaddress.IPv4Address(value)) != value
                    or ipaddress.IPv4Address(value) not in network):
                raise ValueError
        if len(set(policy['sources'])) != len(policy['sources']):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ValueError('collector-invalid-tailnet-ingress') from None


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or set(request) != {'policy', 'enabled', 'local_address'}:
            raise ValueError
        validate(request['policy'])
        if request['policy'] and (request['enabled'] is not True
                                  or request['policy']['address'] != request['local_address']):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise SystemExit('collector-invalid-tailnet-ingress') from None
