#!/usr/bin/env python3
"""Build the fixed private adapter topology from admitted role context."""
from __future__ import annotations

import argparse
import json
import sys
from transport_egress_normalizer import validate_config
from transport_egress_kernel import validate as validate_policy

MAX_INPUT = 131072


def build(context, input_only=False):
    vpn, secrets = context['vpn'], context['secrets']
    xray = bool(vpn.get('enable_xray_reality', True) or vpn.get('enable_nginx_xhttp', True))
    hysteria = bool(vpn.get('enable_hysteria', True))
    warp = bool(vpn.get('enable_warp_outbound', False) and xray)
    if not xray and not hysteria:
        raise ValueError('no-enabled-frontend')
    backends = {'direct': {'address': '127.0.0.1', 'port': 12090, 'username': 'gateway-direct', 'password': secrets['direct_gateway_password'], 'udp_source_port_min': 16000, 'udp_source_port_max': 17999}}
    listeners = []
    for enabled, name, user, port, pool, backend in [(xray, 'direct_xray', 'xray', 12080, 13000, 'direct'), (hysteria, 'direct_hysteria', 'hysteria', 12081, 14000, 'direct'), (warp, 'warp_xray', 'xray', 12082, 15000, 'warp')]:
        if enabled:
            listener = {'name': name, 'address': '127.0.0.1', 'port': port, 'username': 'normalizer-'+name.replace('_', '-'), 'password': secrets[name+'_password'], 'backend': backend, 'udp_port_min': pool, 'udp_port_max': pool+999}
            if not input_only:
                listener['frontend_uid'] = context['frontend_uids'][user]
            listeners.append(listener)
    if warp:
        backends['warp'] = {'address': '10.250.254.2', 'port': 12091, 'username': 'gateway-warp', 'password': secrets['warp_gateway_password'], 'udp_source_port_min': 18000, 'udp_source_port_max': 18999}
    config = {'schema_version': 1, 'backends': backends, 'listeners': listeners,
              'resolver': {'nameservers': ['1.1.1.1', '8.8.8.8'], 'timeout_seconds': 1, 'attempts': 1, 'lookup_timeout_seconds': 5, 'workers': 4},
              'policy': {'owned_addresses': sorted(set(context['owned_addresses'])), 'management_tcp_ports': sorted(set(context['management_tcp_ports'])), 'management_udp_ports': sorted(set(context['management_udp_ports']))},
              'limits': {'max_connections': 256, 'max_associations': 128, 'max_pending_packets': 256, 'max_datagram_bytes': 65507, 'handshake_seconds': 5, 'connect_seconds': 5, 'idle_seconds': 300, 'udp_quarantine_seconds': 240, 'max_bindings_per_association': 128}}
    if not input_only:
        config['runtime_uid'] = context['normalizer_uid']
    validate_config(config, input_only=input_only)
    result = {'normalizer': config}
    if not input_only:
        policy = {'schema_version': 1, 'normalizer_uid': context['normalizer_uid'], 'gateway_uid': context['gateway_uid'],
                  'listeners': [{key: value for key, value in item.items() if key not in {'username', 'password'}} for item in listeners],
                  'backends': {name: {key: value for key, value in item.items() if key not in {'username', 'password'}} for name, item in backends.items()},
                  'resolver': {'nameservers': config['resolver']['nameservers']}, 'policy': config['policy']}
        if vpn.get('enable_cascade_ingress', False):
            policy['classifier_uid'] = context['classifier_uid']
        if warp:
            policy['warp_gateway_uid'] = context['warp_gateway_uid']
            policy['warp'] = {'namespace': 'ripdpi-warp', 'host_interface': 'rpd-warp-host', 'namespace_interface': 'rpd-warp-ns', 'host_address': '10.250.254.1', 'namespace_address': '10.250.254.2', 'tunnel_ifindex': context.get('tunnel_ifindex')}
        validate_policy(policy)
        result['policy'] = policy
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-only', action='store_true')
    args = parser.parse_args()
    try:
        data = sys.stdin.buffer.read(MAX_INPUT+1)
        if len(data) > MAX_INPUT:
            raise ValueError('oversized-context')
        result = build(json.loads(data), args.input_only)
        print(json.dumps(result, separators=(',', ':')))
        return 0
    except (KeyError, ValueError, TypeError):
        print('transport-egress-context-refused', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
