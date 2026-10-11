#!/usr/bin/env python3
"""Validate a candidate with the same assets as the managed Xray service."""

from __future__ import annotations

import argparse
import os
import json
import stat
import shlex
import subprocess
import sys


def managed_authority(explicit: str | None, key: str) -> str:
    if explicit is None:
        result = subprocess.run(
            ["systemctl", "show", "xray.service", "--property=Environment", "--value"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        values = [
            entry.removeprefix(key + "=")
            for entry in shlex.split(result.stdout)
            if entry.startswith(key + "=")
        ]
        if len(values) != 1:
            raise ValueError("missing or ambiguous runtime authority")
        explicit = values[0]
    if not os.path.isabs(explicit) or any(ord(char) < 32 for char in explicit):
        raise ValueError("invalid runtime authority")
    return explicit


def admitted_frontend(config):
    """A syntactically valid rollback cannot restore unguarded egress."""
    outbounds = config.get('outbounds')
    if not isinstance(outbounds, list) or not 2 <= len(outbounds) <= 4:
        raise ValueError('unguarded-outbound-shape')
    tags = set()
    for outbound in outbounds:
        if not isinstance(outbound, dict) or set(outbound) - {'tag', 'protocol', 'settings', 'streamSettings', 'targetStrategy'}:
            raise ValueError('unguarded-outbound-shape')
        tag = outbound.get('tag')
        if tag in tags or tag not in {'direct', 'block', 'warp-out', 'cascade-classifier'}:
            raise ValueError('unguarded-outbound-tag')
        tags.add(tag)
        if tag == 'block':
            if outbound.get('protocol') != 'blackhole':
                raise ValueError('unguarded-blackhole')
            continue
        if outbound.get('protocol') != 'socks':
            raise ValueError('unguarded-recipient-egress')
        servers = outbound.get('settings', {}).get('servers')
        if not isinstance(servers, list) or len(servers) != 1:
            raise ValueError('unguarded-gateway-shape')
        server = servers[0]
        if not isinstance(server, dict) or set(server) != {'address', 'port', 'users'} or server['address'] != '127.0.0.1':
            raise ValueError('unguarded-gateway-authority')
        port, username = {'direct': (12080, 'normalizer-direct-xray'), 'warp-out': (12082, 'normalizer-warp-xray'), 'cascade-classifier': (10808, 'cascade-xray')}[tag]
        if server['port'] != port or type(server['port']) is not int or not isinstance(server['users'], list) or len(server['users']) != 1:
            raise ValueError('unguarded-gateway-authority')
        account = server['users'][0]
        if not isinstance(account, dict) or set(account) != {'user', 'pass'} or account['user'] != username:
            raise ValueError('unguarded-gateway-identity')
        password = account['pass']
        if not isinstance(password, str) or not 32 <= len(password) <= 255 or any(not 32 <= ord(char) <= 126 for char in password):
            raise ValueError('unguarded-gateway-credential')
        if tag != 'cascade-classifier' and (set(outbound) != {'tag', 'protocol', 'settings'} or set(outbound['settings']) != {'servers'}):
            raise ValueError('unguarded-gateway-override')
    if not {'direct', 'block'} <= tags or {'warp-out', 'cascade-classifier'} <= tags:
        raise ValueError('unguarded-outbound-topology')
    routing = config.get('routing', {})
    if routing.get('domainStrategy') != 'AsIs' or not isinstance(routing.get('rules'), list):
        raise ValueError('unguarded-routing-authority')
    if any(rule.get('outboundTag') not in tags for rule in routing['rules']):
        raise ValueError('unguarded-routing-authority')


def read_candidate(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > 1048576:
            raise ValueError('invalid-config-authority')
        raw = os.read(descriptor, 1048577)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('ambiguous-config')
                result[key] = value
            return result
        config = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(config, dict):
            raise ValueError('invalid-config-shape')
        admitted_frontend(config)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary")
    parser.add_argument("--asset-dir")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dump-config", action="store_true")
    args = parser.parse_args()
    try:
        args.binary = managed_authority(args.binary, "XRAY_RUNTIME_BINARY")
        if not os.path.isabs(args.binary) or not os.path.isabs(args.config):
            raise ValueError("absolute paths required")
        read_candidate(args.config)
        environment = {**os.environ, "XRAY_LOCATION_ASSET": managed_authority(args.asset_dir, "XRAY_LOCATION_ASSET")}
        command = [args.binary, "run", "-test"]
        if args.dump_config:
            command.append("-dump-config")
        command.extend(["-config", args.config])
        os.execve(args.binary, command, environment)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        print("Xray configuration or managed runtime authority was refused.", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
