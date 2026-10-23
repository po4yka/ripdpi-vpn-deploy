#!/usr/bin/env python3
"""Resolve empty device authorities into the canonical retired transport state."""
from __future__ import annotations

import copy
import json
import sys


def project(document, context):
    result = copy.deepcopy(context)
    vpn = result.setdefault('vpn', {})
    if not isinstance(vpn, dict):
        raise TypeError('invalid-device-runtime-context')
    for section, flags in (('xray', ('enable_xray_reality', 'enable_nginx_xhttp')),
                           ('hysteria', ('enable_hysteria',))):
        block = document.get(section)
        if isinstance(block, dict) and block.get('clients') == []:
            vpn.update(dict.fromkeys(flags, False))
    cohorts = document.get('xray', {}).get('cohorts', [])
    if not isinstance(cohorts, list) or any(not isinstance(row, dict) or not isinstance(row.get('clients'), list) for row in cohorts):
        raise ValueError('invalid-device-runtime-cohorts')
    names = [row.get('name') for row in cohorts]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValueError('invalid-device-runtime-cohorts')
    active_cohorts = [row['name'] for row in cohorts if row['clients']]
    if cohorts and not active_cohorts:
        vpn['enable_xray_reality'] = False
    variants = document.get('snell_secrets', {}).get('variants')
    active_variants = None
    if variants is not None:
        if (not isinstance(variants, list) or any(not isinstance(row, dict) or not isinstance(row.get('users'), list) for row in variants)
                or len({row['id'] for row in variants}) != len(variants)):
            raise ValueError('invalid-device-runtime-variants')
        configured = result.get('snell', {}).get('variants', [])
        active_variants = [row['id'] for row in variants if row['users']]
        if configured and not {row['id'] for row in configured} <= {row['id'] for row in variants}:
            raise ValueError('missing-device-runtime-variant')
        if configured:
            result['snell']['variants'] = [row for row in configured if row['id'] in active_variants]
            if not result['snell']['variants']:
                vpn['enable_snell'] = False
    return result, active_cohorts, active_variants


def main():
    try:
        raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError
        request = json.loads(raw)
        context, cohorts, variants = project(request['secrets'], request['context'])
        print(json.dumps({'vpn': context.get('vpn', {}), 'xray_cohorts': cohorts, 'snell_variants': variants}))
        return 0
    except (ValueError, KeyError, TypeError, AttributeError):
        print('device-runtime-context-refused', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
